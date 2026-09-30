# -*- coding: utf-8 -*-
"""제목 위계 굵게 검사 (rubric F-m9, plan_v2 2026-09-28).

11pt 통일(style.uniform_font_pt) 뒤에는 굵게가 제목의 유일한 표지다. t3·외부 원본은 장 제목(「1. …」)
charPr 에 굵게가 없어 본문과 구분되지 않았다(82_외과수정 #1~#5 에서 손으로 charPr 7 로 바꿈).

    python check_headings.py --hwpx <out.hwpx> [--spec 50_form_spec.json]

위계: 장 제목 `^\\d\\.\\s`, 절 제목 `^\\d-\\d+\\.\\s`. 문단의 모든 글자 run 이 가리키는 charPr 에 <hh:bold/> 가 있어야 한다.
기대값은 50_form_spec style.heading_bold ({"h2": true, "h3": true}) 로 바꿀 수 있다(없으면 둘 다 true).
0 이면 exit 0, 하나라도 있으면 exit 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile

LEVELS = (("h2", re.compile(r"^\d\.\s")), ("h3", re.compile(r"^\d-\d+\.\s")))


def check_hwpx(path: str, spec: dict | None = None) -> tuple[bool, list[str]]:
    want = {"h2": True, "h3": True}
    want.update(((spec or {}).get("style") or {}).get("heading_bold") or {})
    with zipfile.ZipFile(path) as z:
        header = z.read("Contents/header.xml").decode("utf-8")
        sec = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                      if re.match(r"Contents/section\d+\.xml$", n))
    bold = {m.group(1): "<hh:bold" in m.group(0)
            for m in re.finditer(r'<hh:charPr id="(\d+)".*?</hh:charPr>', header, re.S)}
    probs, seen = [], {"h2": 0, "h3": 0}
    for p in re.findall(r"<hp:p\b.*?</hp:p>", sec, re.S):
        if "<hp:tbl" in p:
            continue
        t = "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", p)).strip()
        for lv, rx in LEVELS:
            if not rx.match(t):
                continue
            seen[lv] += 1
            runs = [m.group(1) for m in re.finditer(r'<hp:run charPrIDRef="(\d+)"[^>]*>\s*<hp:t>', p)]
            if want.get(lv) and not all(bold.get(c) for c in runs):
                probs.append(f"{'장' if lv == 'h2' else '절'} 제목 굵게 아님: {t[:24]} (charPr {','.join(runs)})")
    return (not probs), probs


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--spec")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8")) if a.spec else {}
    ok, probs = check_hwpx(a.hwpx, spec)
    for p in probs:
        print("  " + p)
    print(("PASS" if ok else "FAIL") + f": 제목 위계 굵게 (문제 {len(probs)}건)")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
