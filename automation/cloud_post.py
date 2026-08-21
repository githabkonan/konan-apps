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

# 【2026-08-12】queue_lint が NG と判定した投稿だけを配信から外す。
# 以前は queue_lint が exit 1 でワークフローごと落としており、
# **煽り構文を含む1本のせいで全チャンネルの配信が16時間半止まった**。
# 不良は隔離して、健全な在庫は流す。
_bad = set()
for _qf in (os.path.join(HERE, "quarantine_lint.json"),
            os.path.join(HERE, "quarantine_media.json"),
            # 【2026-08-12 konan指摘】題材からアプリへ話が飛んでいる動画。
            # 「台湾軍が橋を封鎖した→陸曹昇任試験のアプリがある」で公開してしまい、
            # konan が限定公開に落として処置した。直したものから外していく。
            os.path.join(HERE, "quarantine_flow.json"),
            # 【2026-08-13】映像に焼き込まれた文字(テロップ・CTA)の禁止語。
            # JSONのキャプションを直しても映像は直らないので、OCRで別途見る。
            # 生成: claude-tools/scripts/video_text_audit.py
            os.path.join(HERE, "quarantine_video_text.json"),
            # 【2026-08-13】テロップと背景の映像が別の話をしている動画、
            # および同じロットの中で使い回された素材。
            # 「レーダーを動かすのが空曹だ」の後ろがカフェの店内、で公開しかけた。
            # 生成: claude-tools/scripts/scene_match_gate.py
            os.path.join(HERE, "quarantine_scene.json"),
            # 【2026-08-13】事実として間違っている動画。機械では見つからないので手で書く。
            # 例: 「コンビニで一番聞く英語は手荷物の確認」— コンビニで手荷物確認はしない。
            os.path.join(HERE, "quarantine_fact.json")):
    if os.path.exists(_qf):
        try:
            _bad |= set(json.load(open(_qf)))
        except Exception as e:
            print(f"WARN {os.path.basename(_qf)} を読めない({e})")
if _bad:
    try:
        _before = len(POSTS)
        POSTS = [p for p in POSTS if p.get("video") not in _bad]
        if len(POSTS) != _before:
            print(f"🚧 隔離により {_before - len(POSTS)}本を配信から除外(残 {len(POSTS)}本)")
    except Exception as e:
        print(f"WARN quarantine.json を読めない({e}) — 隔離なしで続行")


# 【2026-08-21 konan 指摘】「ショートスリーパーのやつはアプリが公開されるまであげなくていい
# ゆうたやんけ、何勝手にあげてんの」= まだ App Store に無いアプリの宣伝動画を2本公開していた。
# 見た人が検索しても何も出ない=集客にならず、チャンネルの信用だけ削る。
# 文章のルールでは止まらないので、配信の直前にストアへ実在を照会して落とす。
# 判定できなかった時(通信断)は落とさない — 1本の不明で配信全体を止めない
# ([[feedback_gates_must_quarantine_not_halt]])。
def _live_app_ids(posts):
    ids = sorted({m.group(1) for p in posts
                  for m in [re.search(r"/id(\d+)", p.get("appstore_url") or "")] if m})
    live, unknown = set(), False
    for i in range(0, len(ids), 10):
        chunk = ids[i:i + 10]
        try:
            d = json.load(urllib.request.urlopen(
                f"https://itunes.apple.com/lookup?id={','.join(chunk)}&country=jp", timeout=20))
            live |= {str(r["trackId"]) for r in d.get("results", [])}
        except Exception as e:
            print(f"WARN ストア照会失敗({str(e)[:60]}) → この分は未判定として通す")
            live |= set(chunk)
            unknown = True
    return live, unknown


