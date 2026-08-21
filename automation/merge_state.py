#!/usr/bin/env python3
"""merge_state.py — state.json を「取りこぼさない」形で origin/main と合流させる。

なぜ必要か(2026-08-08):
  autopost の Persist ステップは `git pull --rebase` していたが、
  こちらが同時に push していると `could not apply ... chore: autopost state` で落ちる。
  実測では投稿自体は成功しているのに state だけ保存されず、
  **72hクールダウンの記録が消えて同じ動画を早く再投稿しかねない**状態になっていた。

やること: ローカルとリモートの state.json を**意味を分かって**合流させる。
  - yt_posted : 和集合(投稿済みは片方にしか無くても投稿済み)
  - hist      : 媒体ごとに「新しい方のタイムスタンプ」を採用(=クールダウンを短くしない安全側)
  - yt_count  : 同じ日付なら大きい方。日付が違うなら新しい日付側を採用
  - その他    : 新しい方(引数で渡した local)を優先

使い方: python3 automation/merge_state.py <相手のstate.json>
        (相手= git show origin/main:automation/state.json の中身を書き出したファイル)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "state.json")


def merge(local, remote):
    out = dict(remote)
    out.update({k: v for k, v in local.items()
                if k not in ("yt_posted", "hist", "yt_count", "yt_date", "th_var")})

    # Threads の言い回し送り(何番まで使ったか)は大きい方を採る = 同じ文を二度出さない安全側
    th = dict(remote.get("th_var", {}))
    for key, i in (local.get("th_var", {}) or {}).items():
        th[key] = max(int(i), int(th.get(key, -1)))
    out["th_var"] = th

    # 投稿済みは和集合。順序は remote を土台に、local の新規を後ろへ
    seen, posted = set(), []
    for v in list(remote.get("yt_posted", [])) + list(local.get("yt_posted", [])):
        if v not in seen:
            seen.add(v)
            posted.append(v)
    out["yt_posted"] = posted

    # hist は「遅い方(新しい方)」を採る = クールダウンを縮めない
    hist = {}
    for src in (remote.get("hist", {}), local.get("hist", {})):
        for ch, m in (src or {}).items():
            cur = hist.setdefault(ch, {})
            for vid, ts in (m or {}).items():
                if vid not in cur or ts > cur[vid]:
                    cur[vid] = ts
    out["hist"] = hist

    # 当日の本数は多い方(=二重投稿を招かない安全側)。日付が違えば新しい日付を採る
    ld, rd = local.get("yt_date"), remote.get("yt_date")
    if ld == rd:
        out["yt_date"] = ld
        out["yt_count"] = max(local.get("yt_count", 0), remote.get("yt_count", 0))
    elif (ld or "") > (rd or ""):
        out["yt_date"], out["yt_count"] = ld, local.get("yt_count", 0)
    else:
        out["yt_date"], out["yt_count"] = rd, remote.get("yt_count", 0)
    return out


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    local = json.load(open(LOCAL))
    remote = json.load(open(argv[0]))
    merged = merge(local, remote)
    json.dump(merged, open(LOCAL, "w"), ensure_ascii=False, indent=1)
    print(f"merged: yt_posted {len(remote.get('yt_posted', []))}+{len(local.get('yt_posted', []))}"
          f" → {len(merged['yt_posted'])} / yt {merged.get('yt_date')} {merged.get('yt_count')}本")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
