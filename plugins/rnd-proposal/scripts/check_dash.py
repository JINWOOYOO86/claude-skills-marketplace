# -*- coding: utf-8 -*-
"""대시류 문자 검사 (rubric S-m5, 사용자 고정 요건 2026-09-27).

연구계획서 최종 hwpx(본문·표 셀·요약문 표 전부)와 원고 md 에 대시류 문자가 하나도 없어야 한다.

    python check_dash.py --hwpx <out.hwpx>        # section0.xml 의 <hp:t> 텍스트 전부
    python check_dash.py --md   <30_proposal.md>  # 원고(집필자 자가 검사용)

대상 문자: U+2012 ‒ · U+2013 – · U+2014 — · U+2015 ―
대상 아님: U+2212 −(수학 마이너스, 「−7 ℃」) · ASCII 하이픈 -
0 이면 exit 0, 하나라도 있으면 exit 2. 치환은 dash_replace.py 가 한다(조립 직전).
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile

DASHES = "‒–—―"
DASH_RE = re.compile("[" + DASHES + "]")
NAMES = {"‒": "U+2012 figure dash", "–": "U+2013 en dash",
         "—": "U+2014 em dash", "―": "U+2015 horizontal bar"}
CTX = 20


def find_in_text(text: str) -> list[dict]:
    """줄 단위. 반환: [{line, ch, name, context}]"""
    out = []
    for i, ln in enumerate(text.splitlines(), 1):
        for m in DASH_RE.finditer(ln):
            s = max(0, m.start() - CTX)
            out.append({"line": i, "ch": m.group(0), "name": NAMES[m.group(0)],
                        "context": ln[s:m.end() + CTX].strip()})
    return out


def _para_texts(section_xml: str) -> list[tuple[str, bool]]:
    """(문단 텍스트, 표 안 여부). hp:p 안의 hp:t 를 이어 붙인다."""
    tbl_spans = [(m.start(), m.end()) for m in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", section_xml, re.S)]

    def in_tbl(pos):
        return any(a <= pos < b for a, b in tbl_spans)

    out = []
    for m in re.finditer(r"<hp:p\b.*?</hp:p>", section_xml, re.S):
        t = "".join(x for x in re.findall(r"<hp:t\b[^>]*>(.*?)</hp:t>", m.group(0), re.S))
        t = re.sub(r"<[^>]+>", "", t)
        t = (t.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
              .replace("&apos;", "'").replace("&amp;", "&"))
        if t:
            out.append((t, in_tbl(m.start())))
    return out


def find_in_hwpx(path: str) -> list[dict]:
    """반환: [{para, in_table, ch, name, context}]"""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)]
        xml = "".join(z.read(n).decode("utf-8", "replace") for n in sorted(names))
    out = []
    for i, (t, tbl) in enumerate(_para_texts(xml), 1):
        for m in DASH_RE.finditer(t):
            s = max(0, m.start() - CTX)
            out.append({"para": i, "in_table": tbl, "ch": m.group(0), "name": NAMES[m.group(0)],
                        "context": t[s:m.end() + CTX].strip()})
    return out


def summarize(hits: list[dict]) -> str:
    if not hits:
        return "대시류 0"
    by = {}
    for h in hits:
        by[h["name"]] = by.get(h["name"], 0) + 1
    tbl = sum(1 for h in hits if h.get("in_table"))
    return f"대시류 {len(hits)}개 (" + " · ".join(f"{k} {v}" for k, v in by.items()) + (f" · 표 안 {tbl}" if tbl else "") + ")"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx")
    ap.add_argument("--md")
    ap.add_argument("--max-show", type=int, default=30)
    a = ap.parse_args()
    if not a.hwpx and not a.md:
        ap.error("--hwpx 또는 --md")
    hits = []
    if a.hwpx:
        hits += find_in_hwpx(a.hwpx)
    if a.md:
        hits += find_in_text(io.open(a.md, encoding="utf-8").read())
    print("=" * 66)
    print("대시류 문자 검사 (S-m5): 부연은 괄호, 구분은 콜론, 범위는 ~, 빈 칸은 「해당 없음」")
    print("=" * 66)
    for h in hits[: a.max_show]:
        where = f"문단 {h['para']}" + (" (표 안)" if h.get("in_table") else "") if "para" in h else f"{h['line']}행"
        print(f"  [{h['name']}] {where}: …{h['context']}…")
    if len(hits) > a.max_show:
        print(f"  … 외 {len(hits) - a.max_show}건")
    print(("FAIL: " if hits else "PASS: ") + summarize(hits))
    return 2 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
