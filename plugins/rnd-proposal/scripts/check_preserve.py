# -*- coding: utf-8 -*-
"""정보 보존 검사: 수정 전후 비교 (rubric C-m5, plan_v2 2026-09-28).

t3 는 우리 채점기 94.5 였지만 외부 원본 대비 퇴행 42건 중 22건이 정보 삭제였다(80_비교검증 (d)).
채점기가 「있는가」만 보고 「사라졌는가」를 보지 않았기 때문이다. 이 검사는 전 판에 있던 것이
후 판에서 사라졌는지 본다.

    python check_preserve.py --before <전.md|hwpx> --after <후.md|hwpx> [--ledger 74_수정원장.md]

전 판: 수정 회차 = 직전 채택 회차, rp-revise = 외부 원본, 보정 = 외부 원본.

잡는 것 (전 판 토큰이 후 판 **어디에도** 없으면 사라진 것. 횟수 감소는 허용: 반복 제거는 정상):
  수치     숫자 토큰(쉼표 제거). 두 자리 이상 또는 소수. 단위 표기 변화(9,000 h ↔ 9,000시간)는 문제 삼지 않는다
  규격명   ISO·EN·ASHRAE·ASTM·KS·IEC·UL·AHRI + 번호
  출처     특허·저널·EU 규정·arXiv·PMC 번호 (check_proofread.SRC)
  고유명사 라틴 대문자 토큰(ECHA·REFPROP·HFO-1234yf)·물질 코드(1336mzz)·「…연구원·위원회·대학교·협회·재단」
  위험 대응 「미달이면·부적합 시·대안·차선·병행·못하면·지연되면」 문장
  산출식   「=」·「합이며」·「산출」 문장
  → 두 문장 종류는 글자 2-gram 이 후 판에 COVER_MIN 이상 남아 있어야 보존으로 본다(표현을 바꾼 것은 허용).
--ledger: 원장 행에 「의도적 제거」가 있으면 그 행 「전」 칸의 토큰은 사라져도 된다.
0 이면 exit 0, 하나라도 사라졌으면 exit 2.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_proofread import SRC  # noqa: E402

NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
STD = re.compile(r"\b(?:ISO|EN|ASHRAE(?:\s+Standard)?|ASTM|KS\s?[A-Z]?|IEC|UL|AHRI)\s*[A-Z]?\d{2,}[\d.\-]*")
LATIN = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9\-]*|(?<![A-Za-z0-9])[A-Z]{2,}(?:-\d+[a-z]*)?")
CODE = re.compile(r"(?<![\d\w])\d{3,4}[a-z]{2,3}\b")
ORG = re.compile(r"[가-힣]{2,}(?:연구원|위원회|대학교|협회|재단)")
RISK = re.compile(r"미달이면|미달\s*시|부적합\s*시|대안|차선|병행|못하면|지연되면")
FORMULA = re.compile(r"=|합이며|산출")
COVER_MIN = 0.6
# 문서 어디에나 있는 라틴 토큰(판정 신호가 아님)
LATIN_SKIP = {"WP", "KPI", "TRL", "DB", "AI", "GWP", "COP", "EU"}


def _text(path: str) -> str:
    if path.lower().endswith(".hwpx"):
        from hwpx_text import hwpx_to_md
        return hwpx_to_md(path)
    return open(path, encoding="utf-8").read()


def _nk(x: str) -> str:
    return re.sub(r"[\s,]", "", x).replace("Standard", "")


def _sections(text: str):
    sec = ""
    for ln in text.splitlines():
        h = re.match(r"^#{2,4}\s+(\d(?:-\d+)?)\.\s", ln)
        if h:
            sec = h.group(1)
        yield sec, ln


def tokens(text: str) -> dict:
    """{종류: {정규화 토큰: (원문, 절)}}"""
    out = {k: {} for k in ("수치", "규격명", "출처", "고유명사")}
    for sec, ln in _sections(text):
        if ln.startswith("#"):
            continue
        for m in NUM.finditer(ln):
            v = m.group(0).replace(",", "")
            if len(v.replace(".", "")) >= 2 or "." in v:
                out["수치"].setdefault(v, (m.group(0), sec))
        for m in STD.finditer(ln):
            out["규격명"].setdefault(_nk(m.group(0)), (m.group(0), sec))
        for m in SRC.finditer(ln):
            out["출처"].setdefault(_nk(m.group(0)), (m.group(0), sec))
        for rx in (LATIN, CODE, ORG):
            for m in rx.finditer(ln):
                w = m.group(0)
                if w not in LATIN_SKIP and not STD.fullmatch(w):
                    out["고유명사"].setdefault(_nk(w), (w, sec))
    return out


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def sentences(text: str) -> dict:
    """{"위험 대응": [(문장, 절)], "산출식": [...]}  개조식 항목·표 행 단위."""
    out = {"위험 대응": [], "산출식": []}
    for sec, ln in _sections(text):
        s = re.sub(r"^\s*-\s*", "", ln).strip()
        if not s or s.startswith("#") or s.startswith("|"):
            continue
        if RISK.search(s):
            out["위험 대응"].append((s, sec))
        if FORMULA.search(s) and NUM.search(s):
            out["산출식"].append((s, sec))
    return out


def _ledger_exempt(path: str | None) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    ex = set()
    for ln in open(path, encoding="utf-8"):
        if ln.startswith("|") and "의도적 제거" in ln:
            for kind in tokens(ln).values():
                ex |= set(kind)
    return ex


def compare(before: str, after: str, ledger: str | None = None) -> dict:
    """반환: {"lost": {종류: [(원문, 절)]}, "ok": bool, "sections": [절]}"""
    tb, ta = tokens(before), tokens(after)
    exempt = _ledger_exempt(ledger)
    flat_after = re.sub(r"[\s,]", "", after).replace("Standard", "")
    lost = {}
    for kind, d in tb.items():
        gone = [(orig, sec) for k, (orig, sec) in d.items()
                if k not in ta[kind] and k not in flat_after and k not in exempt]
        if gone:
            lost[kind] = gone
    bg_after = _bigrams(after)
    for kind, items in sentences(before).items():
        gone = []
        for s, sec in items:
            bg = _bigrams(s)
            if bg and len(bg & bg_after) / len(bg) < COVER_MIN:
                gone.append((s[:50], sec))
        if gone:
            lost[kind] = gone
    secs = sorted({sec for v in lost.values() for _, sec in v if sec})
    return {"lost": lost, "ok": not lost, "sections": secs}


def summarize(res: dict) -> str:
    if res["ok"]:
        return "사라진 정보 0"
    return "사라진 정보 " + " · ".join(f"{k} {len(v)}" for k, v in res["lost"].items())


def check_paths(before: str, after: str, ledger: str | None = None) -> dict:
    return compare(_text(before), _text(after), ledger)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--ledger")
    ap.add_argument("--max-show", type=int, default=8)
    a = ap.parse_args()
    res = check_paths(a.before, a.after, a.ledger)
    for kind, items in res["lost"].items():
        print(f"  [{kind}] {len(items)}건: " + " · ".join(f"{t}({s})" for t, s in items[: a.max_show])
              + (" …" if len(items) > a.max_show else ""))
    print(("PASS" if res["ok"] else "FAIL") + ": " + summarize(res))
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
