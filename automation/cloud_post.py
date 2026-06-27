#!/usr/bin/env python3
"""cloud_post.py — GitHub Actions上で動く Mac非依存の自動投稿(IG Reels + Threads)
================================================================
原則3: 公式API/認可スケジューラのみ(bot検知対象外)。
- トークンは GitHub Secrets(env): IG_USER_ID / IG_TOKEN / THREADS_USER_ID / THREADS_ACCESS_TOKEN
- ローテは「JST日付×6スロット+その日のスロット番号」で決定的に算出=状態ファイル不要
- 動画は同リポの GitHub Pages(video_base)から公開URLで渡す
"""
import json, os, sys, time, datetime, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
Q = json.load(open(os.path.join(HERE, "post_queue.json")))
BASE_VID = Q["video_base"].rstrip("/")
POSTS = Q["posts"]
N = len(POSTS)

JST_SLOTS = [7, 12, 15, 18, 20, 22]
now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)  # JST
day_num = (now.date() - datetime.date(2026, 1, 1)).days
slot = min(range(len(JST_SLOTS)), key=lambda i: abs(JST_SLOTS[i] - now.hour))
idx = (day_num * len(JST_SLOTS) + slot) % N
post = POSTS[idx]
video_url = f"{BASE_VID}/{post['video']}"
caption = post["caption"]
print(f"[{now.isoformat()}] JST slot={slot} idx={idx} app={post.get('app')} video={post['video']}")


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=90))


def _get(url, params):
    return json.load(urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=60))


def publish_threads():
    uid = os.environ["THREADS_USER_ID"]; tok = os.environ["THREADS_ACCESS_TOKEN"]
    B = "https://graph.threads.net/v1.0"
    cid = _post(f"{B}/{uid}/threads", {"media_type": "VIDEO", "video_url": video_url, "text": caption, "access_token": tok})["id"]
    st = None
    for _ in range(40):
        time.sleep(6)
        st = _get(f"{B}/{cid}", {"fields": "status", "access_token": tok}).get("status")
        if st in ("FINISHED", "PUBLISHED"): break
        if st == "ERROR": raise RuntimeError(f"threads status ERROR")
    if st not in ("FINISHED", "PUBLISHED"): raise RuntimeError(f"threads timeout status={st}")
    time.sleep(2)
    return _post(f"{B}/{uid}/threads_publish", {"creation_id": cid, "access_token": tok}).get("id")


def publish_instagram():
    ig = os.environ["IG_USER_ID"]; tok = os.environ["IG_TOKEN"]
    B = "https://graph.instagram.com/v21.0"
    cid = _post(f"{B}/{ig}/media", {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true", "access_token": tok})["id"]
    sc = None
    for _ in range(40):
        time.sleep(6)
        sc = _get(f"{B}/{cid}", {"fields": "status_code", "access_token": tok}).get("status_code")
        if sc == "FINISHED": break
        if sc == "ERROR": raise RuntimeError("IG status ERROR")
    if sc != "FINISHED": raise RuntimeError(f"IG timeout status={sc}")
    time.sleep(2)
    return _post(f"{B}/{ig}/media_publish", {"creation_id": cid, "access_token": tok}).get("id")


results = {}
for name, fn in [("threads", publish_threads), ("instagram", publish_instagram)]:
    try:
        pid = fn(); results[name] = {"ok": True, "id": pid}; print(f"  {name}: OK {pid}")
    except Exception as e:
        body = getattr(e, "read", lambda: b"")()
        results[name] = {"ok": False, "err": str(e)[:200]}
        print(f"  {name}: ERR {str(e)[:200]} {(body[:200] if body else '')}")
print("RESULT", json.dumps(results, ensure_ascii=False))
if not any(r.get("ok") for r in results.values()):
    sys.exit(1)
