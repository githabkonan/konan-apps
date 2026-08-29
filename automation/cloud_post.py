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

# 【2026-08-06 konan指示】プラットフォームで役割を分ける。
#  - IG / Threads = 枠が多いので「偏らずいろんなアプリを紹介する」= 売上加重をかけず全アプリ均等
#  - YouTube      = 枠が少ないので「伸びてる/DLされてるアプリに厳選」= 売上加重を効かせる
def _spread(idxs):
    """【2026-08-22 konan指摘】「なぜ同じアプリの投稿が3個あんの?」「陸曹が3つ立て続けに出されてる」。
    キューは工場がアプリごとにまとめて追記するので、並び順そのものがアプリの塊になっていた。
    ローテ表を素直に前から辿ると、1ランの中で同じアプリが3〜4本並ぶ。

    直し方: アプリごとに自分の投稿を 0〜1 の等間隔に置き、その位置で全体を並べ直す。
    57本あるアプリは6.2枠に1回、5本しかないアプリは71枠に1回、と全体に散らばる。
    塊はできないが、本数比は保たれる(在庫の多いアプリを捨てない)。"""
    by = {}
    for i in idxs:
        by.setdefault(_app_id(POSTS[i]), []).append(i)
    keyed = [((k + 0.5) / len(v), aid, i)
             for aid, v in by.items() for k, i in enumerate(v)]
    return [i for _pos, _aid, i in sorted(keyed)]


# 加重ローテ表: pass1=全post1回ずつ、pass2以降は重み>=passの投稿だけ追加(高稼働アプリほど登場回数が増える)
# 各パスの中を _spread でばらすので、加重(=登場回数の比)は保ったままアプリの塊が消える。
ROTATION_WEIGHTED = [i for _pass in range(1, 6)
                     for i in _spread([j for j, p in enumerate(POSTS) if _weight(p) >= _pass])]
ROTATION_FLAT = _spread(range(len(POSTS)))
ROTATIONS = {"instagram": ROTATION_WEIGHTED, "threads": ROTATION_FLAT, "youtube": ROTATION_WEIGHTED}  # IGも売上加重(2026-08-23)

now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)  # JST
day_num = (now.date() - datetime.date(2026, 1, 1)).days
seq = day_num * 24 + now.hour

# 【2026-08-22 konan指示】「インスタも100本上限なら24時間で100本出す設計にしろ。
# もちろんトラブルあった場合、元取ろうとしてスパム投稿はするな」。
#
# これ以前は平日ピーク(朝7/昼12/夕18-20)に厚く寄せて1日21本、谷は0本、という配分だった。
# 1日100本=毎時4〜5本になると「ピークに寄せる」意味が無くなる(どの時間も投げるので)ため廃止した。
# あわせて遅れの取り戻し(_catchup)も廃止。止まった直後にまとめ出しすると一番スパムらしく見える。
# 落ちたランのぶんは捨てる。これは Threads 側と同じ判断。
def _even_share(total, runs, i):
    """total 本を runs 回へ均等割りしたときの、i 回目の本数。合計はぴったり total になる。

    100本/24回なら 4,4,4,5,4,4,4,5,... と散る。切り上げ(=5固定)にすると
    日の前半で上限を食い切って後半が無投稿になるので、必ずこの形で割る。
    """
    return total * (i + 1) // runs - total * i // runs


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


