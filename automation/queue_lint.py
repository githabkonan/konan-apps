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
            for key, sub in [("video", "videos"), ("cover", "videos")]:
                f = p.get(key)
                if f and not os.path.exists(os.path.join(REPO, sub, f)):
                    errs.append(f"{tag}: {key}ファイル未配置 {sub}/{f}")
        blob_all = (p.get("ig_caption") or "") + "\n" + (p.get("threads_text") or "")
        # 禁止語はキャプションだけでなく全テキスト項目(yt_title/yt_desc/app 名まで)を見る
        blob_every = "\n".join(v for v in p.values() if isinstance(v, str))
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
        tt = p.get("threads_text", "")
        if re.search(r"このシーン|この動画|この映像", tt):
            errs.append(f"{tag}: threads_textが映像参照(Threadsはテキスト専用=自己完結文にする・2026-07-27 konan指摘)")
        v = p.get("video")
        if v:
            prev = seen_video.get(v)
            if prev is not None and posts[prev].get("appstore_url") != p.get("appstore_url"):
                errs.append(f"{tag}: 同一video {v} を別アプリと共用(F-379)")
            seen_video[v] = i
        if len(errs) > _n0:
            bad_keys.add(_key(p, i))
    return errs

def main(argv):
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
    else:
        if os.path.exists(qpath):
            os.remove(qpath)
        print(f"OK {len(targets)} files clean")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
