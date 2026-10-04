#!/usr/bin/env python3
"""投稿キューの App Store ID が実在するかの検査(2026-10-04 追加)。

9/21 製の3本(予備自衛官補・空曹・入隊)に存在しないIDが入り、cloud_post.py の
「未公開アプリ除外」に黙って弾かれ続けて2週間1度も配信されなかった。
実行時の除外ログは誰も読まないので、在庫に入る時点(pre-push)と朝チェックで止める。

  - 同じアプリ名の別エントリが実在IDを持つのに、このエントリのIDが実在しない → 誤ID = FAIL
  - アプリ名ごと実在IDが無い → 未公開(または誤ID)= WARN(公開前の先行在庫はあり得る)
通信失敗は判定不能として通す(1本の不明で配信全体を止めない)。
"""
import json, os, re, sys, urllib.request

Q = os.path.join(os.path.dirname(os.path.abspath(__file__)), "post_queue.json")


def check():
    posts = json.load(open(Q, encoding="utf-8"))["posts"]
    rid = lambda p: (re.search(r"/id(\d+)", p.get("appstore_url") or "") or [None, None])[1]
    ids = sorted({rid(p) for p in posts if rid(p)})
    live = set()
    for i in range(0, len(ids), 10):
        chunk = ids[i:i + 10]
        try:
            d = json.load(urllib.request.urlopen(
                f"https://itunes.apple.com/lookup?id={','.join(chunk)}&country=jp", timeout=20))
        except Exception as e:
            print(f"WARN appid_gate: ストア照会失敗({str(e)[:60]})→ 判定不能として通す")
            return [], []
        live |= {str(r["trackId"]) for r in d.get("results", [])}
    live_by_app = {}
    for p in posts:
        if rid(p) in live:
            live_by_app.setdefault(p.get("app"), rid(p))
    wrong, unpub = [], []
    for p in posts:
        if rid(p) in live:
            continue
        if p.get("app") in live_by_app:
            wrong.append((p.get("app"), p.get("video"), rid(p), live_by_app[p["app"]]))
        else:
            unpub.append((p.get("app"), p.get("video"), rid(p)))
    return wrong, unpub


if __name__ == "__main__":
    wrong, unpub = check()
    for a, v, bad, good in wrong:
        print(f"FAIL appid_gate: {a} / {v} の ID {bad} は実在しない(同アプリの実在ID = {good})")
    for a, v, bad in unpub:
        print(f"WARN appid_gate: {a} / {v} の ID {bad} はストアに無い(未公開なら配信で除外される)")
    if wrong:
        sys.exit(1)
    print(f"OK appid_gate: 誤ID 0 本(未公開 {len(unpub)} 本)")
