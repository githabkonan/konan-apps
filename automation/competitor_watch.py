#!/usr/bin/env python3
"""competitor_watch.py — 競合デベロッパーの新作/変化を検知(トークン0・cron用)。
2026-07-15 RUMAHSAKU CORP.(教育アプリ量産・203本/12ヶ月)が自衛官採用系に無料+IAP¥800で参入した事件を受けて新設。
検知: 監視デベロッパーの (1)新アプリ (2)アプリ名に危険語(昇任/陸曹/海曹/空曹/予備自 等) (3)評価数の急増。
出力: state差分を claude-tools/autonomous/competitor_state.json に保存、危険検知は stdout + inbox/alerts.md に追記。
GitHub Actions(metrics.ymlに同居)で毎日1回実行=PC状態と無関係・トークン0。
"""
import json, os, urllib.request, urllib.parse, datetime

WATCH_ARTISTS = {
    "1828221168": "RUMAHSAKU CORP.",
}
DANGER_WORDS = ["昇任", "陸曹", "海曹", "空曹", "予備自", "幹部候補", "消防設備士", "QC検定", "品質管理"]
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "competitor_state.json")
ALERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "competitor_alerts.md")

def lookup_artist(aid):
    u = f"https://itunes.apple.com/jp/lookup?id={aid}&entity=software&limit=200"
    d = json.loads(urllib.request.urlopen(u, timeout=30).read())
    return [r for r in d.get("results", []) if r.get("wrapperType") == "software"]

def main():
    prev = {}
    if os.path.exists(STATE):
        try: prev = json.load(open(STATE))
        except Exception: pass
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    state = {"ts": now, "artists": {}}
    alerts = []
    for aid, name in WATCH_ARTISTS.items():
        apps = lookup_artist(aid)
        cur = {str(a["trackId"]): {"name": a["trackName"], "price": a.get("formattedPrice"),
               "ratings": a.get("userRatingCount", 0)} for a in apps}
        state["artists"][aid] = {"name": name, "count": len(cur), "apps": cur}
        old = prev.get("artists", {}).get(aid, {}).get("apps", {})
        for tid, a in cur.items():
            if tid not in old:
                danger = [w for w in DANGER_WORDS if w in a["name"]]
                mark = " 🔴危険語:" + ",".join(danger) if danger else ""
                alerts.append(f"[{now}] {name} 新作: {a['name']} ({a['price']}){mark}")
            elif old[tid].get("ratings", 0) + 10 <= a["ratings"]:
                alerts.append(f"[{now}] {name} 評価急増: {a['name']} {old[tid]['ratings']}→{a['ratings']}件")
    json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
    if alerts and prev:  # 初回実行(prev空)はベースライン取得のみ
        with open(ALERTS, "a") as f:
            f.write("\n".join(alerts) + "\n")
        print("\n".join(alerts))
    else:
        total = sum(v["count"] for v in state["artists"].values())
        print(f"watch ok: {total} apps tracked, no alerts")

if __name__ == "__main__":
    main()
