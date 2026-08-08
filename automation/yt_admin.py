#!/usr/bin/env python3
"""yt_admin.py — 公開済みYouTube動画の是正ツール(2026-08-07 F-409 で新設)

きっかけ: ¥3,000 の「自衛官陸曹昇任試験対策」を「無料でダウンロードできる」と紹介する
Shorts を公開していた(konan 指摘)。配信ラインを直しても**もう公開されている嘘は消えない**ので、
公開済みを機械で洗って落とす手段が要る。

やること:
  1. チャンネルのアップロード一覧を全件取得
  2. 説明文から App Store の id を拾い、**実価格を App Store に照会**
  3. 有料アプリなのに「無料」と言っている動画を検出
  4. --apply を付けた時だけ privacyStatus=private にする(削除はしない=取り消せる)

使い方:
  python3 automation/yt_admin.py                 # 検出のみ(既定/GitHub Actions)
  python3 automation/yt_admin.py --local         # Macのcredentials/youtube.jsonで実行
  python3 automation/yt_admin.py --apply         # 非公開化を実行
  python3 automation/yt_admin.py --apply --video-ids abc123,def456   # 指定IDだけ非公開化
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

FREE_WORD = re.compile(r"無料|タダ|0円|ゼロ円|\bfree\b", re.I)

# 【2026-08-08】価格の嘘だけでなく、konan が禁止した「試験系自己啓発」トーンも公開済みから洗う。
# 「あくまでアプリ紹介。こんなアプリあるよ!って知ってもらうだけでいい」(2026-08-05 konan)
HYPE_WORD = re.compile(
    r"差(はここで開く|がついてき|が開く)|締切まで(時間がない|あと|残り)|試験まであと\s*\d"
    r"|今(動かないと|やらないと|始めないと)|動かす側|見送る側|合格まで(あと|残り)")
APP_ID = re.compile(r"/id(\d+)")
API = "https://www.googleapis.com/youtube/v3"


def _get(url, tok, **params):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"Authorization": f"Bearer {tok}"})
    return json.load(urllib.request.urlopen(req, timeout=60))


LOCAL_CRED = "/Users/konan/claude-tools/marketing/auto-post/credentials/youtube.json"


def access_token(local=False):
    """--local ならMac上の credentials/youtube.json を使う(GitHub Actions外で回すため)。"""
    if local:
        c = json.load(open(LOCAL_CRED))
        cid, sec, ref = c["client_id"], c["client_secret"], c["refresh_token"]
    else:
        cid, sec, ref = os.environ["YT_CLIENT_ID"], os.environ["YT_CLIENT_SECRET"], os.environ["YT_REFRESH_TOKEN"]
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                   "refresh_token": ref, "grant_type": "refresh_token"}).encode()
    return json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))["access_token"]


def token_scopes(tok):
    """権限不足を「実行して失敗」でなく先に言う。videos.update には youtube / youtube.force-ssl が要る。"""
    try:
        d = json.load(urllib.request.urlopen(
            f"https://oauth2.googleapis.com/tokeninfo?access_token={tok}", timeout=30))
        return d.get("scope", "").split()
    except Exception as e:
        print(f"WARN scope確認に失敗: {e}")
        return []


def all_uploads(tok):
    ch = _get(f"{API}/channels", tok, part="contentDetails", mine="true")
    pl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    out, page = [], None
    while True:
        kw = {"part": "snippet", "playlistId": pl, "maxResults": 50}
        if page:
            kw["pageToken"] = page
        d = _get(f"{API}/playlistItems", tok, **kw)
        for it in d.get("items", []):
            sn = it["snippet"]
            out.append({"id": sn["resourceId"]["videoId"], "title": sn["title"],
                        "desc": sn.get("description", ""), "at": sn.get("publishedAt")})
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def prices(app_ids):
    out, ids = {}, sorted(set(app_ids))
    for i in range(0, len(ids), 10):
        url = f"https://itunes.apple.com/lookup?id={','.join(ids[i:i + 10])}&country=jp"
        try:
            d = json.load(urllib.request.urlopen(url, timeout=20))
        except Exception as e:
            print(f"WARN 価格照会失敗: {e}")
            continue
        for r in d.get("results", []):
            out[str(r["trackId"])] = {"price": r.get("price"), "label": r.get("formattedPrice"),
                                      "name": r.get("trackName")}
    return out


def set_private(tok, vid):
    body = json.dumps({"id": vid, "status": {"privacyStatus": "private"}}).encode()
    req = urllib.request.Request(f"{API}/videos?part=status", data=body, method="PUT",
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json; charset=UTF-8"})
    return json.load(urllib.request.urlopen(req, timeout=60))["status"]["privacyStatus"]


def main(argv):
    apply = "--apply" in argv
    forced = []
    for a in argv:
        if a.startswith("--video-ids="):
            forced = [x for x in a.split("=", 1)[1].split(",") if x]

    tok = access_token(local="--local" in argv)
    scopes = token_scopes(tok)
    can_edit = any(s.endswith("/auth/youtube") or s.endswith("/auth/youtube.force-ssl")
                   or s.endswith("/auth/youtubepartner") for s in scopes)
    print("SCOPES:", " ".join(scopes) or "(取得できず)")
    can_read = can_edit or any(s.endswith("/auth/youtube.readonly") for s in scopes)
    if not can_read:
        print("NG 権限不足: このトークンは youtube.upload だけで、公開済み動画を読むことも編集することもできない。")
        print("   → 1回だけ同意し直せば直る:")
        print("      python3 /Users/konan/claude-tools/marketing/auto-post/yt_oauth_upgrade.py")
        return 2
    if apply and not can_edit:
        print("NG 権限不足: videos.update には youtube.force-ssl が要る(今は無い)。")
        print("   → python3 /Users/konan/claude-tools/marketing/auto-post/yt_oauth_upgrade.py")
        return 2

    vids = all_uploads(tok)
    print(f"アップロード総数: {len(vids)}")
    pr = prices([m.group(1) for v in vids for m in [APP_ID.search(v["desc"])] if m])

    bad = []
    for v in vids:
        if forced:
            if v["id"] in forced:
                bad.append((v, "指定"))
            continue
        mh = HYPE_WORD.search(v["title"] + "\n" + v["desc"])
        if mh:
            bad.append((v, f"煽りトーン「{mh.group(0)}」— アプリ紹介に徹する(2026-08-05 konan明言)"))
            continue
        m = APP_ID.search(v["desc"])
        if not m:
            continue
        info = pr.get(m.group(1))
        if not info or not (info.get("price") or 0) > 0:
            continue
        if FREE_WORD.search(v["title"] + "\n" + v["desc"]):
            bad.append((v, f"{info['name']} は {info['label']} なのに「無料」"))

    if not bad:
        print("OK 価格の嘘は見つからなかった")
        return 0

    print(f"\n=== 是正対象 {len(bad)}本 ===")
    for v, why in bad:
        print(f"  https://youtube.com/shorts/{v['id']}  {v['at'][:10]}  {v['title'][:40]}")
        print(f"    理由: {why}")

    if not apply:
        print("\n(検出のみ。実行するには --apply)")
        return 1

    for v, _ in bad:
        try:
            st = set_private(tok, v["id"])
            print(f"  非公開化 OK {v['id']} → {st}")
        except Exception as e:
            body = getattr(e, "read", lambda: b"")()
            print(f"  非公開化 FAIL {v['id']}: {e} {body[:300].decode('utf-8', 'replace')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
