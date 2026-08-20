#!/usr/bin/env python3
"""queue_lint.py — post_queue.json / *_launch_pack.json の必須キー・整合検査。
F-379系(キー欠落・動画参照ミス)をpush前に機械で止める。
使い方: python3 automation/queue_lint.py [ファイル...]  # 省略時=queue+全launch_pack
検査: 必須キー(threads_text/ig_caption/video/cover/app)・appstore_urlのid形式・
      video/coverのローカル実在(queueのみ)・同一videoを複数エントリが別captionで参照してないか・
      **価格の嘘**(有料アプリなのに「無料」と言っている / F-409 2026-08-07 konan指摘)
"""
import json, re, sys, glob, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REQUIRED = ["app", "video", "ig_caption", "threads_text"]  # cover はcloud_post側で任意(あれば警告のみ)

try:
    YT_POSTED = set(json.load(open(os.path.join(HERE, "state.json"))).get("yt_posted", []))
except Exception:
    YT_POSTED = set()

# 【2026-08-13 konan 明言「無料、有料の件あるけどどちらもわざわざ投稿で言う必要ないからね?
#   無料だから!とか有料だが!とかわざわざいらんから」】
# 以前は「有料アプリを無料と書いていないか」を App Store の実価格と突き合わせていた(F-409)。
# だが値段は動く(審査中の買い切り移行9本など)し、映像は焼き込んだら直せない。
# **投稿では値段の話を一切しない**なら、価格が動いても在庫が嘘にならない。
# 値段はストアの製品ページと課金シートが示す。こちらは存在を知らせるだけでよい。
PRICE_TALK = re.compile(r"無料|有料|タダ|0円|ゼロ円|買い切り|サブスク|課金|"
                        r"\bfree\b|\bpaid\b|\bgratis\b|\bkostenlos\b", re.I)

# 【2026-08-05 konan 明言 → 2026-08-08 再発でゲート化】
# 「自衛官の昇任系が試験系自己啓発チャンネルみたいになってて言語化できない恥ずかしさがある。
#   こんなアプリあるよ!って知ってもらうだけでいい。あくまでアプリ紹介」
# プロンプトに書くだけでは 2026-08-08 のバッチで「締切まで時間がない。」がすり抜けた。
# **煽り構文を機械で落とす。** 事実の告知(「締切は9月10日だ」)は通し、焦らせる言い回しだけを弾く。
# 【2026-08-12 konan 指摘「過去問っていうのは法的にアウトなのかどうか調べてから使え」→調査してNG】
# うちの問題は全部こちらで作った類題で、実際の試験問題ではない。それを「過去問」と書くのは
# 景表法の優良誤認 + App Store Guideline 2.3.1(正確なメタデータ)。「予想問題」は konan 却下。
# 189本中71本がこの文言で出荷寸前だったので、人間の目でなく機械で落とす。
BANNED_WORDS = [
    ("過去問", "実際の試験問題ではないので優良誤認(2026-08-12)。「対策問題」「問題を回す」に言い換える"),
    ("予想問題", "根拠のない当て物に見える(konan却下)。「対策問題」に言い換える"),
]

