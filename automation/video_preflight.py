#!/usr/bin/env python3
"""video_preflight.py — 投稿キュー動画の機械ゲート(2026-07-15 konan「ナレーション必須マジで気をつけて」)。
検査: post_queue.json の全動画に対し
  1) 音声ストリーム存在
  2) 発話量: 音声帯域(300-3400Hz)の非無音時間が全長の35%以上(無音スライドショー=効果音3発だけ、を弾く)
FAIL が1本でもあれば exit 1(CIを落とす=無音動画は配信されない)。
ローカル: python3 automation/video_preflight.py [動画パス...]  # 引数なし=キュー全部
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEOS = os.path.join(HERE, "..", "videos")
FF = os.environ.get("FFMPEG", "ffmpeg")
MIN_VOICED_RATIO = 0.35

def voiced_ratio(path):
    """音声帯域の非無音率と全長を返す"""
    r = subprocess.run([FF, "-i", path, "-vn",
                        "-af", "highpass=f=300,lowpass=f=3400,silencedetect=n=-30dB:d=0.3",
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
    if not m:
        return None, 0.0
    total = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    silent = 0.0
    for sm in re.finditer(r"silence_duration: ([\d.]+)", txt):
        silent += float(sm.group(1))
    # 末尾無音(silence_startが出てsilence_endが無い)も加算
    starts = re.findall(r"silence_start: ([\d.]+)", txt)
    ends = re.findall(r"silence_end", txt)
    if len(starts) > len(ends):
        silent += max(0.0, total - float(starts[-1]))
    if "Audio:" not in txt:
        return 0.0, total
    return max(0.0, (total - silent) / total) if total else 0.0, total

def main():
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        pq = json.load(open(os.path.join(HERE, "post_queue.json")))
        targets = [os.path.join(VIDEOS, p["video"]) for p in pq["posts"]]
    fails = []
    for t in targets:
        if not os.path.exists(t):
            fails.append((os.path.basename(t), "ファイル不存在")); continue
        vr, dur = voiced_ratio(t)
        if vr is None:
            fails.append((os.path.basename(t), "解析不能")); continue
        ok = vr >= MIN_VOICED_RATIO
        print(f"{'OK  ' if ok else 'FAIL'} {os.path.basename(t)}  voiced={vr:.0%} dur={dur:.0f}s")
        if not ok:
            fails.append((os.path.basename(t), f"発話量{vr:.0%} < {MIN_VOICED_RATIO:.0%}=ナレ無し/無音疑い"))
    if fails:
        print("\n🔴 GATE FAIL — 以下は配信禁止(ナレーション必須):")
        for n, why in fails:
            print(f"  {n}: {why}")
        sys.exit(1)
    print(f"\n✅ 全{len(targets)}本 PASS(ナレーションゲート)")

if __name__ == "__main__":
    main()
