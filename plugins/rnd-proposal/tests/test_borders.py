# -*- coding: utf-8 -*-
"""결함 B — 표 셀 테두리 실선 (2026-09-26).

전에는 header_index 가 굵기만 읽어 DASH 와 SOLID 가 같은 키에 섞였고 작은 id 가 이겼다.
proposal-draft 양식에서 (0.15×4, 무채움) 은 id 19(DASH) 와 68(SOLID) 둘인데 19 가 찍혔다.
"""
import os
import zipfile

import pytest

from conftest import (FORM_DRAFT, TEMPLATE_DRAFT, OLD_ENGINE_OUT, KORDOC_OUT, needs)
from engine.hwpx import border_check, borderfill, header_index
from engine.hwpx.consts import BORDER_INNER


@pytest.fixture(scope="module")
def hidx():
    return header_index.from_hwpx(TEMPLATE_DRAFT)


def test_border_types_parsed_and_no_missing_type_attr(hidx):
    """type 을 읽고, 「부재 시 SOLID」 가정이 실측과 어긋나지 않는지 같이 본다."""
    assert hidx.border_fill["19"].types == ("DASH",) * 4
    assert hidx.border_fill["19"].all_solid is False
    assert hidx.border_fill["68"].all_solid is True
    with zipfile.ZipFile(TEMPLATE_DRAFT) as z:
        hdr = z.read("Contents/header.xml").decode("utf-8")
    import re
    sides = re.findall(r"<hh:(?:left|right|top|bottom)Border\b[^>]*>", hdr)
    assert sides and all('type="' in s for s in sides), "type 속성이 없는 변이 있다"


def test_template_lookup_prefers_solid(hidx):
    res = borderfill.BorderFillResolver(hidx)
    bid, why = res.lookup({"l": BORDER_INNER, "r": BORDER_INNER,
                           "t": BORDER_INNER, "b": BORDER_INNER, "fill": None})
    assert bid == "68" and why is None
    assert "19" not in hidx.border_fill_index().values()


def test_template_grid_all_solid(hidx):
    res = borderfill.BorderFillResolver(hidx)
    g = res.grid(4, 4)
    assert len(g.grid) == 16 and not g.warnings
    assert all(hidx.border_fill[b].all_solid for b in g.grid.values())
    assert res.default_id() == "68"


@needs(OLD_ENGINE_OUT)
def test_gate_fails_old_engine_output():
    cells, _ = border_check.check_hwpx(OLD_ENGINE_OUT)
    assert len(cells) == 99
    assert {v.bf_id for v in cells} == {"19"}
    from engine.hwpx import validate_hwpx
    r = validate_hwpx.validate(OLD_ENGINE_OUT, FORM_DRAFT, level=4)
    assert any("표 셀 테두리 비SOLID 99건" in e for e in r.errors)


def test_rebuilt_table_passes(tmp_path):
    """3×3 표 하나를 새로 조립하면 위반 0건, header.xml 은 원본과 바이트 동일."""
    from engine.hwpx import build_hwpx, validate_hwpx
    md = tmp_path / "t.md"
    md.write_text("# 시험\n\n## 2. 수요연계성\n\n- 표는 아래와 같음\n\n"
                  "| 구분 | 내용 | 값 |\n|---|---|---|\n| a | b | 1 |\n| c | d | 2 |\n",
                  encoding="utf-8")
    out = tmp_path / "t.hwpx"
    build_hwpx.build(FORM_DRAFT, str(md), str(out))
    cells, _ = border_check.check_hwpx(str(out))
    assert cells == []
    r = validate_hwpx.validate(str(out), FORM_DRAFT, level=4)
    assert not [e for e in r.errors if "표 셀 테두리" in e]
    assert "바이트 동일" in r.info.get("header", "")


@needs(KORDOC_OUT)
def test_kordoc_output_double_slim_detected_and_allowlisted():
    cells, _ = border_check.check_hwpx(KORDOC_OUT)
    assert len(cells) == 62
    assert all("DOUBLE_SLIM" in v.types for v in cells)
    cells2, _ = border_check.check_hwpx(KORDOC_OUT, allow_types=("SOLID", "DOUBLE_SLIM"))
    assert cells2 == []


@needs(KORDOC_OUT)
def test_sample_form_default_is_solid():
    """양식 겸 샘플 header 는 0.3/0.15 조합이 없다 — 그래도 기본 셀이 NONE(id 1) 이면 안 된다."""
    h = header_index.from_hwpx(KORDOC_OUT)
    res = borderfill.BorderFillResolver(h)
    assert res.default_id() != "1" and h.border_fill[res.default_id()].all_solid
    g = res.grid(3, 3)
    assert len(g.grid) == 9 and all(h.border_fill[b].all_solid for b in g.grid.values())
