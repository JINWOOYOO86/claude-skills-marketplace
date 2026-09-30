# -*- coding: utf-8 -*-
"""t4 정지 원인 중 검사기 오류 (plan_t4fix 2·3): T-m3 핵심어 계수 · S-m2 영문 과제명 · 실패 절 배정.
실제 원고로 확인한다(없으면 skip)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "harness_patches"))

import check_rubric as cr  # noqa: E402
import check_wording as cw  # noqa: E402
import gate_form as gf  # noqa: E402
from conftest import KORDOC_OUT, needs  # noqa: E402

H = os.path.dirname(KORDOC_OUT)
T4 = os.path.join(H, "workspace", "proj-t4")
DOCS = {"t4_r0": os.path.join(T4, "rounds", "r0", "30_proposal.hwpx"),
        "t4_r1": os.path.join(T4, "rounds", "r1", "30_proposal.hwpx"),
        "t3": os.path.join(H, "workspace", "proj-t3", "30_proposal.hwpx"),
        "orig": os.path.join(H, "orig.hwpx"),
        "final": os.path.join(H, "final.hwpx")}
SPEC = os.path.join(T4, "50_form_spec.json")


@needs(SPEC)
@pytest.mark.parametrize("key", list(DOCS))
def test_keywords_counted_per_language_from_the_keyword_cell(key):
    if not os.path.exists(DOCS[key]):
        pytest.skip("실측 파일 없음")
    spec = json.load(open(SPEC, encoding="utf-8"))
    doc = gf.Doc(DOCS[key], [(n["id"], n["title"]) for n in spec["outline"]])
    ok, d = gf.sp_keywords_cell(gf.keyword_cell(doc.tables("0")))
    assert ok and d == "국문 5개 / 영문 5개 (각 5개 이내)", d


def test_keywords_cell_rules():
    assert gf.sp_keywords_cell("가, 나, 다, 라, 마 / a, b, c, d, e")[0]
    assert not gf.sp_keywords_cell("가, 나, 다, 라, 마, 바 / a, b, c, d, e")[0]        # 국문 6개
    assert gf.sp_keywords_cell("(국문) 가·나·다·라·마 (영문) a·b·c·d·e")[0]
    assert gf.sp_keywords_cell("친환경/고효율 냉매, 나, 다, 라, 마 / a, b, c, d, e")[0]  # 낱말 안의 「/」는 경계가 아니다
    tables = [[["항목", "내용"], ["핵심어 (국문/영문)", "가, 나 / a, b"]]]
    assert gf.keyword_cell(tables) == "가, 나 / a, b"


@pytest.mark.parametrize("name", ["r0", "r1"])
def test_english_title_in_title_cell_counts(name):
    p = os.path.join(T4, "rounds", name, "30_proposal.build.md")
    if not os.path.exists(p):
        pytest.skip("실측 파일 없음")
    assert cw.en_title(open(p, encoding="utf-8").read()).startswith("Development of Eco-friendly")


def test_english_title_rules():
    assert cw.en_title("| 과제명 | 가나 / Development of X |") == "Development of X"
    assert cw.en_title("| 과제명 | (국문) 가나 (영문) Development of X |") == "Development of X"
    # 과제명 칸에 영문이 없으면 핵심어 칸의 「(영문)」을 과제명으로 오인하지 않는다
    assert cw.en_title("| 과제명 | 가나다 |\n| 핵심어 | (국문) 가 (영문) low-GWP |") is None


def test_gate_failure_goes_only_to_failing_section():
    c = {"id": "T-m3", "impl": "gate_form:F-4", "applies_to": ["0", "2-2", "2-3", "3-1", "3-3"]}
    sig = {"md": "", "gate_bad": {"gate_form:F-4": ["F-4 0 KEYWORDS5"]}}
    assert cr.fail_sections(c, "11개 (5개 이내)", sig, {}) == ["0"]
    sig["gate_bad"]["gate_form:F-4"] = ["F-4 2-2 TABLE_A", "F-4 3-3 TABLE_B"]
    assert cr.fail_sections(c, "", sig, {}) == ["2-2", "3-3"]
    sig["gate_bad"]["gate_form:F-4"] = []                                   # 위치 모름 → 편집자(applies_to 전체로 보내지 않음)
    assert cr.fail_sections(c, "", sig, {}) == []
    one = {"id": "X", "impl": "gate_form:F-4 2-1 FIG_OR_TABLE", "applies_to": ["2-1"]}
    assert cr.fail_sections(one, "", {"md": ""}, {}) == ["2-1"]
