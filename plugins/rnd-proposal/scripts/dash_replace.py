# -*- coding: utf-8 -*-
"""대시류 문자 치환 (조립 직전, 결정적·멱등). rubric S-m5 의 짝.

사용자 규칙(2026-09-27): 부연은 괄호, 구분은 콜론, 범위는 ~, 빈 칸은 「해당 없음」.

    python dash_replace.py --in <파일…> [--ledger <원장.md>] [--dry]

규칙은 이 순서로 줄마다 적용한다.
  1 범위     숫자 대시 숫자                        → 숫자~숫자
  2 빈 칸    표 셀 내용이 대시뿐                    → 해당 없음      (진짜 빈 칸 `|  |` 은 그대로)
             단 머리가 기준값·실적·건수 열인 칸은    → 0              (값이 0 이라는 뜻, C-m6 2026-09-28)
  3 구분     글머리·제목·번호·인용·표 셀 첫머리의 라벨 뒤 ` 대시 ` → 라벨: 내용 (산문 줄은 규칙 4)
  4 부연     문장 중간 ` 대시 X`                   → (X)           X 는 줄·셀·문장 끝까지
  5 연결     공백 없는 낱말 사이 대시(R1234yf–압축기유) → 가운뎃점 ·     (추가 규칙, 계획 D-2)
  6 잔여     그 밖의 대시                          → 공백 있으면 콜론, 없으면 가운뎃점
대상 문자는 check_dash.DASHES 와 같다(U+2212 − 와 하이픈은 손대지 않는다).
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

DASHES = "‒–—―"
D = "[" + DASHES + "]"
CLOSERS = "」』\"'`"      # 」 』 " ' ` : 부연 X 는 이 닫는 기호 앞에서 끝난다
RULES = {
    1: ("범위", re.compile(r"(\d[\d,.]*)\s*" + D + r"\s*(?=\d)")),
    2: ("빈 칸", re.compile(r"(?<=\|)(\s*)" + D + r"+(\s*)(?=\|)")),
    3: ("구분", re.compile(r"^(\s*(?:[-*+]\s+|#{1,6}\s+|\d+[.)]\s+|>\s+|\|\s*))([^" + DASHES + r":：|]{1,60}?)\s+" + D + r"\s+")),
    4: ("부연", re.compile(r"\s+" + D + r"\s+([^|)\]" + CLOSERS + DASHES + r"]+?)(?=\s*(?:[.;。]\s|[.;。]$|[|)\]" + CLOSERS + r"]|$))")),
    5: ("연결", re.compile(r"(?<=[^\s\d" + DASHES + r"])" + D + r"(?=[^\s\d" + DASHES + r"])")),
    6: ("잔여", re.compile(D)),
}


LABEL_RULE3 = re.compile(r"^(\s*)([^" + DASHES + r":：|]{1,60}?)\s+" + D + r"\s+")   # label_lines: 글머리 없어도 라벨로 본다


def replace_line(ln: str, label_lines: bool = False) -> tuple[str, list[tuple[int, str, str]]]:
    """한 줄 치환. 반환: (새 줄, [(규칙 번호, 전, 후)]). label_lines: 줄 첫머리를 항상 라벨로 본다(양식 명세 문자열용)."""
    log = []
    if not re.search(D, ln):
        return ln, log
    before = ln
    ln = RULES[1][1].sub(lambda m: m.group(1) + "~", ln)
    ln = RULES[2][1].sub(lambda m: m.group(1) + "해당 없음" + m.group(2), ln)
    ln = RULES[3][1].sub(lambda m: m.group(1) + m.group(2) + ": ", ln)
    if label_lines:
        ln = LABEL_RULE3.sub(lambda m: m.group(1) + m.group(2) + ": ", ln)
    def _paren(m):
        x = m.group(1).strip()
        if x.startswith("("):                          # 이미 괄호로 시작하면 대시만 뺀다(겹치지 않는다)
            return " " + m.group(1).strip()
        return " (" + x + ")"
    ln = RULES[4][1].sub(_paren, ln)
    ln = RULES[5][1].sub("·", ln)
    ln = re.sub(r"\s*" + D + r"\s*", lambda m: ": " if " " in m.group(0) else "·", ln)
    if ln != before:
        # 어느 규칙이 적용됐는지는 전/후 차이로 기록한다(한 줄에 여러 규칙이 겹칠 수 있다)
        rule = _dominant_rule(before)
        log.append((rule, before, ln))
    return ln, log


ZERO_COLS = re.compile(r"기준값|현재\s*수준|현재값|실적|보유|건수")   # check_blank.ZERO_COLS 와 같다


def _zero_cells(row: str, head: list[str]) -> str:
    """규칙 2 앞: 머리가 기준값·실적·건수 열인 칸이 대시뿐이면 「0」(값이 0 이라는 뜻이다. C-m6, 2026-09-28)."""
    cells = row.split("|")
    for j in range(1, len(cells) - 1):
        col = head[j - 1] if j - 1 < len(head) else ""
        if ZERO_COLS.search(col) and re.fullmatch(r"\s*" + D + r"+\s*", cells[j]):
            cells[j] = re.sub(D + "+", "0", cells[j])
    return "|".join(cells)


def _dominant_rule(before: str) -> int:
    for k in (1, 2, 3, 4, 5):
        if RULES[k][1].search(before):
            return k
    return 6


def replace_text(text: str, label_lines: bool = False) -> tuple[str, list[dict]]:
    """전체 텍스트. 반환: (새 텍스트, [{line, rule, before, after, section}])"""
    out, log, section, head = [], [], "", None
    for i, ln in enumerate(text.splitlines(keepends=True), 1):
        body = ln.rstrip("\r\n")
        if re.match(r"^#{1,6}\s+", body):
            section = re.sub(r"^#{1,6}\s+", "", body)
        head = (head or [c.strip() for c in body.strip().strip("|").split("|")]) if body.startswith("|") else None
        if head and body.startswith("|") and re.search(D, body):
            body = _zero_cells(body, head)
        new, rows = replace_line(body, label_lines)
        for rule, b, a in rows:
            log.append({"line": i, "rule": rule, "name": RULES[rule][0], "before": b.strip(), "after": a.strip(),
                        "section": section})
        out.append(new + ln[len(body):])
    return "".join(out), log


def apply_file(path: str, ledger: str | None = None, dry: bool = False) -> list[dict]:
    text = io.open(path, encoding="utf-8").read()
    new, log = replace_text(text)
    if log and not dry:
        io.open(path, "w", encoding="utf-8", newline="").write(new)
    if ledger and not dry:
        write_ledger(ledger, path, log)
    return log


def write_ledger(ledger: str, src: str, log: list[dict]) -> None:
    lines = [f"# 대시류 치환 원장: {os.path.basename(src)}", "",
             "규칙: 1 범위(~) · 2 빈 칸(해당 없음) · 3 구분(콜론) · 4 부연(괄호) · 5 연결(가운뎃점) · 6 잔여", "",
             "| # | 규칙 | 전 | 후 | 절 |", "|---|---|---|---|---|"]
    for i, r in enumerate(log, 1):
        cell = lambda s: s.replace("|", "｜")
        lines.append(f"| {i} | {r['rule']} {r['name']} | {cell(r['before'])} | {cell(r['after'])} | {cell(r['section'])} |")
    if not log:
        lines.append("| 해당 없음 | | | | |")
    io.open(ledger, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--ledger", help="치환 원장(md). 입력이 하나일 때")
    ap.add_argument("--dry", action="store_true", help="바꾸지 않고 원장만 화면에")
    a = ap.parse_args()
    total = 0
    for p in a.inputs:
        log = apply_file(p, a.ledger if len(a.inputs) == 1 else None, a.dry)
        total += len(log)
        print(f"{os.path.basename(p)}: {len(log)}줄 치환" + (" (dry)" if a.dry else ""))
        for r in log[:12]:
            print(f"  [{r['rule']} {r['name']}] {r['line']}행: {r['before'][:70]}")
            print(f"      → {r['after'][:70]}")
        if len(log) > 12:
            print(f"  … 외 {len(log) - 12}줄")
    print(f"합계 {total}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
