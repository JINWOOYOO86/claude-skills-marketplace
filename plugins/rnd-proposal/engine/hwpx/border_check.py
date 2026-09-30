# -*- coding: utf-8 -*-
"""표 셀 테두리 검사 — 모든 표 셀의 네 변이 SOLID 인가 (결함 B 게이트, 2026-09-26).

    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.hwpx.border_check --hwpx out.hwpx
        [--allow-types SOLID,DOUBLE_SLIM] [--allow-ids 14,22] [--json]

exit: 0 위반 없음 / 1 표 수준(hp:tbl) 테두리만 비SOLID (경고) / 2 셀 위반

왜 따로 두나
-----------
조립 경로가 둘이다 — 엔진(`build_hwpx`)과 kordoc(`harness_assemble`). 둘 다 이 모듈을
불러 같은 규칙으로 잰다. 실측(2026-09-26): 엔진 경로 산출물은 셀 211개 중 99개가
DASH(id 19), kordoc 경로 산출물은 머리행 경계 62개가 DOUBLE_SLIM 이었다. 둘 다 사람 눈에는
「표 선이 들쭉날쭉하다」로 보이고 양식 일관성 감점 사유다.

stdlib 만 쓴다 — harness_assemble 은 플러그인 밖에서도 단독 실행되기 때문이다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass, asdict
from xml.etree import ElementTree as ET

HH = "http://www.hancom.co.kr/hwpml/2011/head"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
SIDES = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


@dataclass
class Violation:
    section: str
    tbl_idx: int          # 그 섹션 안에서 몇 번째 표인가 (1-base)
    tbl_id: str
    row: int
    col: int
    bf_id: str
    types: tuple

    def __str__(self) -> str:
        return (f"{self.section} 표{self.tbl_idx}(id {self.tbl_id}) "
                f"(r{self.row},c{self.col}) bf={self.bf_id} {'/'.join(self.types)}")


def border_types(header_xml: bytes) -> dict[str, tuple]:
    """borderFill id → (l, r, t, b) 선 종류. type 속성이 없으면 SOLID 로 본다."""
    root = ET.fromstring(header_xml)
    out = {}
    for bf in root.iter(f"{{{HH}}}borderFill"):
        types = []
        for side in SIDES:
            el = bf.find(f"{{{HH}}}{side}")
            types.append((el.get("type") or "SOLID") if el is not None else "SOLID")
        out[bf.get("id")] = tuple(types)
    return out


def cell_border_violations(header_xml: bytes, section_xml: bytes, *,
                           section_name: str = "section0",
                           allow_types: frozenset = frozenset({"SOLID"}),
                           allow_ids: frozenset = frozenset(),
                           exempt_tbl_ids: frozenset = frozenset()
                           ) -> tuple[list[Violation], list[Violation]]:
    """(셀 위반, 표 수준 위반).

    셀 위반: hp:tc 의 borderFillIDRef 가 가리키는 항목의 네 변 중 allow_types 밖이 하나라도 있음.
    표 위반: hp:tbl 자체의 borderFillIDRef — 한글은 셀 값을 우선 그리므로 경고로만 다룬다.
    header 에 없는 id 는 여기서 세지 않는다(참조 무결성은 L2 몫).
    exempt_tbl_ids: 양식 원본 그대로 실은 첫머리 표(제목 상자·개요표)의 hp:tbl@id.
    """
    types = border_types(header_xml)
    root = ET.fromstring(section_xml)
    cells, tbls = [], []
    # 중첩 표는 바깥 표를 순회할 때 안쪽 셀까지 섞이지 않게, 각 표의 직계 tr/tc 만 본다.
    for i, tbl in enumerate(root.iter(f"{{{HP}}}tbl"), start=1):
        tid = tbl.get("id") or "?"
        if tid in exempt_tbl_ids:
            continue
        tb = tbl.get("borderFillIDRef")
        if tb in types and tb not in allow_ids and any(t not in allow_types for t in types[tb]):
            tbls.append(Violation(section_name, i, tid, -1, -1, tb, types[tb]))
        for tr in tbl.findall(f"{{{HP}}}tr"):
            for tc in tr.findall(f"{{{HP}}}tc"):
                bid = tc.get("borderFillIDRef")
                if bid not in types or bid in allow_ids:
                    continue
                if all(t in allow_types for t in types[bid]):
                    continue
                addr = tc.find(f"{{{HP}}}cellAddr")
                r = int(addr.get("rowAddr")) if addr is not None else -1
                c = int(addr.get("colAddr")) if addr is not None else -1
                cells.append(Violation(section_name, i, tid, r, c, bid, types[bid]))
    return cells, tbls


def check_hwpx(path: str, *, allow_types=("SOLID",), allow_ids=(),
               exempt_tbl_ids=()) -> tuple[list[Violation], list[Violation]]:
    """hwpx 파일 전체(모든 section) 검사."""
    cells, tbls = [], []
    with zipfile.ZipFile(path) as z:
        hdr = z.read("Contents/header.xml")
        for n in sorted(z.namelist()):
            m = re.fullmatch(r"Contents/(section\d+)\.xml", n)
            if not m:
                continue
            c, t = cell_border_violations(
                hdr, z.read(n), section_name=m.group(1),
                allow_types=frozenset(allow_types), allow_ids=frozenset(map(str, allow_ids)),
                exempt_tbl_ids=frozenset(map(str, exempt_tbl_ids)))
            cells += c
            tbls += t
    return cells, tbls


def summarize(cells: list[Violation]) -> str:
    """「N건: bf=19 DASH/DASH/DASH/DASH ×99 · …」 — 게이트 메시지용."""
    if not cells:
        return "0건"
    by = {}
    for v in cells:
        by.setdefault((v.bf_id, v.types), 0)
        by[(v.bf_id, v.types)] += 1
    parts = [f"bf={b} {'/'.join(t)} ×{n}" for (b, t), n in sorted(by.items(), key=lambda x: -x[1])]
    return f"{len(cells)}건: " + " · ".join(parts[:4])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--allow-types", default="SOLID", help="쉼표 구분. 기본 SOLID")
    ap.add_argument("--allow-ids", default="", help="허용할 borderFill id, 쉼표 구분")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    allow_t = tuple(x.strip() for x in a.allow_types.split(",") if x.strip())
    allow_i = tuple(x.strip() for x in a.allow_ids.split(",") if x.strip())
    cells, tbls = check_hwpx(a.hwpx, allow_types=allow_t, allow_ids=allow_i)
    if a.json:
        print(json.dumps({"cells": [asdict(v) for v in cells],
                          "tables": [asdict(v) for v in tbls]}, ensure_ascii=False, indent=1))
    else:
        print(f"표 셀 테두리 비SOLID {summarize(cells)}")
        for v in cells[:10]:
            print("  ", v)
        if tbls:
            print(f"표 수준 테두리 비SOLID {len(tbls)}건 (경고): "
                  + ", ".join(f"표{v.tbl_idx} bf={v.bf_id}" for v in tbls[:6]))
    if cells:
        return 2
    return 1 if tbls else 0


if __name__ == "__main__":
    sys.exit(main())
