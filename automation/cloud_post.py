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
# Threads は上限250/日と余裕があるので1回の起動で複数本(別アプリ)を投稿してpaceを稼ぐ。
# GitHubのスケジューラが大半の起動をスキップするため、1起動あたりの本数で取りこぼしを補う。
THREADS_PER_RUN = int(os.environ.get("THREADS_PER_RUN", "3"))
IG_PER_RUN = int(os.environ.get("IG_PER_RUN", "3"))  # IG公開上限は100/日と余裕(実測quota 5/100)。1起動3本でpaceを出す
print(f"[{now.isoformat()}] seq={seq} threads/run={THREADS_PER_RUN} ig/run={IG_PER_RUN}")


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=120))


def _get(url, params):
    return json.load(urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=60))


def publish_threads(post):
    """テキスト + URL のみ(動画は使わない)。"""
    uid = os.environ["THREADS_USER_ID"]; tok = os.environ["THREADS_ACCESS_TOKEN"]
    B = "https://graph.threads.net/v1.0"
    cid = _post(f"{B}/{uid}/threads", {"media_type": "TEXT", "text": post["threads_text"], "access_token": tok})["id"]
    time.sleep(3)
    return _post(f"{B}/{uid}/threads_publish", {"creation_id": cid, "access_token": tok}).get("id")


def publish_instagram(post):
    """動画 Reel + cover(検索画面フレーム)。"""
    ig = os.environ["IG_USER_ID"]; tok = os.environ["IG_TOKEN"]
    B = "https://graph.instagram.com/v21.0"
    video_url = f"{BASE}/{post['video']}"
    params = {"media_type": "REELS", "video_url": video_url, "caption": post["ig_caption"],
              "share_to_feed": "true", "access_token": tok}
    if post.get("cover"):
        params["cover_url"] = f"{BASE}/{post['cover']}"
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


results = []
ok_count = 0

# Threads: 1起動で別アプリを複数本(rotation: seq*K+i)。間隔を空けて連投感を緩和。
for i in range(THREADS_PER_RUN):
    tp = POSTS[(seq * THREADS_PER_RUN + i) % N]
    ok, val = with_retry(lambda p=tp: publish_threads(p))
    results.append({"ch": "threads", "app": tp.get("app"), "ok": ok, ("id" if ok else "err"): val})
    print(f"  threads[{tp.get('app')}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
    if ok: ok_count += 1
    if i < THREADS_PER_RUN - 1: time.sleep(45)

# Instagram: 25/日上限なので1本(rotation: seq)
for i in range(IG_PER_RUN):
    ip = POSTS[(seq + i) % N]
    ok, val = with_retry(lambda p=ip: publish_instagram(p))
    results.append({"ch": "instagram", "app": ip.get("app"), "ok": ok, ("id" if ok else "err"): val})
    print(f"  instagram[{ip.get('app')}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
    if ok: ok_count += 1

print("RESULT", json.dumps(results, ensure_ascii=False))
# 全滅したら赤(=気づける)。一部失敗は許容(他は投稿済)だがログには残す。
if ok_count == 0:
    sys.exit(1)