try:
    _live, _ = _live_app_ids(POSTS)
    _unpub = [p for p in POSTS
              if not re.search(r"/id(\d+)", p.get("appstore_url") or "")
              or re.search(r"/id(\d+)", p["appstore_url"]).group(1) not in _live]
    if _unpub:
        for p in _unpub[:10]:
            print(f"  ⛔ 未公開アプリ: {p.get('app')} / {p.get('video')}")
        POSTS = [p for p in POSTS if p not in _unpub]
        print(f"⛔ 未公開アプリの宣伝 {len(_unpub)}本を配信から除外(残 {len(POSTS)}本)")
except Exception as e:
    print(f"WARN 未公開アプリ判定に失敗({str(e)[:80]}) — 判定なしで続行")

N = len(POSTS)

# 2026-07-20: 加重値は weights.json(gen_marketing_weights.py が直近30日のASC実売上から毎日再計算しpush)を読む。
# 未生成時のフォールバック=2026-07-19時点の手動集計。未提出の新規ローンチ(URL無し)=2(露出優先)/ ゼロ課金でも1(noise一発でapp切りしない)
try:
    REVENUE_WEIGHT = json.load(open(os.path.join(HERE, "weights.json")))
except Exception:
    REVENUE_WEIGHT = {"6774074604": 5, "6778490302": 3, "6776236258": 2}
# 【2026-08-08 konan 明言】「この八本は確実にマーケよろしく特にようつべ」
# 全部が有料アプリ=売上に直結する本命。ASCの実売上がまだ小さくても YouTube 枠では最優先で回す。
# weights.json は毎日 ASC 実績から再生成されるので、そこに書くと翌日消える。
# **消えない場所(=消費側)に下限として置く。**
KONAN_PRIORITY = {
    "6774074604": "自衛官陸曹昇任試験対策",
    "6772919770": "自衛官入隊試験対策",
    "6776236258": "自衛官一般幹部候補生試験対策",
    "6778490302": "予備自衛官補 採用試験対策",
    "6789518576": "自衛官海曹昇任試験対策",
    "6789531149": "自衛官空曹昇任試験対策",
    "6793729335": "ミリタリー英語トレーナー",
    "6793410091": "韓国語脳トレーナー",
}
PRIORITY_FLOOR = 5  # ROTATION_WEIGHTED の最大パス数=ローテ内に5回出る


def _app_id(p):
    m = re.search(r"id(\d+)", p.get("appstore_url") or "")
    return m.group(1) if m else ""


def _weight(p):
    url = p.get("appstore_url") or ""
    if not url:
        return 2
    m = re.search(r"id(\d+)", url)
    aid = m.group(1) if m else ""
    w = REVENUE_WEIGHT.get(aid, 1)
    if aid in KONAN_PRIORITY:
        return max(w, PRIORITY_FLOOR)  # 実績が下がっても優先は落とさない
    return w

# 加重ローテ表: pass1=全post1回ずつ、pass2以降は重み>=passの投稿だけ追加(高稼働アプリほど登場回数が増える)
# 【2026-08-06 konan指示】プラットフォームで役割を分ける。
#  - IG / Threads = 枠が多いので「偏らずいろんなアプリを紹介する」= 売上加重をかけず全アプリ均等
#  - YouTube      = 枠が少ないので「伸びてる/DLされてるアプリに厳選」= 売上加重を効かせる
ROTATION_WEIGHTED = [i for _pass in range(1, 6) for i, p in enumerate(POSTS) if _weight(p) >= _pass]
ROTATION_FLAT = list(range(len(POSTS)))
ROTATIONS = {"instagram": ROTATION_FLAT, "threads": ROTATION_FLAT, "youtube": ROTATION_WEIGHTED}

now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)  # JST
day_num = (now.date() - datetime.date(2026, 1, 1)).days
seq = day_num * 24 + now.hour

