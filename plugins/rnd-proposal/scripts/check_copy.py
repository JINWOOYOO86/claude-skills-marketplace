# -*- coding: utf-8 -*-
"""문체 예시 원본 복사 검사 (rubric S-m7, plan_v2 5단계 16, 2026-09-28).

집필 brief 는 skills/rp-run/style_patterns.md(고유명사·수치를 가린 문장 틀)를 준다. 그 틀의 원본(사람이 다듬은
제출본)과 원고가 **8어절 이상 연속으로 같으면** 예시를 베낀 것으로 본다. 근거팩에도 있는 8어절 묶음은 빼고 센다
(같은 근거에서 나온 고유명·지표명은 베낀 것이 아니다).

    python check_copy.py --md <원고 md 또는 hwpx> --ref <원본 md 또는 hwpx> [--pack <근거팩 폴더>]

원본은 공개 저장소에 두지 않는다: rubric 은 criteria 폴더의 style_ref.md(원본을 hwpx_text 로 뽑은 것)를 쓴다.
줄(표는 칸, 칸 안의 「 / 」 구분) 경계를 넘는 묶음은 세지 않는다. 제목 줄은 빼고, 과제명(원고 첫 # 줄)과
같은 묶음도 뺀다(과제명은 주어진 값이다).
0 이면 exit 0, 있으면 exit 2.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

N = 8
PUNCT = "()[]{}「」『』<>,.;:·\"'`*"


def _load(path: str) -> str:
    if path.lower().endswith(".hwpx"):
        from hwpx_text import hwpx_to_md
        return hwpx_to_md(path)
    return open(path, encoding="utf-8").read()


def units(text: str) -> list[tuple[str, list[str]]]:
    """(절, 어절 목록) 단위: 개조식 한 줄 또는 표 한 칸. 제목·구분선은 뺀다."""
    out, sec = [], ""
    for ln in text.splitlines():
        h = re.match(r"^#{1,4}\s+(\d(?:-\d+)?)?", ln)
        if h:
            sec = h.group(1) or sec
            continue
        if re.match(r"^\|\s*:?-{3}", ln):
            continue
        parts = ln.strip().strip("|").split("|") if ln.lstrip().startswith("|") else [ln]
        parts = [q for p in parts for q in p.split(" / ")]
        for p in parts:
            p = re.sub(r"^\s*(?:-\s+|[□○ㅇ]\s*)", "", p)
            words = [w.strip(PUNCT) for w in p.split()]
            words = [w for w in words if w]
            if len(words) >= N:
                out.append((sec, words))
    return out


def grams(text: str) -> set[tuple[str, ...]]:
    g = set()
    for _, w in units(text):
        g.update(tuple(w[i:i + N]) for i in range(len(w) - N + 1))
    return g


def pack_text(pack: str | None) -> str:
    if not pack or not os.path.isdir(pack):
        return ""
    return "\n".join(open(f, encoding="utf-8", errors="ignore").read()
                     for f in glob.glob(os.path.join(pack, "**", "*.md"), recursive=True))


def check_text(text: str, ref: str, pack: str = "") -> tuple[bool, list[str], list[str]]:
    """반환: (ok, 문제 목록(원고 줄마다 한 건), 절 id 목록)."""
    title = "\n".join(re.sub(r"^#\s+", "- ", ln) for ln in text.splitlines() if re.match(r"^#\s", ln))
    shared = grams(ref) - grams(pack) - grams(title)
    probs, secs = [], []
    for sec, w in units(text):
        hit = [i for i in range(len(w) - N + 1) if tuple(w[i:i + N]) in shared]
        if hit:
            i = hit[0]
            probs.append(f"{sec}절: {' '.join(w[i:i + N])}")
            secs.append(sec)
    return (not probs), probs, sorted(set(s for s in secs if s))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--pack")
    a = ap.parse_args()
    ok, probs, _ = check_text(_load(a.md), _load(a.ref), pack_text(a.pack))
    for p in probs:
        print("원본과 8어절 일치:", p)
    print(f"S-m7 {'통과' if ok else '실패'}: {len(probs)}줄")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
