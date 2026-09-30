# -*- coding: utf-8 -*-
"""외부 교정 = 「문제 목록 받기」 (plan_v2 4단계 13, 2026-09-28) — 그리고 교정본 손실 검사.

## 왜 바꿨나

외부 모델에게 문장을 고치게 하면 사실을 바꾼다. 61_검토피드백 실측: 「0.8790」 을 「주관기관의 선행연구를 통해 사전 확보함」으로
옮기라고 했다(출처 귀속 변경). 반대로 평가자로 쓰면 우리 채점기의 맹점을 잡았다(81_비교검증).
그래서 외부 모델에게서는 **위치(원문 인용)·문제·이유만** 받는다. 원고 문장은 한 글자도 받지 않는다.
실제 수정은 교정 회차에서 rp-editor 가 고치기 모드(op, edit_apply)로 하고, 회차 채택 판정(adopt)을 거친다.
(0.8.0 까지의 「제안 받아 기계 검사로 채택·반영」 경로 --proposals/--apply 는 삭제했다.)

## 두 모드

1) 문제 목록 판정
    python check_proofread.py --problems 60_교정문제.md --md 30_proposal.md --out 60_교정문제.json
   받은 표 `| # | 절 | 원문 인용 | 문제 | 이유 |` 의 행마다 인용이 원고에 **정확히 한 번** 있는지만 본다.
   있으면 「유효」, 0회·2회 이상이면 「기각: 인용 n회」. 제안·수정문 열이 붙어 오면 버린다(원장에도 싣지 않는다).
   유효 행은 JSON 으로 내보내 교정 회차 편집자의 입력이 된다. 원장 md 에 판정 열을 채워 다시 쓴다.

2) 전후 손실 검사 (기존)
    python check_proofread.py --before <원본 build.md> --after <교정 반영 build.md>

exit 0 통과 · 2 오류(파일 없음·표 없음) 또는 손실.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys

# ── 토큰 (check_preserve 가 SRC 를 쓴다) ───────────────────────────────────
NUM = re.compile(
    r"\d[\d,]*\.?\d*\s*(?:℃|%|kW|MW|MWh|kWh|GWh|TOE|tCO2?|bar|K|h시간|h|년|억원|만원|배|건|명|쪽|p)"
    r"|\bCOP\s*\d+\.?\d*"
    r"|\d+\.\d+")
SRC = re.compile(r"(?:EP|US|KR|WO|JP)\s?\d[\d\-/,]*\s?[A-Z]?\d?"      # 특허번호
                 r"|[A-Z][A-Za-z]+\s+\d+\(\d+\)\s*\d+"                # 저널 권(호) 쪽
                 r"|RS-\d{4}-\d+"                                     # 과제번호
                 r"|\(EU\)\s*\d{4}/\d+"                               # EU 규정 번호
                 r"|\d+\s*FR\s*\d+"                                   # Federal Register
                 r"|arXiv[:\s]*\d{4}\.\d{4,5}"
                 r"|PMC\d+")
DATE = re.compile(r"20\d{2}[.\-]\d{1,2}[.\-]\d{1,2}|20\d{2}년\s?\d{1,2}월")
DASH = re.compile("[‒-―]")


# ── 문제 목록 ──────────────────────────────────────────────────────────────
def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _unquote(s: str) -> str:
    s = s.strip()
    while s and s[0] in "「『\"'“‘" and s[-1] in "」』\"'”’":
        s = s[1:-1].strip()
    return s.strip("…").strip()


def parse_problems(text: str) -> list[dict]:
    """`| # | 절 | 원문 인용 | 문제 | 이유 | …` 행. 머리 행·구분 행·번호 없는 행은 건너뛴다. 넷째 열 뒤의 열(제안 등)은 버린다."""
    rows = []
    for ln in text.splitlines():
        if not ln.strip().startswith("|") or re.match(r"^\|\s*:?-{3}", ln.strip()):
            continue
        c = _cells(ln)
        if len(c) < 5 or not re.match(r"^\d+$", c[0]):
            continue
        rows.append({"id": c[0], "section": c[1], "quote": _unquote(c[2]), "problem": c[3], "why": c[4]})
    return rows


def judge_problems(rows: list[dict], md: str) -> list[dict]:
    flat = re.sub(r"\s+", " ", md)
    out = []
    for r in rows:
        q = re.sub(r"\s+", " ", r["quote"])
        n = flat.count(q) if q else 0
        out.append({**r, "status": "유효" if n == 1 else f"기각: 인용 {n}회"})
    return out


def run_problems(path: str, md_path: str, out_json: str | None) -> list[dict]:
    rows = judge_problems(parse_problems(io.open(path, encoding="utf-8").read()), io.open(md_path, encoding="utf-8").read())
    head = [ln for ln in io.open(path, encoding="utf-8").read().splitlines() if ln.startswith("#")][:1] or ["# 외부 교정 문제 목록"]
    L = head + ["", "| # | 절 | 원문 인용 | 문제 | 이유 | 판정 |", "|---|---|---|---|---|---|"]
    cell = lambda s: (s or "").replace("|", "／")
    for r in rows:
        L.append(f"| {r['id']} | {cell(r['section'])} | {cell(r['quote'])} | {cell(r['problem'])} | {cell(r['why'])} | {r['status']} |")
    io.open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    if out_json:
        json.dump([r for r in rows if r["status"] == "유효"], io.open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rows


# ── 전후 손실 검사 (기존) ───────────────────────────────────────────────────
def before_after(before: str, after: str) -> int:
    b, c = io.open(before, encoding="utf-8").read(), io.open(after, encoding="utf-8").read()
    bad = []
    print("=" * 66)
    print("교정본 검사: 지우면 안 되는 것이 지워졌는가")
    print("=" * 66)
    from collections import Counter
    for label, rx in (("수치", NUM), ("출처", SRC)):
        cb, cc = Counter(rx.findall(b)), Counter(rx.findall(c))
        gone = sorted(k for k in cb if cc[k] == 0)
        fewer = sorted((k, cb[k], cc[k]) for k in cb if 0 < cc[k] < cb[k])
        print(f"  {label} 소멸{'':<6}{len(gone):>4}건  {'OK' if not gone else '★손실'}")
        if gone:
            print(f"     사라진 것: {' · '.join(gone[:10])}" + (" …" if len(gone) > 10 else ""))
            bad.append(f"{label} {len(gone)}건 소멸")
        if fewer:
            print(f"  {label} 횟수↓{'':<5}{len(fewer):>4}건  검토")
            print("     " + " · ".join(f"{k} {x}→{y}" for k, x, y in fewer[:6]))
    LEAD = re.compile(r"^- ", re.M)
    SLOT = re.compile(r"^  - ", re.M)
    for label, rx in (("리드 □", LEAD), ("슬롯 ○", SLOT)):
        nb, nc = len(rx.findall(b)), len(rx.findall(c))
        ok = nb == nc
        print(f"  {label:<10}{nb:>4} → {nc:<4} {'OK' if ok else '★변동'}")
        if not ok:
            bad.append(f"{label} {nb}→{nc}")
    BROKEN = re.compile("\\|\\s*[:‒-―-]\\s*\\|")
    for label, rx, limit in (("대시류", DASH, 0), ("연월일 표기", DATE, 0), ("깨진 표 칸", BROKEN, 0)):
        n = len(rx.findall(c))
        print(f"  {label:<10}{n:>4}건  {'OK' if n <= limit else '★위반'}")
        if n > limit:
            bad.append(f"{label} {n}건")
    print()
    if bad:
        print("FAIL: " + " · ".join(bad))
        print("이 교정본은 채택하지 않는다. 지적된 항목을 되살린 뒤 다시 검사한다.")
        return 2
    print("PASS: 지워진 것 없음. 조립해서 게이트로 넘겨도 된다.")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", help="60_교정문제.md: 외부 모델이 준 문제 목록")
    ap.add_argument("--md", help="원고 (인용 대조)")
    ap.add_argument("--out", help="유효 문제 JSON (교정 회차 편집자 입력)")
    ap.add_argument("--before", help="원본 원고 (전후 손실 검사)")
    ap.add_argument("--after", help="교정본 (전후 손실 검사)")
    a = ap.parse_args()
    if a.problems:
        if not a.md:
            ap.error("--problems 에는 --md 가 필요하다")
        rows = run_problems(a.problems, a.md, a.out)
        ok = sum(r["status"] == "유효" for r in rows)
        for r in rows:
            print(f"  [{r['status']}] #{r['id']:<3} {r['section']:<4} {r['problem'][:50]}")
        print(f"문제 {len(rows)}건 · 유효 {ok} · 기각 {len(rows) - ok}" + (f" → {a.out}" if a.out else ""))
        return 0 if rows else 2
    if a.before and a.after:
        return before_after(a.before, a.after)
    ap.error("--problems 또는 --before/--after 가 필요하다")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