# 【2026-08-06 konan指示】投稿時刻を戦略化する。平日は生活動線のピーク(朝7/昼12/夕18-20)に厚く寄せ、
# 谷の時間帯は投げない。休日は終日ばらけさせる。
# cron 自体は毎時のまま(GitHubのスケジューラは20-50分遅延するため、cronを絞ると枠が丸ごと消える既知の事故がある)。
# 絞るのは「起動する時刻」ではなく「その起動で何本流すか」。
_PRIME = {7, 12, 18, 19, 20}      # 平日のピーク
_SUB = {8, 21, 22}                # 平日の準ピーク
# 【2026-08-12 konan 指摘】「今世間は夏季休暇の連休中」。
# 曜日だけで平日/休日を決めると、お盆や年末年始に**実態と真逆の配信**になる。
# 連休中は水曜でも生活動線は休日型(終日ばらける)なので、休日扱いにする。
_HOLIDAY_RANGES = [
    ("2026-08-08", "2026-08-16"),   # お盆(夏季休暇)
    ("2026-12-27", "2027-01-04"),   # 年末年始
    ("2027-04-29", "2027-05-06"),   # GW
]


def _is_holiday_season():
    d = now.date().isoformat()
    return any(a <= d <= b for a, b in _HOLIDAY_RANGES)


def _per_run_default():
    if now.weekday() >= 5 or _is_holiday_season():   # 土日・連休=終日ばらけさせる
        return 1 if 6 <= now.hour <= 23 else 0
    if now.hour in _PRIME: return 3
    if now.hour in _SUB:   return 2
    return 0                      # 平日の谷は投げない(IG 25本/日の上限内に収める)
# 平日の想定本数 = 3本×5枠 + 2本×3枠 = 21本/日(IG上限25に余白4)
# 【2026-08-12・F-418】ピーク枠を落とした日は、その分が丸ごと失われていた。
# 8/11 22:10 を最後に配信が16時間半止まり、復旧後も「今は谷だから0本」で
# **一日分が消えたまま**だった。YouTube には取り返す仕組み(F-410 ペース追従)があるのに
# IG/Threads には無かった。同じものを入れる。
_DAILY_TARGET = 18 if now.weekday() >= 5 else 21   # _per_run_default() の想定合計
_CATCHUP_MAX = int(os.environ.get("SOCIAL_CATCHUP_MAX", "3"))
_WIN_S, _WIN_E = 7, 22                              # 投稿する時間帯(JST)


def _today_count(platform):
    """今日その媒体に何本出したか。hist(動画→最終使用時刻)から数える。

    ※ グローバル STATE はこの位置より後(250行目付近)で定義されるため参照できない。
      ここで state.json を直接読む。**STATE を使うと NameError で配信ライン全体が落ちる。**
    """
    try:
        _st = json.load(open(os.path.join(HERE, "state.json")))
    except Exception:
        return 0
    d = (_st.get("hist") or {}).get(platform, {})
    today = now.date().isoformat()
    return sum(1 for v in d.values() if str(v)[:10] == today)