# 【2026-08-20 F-423・konan激怒】海外向けアプリの動画に日本語ナレーションが焼き込まれたまま
# YouTube公開された(Esthetician 2本)。キャプションが英語でも映像の中の音声が日本語なら
# その国の視聴者には無意味 = 「海外は映像も音声も全部その国の言語」(2026-08-09 konan明言)違反。
# 判定: キャプションに日本語が1文字も無い = 海外向け投稿とみなし、
#       automation/audio_lang.json(whisper実測キャッシュ)で音声言語を確認する。
#       未検査は fail-closed(F-422「検査スキップ=合格」の錯覚を許さない)。
#       キャッシュは `python3 automation/queue_lint.py --probe` が生成する(ローカル・whisper tiny)。
# 【2026-08-20 F-424・konan指摘】SARメタデータ壊れ(ピクセル比が横長扱い)の動画74本が在庫に混入し、
# IGリールで横に引き伸ばされ文字も潰れて公開されていた。コード上の解像度だけでなく
# 「表示上の縦横比」を実測して 9:16 以外を隔離する。ffmpeg必須(無ければ設定不備として全停止)。
import subprocess as _sp
DIMS_CACHE_FILE = os.path.join(HERE, "video_dims_cache.json")
_FFMPEG_CANDIDATES = ["/Users/konan/.local/bin/ffmpeg", "ffmpeg", "/usr/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]

def _ffmpeg_bin():
    import shutil as _sh
    for c in _FFMPEG_CANDIDATES:
        if os.path.sep in c and os.path.exists(c):
            return c
        w = _sh.which(c)
        if w:
            return w
    return None

def check_display_aspect(path, cache):
    """(ok, why) — 表示縦横比が9:16(±2%)か。結果はmtime付きでキャッシュ。"""
    st = os.stat(path)
    key = f"{os.path.basename(path)}:{st.st_size}:{int(st.st_mtime)}"
    if key in cache:
        return tuple(cache[key])
    ff = _ffmpeg_bin()
    if not ff:
        raise SystemExit("ffmpeg が見つからない — 画面比検査ができないので停止(設定不備)")
    r = _sp.run([ff, "-i", path], capture_output=True, text=True)
    m = re.search(r"Video:.*?(\d{3,4})x(\d{3,4})", r.stderr)
    if not m:
        res = (False, "映像ストリームを読めない")
    else:
        w, h = int(m.group(1)), int(m.group(2))
        sar = re.search(r"\[?SAR (\d+):(\d+)", r.stderr)
        disp = (w / h) * (int(sar.group(1)) / int(sar.group(2)) if sar else 1.0)
        if abs(disp - 9 / 16) > 0.02 * (9 / 16):
            res = (False, f"表示比 {disp:.3f}(SAR込み)が9:16でない")
        else:
            res = (True, "")
    cache[key] = list(res)
    return res

JA_CHARS = re.compile(r"[ぁ-んァ-ン一-龥]")
AUDIO_LANG_FILE = os.path.join(HERE, "audio_lang.json")

def _audio_lang_cache():
    try:
        return json.load(open(AUDIO_LANG_FILE))
    except Exception:
        return {}

HYPE_PATTERNS = [
    (r"締切まで(時間がない|あと|残り)", "締切で焦らせている"),
    (r"試験まであと\s*\d", "カウントダウンで焦らせている"),
    (r"今(動かないと|やらないと|始めないと)", "今やらないと、で焦らせている"),
    (r"(動かす側|見送る側|上に行く(なら|か))", "二択を突きつけて発奮させている"),
    (r"先輩は.{0,8}(隙間時間|スキマ時間)", "成功者の習慣を語っている"),
    (r"(差はここで開く|差が開く)", "格差を主題にしている"),
    (r"合格まで(あと|残り)", "合否を主題にしている"),
]


def lint(path, bad_keys=None):
    """NG を検出する。bad_keys(set) を渡すと、NG になった投稿の識別子をそこに入れる。

    【2026-08-12】以前は NG が1件でも exit 1 にしてワークフローごと落としていた。
    その結果、煽り構文を含む**1本**のせいで IG/Threads/YouTube の配信が
    16時間半すべて止まった。**不良品は隔離し、健全な在庫は流す**のが正しい。
    """
    errs = []
    bad_keys = bad_keys if bad_keys is not None else set()
    d = json.load(open(path))
    posts = d["posts"] if isinstance(d, dict) else d
    is_queue = os.path.basename(path) == "post_queue.json"
    seen_video = {}
    def _key(post, idx):
        return post.get("video") or f"{os.path.basename(path)}#{idx}"

    for i, p in enumerate(posts):
        tag = f"{os.path.basename(path)}[{i}] {p.get('app','?')}"
        _n0 = len(errs)
        for k in REQUIRED:
            if not p.get(k):
                errs.append(f"{tag}: 必須キー欠落 {k}")
        url = p.get("appstore_url", "")
        if url and not re.search(r"apps\.apple\.com/.+/id\d+", url):
            errs.append(f"{tag}: appstore_url形式不正 {url}")
        if is_queue:
            for key, sub in [("video", "videos"), ("cover", "videos"), ("yt_thumb", "videos")]:
                f = p.get(key)
                if f and not os.path.exists(os.path.join(REPO, sub, f)):
                    errs.append(f"{tag}: {key}ファイル未配置 {sub}/{f}")
        if is_queue and p.get("video"):
            vpath = os.path.join(REPO, "videos", p["video"])
            if os.path.exists(vpath):
                _c = getattr(lint, "_dims_cache", None)
                if _c is None:
                    try:
                        _c = json.load(open(DIMS_CACHE_FILE))
                    except Exception:
                        _c = {}
                    lint._dims_cache = _c
                okv, why = check_display_aspect(vpath, _c)
                if not okv:
                    errs.append(f"{tag}: 画面比NG — {why}(9:16必須・F-424)")
        blob_all = (p.get("ig_caption") or "") + "\n" + (p.get("threads_text") or "")
        # 禁止語はキャプションだけでなく全テキスト項目(yt_title/yt_desc/app 名まで)を見る
        blob_every = "\n".join(
            v if isinstance(v, str) else "\n".join(v)
            for v in p.values() if isinstance(v, (str, list)))
        for word, why in BANNED_WORDS:
            if word in blob_every:
                errs.append(f"{tag}: 禁止語「{word}」— {why}")
        m = PRICE_TALK.search(blob_every)
        if m:
            errs.append(f"{tag}: 値段の話「{m.group(0)}」— 投稿で無料/有料に触れない"
                        f"(2026-08-13 konan明言)。存在を知らせるだけでよい")
        for pat, why in HYPE_PATTERNS:
            m = re.search(pat, blob_all)
            if m:
                errs.append(f"{tag}: 煽り構文「{m.group(0)}」— {why}"
                            f"(アプリ紹介に徹する・2026-08-05 konan明言)")
        # ── 海外向け×音声言語(F-423) ──
        cap_blob = (p.get("ig_caption") or "") + (p.get("threads_text") or "") + (p.get("yt_title") or "")
        if is_queue and cap_blob.strip() and not JA_CHARS.search(cap_blob):
            vlang = _audio_lang_cache().get(p.get("video") or "")
            if vlang is None:
                errs.append(f"{tag}: 海外向け投稿なのに音声言語が未検査 — "
                            f"`python3 automation/queue_lint.py --probe` で実測してから流す(F-423)")
            elif vlang == "ja":
                errs.append(f"{tag}: 海外向け投稿に日本語音声(whisper実測) — "
                            f"その国の言語で作り直す(2026-08-09 konan明言/F-423)")
        tt = p.get("threads_text", "")
        if re.search(r"このシーン|この動画|この映像", tt):
            errs.append(f"{tag}: threads_textが映像参照(Threadsはテキスト専用=自己完結文にする・2026-07-27 konan指摘)")
        # ── YouTube メタデータ ──
        # 自チャンネル239本の実測: タイトルに「アプリ」= 平均48再生 / 入っていない = 241。
        # 問いかけ形 = 324 / それ以外 = 166。だから「アプリの説明」を書いた時点で負ける。
        # 投稿済みの動画はYouTube側をもう直せない(隔離するとIG/Threadsの再投稿まで止まる)ので対象外。
        yt = "" if p.get("video") in YT_POSTED else p.get("yt_title", "")
        if yt:
            if len(yt) > 100:
                errs.append(f"{tag}: yt_titleが100字超({len(yt)}字)— YouTubeが切る")
            if "アプリ" in yt:
                errs.append(f"{tag}: yt_titleに「アプリ」— 実測で平均48再生(入れない場合241)。中身でなく話題で釣る")
            if not re.search(r"[?？0-9０-９]", yt):
                errs.append(f"{tag}: yt_titleに問いかけも数字も無い — 実測で問いかけ形は平均324、それ以外166")
            # 【2026-08-16 konan 指示「タイトルにハッシュタグつけるようにね」】
            # 縦3分未満は #shorts が無くてもShorts判定されるので、枠を題材ハッシュタグに使う。
            if not re.search(r"#\S", yt):
                errs.append(f"{tag}: yt_titleにハッシュタグが無い — 検索の入口を捨てている")
            if not p.get("yt_tags"):
                errs.append(f"{tag}: yt_tags未設定 — 検索の入口を捨てている")
            if not p.get("yt_thumb"):
                errs.append(f"{tag}: yt_thumb未設定 — YouTubeが勝手に1フレーム選ぶ(検索でクリックされない)")
            yd = p.get("yt_desc", "")
            if "#" not in yd:
                errs.append(f"{tag}: yt_descにハッシュタグが無い")
            if url and url not in yd:
                errs.append(f"{tag}: yt_descにApp StoreのURLが無い")
        v = p.get("video")
        if v:
            prev = seen_video.get(v)
            if prev is not None and posts[prev].get("appstore_url") != p.get("appstore_url"):
                errs.append(f"{tag}: 同一video {v} を別アプリと共用(F-379)")
            seen_video[v] = i
        if len(errs) > _n0:
            bad_keys.add(_key(p, i))
    return errs

def probe_audio_langs():
    """海外向け(キャプション無日本語)エントリの動画音声をwhisper tinyで実測してキャッシュする。"""
    q = json.load(open(os.path.join(HERE, "post_queue.json")))
    cache = _audio_lang_cache()
    import subprocess, tempfile
    FF = "/Users/konan/.local/bin/ffmpeg"
    try:
        import whisper
        model = whisper.load_model("tiny")
    except Exception as e:
        print("whisper不可:", e); return 1
    for p in q["posts"]:
        v = p.get("video") or ""
        cap = (p.get("ig_caption") or "") + (p.get("threads_text") or "") + (p.get("yt_title") or "")
        if not v or v in cache or not cap.strip() or JA_CHARS.search(cap):
            continue
        path = os.path.join(REPO, "videos", v)
        if not os.path.exists(path):
            continue
        wav = tempfile.mktemp(suffix=".wav")
        subprocess.run([FF, "-y", "-i", path, "-t", "25", "-ar", "16000", "-ac", "1", wav],
                       capture_output=True)
        try:
            r = model.transcribe(wav, fp16=False)
            lang = "ja" if JA_CHARS.search(r.get("text", "")) else (r.get("language") or "?")
            cache[v] = lang
            print(f"probe: {v} → {lang}")
        finally:
            os.remove(wav)
    json.dump(cache, open(AUDIO_LANG_FILE, "w"), ensure_ascii=False, indent=1)
    print(f"audio_lang.json 更新({len(cache)}件)")
    return 0


def main(argv):
    if argv and argv[0] == "--probe":
        return probe_audio_langs()
    targets = argv or [os.path.join(HERE, "post_queue.json")] + sorted(glob.glob(os.path.join(HERE, "*_launch_pack.json")))
    all_errs = []
    bad_keys = set()
    total = 0
    for t in targets:
        d = json.load(open(t))
        total += len(d["posts"] if isinstance(d, dict) else d)
        all_errs += lint(t, bad_keys)
    for e in all_errs:
        print("NG", e)

    # 【2026-08-12】NG は「隔離」であって「全停止」ではない。
    # 以前は1本の煽り構文で exit 1 → ワークフロー全体が落ち、
    # IG/Threads/YouTube の配信が16時間半止まった。被害が不良1本分で収まる形にする。
    qpath = os.path.join(HERE, "quarantine_lint.json")   # ゲートごとに分ける(相互上書き防止)
    if bad_keys:
        json.dump(sorted(bad_keys), open(qpath, "w"), ensure_ascii=False, indent=1)
        print(f"\n🚧 隔離 {len(bad_keys)}件 / 全{total}件 — この分だけ配信から外して続行します")
        print(f"   → {qpath}(cloud_post.py がこれを読んで除外する)")
        # 全滅なら配信するものが無いので、これは本当に止める
        if len(bad_keys) >= total:
            print("❌ 全件NG — 配信できるものが無いので停止します")
            return 1
    if getattr(lint, "_dims_cache", None) is not None:
        json.dump(lint._dims_cache, open(DIMS_CACHE_FILE, "w"))
    else:
        if os.path.exists(qpath):
            os.remove(qpath)
        print(f"OK {len(targets)} files clean")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
