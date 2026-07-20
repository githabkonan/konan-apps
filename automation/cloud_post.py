#!/usr/bin/env python3
"""cloud_post.py — GitHub Actions上で動く Mac非依存の自動投稿。
================================================================
原則3: 公式API/認可スケジューラのみ(bot検知対象外)。
- Threads = テキスト + App Store URL(動画なし。konan指示 2026-06-29)
- Instagram = 動画 Reel + cover(=動画内のApp Store検索フレーム。顔なし)
- 媒体ごとに独立して成否判定+リトライ。失敗したら exit 1(Actionが赤=気づける)
- ローテは「JST日付×24 + 時」で決定的=状態ファイル不要(毎時で別アプリに回る)
- トークン: GitHub Secrets(env) IG_USER_ID / IG_TOKEN / THREADS_USER_ID / THREADS_ACCESS_TOKEN / YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN
- YouTube = Shorts動画(公式API・2026-07-07監査承認済=公開可)。新規chスパム回避で seq%3==0 の起動のみ1本(≈2-3本/日)
- Threads/IG のローテはASC実売上(revenue.db)で重み付け(2026-07-19 konan「売れるアプリをより打ってかないと・ASCの結果と紐付いてない」)。
  重み無しの均等ローテはゼロ課金アプリ(ライフコントロール等)を稼ぎ頭(陸曹昇任等)と同じ露出にしてしまっていた。
"""
import json, os, sys, time, datetime, urllib.parse, urllib.request, re

HERE = os.path.dirname(os.path.abspath(__file__))
Q = json.load(open(os.path.join(HERE, "post_queue.json")))
BASE = Q["video_base"].rstrip("/")
POSTS = Q["posts"]
N = len(POSTS)

# 2026-07-19: revenue.db実測(SKU単位)から手動集計した加重値。App Store IDで紐付け。
# 陸曹昇任(¥31,410)=5 / 予備自(¥11,100)=3 / 幹部(¥6,660)=2 / 未提出の新規ローンチ(英語脳等)=2(露出優先)/ 他は全部1(ゼロ課金でも完全ゼロにはしない=noise一発でapp切りしない)
REVENUE_WEIGHT = {"6774074604": 5, "6778490302": 3, "6776236258": 2}
def _weight(p):
    url = p.get("appstore_url") or ""
    if not url:
        return 2
    m = re.search(r"id(\d+)", url)
    return REVENUE_WEIGHT.get(m.group(1) if m else "", 1)

# 加重ローテ表: pass1=全post1回ずつ、pass2以降は重み>=passの投稿だけ追加(高稼働アプリほど登場回数が増える)
ROTATION = [i for _pass in range(1, 6) for i, p in enumerate(POSTS) if _weight(p) >= _pass]

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