def _catchup(platform, base):
    """今の時刻なら何本出ているべきか。遅れていれば谷でも取り返す。"""
    if not (_WIN_S <= now.hour <= _WIN_E):
        return base
    span = (_WIN_E + 1 - _WIN_S) * 60
    elapsed = max(0, min(span, (now.hour - _WIN_S) * 60 + now.minute))
    should = -(-_DAILY_TARGET * elapsed // span)          # 切り上げ
    behind = should - _today_count(platform)
    if behind <= 0:
        return base
    n = max(base, min(behind, _CATCHUP_MAX))
    if n > base:
        print(f"  {platform}: ペース {_today_count(platform)}/{should}本 → {n}本で取り返す")
    return n


THREADS_PER_RUN = int(os.environ.get("THREADS_PER_RUN") or _catchup("threads", _per_run_default()))
IG_PER_RUN = int(os.environ.get("IG_PER_RUN") or _catchup("instagram", _per_run_default()))

# 【F-412 / 2026-08-13】Threads は7/30以降に4件をスパム削除されて 8/12 に完全停止した。
# 削除されたのは1日21本想定で同型を投げていた頃のもの。形式(テキスト)は konan 指示どおり戻し、本数を絞った。
# 【2026-08-15】6本/日を3日間回して削除は再発せず。ただし _catchup が窓の頭で上限を食い切り、
# 6本すべてが14時までに固まって以降10時間無投稿になっていた(konan 指摘「全然投稿されてなかった」)。
# 上限を12本へ上げたうえで、窓の経過時間に比例した本数までしか解禁しない。前倒しの固め打ちを構造的に止める。
THREADS_MAX_PER_DAY = int(os.environ.get("THREADS_MAX_PER_DAY", "12"))
_th_today = _today_count("threads")
if _WIN_S <= now.hour <= _WIN_E:
    _th_span = (_WIN_E + 1 - _WIN_S) * 60
    _th_elapsed = max(0, min(_th_span, (now.hour - _WIN_S) * 60 + now.minute))
    _th_unlocked = -(-THREADS_MAX_PER_DAY * _th_elapsed // _th_span)
else:
    _th_unlocked = 0
# 【2026-08-21 konan「スレッドも投稿ペース遅い。改善しろ」】1ラン1本固定だとランの間引き(GitHub cron遅延)で
# 解禁ペースに追いつけない。遅れ2本以上なら1ランで2本まで挽回(45秒間隔は既存)。日次12・段階解禁は維持
_th_behind = max(0, min(THREADS_MAX_PER_DAY, _th_unlocked) - _th_today)
THREADS_PER_RUN = min(THREADS_PER_RUN, (2 if _th_behind >= 2 else 1), _th_behind)
# 【2026-07-29】IGが Media Publish Limit Exceeded で全滅した事故を受けて、勘で本数を決めるのをやめる。
# IG Graph API の content_publishing_limit を毎回叩いて「実際の残枠」を取得し、余白を残して埋める(=ギリギリを攻める)。
def _get(url, params):
    return json.load(urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=60))

IG_SAFETY_MARGIN = int(os.environ.get("IG_SAFETY_MARGIN", "5"))  # 上限に対して常にこれだけ残す

def ig_quota():
    """(使用済, 上限) を返す。取得失敗時は (None, None)"""
    try:
        ig = os.environ["IG_USER_ID"]; tok = os.environ["IG_TOKEN"]
        d = _get(f"https://graph.instagram.com/v21.0/{ig}/content_publishing_limit",
                 {"fields": "config,quota_usage", "access_token": tok})
        row = d["data"][0]
        return int(row.get("quota_usage", 0)), int(row.get("config", {}).get("quota_total", 50))
    except Exception as e:
        print(f"  ig quota取得失敗({str(e)[:60]}) → 保守的に1本のみ")
        return None, None

_used, _cap = ig_quota()
if _used is not None:
    _room = max(0, _cap - _used - IG_SAFETY_MARGIN)
    IG_PER_RUN = min(IG_PER_RUN, _room)
    print(f"  ig quota: {_used}/{_cap} 使用済 → 今回投稿可能 {IG_PER_RUN}本(安全余白{IG_SAFETY_MARGIN})")
else:
    IG_PER_RUN = min(IG_PER_RUN, 1)
print(f"[{now.isoformat()}] seq={seq} threads/run={THREADS_PER_RUN} ig/run={IG_PER_RUN}")


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=120))




def threads_text(post):
    """Threads本文。文字 + App Store の URL だけ。

    【2026-08-13 konan再指示】「スレッドは文字の投稿とアップストアのURLだけでいい。
    昔も同じ指摘したと思う」— 実際 2026-06-29 に同じ指示を受けている(このファイル冒頭)。
    F-412(スパム削除)の対策として動画つき+リンク削除に作り替えたのは指示に反していた。
    """
    return (post.get("threads_text") or "").strip()[:500]


