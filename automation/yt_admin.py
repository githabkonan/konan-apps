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


PR_TAG = "#PR"
# 全角・半角のゆらぎで既存の PR 付き動画に二重付与しないよう両方を検知する
PR_TAG_ALTS = ("#PR", "＃PR", "#Pr", "#pr", "＃Pr", "＃pr")


def _has_pr(title):
    return any(t in title for t in PR_TAG_ALTS)


def _video_snippet(tok, vid):
    """videos.update は snippet の必須項目(title/categoryId)を含めて送る必要があるので現行値を取得する。"""
    d = _get(f"{API}/videos", tok, part="snippet", id=vid)
    items = d.get("items", [])
    return items[0]["snippet"] if items else None


def set_title(tok, vid, new_title):
    """タイトルだけを書き換える。categoryId など他の必須項目は現行値を保持。"""
    sn = _video_snippet(tok, vid)
    if not sn:
        return None
    sn["title"] = new_title[:100]
    body = json.dumps({"id": vid, "snippet": sn}).encode()
    req = urllib.request.Request(f"{API}/videos?part=snippet", data=body, method="PUT",
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json; charset=UTF-8"})
    return json.load(urllib.request.urlopen(req, timeout=60))["snippet"]["title"]


def _title_with_pr(title):
    """既存タイトルに ' #PR' を足す(100字制限内、全角/半角どちらかで既に含まれていればそのまま)。"""
    if _has_pr(title):
        return title
    if len(title) > 96:
        return title[:96] + " " + PR_TAG
    return title + " " + PR_TAG


def apply_pr_bulk(tok, videos, dry=True, limit=None):
    """タイトルに #PR が無い動画に一括で追加。dry=True は変更対象の列挙のみ。
    limit で件数を絞る(クォータ管理)。1件 videos.update = 50 unit + videos.list = 1 unit。
    """
    targets = [v for v in videos if not _has_pr(v["title"])]
    if limit:
        targets = targets[:limit]
    print(f"対象: {len(targets)}本(全 {len(videos)} 中、既に #PR 済みは除外)")
    if dry:
        for v in targets[:5]:
            print(f"  DRY {v['id']}: {v['title'][:50]}  →  {_title_with_pr(v['title'])[:60]}")
        if len(targets) > 5:
            print(f"  … 他 {len(targets)-5} 本")
        return 0, 0, 0, len(targets)
    updated, failed = 0, 0
    for i, v in enumerate(targets, 1):
        new = _title_with_pr(v["title"])
        try:
            set_title(tok, v["id"], new)
            updated += 1
            print(f"  [{i}/{len(targets)}] OK {v['id']}: +#PR")
        except Exception as e:
            failed += 1
            body = getattr(e, "read", lambda: b"")()
            msg = body[:300].decode("utf-8", "replace") if body else ""
            print(f"  [{i}/{len(targets)}] FAIL {v['id']}: {e} {msg}")
            # クォータ超過 (quotaExceeded) は即座に打ち切る
            if "quotaExceeded" in msg or "rateLimitExceeded" in msg:
                print(f"  → クォータ超過で中断({updated} 本更新済み、残 {len(targets) - i} 本)")
                return updated, failed, len(targets) - i, len(targets)
    return updated, failed, 0, len(targets)


def main(argv):
    apply = "--apply" in argv
    apply_pr = "--apply-pr" in argv
    dry_pr = "--dry-pr" in argv
    pr_limit = None
    for a in argv:
        if a.startswith("--pr-limit="):
            try:
                pr_limit = int(a.split("=", 1)[1])
            except ValueError:
                pass
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

    # 【2026-09-27 F-413】景表法対策: タイトルに #PR を一括追加(--dry-pr で確認、--apply-pr で実行)
    if dry_pr or apply_pr:
        if apply_pr and not can_edit:
            print("NG 権限不足: --apply-pr には youtube.force-ssl 必要")
            return 2
        u, f, remain, total = apply_pr_bulk(tok, vids, dry=not apply_pr, limit=pr_limit)
        if apply_pr:
            print(f"\n=== #PR 一括追加 完了: 更新 {u} / 失敗 {f} / 残 {remain} / 対象 {total} ===")
        return 0 if f == 0 else 1

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
