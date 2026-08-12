#!/usr/bin/env python3
"""投稿文の品質採点。ローカルLLM(Ollama)で1件ずつ採点し、低得点を洗い出す。"""
import json, sys, pathlib, urllib.request, re

ROOT = pathlib.Path(__file__).resolve().parent
OLLAMA = "http://localhost:11434/api/generate"
MODEL = "qwen3:14b"

RUBRIC = """あなたは日本語SNS投稿の編集者です。以下の投稿文を採点してください。

【良い投稿の条件】
- 冒頭で読者に「事実・数字・気づき」を渡している(読んだだけで得がある)
- アプリの話は最後に軽く触れる程度
- 人間が書いた自然な口調。話し言葉。
- 具体的な固有名詞や数字が入っている

【悪い投稿の条件】
- アプリの機能説明が中心(「〜が使えます」「便利です」)
- 誰でも書ける一般論だけ。中身がない
- AI が書いた感じ(ひらがな多用、「〜しませんか?」、過剰な整い方)
- 自己啓発くさい煽り(「今すぐ」「人生が変わる」「やらないと損」)
- 値段や無料/有料の話が出てくる(禁止)

【出力形式】厳密にJSONのみ。説明文は書かない。
{"score": 1〜5の整数, "reason": "20字以内の理由"}

score=5 は文句なし。score=3 は可もなく不可もなし。score<=2 は書き直しが必要。

【採点対象】
"""


def ask(text):
    body = json.dumps({
        "model": MODEL,
        "prompt": RUBRIC + text,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.load(r)["response"]
    m = re.search(r'\{.*?\}', out, re.S)
    if not m:
        return {"score": 0, "reason": "採点不能"}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"score": 0, "reason": "採点不能"}


def main():
    q = json.loads((ROOT / "post_queue.json").read_text(encoding="utf-8"))
    posts = q["posts"]
    results = []
    for i, p in enumerate(posts):
        txt = p.get("ig_caption", "")
        r = ask(txt)
        r["idx"] = i
        r["app"] = p.get("app")
        results.append(r)
        print("%3d/%d  score=%s  %s  %s" % (i + 1, len(posts), r.get("score"), p.get("app"), r.get("reason")), flush=True)
    (ROOT / "post_grades.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    low = [r for r in results if (r.get("score") or 0) <= 2]
    print("\n低得点(要書き直し): %d 件 / %d" % (len(low), len(results)))


if __name__ == "__main__":
    main()