# IG の公式上限は **100投稿 / 24時間の移動窓**(2026-08-22 に content_publishing_limit で実測。
# Meta のフィールド解説ページは50のまま古い)。カルーセルも1投稿として数える。
# 実際の天井は下の ig_quota() が毎回 API に聞いて守るので、ここは「均等に割る」だけの役目。
# 【2026-08-23 IG一次調査】Instagram Ranking Explained(公式)は「すでに投稿済みのリール」を表示抑制対象と明記、
# Community Guidelinesは反復投稿をスパム行為と明記。100/24hは技術上限であって安全量ではない。
# → 各動画1回限り(再投稿ローテ廃止)・1日12本・売れ筋優先(konan 8/23「絞るなら売れ筋トップ優先」)
# 【v4・2026-08-26 konan全面改修】最適投稿数調査(二次ソース)で IG Reels は1〜2本/日が最適、
# 3本超は既存投稿の露出を食い合う。物量24本/日は12倍過剰で自滅路線だった。
IG_MAX_PER_DAY = int(os.environ.get("IG_MAX_PER_DAY", "2"))
# 【2026-08-23 konan】利用上限中は動画を作れない → 新作在庫を火曜22時(YT_HORIZONと同じ)まで按分して切らさない
try:
    _ig_left = [p for p in POSTS if p.get("video") and p["video"] not in STATE.get("ig_posted", []) and p["video"] not in STATE.get("hist", {}).get("instagram", {})]
    _ig_days = -(-int((datetime.datetime.fromisoformat(os.environ.get("YT_HORIZON", "2026-09-01T22:00")) - now).total_seconds()) // 86400)
    if _ig_days > 0 and len(_ig_left) < IG_MAX_PER_DAY * _ig_days:
        IG_MAX_PER_DAY = max(1, min(IG_MAX_PER_DAY, -(-len(_ig_left) // _ig_days)))
except Exception:
    pass   # 2026-08-23 konan「本数は関係ない」→新作24本を全部1回ずつ(再投稿だけ廃止)
# 【2026-08-26 konan指示「時間も一番バズりやすい時間にしろ」】均等割りをやめ、バズりやすい枠だけに出す。
# 日本のIGリールの山は 7-8時 / 12-13時 / 20-21時(2026年調査・複数媒体一致)。アルゴリズムが初速を
# 評価する時間を確保するため「山の1〜2時間前に出す」が定石 → 山の1時間前に枠を置く。
# 2本/日なら 19時(夜の主戦場)と 11時(昼)。cronが落ちた枠は後続ランが日次上限の範囲で拾う
# (上限2本なので、まとめ出しでスパムに見える量にはならない)。
IG_HOUR_RANK = [19, 11, 20, 12, 7, 21, 8, 13, 18, 22, 10, 17, 9, 16, 23, 15, 14, 6]
IG_ACTIVE_HOURS = IG_HOUR_RANK[:max(0, IG_MAX_PER_DAY)]
_ig_today = _today_count("instagram")
_ig_slot_target = sum(1 for h in IG_ACTIVE_HOURS if now.hour >= h)
IG_PER_RUN = int(os.environ.get("IG_PER_RUN") or
                 max(0, min(_ig_slot_target, IG_MAX_PER_DAY) - _ig_today))

# 【F-412 / 2026-08-13】Threads は7/30以降に4件をスパム削除されて 8/12 に完全停止した。
# 削除されたのは1日21本想定で同型を投げていた頃のもの。形式(テキスト)は konan 指示どおり戻し、本数を絞った。
# 【2026-08-15】6本/日を3日間回して削除は再発せず。ただし _catchup が窓の頭で上限を食い切り、
# 6本すべてが14時までに固まって以降10時間無投稿になっていた(konan 指摘「全然投稿されてなかった」)。
# 上限を12本へ上げたうえで、窓の経過時間に比例した本数までしか解禁しない。前倒しの固め打ちを構造的に止める。
# 【2026-08-22 konan指示】「スレッドは24時間で240本出す設計にしろ」「毎回言い回し変えて、
# バンされないようにして」「これだけ枠が多いから、全部のアプリね」。
# 公式上限は250投稿/24h(threads_publishing_limit で実測)なので240は枠内。ただし
# **F-412の削除は本数ではなく同型テキストの反復が原因**だったので、本数を上げる条件は
# 言い回しの作り置き(threads_variants.json)が入っていること。1投稿1文型の使い回しはしない。
# 窓は24時間。240本を17時間に詰めるより、24時間へ均すほうが機械的に見えない(IGも同じ形にした)。
# 【2026-08-22 16:40】僕が一度これを 6本/日 に落としたが、konan「日に6本に変えたとこで
# 根本原因は解決されないからやめろ」で撤回し 240 に戻した。実測(video_metrics.db)でも
# 7/30以降は 1〜7本/日に落としても平均viewsは 0.3〜4.7 のままで、**本数を減らしても回復しない**。
# = 本数は原因ではない。減らすと露出だけ失って原因は残る。本数はここで触らない。
THREADS_MAX_PER_DAY = int(os.environ.get("THREADS_MAX_PER_DAY", "3"))   # v4(2026-08-26): 最適2〜3本/日調査に合わせる(旧240→回復期4→3)
THREADS_RUNS_PER_DAY = int(os.environ.get("THREADS_RUNS_PER_DAY", "24"))  # cron は毎時
THREADS_GAP_S = int(os.environ.get("THREADS_GAP_S", "25"))       # 連投間隔
_th_today = _today_count("threads")
# 【2026-08-22 konan指示】「24時間かけて240本だから、仮に何かのトラブルで4時間くらい
# 投稿できてなかったとしても、そこから元取るように240本投稿しようとしなくていい」。
# = 遅れは取り戻さない。1ランの本数は 240/24=10本 の固定で、落ちたランのぶんは捨てる。
# 取り戻す設計だと、止まった直後にまとめ出しが起きて一番スパムらしく見える。
# 日次上限だけは別に見て、その日の合計が THREADS_MAX_PER_DAY を超えないようにする。
_th_per_run = _even_share(THREADS_MAX_PER_DAY, THREADS_RUNS_PER_DAY, now.hour)
THREADS_PER_RUN = max(0, min(_th_per_run, THREADS_MAX_PER_DAY - _th_today))


def threads_quota():
    """Threads の公式な残枠を API に聞く。勘で本数を決めない(IG と同じやり方)。

    【2026-08-22】公式上限は 250投稿/24時間(threads_publishing_limit)。
    F-412 の削除は本数ではなく「同型テキスト+App Storeリンクの使い回し」が原因だったので、
    上限そのものは遠い。ただし上限に触れると一気に止まるので、実測値を毎回見て天井は必ず守る。
    """
    try:
        uid = os.environ["THREADS_USER_ID"]; tok = os.environ["THREADS_ACCESS_TOKEN"]
        d = _get(f"https://graph.threads.net/v1.0/{uid}/threads_publishing_limit",
                 {"fields": "quota_usage,config", "access_token": tok})
        row = d["data"][0]
        return int(row.get("quota_usage", 0)), int(row.get("config", {}).get("quota_total", 250))
    except Exception as e:
        print(f"  threads quota取得失敗({str(e)[:60]}) → 日次上限だけで判断")
        return None, None
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
_th_used, _th_cap = threads_quota()   # _get の定義後に呼ぶ
if _th_used is not None:
    THREADS_PER_RUN = min(THREADS_PER_RUN, max(0, _th_cap - _th_used - 10))
    print(f"  threads quota: {_th_used}/{_th_cap} 使用済(公式上限)")
print(f"[{now.isoformat()}] seq={seq} threads/run={THREADS_PER_RUN} ig/run={IG_PER_RUN}")


def _post(url, params):
    data = urllib.parse.urlencode(params).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=120))




try:
    THREADS_VARIANTS = json.load(open(os.path.join(HERE, "threads_variants.json")))
except Exception:
    THREADS_VARIANTS = {}
try:
    THREADS_REPLIES = json.load(open(os.path.join(HERE, "threads_replies.json")))
except Exception:
    THREADS_REPLIES = {}


def threads_text(post):
    """Threads本文。文字 + App Store の URL だけ。

    【2026-08-13 konan再指示】「スレッドは文字の投稿とアップストアのURLだけでいい。
    昔も同じ指摘したと思う」— 実際 2026-06-29 に同じ指示を受けている(このファイル冒頭)。
    F-412(スパム削除)の対策として動画つき+リンク削除に作り替えたのは指示に反していた。

    【2026-08-22 konan「毎回言い回し変えて」】同じ投稿を出す時は毎回違う言い回しを使う。
    候補は手元のローカルLLMで作り置きしてある(scripts/threads_variants.py → threads_variants.json)。
    どこまで使ったかは state.json に持つので、作り置きを一周するまで同じ文は二度出ない。
    """
    base = (post.get("threads_text") or "").strip()
    key = post.get("video") or post.get("app")
    pool = THREADS_VARIANTS.get(key) or []
    if not pool:
        return base[:500]
    used = STATE.setdefault("th_var", {})
    i = int(used.get(key, -1)) + 1
    used[key] = i
    return pool[i % len(pool)].strip()[:500]


def ig_caption(post):
    """IGのキャプション。本文だけ言い回しを差し替え、CTA(検索語)とタグは元のまま残す。

    【2026-08-22】IGを1日100本へ上げた。354投稿を100本/日で回すと同じ投稿が3.5日ごとに戻る。
    そこで**毎回同じ文**を出すと、F-412(Threadsの同型連投でスパム削除)と同じ条件になる。
    言い回しは Threads 用に作り置きした `threads_variants.json` を流用する
    (別媒体なので同じ文が両方に出ても「その媒体の中での反復」にはならない)。
    ただし IG はリンクが機能しないので URL は落とし、タグは元キャプションのものを使う。
    どこまで使ったかは Threads と別カウンタ(`ig_var`)で持つ。作り置きが無い投稿は元の文のまま。
    """
    base = post.get("ig_caption") or ""
    key = post.get("video") or post.get("app")
    pool = THREADS_VARIANTS.get(key) or []
    tail = [l for l in base.split("\n")
            if l.startswith("App Store") or l.lstrip().startswith("#")]
    # 【2026-08-22】Threadsが1投稿1〜5再生で止まっている原因はフォロワー1人=届く先が無いこと。
    # 返信で外に出るにはMeta審査が要るので、当面はこちら側から観客を渡すしかない。
    # IGは1日2.2万再生あり、同じ@名なのでタップ不要で辿れる。ハンドル1行だけ足す。
    if not pool or not tail:
        return "\n".join([base, "Threads @tyokobisakusaku"])[:2200]
    tail = tail + ["Threads @tyokobisakusaku"]
    used = STATE.setdefault("ig_var", {})
    i = int(used.get(key, -1)) + 1
    used[key] = i
    body = pool[i % len(pool)]
    body = re.sub(r"https?://\S+", "", body)     # IGは本文リンクが効かないので消す
    body = re.sub(r"#\S+", "", body)             # タグは元キャプションの並びを使う
    body = "\n".join(l.rstrip() for l in body.split("\n") if l.strip())
    if not body:
        return "\n".join([base, "Threads @tyokobisakusaku"])[:2200]
    # 【2026-08-23 IG一次調査】ハッシュタグは1投稿5個まで(2025年仕様)。超過分は落とす
    tail2, ntag = [], 0
    for l in tail:
        if l.lstrip().startswith("#"):
            tags = [t for t in l.split() if t.startswith("#")][: max(0, 5 - ntag)]
            ntag += len(tags)
            if tags: tail2.append(" ".join(tags))
        else:
            tail2.append(l)
    return "\n".join([body] + tail2)[:2200]


_URL_RE = re.compile(r"https?://\S+")

def _split_body_and_url(post):
    """本文からURLを抜き、返信用URLを返す。
    【2026-08-23 konan指示】Threadsは本文に外部URLがあると配信が絞られる傾向。
    → 本文はURLなし、URLは自分の投稿への返信に貼る「二段構え」に変更。
    在庫(threads_text・言い回しの作り置き)は触らず、ここで機械的に分離する。"""
    text = threads_text(post)
    urls = _URL_RE.findall(text)
    body = _URL_RE.sub("", text)
    body = re.sub(r"[ \t]+\n", "\n", body).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    url = post.get("appstore_url") or post.get("url") or (urls[0].rstrip(")。、") if urls else "")
    return body[:500], url


def threads_account(post):
    """投稿の中身から出し先アカウントを決める。**手元にあるトークンで決めない。**

    konan 2026-08-28「ノートの宣伝投稿はサクッとじゃないの?」
    アプリ宣伝=@tyokobisakusaku(さくさく) / note集客=@sakuttotyokobi(さくっと)で
    商品ごとに導線を分ける、が konan の設計。さくっとのトークンが無いからといって
    さくさくに出すのは違反(実際にそれで誤投稿した)。無いなら**出さない**。
    """
    if post.get("type") == "note":
        uid = os.environ.get("NOTE_THREADS_USER_ID")
        tok = os.environ.get("NOTE_THREADS_ACCESS_TOKEN")
        if not (uid and tok):
            raise RuntimeError(
                "note枠は @sakuttotyokobi 専用。NOTE_THREADS_USER_ID / "
                "NOTE_THREADS_ACCESS_TOKEN が無いので投稿しない(さくさくには絶対に出さない)")
        return uid, tok
    return os.environ["THREADS_USER_ID"], os.environ["THREADS_ACCESS_TOKEN"]


def publish_threads(post):
    """二段構え: ①本文(URLなし)を投稿 → ②その投稿への返信でApp Store URLを貼る。"""
    uid, tok = threads_account(post)
    B = "https://graph.threads.net/v1.0"
    body, url = _split_body_and_url(post)
    cid = _post(f"{B}/{uid}/threads", {"media_type": "TEXT", "text": body, "access_token": tok})["id"]
    # 【F-451・2026-08-29】作成直後に publish すると "Media Not Found"(code 24/4279009)で落ちる。
    # コンテナが反映されるまで待つ。返信処理は同じ理由で既に sleep(20) を入れてあった。
    pid = None
    for _i in range(5):
        time.sleep(20)
        try:
            pid = _post(f"{B}/{uid}/threads_publish", {"creation_id": cid, "access_token": tok}).get("id")
            break
        except Exception as e:
            detail = ""
            try: detail = e.read().decode("utf-8", "replace")[:200]
            except Exception: pass
            if "4279009" not in detail or _i == 4:
                raise
            print(f"  threads: コンテナ未反映で公開を再試行({_i + 1}/5)")
    if pid and url:
        STATE.setdefault("th_pending_replies", []).append(
            {"pid": pid, "key": post.get("video") or post.get("app"), "url": url,
             "acct": "note" if post.get("type") == "note" else "main"})
        _threads_flush_replies(uid, tok, "note" if post.get("type") == "note" else "main")
    return pid


def _threads_flush_replies(uid, tok, acct="main"):
    """未完了のURL返信を試す。失敗はエラー本文ごと記録し、次のランで再試行(konan 8/23「本文だけで返信が無い」)。

    親投稿を出したアカウントでしか返信しない。混ざると「さくさくがさくっとの投稿に返信」になる
    ([[feedback_route_by_audience_not_by_token]])。
    """
    B = "https://graph.threads.net/v1.0"
    pend = STATE.setdefault("th_pending_replies", [])
    keep = []
    for it in pend:
        if it.get("acct", "main") != acct:
            keep.append(it); continue
        pid, key, url = it["pid"], it["key"], it["url"]
        pool = THREADS_REPLIES.get(key) or []
        if pool:
            used = STATE.setdefault("th_rep", {})
            j = int(used.get(key, -1)) + 1; used[key] = j
            reply_text = pool[j % len(pool)]
        else:
            reply_text = url
        try:
            time.sleep(20)   # 公開直後は返信先が未反映のことがある(3秒では400だった)
            rc = _post(f"{B}/{uid}/threads", {"media_type": "TEXT", "text": reply_text,
                                              "reply_to_id": pid, "access_token": tok})["id"]
            time.sleep(5)
            _post(f"{B}/{uid}/threads_publish", {"creation_id": rc, "access_token": tok})
            print(f"  threads: URL返信OK → {pid}")
        except Exception as e:
            body = ""
            try: body = e.read().decode("utf-8", "replace")[:300]
            except Exception: pass
            it["tries"] = it.get("tries", 0) + 1
            print(f"  threads: URL返信に失敗(再試行{it['tries']}回目) {str(e)[:80]} {body}")
            if it["tries"] < 6:
                keep.append(it)
    STATE["th_pending_replies"] = keep
    save_state()


def _unused_old_reply_block(uid, tok, pid, url, post):
    if pid and url:
        try:
            time.sleep(3)
            # 返信文=アプリ名+サブタイトル+URL(threads_replies.json・審査済み文言から機械生成)。
            # 言い回しは投稿ごとに順繰り。作り置きが無ければURLだけ
            key = post.get("video") or post.get("app")
            pool = THREADS_REPLIES.get(key) or []
            if pool:
                used = STATE.setdefault("th_rep", {})
                j = int(used.get(key, -1)) + 1; used[key] = j
                reply_text = pool[j % len(pool)]
            else:
                reply_text = url
            rc = _post(f"{B}/{uid}/threads", {"media_type": "TEXT", "text": reply_text,
                                              "reply_to_id": pid, "access_token": tok})["id"]
            _post(f"{B}/{uid}/threads_publish", {"creation_id": rc, "access_token": tok})
        except Exception as e:
            print(f"  threads: URL返信に失敗(本文は公開済み) {str(e)[:120]}")
    return pid


def publish_instagram(post):
    """動画 Reel + cover(検索画面フレーム)。"""
    ig = os.environ["IG_USER_ID"]; tok = os.environ["IG_TOKEN"]
    B = "https://graph.instagram.com/v21.0"
    video_url = f"{BASE}/{post['video']}"
    params = {"media_type": "REELS", "video_url": video_url, "caption": ig_caption(post),
              "share_to_feed": "true", "access_token": tok}
    if post.get("cover"):
        params["cover_url"] = f"{BASE}/{post['cover']}"
    cid = _post(f"{B}/{ig}/media", params)["id"]
    sc = None
    # 【2026-08-23】24h枠超過時にコンテナが永遠にIN_PROGRESSのままになり、40回×6秒×2試行×5本=40分固まって
    # ランが落ちた(12:21)。待ちは最大2分、超えたらそのランのIGは打ち切る
    for _ in range(20):
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
    # 【2026-08-22】Threadsが1投稿1〜5再生から動かない原因は本数でも中身でもなく
    # **フォロワーが1人で配信先が無い**こと(threads_diag.py の実測)。
    # 会話に入る(返信)にはMeta審査が要るので、当面の無料の入口はここしかない。
    # YouTubeは1日8.7万再生出ているので、説明欄が唯一まとまった観客に触れる面になる。
    desc += "\n\nThreads: https://www.threads.com/@tyokobisakusaku"
    # 【2026-08-28 konan指示】note の宣伝も投稿工場に載せる。YT説明欄は唯一まとまった
    # 観客に触れる面(1日8.7万再生)で、審査も要らず貼り替えも効く。最新記事1本だけ出す
    if NOTE_NOTES and NOTE_NOTES[0].get("url"):
        desc += f"\nnote: {NOTE_NOTES[0]['url']}"
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
    # 【2026-08-23 YT一次調査・ルール2】題材混在チャンネルはおすすめ精度が落ちる→ジャンル別プレイリストで分離
    try:
        _yt_add_to_playlist(tok, vid, post)
    except Exception as e:
        print(f"  playlist skip: {str(e)[:100]}")
    return f"https://youtube.com/shorts/{vid}"


YT_GENRES = [
    ("自衛官 試験対策", ("自衛官", "予備自衛官", "陸曹", "海曹", "空曹", "幹部候補", "入隊")),
    ("消防設備士 試験対策", ("消防設備士",)),
    ("QC検定 試験対策", ("QC検定",)),
    ("運行管理者 試験対策", ("運行管理者",)),
    ("語学トレーナー", ("英語", "韓国語", "中国語", "語学")),
    ("生活・習慣アプリ", ("TASK", "推し", "散財", "ライフ", "スリーパー", "睡眠")),
]

def _yt_add_to_playlist(tok, vid, post):
    app = post.get("app") or ""
    name = next((n for n, keys in YT_GENRES if any(k in app for k in keys)), None)
    if not name:
        return
    pls = STATE.setdefault("yt_playlists", {})
    plid = pls.get(name)
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    if not plid:
        body = json.dumps({"snippet": {"title": name}, "status": {"privacyStatus": "public"}}).encode()
        req = urllib.request.Request("https://www.googleapis.com/youtube/v3/playlists?part=snippet,status",
                                     data=body, method="POST", headers=H)
        plid = json.load(urllib.request.urlopen(req, timeout=60))["id"]
        pls[name] = plid
    body = json.dumps({"snippet": {"playlistId": plid,
                                   "resourceId": {"kind": "youtube#video", "videoId": vid}}}).encode()
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet",
                                 data=body, method="POST", headers=H)
    urllib.request.urlopen(req, timeout=60)
    print(f"  playlist: {name}")


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
IG_POSTED = STATE.setdefault("ig_posted", [])  # IGに投稿済みの動画(恒久・2026-08-23 再投稿廃止)
for _v in HIST.get("instagram", {}):
    if _v not in IG_POSTED: IG_POSTED.append(_v)   # 履歴にある=一度出している
COOLDOWN_H = float(os.environ.get("REPOST_COOLDOWN_H", "72"))

def save_state():
    json.dump(STATE, open(STATE_PATH, "w"))

# 【2026-08-22】Threads だけクールダウンを分ける。240本/日をキュー336本から出すので、
# 72h のままだと3日で必要960本に対し在庫336本=枯れる。言い回しは毎回変わる(threads_variants)ので
# 同じアプリが翌日また出ること自体は問題にならない。IG/YT は 72h のまま触らない。
COOLDOWN_BY_PLATFORM = {"threads": float(os.environ.get("THREADS_COOLDOWN_H", "18"))}


def cooled(platform, post):
    if platform == "instagram" and post.get("video") in IG_POSTED:
        return False   # IGは各動画1回限り(公式: 投稿済みリールは表示抑制)
    ts = HIST.get(platform, {}).get(post.get("video", post.get("app")), "")
    if not ts: return True
    try:
        last = datetime.datetime.fromisoformat(ts)
        return (now - last).total_seconds() >= COOLDOWN_BY_PLATFORM.get(platform, COOLDOWN_H) * 3600
    except Exception: return True

def mark(platform, post):
    HIST.setdefault(platform, {})[post.get("video", post.get("app"))] = now.isoformat()
    if platform == "instagram" and post.get("video") and post["video"] not in IG_POSTED:
        IG_POSTED.append(post["video"])
    save_state()

_RUN_APPS = {}   # {platform: 今回のランで既に出したアプリID} — 1ラン内の重複を止める


def pick(platform, start_idx):
    """start_idxから順にローテ表を辿り、クールダウン明けの動画を探す。全滅ならNone(=見送り)。
    ローテ表はプラットフォーム別(IG/Threads=均等・YouTube=売上加重)。

    【2026-08-22】Threads は**言い回しの作り置きがある投稿を先に使う**。
    240本/日は同じ文の繰り返しが一番危ない(F-412の真因は本数でなく同型テキストの反復)。
    作り置きが無い投稿しか残っていない時だけ、それを使う(止めるよりは出す)。"""
    rot = ROTATIONS.get(platform, ROTATION_WEIGHTED)
    R = len(rot)
    fallback = None
    used = _RUN_APPS.setdefault(platform, set())
    for k in range(R):
        p = POSTS[rot[(start_idx + k) % R]]
        if not cooled(platform, p):
            continue
        # 【2026-08-22 konan指摘】1ランの中で同じアプリを二度出さない。
        # 並べ替え(_spread_by_app)だけだと在庫の多いアプリが同じランに二度来ることがある。
        # ここは最後の砦なので、アプリが尽きた時だけ(=候補が全部使用済みの時だけ)緩める。
        if _app_id(p) in used:
            fallback = fallback or p
            continue
        # 言い回しの作り置きがある投稿を先に使う(無い投稿は毎回同じ文になるので後回し)。
        if platform in ("threads", "instagram") and THREADS_VARIANTS:
            if not THREADS_VARIANTS.get(p.get("video") or p.get("app")):
                fallback = fallback or p
                continue
        used.add(_app_id(p))
        return p
    if fallback is not None:
        used.add(_app_id(fallback))
    return fallback

# Threads: 1起動で別アプリを複数本(rotation: seq*K+i)。間隔を空けて連投感を緩和。
# ===== Threads【2026-08-23 konan指示・運用変更(改)】=====
# ・1日24枠=毎時1本。全アプリ(24本前後)を毎日1回ずつ網羅する
# ・売上順(weights.json=ASC実績+konan優先の下限)で並べ、**売れているアプリほど人が見ている時間帯**に置く
#   時間帯の人気順(日本のThreads・平日夜〜昼が主戦場): 20,19,21,18,12,7,22,8,13,17,23,9,11,10,16,14,15,6,0,1,2,3,4,5
# ・投稿の仕方は二段構え(本文URLなし→自分への返信でアプリ名+サブタイトル+URL)
# ・1枠1回を state(th_slots: {日付: [済み時]}) で保証。cron遅延で落ちた枠は直前1枠だけ拾う(まとめ出しはしない)
# 【2026-08-23 一次調査】日本語圏Threadsの山は 7-9時 / 12-14時 / 21-24時(SOP/threads-operation-2026-08.md)
TH_HOUR_RANK = [21, 12, 8, 19, 22, 13, 7, 20, 23, 9, 18, 14, 17, 11, 10, 16, 15, 6, 0, 1, 2, 3, 4, 5]
# 回復期(2026-08-23〜): 1日4本。アカウント制限(5週間1本1再生)の固定化を避ける。
# 1本あたり再生が20を超えたら 6→8 へ段階増(morning_check/metrics_log.jsonl で判定)。24本は数字が許した時だけ
THREADS_DAILY_SLOTS = int(os.environ.get("THREADS_DAILY_SLOTS", "4"))
TH_ACTIVE_HOURS = TH_HOUR_RANK[:THREADS_DAILY_SLOTS]
# 【2026-08-26 konan 12:14指示「スレッドの今日の分は今、18時、21時にしろ」】
# 8時枠を隔離事故で逃した今日だけ18時に補填枠を置く。日付条件なので明日から自然に消える
if now.date().isoformat() == "2026-08-26":
    TH_ACTIVE_HOURS = [21, 12, 18]

# 【2026-08-28 konan指示】「ノートの宣伝も投稿工場の内容に組み込む」
# note有料記事の集客ポストは note工場が output/<slug>/05_sns_posts.md に5本作っている。
# それを note-factory/sns_queue.py が note_queue.json に落とし、ここが1日1枠で消費する。
# **枠は増やさずアプリ枠から1つ借りる**(本数を増やすとF-412=同型連投の再発条件に近づく)。
# 投稿の形はアプリと同じ二段構え(本文はURLなし → 自分への返信でnoteのURL)。
# 出し先は **@sakuttotyokobi 固定**(threads_account 参照)。専用トークンが無い間は枠ごと作らない。
try:
    NOTE_NOTES = json.load(open(os.path.join(HERE, "note_queue.json")))["notes"]
except Exception:
    NOTE_NOTES = []
NOTE_READY = bool(os.environ.get("NOTE_THREADS_USER_ID") and os.environ.get("NOTE_THREADS_ACCESS_TOKEN"))
NOTE_HOUR = TH_ACTIVE_HOURS[-1] if (NOTE_NOTES and NOTE_READY and len(TH_ACTIVE_HOURS) > 1) else None
if NOTE_HOUR is not None:
    TH_ACTIVE_HOURS = TH_ACTIVE_HOURS[:-1]


def _note_post():
    """公開済みnoteの集客ポストを1本。記事も言い回しも順に回して同じ文を二度出さない。"""
    if not NOTE_NOTES:
        return None
    qua = set(STATE.get("note_quarantine") or [])
    pool = [x for x in NOTE_NOTES if x["key"] not in qua]
    if not pool:
        return None
    st = STATE.setdefault("note_var", {})
    i = int(st.get("_article", -1)) + 1
    st["_article"] = i
    n = pool[i % len(pool)]
    j = int(st.get(n["key"], -1)) + 1
    st[n["key"]] = j
    return {"app": n["key"], "type": "note", "url": n.get("url", ""),
            "threads_text": n["variants"][j % len(n["variants"])]}

def _threads_ranked_apps():
    ids = {}
    for p_ in POSTS:
        aid = _app_id(p_)
        if aid and p_.get("threads_text"): ids[aid] = p_.get("app")
    return sorted(ids, key=lambda a: (-float(REVENUE_WEIGHT.get(a, 0)) - (0.5 if a in KONAN_PRIORITY else 0), a))

def _threads_plan():
    """{時: アプリID}。Top1→最も人が見る時間。アプリが24本未満なら余った枠は上位から2巡目"""
    ranked = _threads_ranked_apps()
    plan = {}
    # 全アプリ網羅は「日」でなく「週」で達成する: 日ごとに上位から回す起点をずらす
    day_off = (day_num * THREADS_DAILY_SLOTS) % max(1, len(ranked)) if ranked else 0
    for i, h in enumerate(TH_ACTIVE_HOURS):
        if not ranked: break
        # 最も人が見る枠には常に売上Top1〜を置き、残り枠で全アプリを日替わり巡回
        idx = i if i < 2 else (day_off + i) % len(ranked)
        plan[h] = ranked[idx]
    return plan

_today_jst = now.date().isoformat()
_th_done = STATE.setdefault("th_slots", {}).setdefault(_today_jst, [])
if os.environ.get("THREADS_ACCESS_TOKEN") and STATE.get("th_pending_replies"):
    _threads_flush_replies(os.environ["THREADS_USER_ID"], os.environ["THREADS_ACCESS_TOKEN"], "main")
if NOTE_READY and STATE.get("th_pending_replies"):
    _threads_flush_replies(os.environ["NOTE_THREADS_USER_ID"], os.environ["NOTE_THREADS_ACCESS_TOKEN"], "note")
_plan = _threads_plan()
_slots = [now.hour]
# 【2026-08-29】GitHubのスケジュールは1時間ではなく数時間まとめて落ちる(8/28は17:24→翌05:34で
# 一度も発火せず、21時枠=最上位枠を2日連続で失った)。旧実装は「直前1時間・:30まで」しか拾わない
# ので、その窓の外で復帰したランは枠を永久に取りこぼす。遡りを3時間に広げる。
# 拾うのは1枠だけ(まとめ出しはF-412の同型連投条件に近づくのでやらない)。
_th_slot_hours = set(TH_ACTIVE_HOURS) | ({NOTE_HOUR} if NOTE_HOUR is not None else set())
for _back in range(1, 4):
    _h_miss = now.hour - _back
    if _h_miss >= 0 and _h_miss in _th_slot_hours and _h_miss not in _th_done:
        _slots.insert(0, _h_miss)
        break
for _h in _slots:
    if not os.environ.get("THREADS_ACCESS_TOKEN") or _h in _th_done:
        continue
    if _h == NOTE_HOUR:
        np_ = _note_post()
        if np_ is None:
            continue
        if not cooled("threads", np_):
            _th_done.append(_h); save_state()
            print(f"  threads: {_h}時枠 note は18h以内に投稿済み=見送り"); continue
        ok, val = with_retry(lambda p=np_: publish_threads(p), attempts=1)
        results.append({"ch": "threads", "app": np_["app"], "ok": ok, ("id" if ok else "err"): val})
        print(f"  threads[{_h}時枠 note {np_['app']}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
        if ok:
            ok_count += 1; mark("threads", np_)
            STATE.setdefault("note_fail", {}).pop(np_["app"], None)
        else:
            # 【F-451・2026-08-29】失敗しても枠は消化する。消化しないと同じ投稿を30分おきに
            # 再試行し続け、note枠(8時)を恒久占有した上に autopost 全体を exit 1 にする。
            # 実際 8/25〜8/29 で 8時枠を毎日落としていた。3回連続で落ちる記事は隔離する。
            nf = STATE.setdefault("note_fail", {})
            nf[np_["app"]] = int(nf.get(np_["app"], 0)) + 1
            if nf[np_["app"]] >= 3:
                STATE.setdefault("note_quarantine", []).append(np_["app"])
                print(f"  threads: note {np_['app']} を3回連続失敗で隔離(以後選ばない)")
        _th_done.append(_h); save_state()
        continue
    target = _plan.get(_h)
    cands = [p_ for p_ in POSTS if target and _app_id(p_) == target and p_.get("threads_text")]
    if not cands:
        print(f"  threads: {_h}時枠 対象アプリ{target}の投稿が無い=見送り"); continue
    rot = STATE.setdefault("th_app_seq", {})
    j = int(rot.get(target, -1)) + 1; rot[target] = j
    tp = cands[j % len(cands)]
    # 【F-442・2026-08-27】同文二重投稿ガード(最後の砦)。枠記録(th_slots)が何かの理由で
    # 消えても、同じ動画の18h以内の再投稿はここで止める(hist は毎回確実に保存されている)。
    # 8/26 に12時枠・21時枠で完全同文が2回ずつ出た。枠は消化扱いにする(出し損ね < 同文連投)。
    if not cooled("threads", tp):
        _th_done.append(_h); save_state()
        print(f"  threads: {_h}時枠 {tp.get('app')} は18h以内に投稿済み=見送り(二重投稿ガード)")
        continue
    # 再試行しない: threads_publish がタイムアウトしても実際は成功している場合があり、
    # 再試行=同文二重投稿になる。失敗時は枠が未消化のまま残るので、次のランが自然に拾う。
    ok, val = with_retry(lambda p=tp: publish_threads(p), attempts=1)
    results.append({"ch": "threads", "app": tp.get("app"), "ok": ok, ("id" if ok else "err"): val})
    print(f"  threads[{_h}時枠 順位{list(_plan.values()).index(target)+1 if target in _plan.values() else '?'} {tp.get('app')}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
    if ok:
        # 【F-442】枠消化(_th_done.append)を mark(=save_state) より先に。逆順だと保存後に
        # append する形になり、後続のIG/YT投稿が無いラン(v4で2本/日に絞って以降は大半)では
        # 枠記録がディスクに載らず、次のランが同じ枠をもう一度出す=同文二重投稿の根本原因。
        ok_count += 1; _th_done.append(_h); mark("threads", tp)
    if len(_slots) > 1: time.sleep(THREADS_GAP_S)

# Instagram: バズりやすい時間帯の枠(IG_ACTIVE_HOURS)だけに投稿(rotation: seq)
for i in range(IG_PER_RUN):
    ip = pick("instagram", seq * 5 + i)
    if ip is None:
        print("  instagram: 全動画クールダウン中=見送り"); break
    ok, val = with_retry(lambda p=ip: publish_instagram(p), attempts=1)   # IGは再試行しない(枠超過で固まる)
    if not ok and ("Limit" in str(val) or "too many actions" in str(val) or "timeout status" in str(val)):
        results.append({"ch": "instagram", "app": ip.get("app"), "ok": False, "err": str(val)[:120]})
        print(f"  instagram: 24h枠超過/処理停滞 → このランのIGは打ち切り"); break
    results.append({"ch": "instagram", "app": ip.get("app"), "ok": ok, ("id" if ok else "err"): val})
    print(f"  instagram[{ip.get('app')}]: {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
    if ok: ok_count += 1; mark("instagram", ip)

# YouTube: 最優秀チャンネルだが同一動画の再アップ=スパム/重複判定リスク → 各動画一度きり。
# 未投稿の動画が無くなったら投稿しない(=新作が投入されると自動再開)。
# 【2026-08-21 konan指示】新クォータ(1回=1pt・100/日)確認済みにつき24本/日へ。
# ただしYouTubeのスパム量産検知は別問題なので、多様化ルール(1アプリ2本まで・角度分散)を前提とする
# 【v4・2026-08-26 konan全面改修】最適投稿数調査で YT Shorts は1〜2本/日が最適(3本超は逆効果)。
# 実測でも本数2.8倍で1本平均23%に低下(量産で自滅)。質量転換: konan台本形式×少数精鋭へ。
YT_MAX_PER_DAY = int(os.environ.get("YT_MAX_PER_DAY", "2"))
# 【2026-08-23 YT一次調査・ルール8】緊急ブレーキ: スパム規約は全動画対象(90日3ストライクで終了)。
# 1本あたり再生が直近7日平均の半分を切ったら 8本/日に絞り、売れ筋(優先枠)だけ出す(konan「絞るなら売れ筋優先」)
YT_BRAKE = False
try:
    _ml = [json.loads(l) for l in open(os.path.join(HERE, "metrics_log.jsonl")) if l.strip()]
    _pv = [r["by_platform"]["youtube"]["views"] / max(r["by_platform"]["youtube"]["n"], 1)
           for r in _ml if r.get("by_platform", {}).get("youtube", {}).get("n")]
    if len(_pv) >= 8 and _pv[-1] < 0.5 * (sum(_pv[-8:-1]) / 7):
        YT_BRAKE = True
        YT_MAX_PER_DAY = min(YT_MAX_PER_DAY, 8)
        print(f"  youtube: ⚠️ 緊急ブレーキ(1本あたり再生 {_pv[-1]:.0f} < 7日平均の半分) → {YT_MAX_PER_DAY}本/日・売れ筋のみ")
except Exception:
    pass
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
    STATE["yt_apps_today"] = []


# 【2026-08-22 konan指示】「youtubeは火曜日の22時まで持つ設計にしろ」
# 在庫は有限で、作り足す工場は konan の週間利用上限を食うので回し続けられない。
# 24本/日で流し続けると在庫が期限前に尽きて、チャンネルが数日まる無音になる。
# → 1日の本数を **在庫 ÷ 期限までの残り日数** で自動的に絞る。薄い日は自然に減り、
#   期限までゼロにならない。期限を過ぎたら絞りは自動で外れる(古い日付が足枷にならない)。
YT_HORIZON = os.environ.get("YT_HORIZON", "2026-09-01T22:00")   # v4: 8/26〜9/1(火)22:00 の1週間分


YT_PER_APP_PER_DAY = int(os.environ.get("YT_PER_APP_PER_DAY", "2"))   # 1アプリ2本/日まで(2026-08-23)


def _yt_daily_budget():
    """今日出してよい本数。在庫と期限から機械で決める。"""
    left = [p for p in POSTS if p.get("video") not in YT_POSTED]
    apps = {_app_id(p) for p in left if _app_id(p)}
    # 【2026-08-23 konan「本数は関係ないと分かったのに減らすな」】1アプリ2本/日まで(在庫アプリ数×2)。
    # 期限までの按分(YT_HORIZON)は「在庫が24本/日に足りない時だけ」効かせ、足りる時は上限まで出す。
    # 在庫の補充は自走ループ(残弾<6で工場起動)が担う
    cap = min(YT_MAX_PER_DAY, len(apps) * YT_PER_APP_PER_DAY, len(left))
    try:
        horizon = datetime.datetime.fromisoformat(YT_HORIZON)
    except ValueError:
        return max(1, cap)
    days = -(-int((horizon - now).total_seconds()) // 86400)  # 切り上げ
    if days <= 0 or len(left) >= YT_MAX_PER_DAY * days:
        return max(1, cap)
    return max(1, min(cap, -(-len(left) // days)))


YT_TODAY_MAX = _yt_daily_budget()


# 【2026-08-26 konan指示「時間も一番バズりやすい時間にしろ」】6-24時の均等配分をやめ、
# バズりやすい時間帯の枠を上から使う。日本のYTショートの視聴の山は 20-23時(夜が最強)・
# 平日は17-20時投稿が定石・土日は10-12時にも山(2026年調査・複数媒体一致)。
# 初速評価の時間を確保するため山の1時間前に置く: 平日=19時・12時 / 土日=11時・19時。
# ペース追従(F-410: cronが落ちても次の生きたランが遅れを吸収)はそのまま残る。
YT_HOUR_RANK = [19, 12, 18, 20, 7, 17, 21, 8, 13, 22, 11, 16, 23, 10, 15, 9, 14, 6]
if now.weekday() >= 5:   # 土日は午前の山(10-12時)を先に使う
    YT_HOUR_RANK = [11, 19, 12, 18, 20, 7, 17, 21, 8, 13, 22, 16, 23, 10, 15, 9, 14, 6]


def _yt_pace_target():
    """今の時刻なら何本上がっているべきか(バズりやすい枠のうち、時刻が過ぎた枠の数)。"""
    return min(YT_TODAY_MAX,
               sum(1 for h in YT_HOUR_RANK[:YT_TODAY_MAX] if now.hour >= h))


# 【2026-08-22 konan指摘・これが仕様】「24このアプリのための24本を1日でって言ったよな?」
# YouTube の1日24本は **24アプリ × 各1本**。同じアプリを1日に2本出した時点で仕様違反。
#
# 前の直し(1ランの中だけ重複を止める)では足りなかった。YT は毎時走るので、
# ランをまたげば同じアプリがまた選ばれる。しかも ROTATION_WEIGHTED は
# PRIORITY_FLOOR=5 で優先アプリをローテ内に5回置くので、**加重そのものが重複の発生源**だった。
# 結果 2026-08-22 は陸曹が1日5本上がった。
#
# 対策: 「今日どのアプリを上げたか」を日付つきで STATE に持ち、**その日はもう選ばない**。
# 加重ローテは「どのアプリを先に出すか」の優先順としてだけ効かせる(登場回数では効かせない)。
_yt_apps_today_list = list(STATE.get("yt_apps_today") or [])
_yt_apps_today = {a for a in set(_yt_apps_today_list) if _yt_apps_today_list.count(a) >= YT_PER_APP_PER_DAY}  # 上限到達アプリだけ避ける


def _yt_next(priority_only, avoid):
    """加重ローテを seq から辿って、まだ上げていない動画を1本返す。

    avoid には「今日すでに上げたアプリ」が入る。同じアプリの2本目は返さない。
    """
    _R = len(ROTATION_WEIGHTED)
    for k in range(_R):
        p = POSTS[ROTATION_WEIGHTED[(seq + k) % _R]]
        if p.get("video") in YT_POSTED:
            continue
        if priority_only and _app_id(p) not in KONAN_PRIORITY:
            continue
        if _app_id(p) in avoid:
            continue
        return p
    return None


if os.environ.get("YT_REFRESH_TOKEN") and YT_WIN_START <= now.hour <= YT_WIN_END:
    _target = _yt_pace_target()
    _behind = _target - STATE.get("yt_count", 0)
    if _behind <= 0:
        print(f"  youtube: ペース内({STATE.get('yt_count',0)}/{_target}本"
              f" 本日上限{YT_TODAY_MAX}本)=今は見送り")
    else:
        _n = min(_behind, YT_CATCHUP_MAX)
        print(f"  youtube: ペース {STATE.get('yt_count',0)}/{_target}本 → {_n}本投稿して取り戻す")
        for _i in range(_n):
            # 【2026-08-06 konan指示】YTは枠が少ないので厳選する=売上加重ローテを辿る
            # (DLされてる/売れてるアプリほど登場回数が増える)。IG実績連動は指標取得を実装してから。
            # 【2026-08-08 konan 明言】「残り九本のうち八本はこの8本を出せ」
            # 加重ローテだけだと確率的にしか寄らない。**優先8本の未投稿があれば必ずそれを先に出す。**
            # 優先枠を使い切ってから、はじめて通常の加重ローテに落ちる。
            # 【2026-08-22 konan指摘】「24このアプリのための24本を1日でって言ったよな?」
            # 1日 = 24アプリ × 各1本。今日すでに上げたアプリは、優先枠であっても二度と選ばない。
            # **ここで avoid を緩めてはいけない**。緩めた結果が陸曹5本だった。
            # 出せる新しいアプリが無くなったら、水増しせずその日は打ち止めにする。
            yp = _yt_next(priority_only=True, avoid=_yt_apps_today)
            if yp is not None:
                print(f"  youtube: 優先枠 → {KONAN_PRIORITY[_app_id(yp)]}")
            elif YT_BRAKE:
                yp = None   # ブレーキ中は売れ筋(優先枠)以外を出さない(2026-08-23)
            else:
                yp = _yt_next(priority_only=False, avoid=_yt_apps_today)
            if yp is None:
                print(f"  youtube: 今日まだ出していないアプリの在庫なし"
                      f"(本日 {len(_yt_apps_today)}アプリ投稿済み)=同じアプリの2本目は出さない")
                break
            ok, val = with_retry(lambda p=yp: publish_youtube(p))
            results.append({"ch": "youtube", "app": yp.get("app"), "ok": ok, ("id" if ok else "err"): val})
            print(f"  youtube[{yp.get('app')}] ({STATE.get('yt_count',0)+1}/{YT_TODAY_MAX}): {'OK ' + str(val) if ok else 'FAIL ' + str(val)}")
            if not ok:
                break  # 連投で同じ失敗を繰り返さない(クォータ超過等)
            ok_count += 1
            STATE["last_yt_seq"] = seq
            STATE["last_yt_ts"] = now.isoformat()
            STATE["yt_count"] = STATE.get("yt_count", 0) + 1
            _yt_apps_today_list.append(_app_id(yp))
            if _yt_apps_today_list.count(_app_id(yp)) >= YT_PER_APP_PER_DAY:
                _yt_apps_today.add(_app_id(yp))
            STATE["yt_apps_today"] = _yt_apps_today_list
            YT_POSTED.append(yp.get("video"))
            save_state()
            seq += 1  # 連投時に同じアプリが続かないようローテを進める

# 【F-442】終了前に必ず保存。「最後の投稿の後に別の save が来る」前提の書き方が
# 二重投稿の温床だった。メモリ上の STATE とディスクを最後に一致させる。
save_state()
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
