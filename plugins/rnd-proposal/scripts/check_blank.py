# -*- coding: utf-8 -*-
"""「0」을 「해당 없음」으로 적은 칸 검사 (rubric C-m6, plan_v2 2026-09-28).

80_비교검증 퇴행 (a) 5: t3 성과지표 표의 기준값이 「해당 없음 → 4건」「해당 없음 → 1,000시간 → 약 9,000시간」
으로 적혀 「기준값이 없다」로 읽혔다. 원본은 「0 → 4」였다. 대시 금지 규칙의 「빈 칸은 해당 없음」이
기준값 0 에까지 번진 결과다(rp-spec 설계서 §2).

    python check_blank.py --md <30_proposal.build.md>
    python check_blank.py --hwpx <out.hwpx>

잡는 것:
  1) 「해당 없음 →」: 화살표 앞은 기준값(출발값)이다. 출발값이 없다는 뜻이면 0 이다.
  2) 표 머리가 기준값·현재·실적·보유·건수 열인 칸이 「해당 없음」뿐인 경우.
진짜 빈 칸(값이 존재하지 않는 칸, 예: 해당 연차에 없는 행)은 「해당 없음」 그대로 둔다.
0 이면 exit 0, 하나라도 있으면 exit 2.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ZERO_COLS = re.compile(r"기준값|현재\s*수준|현재값|실적|보유|건수")
ARROW = re.compile(r"해당\s*없음\s*(?:→|->|⇒)")


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def check_text(text: str) -> tuple[bool, list[str], list[str]]:
    """반환: (ok, 문제 목록, 절 id 목록)."""
    probs, secs, sec = [], [], ""
    lines = text.splitlines()
    head = None
    for i, ln in enumerate(lines):
        h = re.match(r"^#{2,4}\s+(\d(?:-\d+)?)\.\s", ln)
        if h:
            sec = h.group(1)
        if not ln.startswith("|"):
            head = None
            continue
        if head is None:
            head = _cells(ln)
            continue
        if re.match(r"^\|\s*:?-{3}", ln):
            continue
        row = _cells(ln)
        for j, c in enumerate(row):
            col = head[j] if j < len(head) else ""
            if ARROW.search(c) or (ZERO_COLS.search(col) and re.fullmatch(r"해당\s*없음", c)):
                probs.append(f"{sec}절 {i + 1}행 「{col or '표'}」 칸: {c[:30]}")
                secs.append(sec)
    for i, ln in enumerate(lines):
        if not ln.startswith("|") and ARROW.search(ln):
            probs.append(f"{i + 1}행: {ln.strip()[:40]}")
    return (not probs), probs, sorted(set(s for s in secs if s))


def check_hwpx(path: str):
    from hwpx_text import hwpx_to_md
    return check_text(hwpx_to_md(path))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--md")
    ap.add_argument("--hwpx")
    a = ap.parse_args()
    if not (a.md or a.hwpx):
        ap.error("--md 또는 --hwpx")
    ok, probs, _ = check_hwpx(a.hwpx) if a.hwpx else check_text(open(a.md, encoding="utf-8").read())
    for p in probs:
        print("  " + p)
    print(("PASS" if ok else "FAIL") + f": 0 을 뜻하는 칸의 「해당 없음」 {len(probs)}건")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
