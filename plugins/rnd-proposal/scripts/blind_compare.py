# -*- coding: utf-8 -*-
"""두 문서 블라인드 비교: 프롬프트 준비와 판정 집계 (plan_v2 1단계, 2026-09-28).

81_비교검증 에서 손으로 한 절차를 고정한다. 심판(ChatGPT 웹 또는 Claude 새 서브에이전트)을 부르는 일은
스킬 rp-blind 가 하고, 이 스크립트는 글을 만들고 답을 센다.

    python blind_compare.py prepare --a X.hwpx --b Y.hwpx --out <dir> [--label-a 원본 --label-b 최종본] [--judge chatgpt|claude]
    python blind_compare.py tally   --dir <dir>

prepare: 두 문서(hwpx 또는 md)의 본문 텍스트만 뽑아 prompt_1.md(A=X, B=Y)·prompt_2.md(A=Y, B=X)와 meta.json 을 쓴다.
         prompt_N.js 는 같은 전문을 ChatGPT 입력창에 넣는 JS 한 줄이다(javascript_tool 에 그대로 넘긴다).
         심판의 답은 같은 폴더의 response_1.md·response_2.md 로 저장한다(rp-blind 스킬).
tally:   두 답의 표를 읽어 문서 이름으로 환산하고, 두 번 모두 같은 문서를 고른 항목만 「확정」한다.
         한 회가 6항목 중 5개 이상을 같은 글자(A 또는 B)로 고르면 「위치 편향 의심」을 표시한다(81 2회차 사례).
         결과 blind.json·blind.md. exit 0 (답 파일이 없거나 표를 못 읽으면 exit 2).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ITEMS = ["양식", "논리", "구체", "간결", "문체", "구조"]
PROMPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "rp-blind", "blind_prompt.md")
BIAS_MIN = 5


def body_text(path: str) -> str:
    if path.lower().endswith(".hwpx"):
        from hwpx_text import hwpx_to_md
        return hwpx_to_md(path)
    return open(path, encoding="utf-8").read()


def build_prompt(text_a: str, text_b: str) -> str:
    head = open(PROMPT, encoding="utf-8").read().strip()
    return f"{head}\n\n=== 문서 A ===\n{text_a.strip()}\n\n=== 문서 B ===\n{text_b.strip()}\n"


def insert_js(text: str) -> str:
    """ChatGPT 입력창에 전문을 넣는 JS (skills/rp-blind/chatgpt_web.md). 클립보드 붙여넣기는 실측 실패(2026-09-27).
    execCommand('insertText') 는 브라우저 창이 OS 포커스를 잃으면 실패한다(실측 2026-09-28: document.hasFocus() false).
    그때는 합성 paste 이벤트(DataTransfer)로 넣는다. ProseMirror 가 paste 를 받아 준다. 결과는 공백 제외 글자 수(ns).
    javascript_tool 은 최상위 await 를 받는다: 앞의 await 가 없으면 Promise 가 {} 로 돌아온다."""
    t = json.dumps(text, ensure_ascii=False)
    return ("await (async () => { const box = document.querySelector('div.ProseMirror[role=\"textbox\"]');"
            " if (!box) return 'no-textbox'; box.focus(); const T = " + t + ";"
            " document.execCommand('selectAll'); document.execCommand('delete'); document.execCommand('insertText', false, T);"
            " await new Promise(r => setTimeout(r, 400)); let via = 'insertText';"
            " if (box.innerText.replace(/\\s/g, '').length < 10) { const dt = new DataTransfer(); dt.setData('text/plain', T);"
            " box.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));"
            " await new Promise(r => setTimeout(r, 800)); via = 'paste'; }"
            " document.title = 'rp'; return 'via=' + via + ' ns=' + box.innerText.replace(/\\s/g, '').length; })()")


def prepare(a: str, b: str, out: str, label_a: str | None = None, label_b: str | None = None,
            judge: str = "chatgpt") -> dict:
    os.makedirs(out, exist_ok=True)
    la = label_a or os.path.splitext(os.path.basename(a))[0]
    lb = label_b or os.path.splitext(os.path.basename(b))[0]
    if la == lb:
        raise SystemExit("두 문서 이름이 같다: --label-a/--label-b 로 구분하라")
    ta, tb = body_text(a), body_text(b)
    for k, (x, y) in (("1", (ta, tb)), ("2", (tb, ta))):
        p = build_prompt(x, y)
        open(os.path.join(out, f"prompt_{k}.md"), "w", encoding="utf-8").write(p)
        open(os.path.join(out, f"prompt_{k}.js"), "w", encoding="utf-8").write(insert_js(p))
    meta = {"docs": {la: os.path.abspath(a), lb: os.path.abspath(b)}, "judge": judge,
            "order": {"1": {"A": la, "B": lb}, "2": {"A": lb, "B": la}}}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return meta


def parse_response(text: str) -> dict:
    """답 표에서 {항목: {"pick": "A"|"B"|"동등", "why": str}}. 못 읽은 항목은 빠진다."""
    got = {}
    for ln in text.splitlines():
        if not ln.strip().startswith("|"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 2 or c[0] not in ITEMS:
            continue
        v = re.sub(r"[*`\s]", "", c[1])
        pick = "동등" if v.startswith("동등") else ("A" if v.upper().startswith("A") else ("B" if v.upper().startswith("B") else None))
        if pick:
            got[c[0]] = {"pick": pick, "why": c[2] if len(c) > 2 else ""}
    return got


def tally(d: str) -> dict:
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    runs = {}
    for k in ("1", "2"):
        p = os.path.join(d, f"response_{k}.md")
        if not os.path.exists(p):
            raise SystemExit(f"답 파일 없음: {p}")
        r = parse_response(open(p, encoding="utf-8").read())
        miss = [i for i in ITEMS if i not in r]
        if miss:
            raise SystemExit(f"response_{k}.md 에서 못 읽은 항목: {', '.join(miss)}")
        runs[k] = r
    res = {"judge": meta.get("judge"), "docs": list(meta["docs"]), "items": {}, "bias": {}}
    for k, r in runs.items():
        letters = [r[i]["pick"] for i in ITEMS]
        top = max(letters.count("A"), letters.count("B"))
        res["bias"][k] = top >= BIAS_MIN
    for i in ITEMS:
        picks = []
        for k in ("1", "2"):
            p = runs[k][i]["pick"]
            picks.append(meta["order"][k][p] if p in ("A", "B") else "동등")
        conf = picks[0] if picks[0] == picks[1] else None
        res["items"][i] = {"run1": picks[0], "run2": picks[1], "confirmed": conf,
                           "why1": runs["1"][i]["why"], "why2": runs["2"][i]["why"]}
    res["wins"] = {n: [i for i in ITEMS if res["items"][i]["confirmed"] == n] for n in res["docs"]}
    # plan_t4fix 6 (2026-09-28): 6항목 전부 한쪽 확정이면 편향 의심(t4 회차 1: Claude 심판이 6/6 cur).
    #   원고를 Claude 가 썼으므로 Claude 심판은 자기 평가 편향 가능으로 표시한다.
    res["sweep"] = next((n for n, w in res["wins"].items() if len(w) == len(ITEMS)), None)
    res["self_bias"] = res.get("judge") == "claude"
    json.dump(res, open(os.path.join(d, "blind.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(os.path.join(d, "blind.md"), "w", encoding="utf-8").write(render(res, meta))
    return res


def render(res: dict, meta: dict) -> str:
    o1, o2 = meta["order"]["1"], meta["order"]["2"]
    L = [f"# 블라인드 비교 (심판: {res.get('judge')})", "",
         f"| 항목 | 1회 (A={o1['A']}, B={o1['B']}) | 2회 (A={o2['A']}, B={o2['B']}) | 확정 |", "|---|---|---|---|"]
    for i in ITEMS:
        it = res["items"][i]
        L.append(f"| {i} | {it['run1']} | {it['run2']} | {it['confirmed'] or '미확정'} |")
    L.append("")
    for n, w in res["wins"].items():
        L.append(f"- {n} 확정 승: {', '.join(w) if w else '없음'}")
    for k, b in res["bias"].items():
        if b:
            L.append(f"- {k}회차: 6항목 중 {BIAS_MIN}개 이상 같은 위치를 골라 위치 편향 의심")
    if res.get("sweep"):
        L.append(f"- ★ 6항목 전부 {res['sweep']} 확정: 편향 의심")
    if res.get("self_bias"):
        L.append("- ★ Claude 심판: 자기 평가 편향 가능(원고를 Claude 가 썼다. 외부 전송 동의가 없거나 ChatGPT 절차가 실패했을 때만 쓴다)")
    return "\n".join(L) + "\n"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["prepare", "tally"])
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--out")
    ap.add_argument("--dir")
    ap.add_argument("--label-a")
    ap.add_argument("--label-b")
    ap.add_argument("--judge", default="chatgpt", choices=["chatgpt", "claude"])
    a = ap.parse_args()
    if a.cmd == "prepare":
        m = prepare(a.a, a.b, a.out, a.label_a, a.label_b, a.judge)
        print(f"[blind] {a.out}: prompt_1.md (A={m['order']['1']['A']}) · prompt_2.md (A={m['order']['2']['A']})")
        return 0
    try:
        res = tally(a.dir)
    except SystemExit as e:
        print(f"[blind] {e}")
        return 2
    print(render(res, json.load(open(os.path.join(a.dir, "meta.json"), encoding="utf-8"))), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
