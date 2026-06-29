#!/usr/bin/env python3
"""cloud_post.py — GitHub Actions上で動く Mac非依存の自動投稿。
================================================================
原則3: 公式API/認可スケジューラのみ(bot検知対象外)。
- Threads = テキスト + App Store URL(動画なし。konan指示 2026-06-29)
- Instagram = 動画 Reel + cover(=動画内のApp Store検索フレーム。顔なし)
- 媒体ごとに独立して成否判定+リトライ。失敗したら exit 1(Actionが赤=気づける)
- ローテは「JST日付×24 + 時」で決定的=状態ファイル不要(毎時で別アプリに回る)
- トークン: GitHub Secrets(env) IG_USER_ID / IG_TOKEN / THREADS_USER_ID / THREADS_ACCESS_TOKEN
"""
import json, os, sys, time, datetime, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
Q = json.load(open(os.path.join(HERE, "post_queue.json")))
BASE = Q["video_base"].rstrip("/")
POSTS = Q["posts"]
N = len(POSTS)

now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)  # JST
day_num = (now.date() - datetime.date(2026, 1, 1)).days
seq = day_num * 24 + now.hour
post = POSTS[seq % N]
video_url = f"{BASE}/{post['video']}"
cover_url = f"{BASE}/{post['cover']}" if post.get("cover") else None
print(f"[{now.isoformat()}] seq={seq} idx={seq % N} app={post.get('app')} type={post.get('type')}")


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=120))


def _get(url, params):
    return json.load(urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=60))


def publish_threads():
    """テキスト + URL のみ(動画は使わない)。"""
    uid = os.environ["THREADS_USER_ID"]; tok = os.environ["THREADS_ACCESS_TOKEN"]
    B = "https://graph.threads.net/v1.0"
    cid = _post(f"{B}/{uid}/threads", {"media_type": "TEXT", "text": post["threads_text"], "access_token": tok})["id"]
    time.sleep(3)
    return _post(f"{B}/{uid}/threads_publish", {"creation_id": cid, "access_token": tok}).get("id")


def publish_instagram():
    """動画 Reel + cover(検索画面フレーム)。"""
    ig = os.environ["IG_USER_ID"]; tok = os.environ["IG_TOKEN"]
    B = "https://graph.instagram.com/v21.0"
    params = {"media_type": "REELS", "video_url": video_url, "caption": post["ig_caption"],
              "share_to_feed": "true", "access_token": tok}
    if cover_url:
        params["cover_url"] = cover_url
    cid = _post(f"{B}/{ig}/media", params)["id"]
    sc = None
    for _ in range(40):
        time.sleep(6)
        sc = _get(f"{B}/{cid}", {"fields": "status_code", "access_token": tok}).get("status_code")
        if sc == "FINISHED": break
        if sc == "ERROR": raise RuntimeError("IG status ERROR")
    if sc != "FINISHED": raise RuntimeError(f"IG timeout status={sc}")
    time.sleep(2)
    return _post(f"{B}/{ig}/media_publish", {"creation_id": cid, "access_token": tok}).get("id")


def with_retry(fn, attempts=2):
    last = None
    for i in range(attempts):
        try:
            return True, fn()
        except Exception as e:
            body = getattr(e, "read", lambda: b"")()
            last = f"{str(e)[:180]} {(body[:180].decode('utf-8','replace') if body else '')}".strip()
            print(f"  attempt {i + 1} ERR: {last}")
            time.sleep(6)
    return False, last


results = {}
for name, fn in [("threads", publish_threads), ("instagram", publish_instagram)]:
    ok, val = with_retry(fn)
    results[name] = {"ok": ok, ("id" if ok else "err"): val}
    print(f"  {name}: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")

print("RESULT", json.dumps(results, ensure_ascii=False))
# 「投稿できてない」を可視化: いずれかの媒体が(リトライ後も)失敗したら赤=気づける
if not all(r["ok"] for r in results.values()):
    sys.exit(1)
