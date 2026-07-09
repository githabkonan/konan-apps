#!/usr/bin/env python3
"""metrics_cloud.py — GitHub Actions上で動く日次メトリクス収集(Mac非依存・スリープ無縁)。
IG/Threads(env secrets)+YouTube(yt-dlp公開統計)を集計し metrics_log.jsonl に1行追記。
非バイナリ・diff可能・公開repoに置いても中身はviews数のみ(機密なし)。
毎日1回だけ実行(呼び出し側workflowが日次cron)。"""
import json, os, subprocess, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "metrics_log.jsonl")
QUEUE = os.path.join(HERE, "post_queue.json")
now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
today = now.date().isoformat()

def get(url):
    return json.load(urllib.request.urlopen(url, timeout=45))

def classify(text):
    try: q = json.load(open(QUEUE))["posts"]
    except Exception: q = []
    for p in q:
        for key in ("ig_caption", "threads_text"):
            head = (p.get(key) or "")[:20]
            if head and head in (text or ""):
                vt = "news" if ("時事" in p["app"] or "news" in p.get("video","")) else ("aruaru" if p.get("video","").endswith("_b.mp4") else "v2")
                return p["app"], vt
    t = text or ""
    if "クマ" in t or "狩猟" in t: return "狩猟テスト", "news"
    if "散財" in t or "10億" in t: return "散財RPG", "game"
    if any(k in t for k in ("自衛官","陸曹","幹部","予備自")): return "自衛官系", "unknown"
    if "QC検定2級" in t: return "QC検定2級B", "aruaru"
    if "QC検定" in t: return "QC3系", "unknown"
    if any(k in t for k in ("消防","乙6","甲4")): return "消防系", "unknown"
    return "不明", "unknown"

rows = []  # (platform, app, vtype, views, likes)

# Instagram
try:
    tok = os.environ["IG_TOKEN"]; uid = os.environ.get("IG_USER_ID", "17841446263440293")
    r = get(f"https://graph.instagram.com/v21.0/{uid}/media?fields=id,caption&limit=50&access_token={tok}")
    for m in r.get("data", []):
        try:
            ins = get(f"https://graph.instagram.com/v21.0/{m['id']}/insights?metric=views,likes,comments&access_token={tok}")
            v = {d["name"]: d["values"][0]["value"] for d in ins["data"]}
            app, vt = classify(m.get("caption",""))
            rows.append(("instagram", app, vt, v.get("views",0), v.get("likes",0)))
        except Exception: pass
except Exception as e: print("IG ERR", str(e)[:100])

# Threads
try:
    tok = os.environ["THREADS_ACCESS_TOKEN"]; uid = os.environ.get("THREADS_USER_ID", "27055021977524299")
    r = get(f"https://graph.threads.net/v1.0/{uid}/threads?fields=id,text&limit=50&access_token={tok}")
    for m in r.get("data", []):
        try:
            ins = get(f"https://graph.threads.net/v1.0/{m['id']}/insights?metric=views,likes&access_token={tok}")
            v = {d["name"]: d.get("values",[{}])[0].get("value",0) for d in ins["data"]}
            app, vt = classify(m.get("text",""))
            rows.append(("threads", app, vt, v.get("views",0), v.get("likes",0)))
        except Exception: pass
except Exception as e: print("Threads ERR", str(e)[:100])

# YouTube (yt-dlp public stats, no auth)
try:
    r = subprocess.run(["yt-dlp","--flat-playlist","-J","https://www.youtube.com/@tyokobisakusaku/shorts"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode == 0:
        d = json.loads(r.stdout)
        for e in (d.get("entries") or []):
            app, _ = classify(e.get("title",""))
            rows.append(("youtube", app, "unknown", e.get("view_count") or 0, e.get("like_count") or 0))
except Exception as e: print("YT note:", str(e)[:100])

# aggregate
def agg(keyfn):
    out = {}
    for plat, app, vt, views, likes in rows:
        k = keyfn(plat, app, vt)
        o = out.setdefault(k, {"n":0,"views":0,"likes":0})
        o["n"] += 1; o["views"] += views; o["likes"] += likes
    return out

summary = {
    "date": today,
    "total": {"media": len(rows), "views": sum(r[3] for r in rows), "likes": sum(r[4] for r in rows)},
    "by_platform": agg(lambda p,a,v: p),
    "by_type": agg(lambda p,a,v: f"{v}/{p}"),
    "by_app": agg(lambda p,a,v: a),
    "yt_top": sorted([{"app":a,"views":vi} for pl,a,vt,vi,li in rows if pl=="youtube"], key=lambda x:-x["views"])[:5],
}
with open(LOG, "a") as f:
    f.write(json.dumps(summary, ensure_ascii=False) + "\n")
print(f"{today}: {len(rows)} media -> total {summary['total']['views']} views. appended to metrics_log.jsonl")
