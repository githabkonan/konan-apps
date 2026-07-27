#!/usr/bin/env python3
"""queue_lint.py — post_queue.json / *_launch_pack.json の必須キー・整合検査。
F-379系(キー欠落・動画参照ミス)をpush前に機械で止める。
使い方: python3 automation/queue_lint.py [ファイル...]  # 省略時=queue+全launch_pack
検査: 必須キー(threads_text/ig_caption/video/cover/app)・appstore_urlのid形式・
      video/coverのローカル実在(queueのみ)・同一videoを複数エントリが別captionで参照してないか
"""
import json, re, sys, glob, os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REQUIRED = ["app", "video", "ig_caption", "threads_text"]  # cover はcloud_post側で任意(あれば警告のみ)

def lint(path):
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
        if is_queue:
            for key, sub in [("video", "videos"), ("cover", "videos")]:
                f = p.get(key)
                if f and not os.path.exists(os.path.join(REPO, sub, f)):
                    errs.append(f"{tag}: {key}ファイル未配置 {sub}/{f}")
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
    all_errs = []
    for t in targets:
        all_errs += lint(t)
    for e in all_errs:
        print("NG", e)
    if not all_errs:
        print(f"OK {len(targets)} files clean")
    return 1 if all_errs else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