def publish_youtube(post):
    """Shorts動画を公開アップロード(resumable)。監査承認済みクライアント。"""
    import http.client
    cid_ = os.environ["YT_CLIENT_ID"]; sec = os.environ["YT_CLIENT_SECRET"]; ref = os.environ["YT_REFRESH_TOKEN"]
    tok = _post("https://oauth2.googleapis.com/token",
                {"client_id": cid_, "client_secret": sec, "refresh_token": ref, "grant_type": "refresh_token"})["access_token"]
    video_url = f"{BASE}/{post['video']}"
    data = urllib.request.urlopen(video_url, timeout=180).read()
    title = post.get("yt_title") or (post["ig_caption"].split("\n")[0][:95] + " #shorts")
    desc = post.get("yt_desc") or (post["ig_caption"] + "\n" + post.get("appstore_url", ""))
    meta = json.dumps({"snippet": {"title": title[:100], "description": desc[:4900], "categoryId": "27"},
                       "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}).encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=meta, method="POST",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(len(data)), "X-Upload-Content-Type": "video/mp4"})
    up_url = urllib.request.urlopen(req, timeout=60).headers["Location"]
    req2 = urllib.request.Request(up_url, data=data, method="PUT",
                                  headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"})
    vid = json.load(urllib.request.urlopen(req2, timeout=600))["id"]
    return f"https://youtube.com/shorts/{vid}"


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

# ---- 重複投稿ガード(2026-07-10 規約リスク対策) ----
# YT: 同一ファイルの再アップはスパム/再利用コンテンツ判定リスク(2026年Shorts検出強化)→ 同じ動画は一度きり。
# IG/Threads: 同一物の高頻度再投稿は減速/スパム様 → 1動画あたり72hクールダウン。
STATE_PATH = os.path.join(HERE, "state.json")
try: STATE = json.load(open(STATE_PATH))
except Exception: STATE = {}
HIST = STATE.setdefault("hist", {})          # {platform: {video: iso_ts}}
YT_POSTED = STATE.setdefault("yt_posted", [])  # YTに投稿済みの動画(恒久)
COOLDOWN_H = float(os.environ.get("REPOST_COOLDOWN_H", "72"))

def save_state():
    json.dump(STATE, open(STATE_PATH, "w"))

def cooled(platform, post):
    ts = HIST.get(platform, {}).get(post.get("video", post.get("app")), "")
    if not ts: return True
    try:
        last = datetime.datetime.fromisoformat(ts)
        return (now - last).total_seconds() >= COOLDOWN_H * 3600
    except Exception: return True

def mark(platform, post):
    HIST.setdefault(platform, {})[post.get("video", post.get("app"))] = now.isoformat()
    save_state()

def pick(platform, start_idx):
    """start_idxから順に(加重ローテ表を辿り)、クールダウン明けの動画を探す。全滅ならNone(=見送り)。"""
    R = len(ROTATION)
    for k in range(R):
        p = POSTS[ROTATION[(start_idx + k) % R]]
        if cooled(platform, p): return p
    return None

# Threads: 1起動で別アプリを複数本(rotation: seq*K+i)。間隔を空けて連投感を緩和。
for i in range(THREADS_PER_RUN):
    tp = pick("threads", seq * THREADS_PER_RUN + i)
    if tp is None:
        print("  threads: 全動画クールダウン中=見送り"); break
    ok, val = with_retry(lambda p=tp: publish_threads(p))
    results.append({"ch": "threads", "app": tp.get("app"), "ok": ok, ("id" if ok else "err"): val})
    print(f"  threads[{tp.get('app')}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
    if ok: ok_count += 1; mark("threads", tp)
    if i < THREADS_PER_RUN - 1: time.sleep(45)

# Instagram: 25/日上限なので1本(rotation: seq)
for i in range(IG_PER_RUN):
    ip = pick("instagram", seq + i)
    if ip is None:
        print("  instagram: 全動画クールダウン中=見送り"); break
    ok, val = with_retry(lambda p=ip: publish_instagram(p))
    results.append({"ch": "instagram", "app": ip.get("app"), "ok": ok, ("id" if ok else "err"): val})
    print(f"  instagram[{ip.get('app')}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
    if ok: ok_count += 1; mark("instagram", ip)

# YouTube: 最優秀チャンネルだが同一動画の再アップ=スパム/重複判定リスク → 各動画一度きり。
# 未投稿の動画が無くなったら投稿しない(=新作が投入されると自動再開)。
YT_MAX_PER_DAY = int(os.environ.get("YT_MAX_PER_DAY", "9"))
# YT投稿はエンゲージメント時間帯に分散。JSTの時のセット(2026-07-19: 最強チャネルなのに枠が一番狭かったため5→9に増枠・スロットも5→9に増設)。
YT_HOURS = {int(h) for h in os.environ.get("YT_HOURS", "6,8,11,13,15,17,19,21,23").split(",")}
today = now.date().isoformat()
if STATE.get("yt_date") != today:
    STATE["yt_date"] = today; STATE["yt_count"] = 0; STATE["last_yt_seq"] = None
yt_done = (STATE.get("last_yt_seq") == seq) or (STATE.get("yt_count", 0) >= YT_MAX_PER_DAY) or (now.hour not in YT_HOURS)
if os.environ.get("YT_REFRESH_TOKEN") and not yt_done:
    yp = next((POSTS[(seq + k) % N] for k in range(N)
               if POSTS[(seq + k) % N].get("video") not in YT_POSTED), None)
    if yp is None:
        print("  youtube: 全動画投稿済み(重複再アップ回避)=新作待ち")
    else:
        ok, val = with_retry(lambda p=yp: publish_youtube(p))
        results.append({"ch": "youtube", "app": yp.get("app"), "ok": ok, ("id" if ok else "err"): val})
        print(f"  youtube[{yp.get('app')}] ({STATE.get('yt_count',0)+1}/{YT_MAX_PER_DAY}): {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
        if ok:
            ok_count += 1
            STATE["last_yt_seq"] = seq
            STATE["yt_count"] = STATE.get("yt_count", 0) + 1
            YT_POSTED.append(yp.get("video"))
            save_state()

print("RESULT", json.dumps(results, ensure_ascii=False))
# exit 1 は「試行したのに全失敗」の本物の障害だけ(=誤アラーム排除)。
# 全クールダウン/上限=results空=正常な見送り→exit 0。一部失敗は許容(他は投稿済)。
if results and ok_count == 0:
    print("ALERT: 全投稿試行が失敗")
    sys.exit(1)
if not results:
    print("no-op: 全動画クールダウン/上限=正常な見送り")
