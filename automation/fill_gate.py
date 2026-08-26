#!/usr/bin/env python3
"""fill_gate.py — 充填ゲート。キューをpushする前に全検査を制作側で完了させる。

konan 2026-08-26 12:00「制作の段階でゲートを通す。充填は1番最終段階。
充填まで完了したらあとは自動で確実に指定された時間に配信される。それを完了と言う」

配信側(GitHub Actions)のゲートは安全網であって、初見の検査をここに残さない。
このスクリプトが exit 0 になるまで充填(push)は完了と言えない。pre-pushフックが強制する。

やること(全部ローカル・順に):
 1. 未検査の動画に焼き込み文字OCR(video_text_audit.py)を掛けて台帳に登録
 2. ナレーションゲート(video_preflight.py)
 3. 文言lint(queue_lint.py)
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AUDIT = "/Users/konan/claude-tools/scripts/video_text_audit.py"


def main():
    q = json.load(open(f"{HERE}/post_queue.json"))
    try:
        ledger = json.load(open(f"{HERE}/video_text_audit.json"))
    except Exception:
        ledger = {}
    ledger_names = {k.split(":")[0] for k in ledger}

    unaudited = []
    for p in q["posts"]:
        v = p.get("video")
        if v and v not in ledger_names and os.path.exists(f"{ROOT}/videos/{v}"):
            unaudited.append(f"{ROOT}/videos/{v}")
    if unaudited:
        print(f"[充填ゲート] 焼き込み文字OCR 未検査{len(unaudited)}本を検査")
        r = subprocess.run([sys.executable, AUDIT] + unaudited)
        if r.returncode != 0:
            print("❌ OCR検査でNG。充填不可")
            return 1

    env = dict(os.environ)
    if not env.get("FFMPEG"):
        # Actionsはapt版、ローカルは ~/.local/bin の単体バイナリ
        local_ff = "/Users/konan/.local/bin/ffmpeg"
        if os.path.exists(local_ff):
            env["FFMPEG"] = local_ff
    for name, script in (("ナレーションゲート", "video_preflight.py"),
                         ("文言lint", "queue_lint.py")):
        r = subprocess.run([sys.executable, f"{HERE}/{script}"], cwd=ROOT, env=env)
        if r.returncode != 0:
            print(f"❌ {name} NG。充填不可")
            return 1

    print("✅ 充填ゲート全通過 — pushすれば完了(以降はActionsが指定時刻に自動配信)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