def publish_threads(post):
    """テキスト投稿(動画なし)。本文に App Store の URL を含める。"""
    uid = os.environ["THREADS_USER_ID"]; tok = os.environ["THREADS_ACCESS_TOKEN"]
    B = "https://graph.threads.net/v1.0"
    cid = _post(f"{B}/{uid}/threads", {"media_type": "TEXT",
                                       "text": threads_text(post),
                                       "access_token": tok})["id"]
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
    snip = {"title": title[:100], "description": desc[:4900], "categoryId": "27"}
    if post.get("yt_tags"):
        tags, n = [], 0
        for t in post["yt_tags"]:
            if n + len(t) > 480: break
            tags.append(t); n += len(t) + 1
        snip["tags"] = tags
    meta = json.dumps({"snippet": snip,
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
    # カスタムサムネ。チャンネル未確認だと403で落ちるが、動画自体は公開済みなので投稿は失敗させない。
    if post.get("yt_thumb"):
        try:
            img = urllib.request.urlopen(f"{BASE}/{post['yt_thumb']}", timeout=120).read()
            treq = urllib.request.Request(
                f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
                data=img, method="POST",
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"})
            urllib.request.urlopen(treq, timeout=180)
            print(f"  thumbnail set: {post['yt_thumb']}")
        except Exception as e:
            body = getattr(e, "read", lambda: b"")()
            print(f"  THUMBNAIL FAILED (動画は公開済み): {str(e)[:120]} "
                  f"{body[:200].decode('utf-8', 'replace') if body else ''}")
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
    """start_idxから順にローテ表を辿り、クールダウン明けの動画を探す。全滅ならNone(=見送り)。
    ローテ表はプラットフォーム別(IG/Threads=均等・YouTube=売上加重)。"""
    rot = ROTATIONS.get(platform, ROTATION_WEIGHTED)
    R = len(rot)
    for k in range(R):
        p = POSTS[rot[(start_idx + k) % R]]
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
# 【2026-08-21 konan指示】新クォータ(1回=1pt・100/日)確認済みにつき24本/日へ。
# ただしYouTubeのスパム量産検知は別問題なので、多様化ルール(1アプリ2本まで・角度分散)を前提とする
YT_MAX_PER_DAY = int(os.environ.get("YT_MAX_PER_DAY", "24"))
# 【F-410・2026-08-07 konan「今日youtubeで3本しか動画が上がってない。なぜ?」】
# 原因は「1ラン=最大1本 × GitHub cron が落ちる」の掛け算。
# schedule は毎時のはずが実測7回/11回しか発火せず(00,03,04,06,06,08,10 UTC)、
# さらに固定75分ギャップで発火したランまで空振りし、12本/日の目標に対し実績5本だった。
# → **ペース追従方式**に変更。今が1日の何%かで「今あるべき本数」を出し、
#   不足していればそのランで最大 YT_CATCHUP_MAX 本まで連続投稿して取り戻す。
#   これなら cron が何回落ちても、次に生きているランが遅れを吸収する。
YT_WIN_START, YT_WIN_END = 6, 23          # 投稿する時間帯(JST)
YT_CATCHUP_MAX = int(os.environ.get("YT_CATCHUP_MAX", "3"))  # 1ランで取り返す上限
today = now.date().isoformat()
if STATE.get("yt_date") != today:
    STATE["yt_date"] = today; STATE["yt_count"] = 0; STATE["last_yt_seq"] = None


def _yt_pace_target():
    """今の時刻なら何本上がっているべきか(6:00-23:59 に YT_MAX_PER_DAY 本を均等配分)。"""
    span = (YT_WIN_END + 1 - YT_WIN_START) * 60
    elapsed = (now.hour - YT_WIN_START) * 60 + now.minute
    elapsed = max(0, min(span, elapsed))
    return min(YT_MAX_PER_DAY, -(-YT_MAX_PER_DAY * elapsed // span))  # 切り上げ


if os.environ.get("YT_REFRESH_TOKEN") and YT_WIN_START <= now.hour <= YT_WIN_END:
    _target = _yt_pace_target()
    _behind = _target - STATE.get("yt_count", 0)
    if _behind <= 0:
        print(f"  youtube: ペース内({STATE.get('yt_count',0)}/{_target}本)=今は見送り")
    else:
        _n = min(_behind, YT_CATCHUP_MAX)
        print(f"  youtube: ペース {STATE.get('yt_count',0)}/{_target}本 → {_n}本投稿して取り戻す")
        for _i in range(_n):
            # 【2026-08-06 konan指示】YTは枠が少ないので厳選する=売上加重ローテを辿る
            # (DLされてる/売れてるアプリほど登場回数が増える)。IG実績連動は指標取得を実装してから。
            # 【2026-08-08 konan 明言】「残り九本のうち八本はこの8本を出せ」
            # 加重ローテだけだと確率的にしか寄らない。**優先8本の未投稿があれば必ずそれを先に出す。**
            # 優先枠を使い切ってから、はじめて通常の加重ローテに落ちる。
            _R = len(ROTATION_WEIGHTED)
            yp = next((POSTS[ROTATION_WEIGHTED[(seq + k) % _R]] for k in range(_R)
                       if POSTS[ROTATION_WEIGHTED[(seq + k) % _R]].get("video") not in YT_POSTED
                       and _app_id(POSTS[ROTATION_WEIGHTED[(seq + k) % _R]]) in KONAN_PRIORITY), None)
            if yp is not None:
                print(f"  youtube: 優先枠 → {KONAN_PRIORITY[_app_id(yp)]}")
            else:
                yp = next((POSTS[ROTATION_WEIGHTED[(seq + k) % _R]] for k in range(_R)
                           if POSTS[ROTATION_WEIGHTED[(seq + k) % _R]].get("video") not in YT_POSTED), None)
            if yp is None:
                print("  youtube: 全動画投稿済み(重複再アップ回避)=新作待ち")
                break
            ok, val = with_retry(lambda p=yp: publish_youtube(p))
            results.append({"ch": "youtube", "app": yp.get("app"), "ok": ok, ("id" if ok else "err"): val})
            print(f"  youtube[{yp.get('app')}] ({STATE.get('yt_count',0)+1}/{YT_MAX_PER_DAY}): {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
            if not ok:
                break  # 連投で同じ失敗を繰り返さない(クォータ超過等)
            ok_count += 1
            STATE["last_yt_seq"] = seq
            STATE["last_yt_ts"] = now.isoformat()
            STATE["yt_count"] = STATE.get("yt_count", 0) + 1
            YT_POSTED.append(yp.get("video"))
            save_state()
            seq += 1  # 連投時に同じアプリが続かないようローテを進める

print("RESULT", json.dumps(results, ensure_ascii=False))
# exit 1 は「試行したのに全失敗」の本物の障害だけ(=誤アラーム排除)。
# 全クールダウン/上限=results空=正常な見送り→exit 0。一部失敗は許容(他は投稿済)。
if results and ok_count == 0:
    print("ALERT: 全投稿試行が失敗")
    sys.exit(1)
if not results:
    print("no-op: 全動画クールダウン/上限=正常な見送り")
    # 【2026-08-13 konan「なんかのバグでそもそも何も投稿されてないみたいな状況は2度と作るな」】
    # 見送りは1ランだけ見れば正常に見える。だが**一日を通して0本**なら、それは谷ではなく故障
    # (在庫の全隔離・ローテ表の空・クールダウンの計算ミス等)。8/11-12 の16時間半停止も
    # 誰も気づかないまま進んだ。昼を過ぎて0本なら失敗として鳴らす(=GitHubが通知を出す)。
    if now.hour >= 12 and all(_today_count(p) == 0 for p in ("instagram", "threads")):
        print("ALERT: 正午を過ぎて本日の投稿が0本 — 見送りではなく配信ラインの故障")
        sys.exit(1)
