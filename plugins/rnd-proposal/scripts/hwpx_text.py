# -*- coding: utf-8 -*-
"""hwpx 본문을 원고 md 꼴로 되돌린다 (plan_v2 1단계, 2026-09-28).

블라인드 비교·정보 보존 검사·외부 원본 채점(check_rubric --md)·rp-revise 가 같은 추출을 쓴다.
서식 정보는 버리고 글과 표 구조만 남긴다.

    python hwpx_text.py <in.hwpx> [--out <out.md>] [--plain]

변환 규칙 (harness_assemble 의 md → hwpx 를 거꾸로):
  요약문 앞 첫 문단 또는 1열 제목 상자 → `# 과제명`
  `N. 제목`                          → `## N. 제목`
  `N-N. 제목`                        → `### N-N. 제목`
  `□ 글`                             → `- 글`
  `○ 글`                             → `  - 글`
  `- 글`·`‐ 글`·`· 글`(셋째 단계)       → `    - 글`
  표                                 → `| 칸 | 칸 |` 행 (첫 행 뒤 `|---|`), 셀 안 여러 문단은 ` / ` 로 잇는다
--plain 이면 글머리·제목 표지를 붙이지 않고 문단 텍스트만 한 줄씩 쓴다(블라인드 전송용이 아니라 대조용).
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _run_text(t_el) -> str:
    # hp:t 안에는 글 외에 hp:tab·hp:lineBreak 같은 자식이 섞인다.
    out = [t_el.text or ""]
    for ch in t_el:
        name = _local(ch.tag)
        if name == "tab":
            out.append(" ")
        elif name == "lineBreak":
            out.append(" ")
        out.append(ch.tail or "")
    return "".join(out)


def _para_items(p) -> list:
    """문단 하나를 [("text", str) | ("table", rows)] 로. 표는 문단의 run 안에 들어 있다."""
    items, buf = [], []
    for run in p:
        if _local(run.tag) != "run":
            continue
        for el in run:
            name = _local(el.tag)
            if name == "t":
                buf.append(_run_text(el))
            elif name == "tbl":
                if "".join(buf).strip():
                    items.append(("text", "".join(buf)))
                buf = []
                items.append(("table", _table_rows(el)))
    if "".join(buf).strip():
        items.append(("text", "".join(buf)))
    return items


def _cell_text(tc) -> str:
    parts = []
    for sub in tc:
        if _local(sub.tag) != "subList":
            continue
        for p in sub:
            if _local(p.tag) != "p":
                continue
            for kind, val in _para_items(p):
                if kind == "text":
                    parts.append(val.strip())
                else:  # 셀 안 표는 드물다: 행을 ; 로 이어 글로 편다
                    parts.append(" ; ".join(" , ".join(r) for r in val))
    return " / ".join(x for x in parts if x)


def _table_rows(tbl) -> list[list[str]]:
    rows = []
    for tr in tbl:
        if _local(tr.tag) != "tr":
            continue
        rows.append([_cell_text(tc) for tc in tr if _local(tc.tag) == "tc"])
    return rows


def read_items(path: str) -> list:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n))
        items = []
        for n in names:
            root = ET.fromstring(z.read(n))
            for p in root:
                if _local(p.tag) == "p":
                    items.extend(_para_items(p))
    return items


def _cell(s: str) -> str:
    return s.replace("|", "／").replace("\n", " ").strip()


def to_md(items: list, plain: bool = False) -> str:
    out, titled = [], False
    for kind, val in items:
        if kind == "table":
            if not val:
                continue
            if not titled and not plain and max(len(r) for r in val) == 1:
                # 요약문 앞 1열 표 = 양식의 제목 상자
                t = " ".join(c.strip() for r in val for c in r if c.strip())
                if t and not any(x.startswith("# ") for x in out):
                    out += ["# " + t, ""]
                continue
            w = max(len(r) for r in val)
            out.append("")
            for i, r in enumerate(val):
                r = r + [""] * (w - len(r))
                out.append("| " + " | ".join(_cell(c) for c in r) + " |")
                if i == 0:
                    out.append("|" + "---|" * w)
            out.append("")
            continue
        t = re.sub(r"\s+", " ", val).strip()
        if not t:
            continue
        if plain:
            out.append(t)
            continue
        if re.match(r"^\d-\d+\.\s", t):
            out += ["", "### " + t, ""]
        elif re.match(r"^\d\.\s", t):
            titled = True
            out += ["", "## " + t, ""]
        elif not titled and not any(x.startswith("# ") for x in out):
            out += ["# " + t, ""]
        elif t[0] == "□":
            out.append("- " + t[1:].strip())
        elif t[0] == "○":
            out.append("  - " + t[1:].strip())
        elif re.match(r"^[-‐·]\s", t):
            out.append("    - " + t[2:].strip())
        else:
            out.append(t)
    md = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


def hwpx_to_md(path: str, plain: bool = False) -> str:
    return to_md(read_items(path), plain)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("hwpx")
    ap.add_argument("--out")
    ap.add_argument("--plain", action="store_true")
    a = ap.parse_args()
    md = hwpx_to_md(a.hwpx, a.plain)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
        print(f"[hwpx_text] {a.out} ({len(md):,}자)")
    else:
        print(md, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
