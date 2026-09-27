#!/usr/bin/env python3
"""#PR が必ず付くことの検査(F-536)。cloud_post.py は import すると配信が走るので、
関数だけを AST で取り出して試す。在庫の全件で Instagram のキャプションと YouTube の題を作り、
#PR が無い物が1件でもあれば非0で終わる。使い方: python3 automation/pr_gate.py"""
import ast, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "cloud_post.py"), encoding="utf-8").read()
tree = ast.parse(src)
want = {"_ensure_pr", "ig_caption"}
ns = {"PR_TAG": "#PR", "re": re, "os": os, "json": json, "STATE": {}, "THREADS_VARIANTS": {}}
try:
    ns["THREADS_VARIANTS"] = json.load(open(os.path.join(HERE, "threads_variants.json")))
except Exception:
    pass
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in want:
        exec(ast.get_source_segment(src, n), ns)
missing = want - set(ns)
if missing:
    print("NG pr_gate: 関数が見つからない", sorted(missing)); sys.exit(1)

def yt_title(post):
    # cloud_post.py の題の作り方と同じ規則(#PR が無ければ末尾に足す)
    t = post.get("yt_title") or (post["ig_caption"].split("\n")[0][:88] + " #shorts #PR")
    if "#PR" not in t:
        t = (t[:96] + " #PR") if len(t) > 96 else (t + " #PR")
    return t[:100]

posts = json.load(open(os.path.join(HERE, "post_queue.json")))["posts"]
bad = []
for variants in (ns["THREADS_VARIANTS"], {}):       # 作り置きあり/なしの両方の経路
    ns["THREADS_VARIANTS"] = variants
    for p in posts:
        cap = ns["_ensure_pr"](ns["ig_caption"](p))
        if not re.search(r"#PR|＃PR", cap):
            bad.append(("instagram", p.get("video")))
        if len([t for l in cap.split("\n") if l.lstrip().startswith("#") for t in l.split() if t.startswith("#")]) > 5:
            bad.append(("instagram:tags>5", p.get("video")))
for p in posts:
    if not re.search(r"#PR|＃PR", yt_title(p)):
        bad.append(("youtube", p.get("video")))
if bad:
    print(f"NG pr_gate: #PR の無い投稿が {len(bad)} 件", bad[:8]); sys.exit(1)
print(f"OK pr_gate: {len(posts)} 本すべてで Instagram のキャプションと YouTube の題に #PR が付く")
