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

# 【F-409・2026-08-07 konan 指摘「陸曹アプリは無料じゃないぞ。なぜ嘘ついてんの?」】
# ¥3,000 の自衛官陸曹昇任アプリを「無料でダウンロードできる」と紹介する動画をYouTubeに公開していた。
# 広告としての虚偽表示(景表法・優良誤認)であり、ストア規約上も危険。
# 人間のレビューに頼らず、**App Store の実価格を機械で引いて突き合わせる**。
FREE_WORD = re.compile(r"無料|タダ|0円|ゼロ円|\bfree\b", re.I)
PRICE_CACHE = os.path.join(HERE, ".price_cache.json")

# 【2026-08-05 konan 明言 → 2026-08-08 再発でゲート化】
# 「自衛官の昇任系が試験系自己啓発チャンネルみたいになってて言語化できない恥ずかしさがある。
#   こんなアプリあるよ!って知ってもらうだけでいい。あくまでアプリ紹介」
# プロンプトに書くだけでは 2026-08-08 のバッチで「締切まで時間がない。」がすり抜けた。
# **煽り構文を機械で落とす。** 事実の告知(「締切は9月10日だ」)は通し、焦らせる言い回しだけを弾く。
HYPE_PATTERNS = [
    (r"締切まで(時間がない|あと|残り)", "締切で焦らせている"),
    (r"試験まであと\s*\d", "カウントダウンで焦らせている"),
    (r"今(動かないと|やらないと|始めないと)", "今やらないと、で焦らせている"),
    (r"(動かす側|見送る側|上に行く(なら|か))", "二択を突きつけて発奮させている"),
    (r"先輩は.{0,8}(隙間時間|スキマ時間)", "成功者の習慣を語っている"),
    (r"(差はここで開く|差が開く)", "格差を主題にしている"),
    (r"合格まで(あと|残り)", "合否を主題にしている"),
]


def fetch_prices(app_ids):
    """App Store の実価格を引く。取得できたぶんだけ返す(ネット不通なら空=検査スキップ)。"""
    import urllib.request
    out = {}
    ids = sorted(set(app_ids))
    for i in range(0, len(ids), 10):
        chunk = ",".join(ids[i:i + 10])
        try:
            url = f"https://itunes.apple.com/lookup?id={chunk}&country=jp"
            d = json.load(urllib.request.urlopen(url, timeout=20))
        except Exception as e:
            print(f"WARN 価格照会に失敗({e}) — 価格検査はこのぶんだけスキップ", file=sys.stderr)
            continue
        for r in d.get("results", []):
            out[str(r.get("trackId"))] = {"price": r.get("price"), "label": r.get("formattedPrice"),
                                          "name": r.get("trackName")}
    if out:  # 直近の実測を残しておく(ネット不通時のフォールバック)
        try:
            old = json.load(open(PRICE_CACHE))
        except Exception:
            old = {}
        old.update(out)
        json.dump(old, open(PRICE_CACHE, "w"), ensure_ascii=False, indent=1)
        return old
    try:
        return json.load(open(PRICE_CACHE))
    except Exception:
        return {}

def lint(path, prices=None):
    prices = prices or {}
    errs = []
    d = json.load(open(path))
    posts = d["posts"] if isinstance(d, dict) else d
    is_queue = os.path.basename(path) == "post_queue.json"
    seen_video = {}
    for i, p in enumerate(posts):
        tag = f"{os.path.basename(path)}[{i}] {p.get('app','?')}"
        for k in REQUIRED:
            if not p.get(k):
                errs.append(f"{tag}: 必須キー欠落 {k}")
        url = p.get("appstore_url", "")
        if url and not re.search(r"apps\.apple\.com/.+/id\d+", url):
            errs.append(f"{tag}: appstore_url形式不正 {url}")
        m_id = re.search(r"/id(\d+)", url)
        if m_id and prices.get(m_id.group(1)):
            info = prices[m_id.group(1)]
            blob = (p.get("ig_caption") or "") + "\n" + (p.get("threads_text") or "")
            if (info.get("price") or 0) > 0 and FREE_WORD.search(blob):
                errs.append(f"{tag}: 価格の嘘 — {info.get('name')} は {info.get('label')} なのに"
                            f"「無料」と書いている(F-409)")
        if is_queue:
            for key, sub in [("video", "videos"), ("cover", "videos")]:
                f = p.get(key)
                if f and not os.path.exists(os.path.join(REPO, sub, f)):
                    errs.append(f"{tag}: {key}ファイル未配置 {sub}/{f}")
        blob_all = (p.get("ig_caption") or "") + "\n" + (p.get("threads_text") or "")
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
    return errs

def main(argv):
    targets = argv or [os.path.join(HERE, "post_queue.json")] + sorted(glob.glob(os.path.join(HERE, "*_launch_pack.json")))
    app_ids = []
    for t in targets:
        d = json.load(open(t))
        for p in (d["posts"] if isinstance(d, dict) else d):
            m = re.search(r"/id(\d+)", p.get("appstore_url", "") or "")
            if m:
                app_ids.append(m.group(1))
    prices = fetch_prices(app_ids)
    all_errs = []
    for t in targets:
        all_errs += lint(t, prices)
    for e in all_errs:
        print("NG", e)
    if not all_errs:
        print(f"OK {len(targets)} files clean")
    return 1 if all_errs else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
