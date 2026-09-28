# -*- coding: utf-8 -*-
"""블라인드 비교 도구·hwpx 본문 추출 (plan_v2 1단계)."""
import json
import os
import re

from conftest import KORDOC_OUT, needs

from scripts import blind_compare as bc
from scripts.hwpx_text import hwpx_to_md

HANDOFF = os.path.dirname(KORDOC_OUT)
T3 = os.path.join(HANDOFF, "workspace", "proj-t3")
ORIG = os.path.join(HANDOFF, "orig.hwpx")

# 81_비교검증_블라인드_채점.md 의 두 답을 옮긴 것 (1회 A=원본, 2회 A=최종본)
R1_81 = """| 항목 | 우위 | 이유 |
|---|---|---|
| 양식 | A | [표 1]~[표 5] 번호·제목이 일관 |
| 논리 | B | 한계와 WP 대응표 |
| 구체 | B | 3일 연속 운전 · GC-MS |
| 간결 | B | 절 첫 문장에 결론 |
| 문체 | A | 작성 지시문이 남음 |
| 구조 | A | 내부 작업 표기 |
"""
R2_81 = """| 항목 | 우위 | 이유 |
|---|---|---|
| 양식 | **A** | 목표 표현 불일치 |
| 논리 | A | KPI 추적성 |
| 구체 | A | 측정 주체·장비 |
| 간결 | A | 긴 ○ 항목 |
| 문체 | A | 24.9배 공급 부족임 |
| 구조 | A | 정부지원 금액이 먼저 |
"""


def _run(tmp_path, r1, r2):
    a, b = tmp_path / "orig.md", tmp_path / "final.md"
    a.write_text("# 과제\n\n- 원본 문장\n", encoding="utf-8")
    b.write_text("# 과제\n\n- 최종 문장\n", encoding="utf-8")
    d = tmp_path / "blind"
    bc.prepare(str(a), str(b), str(d), "원본", "최종본")
    (d / "response_1.md").write_text(r1, encoding="utf-8")
    (d / "response_2.md").write_text(r2, encoding="utf-8")
    return d, bc.tally(str(d))


def test_prepare_swaps_order(tmp_path):
    d, _ = _run(tmp_path, R1_81, R2_81)
    p1 = (d / "prompt_1.md").read_text(encoding="utf-8")
    p2 = (d / "prompt_2.md").read_text(encoding="utf-8")
    assert p1.index("원본 문장") < p1.index("최종 문장")
    assert p2.index("최종 문장") < p2.index("원본 문장")
    # 문서 이름·파일 경로는 심판에게 가지 않는다
    for p in (p1, p2):
        assert "원본" not in p.replace("원본 문장", "") and "orig" not in p


def test_tally_reproduces_81(tmp_path):
    d, res = _run(tmp_path, R1_81, R2_81)
    conf = {i: res["items"][i]["confirmed"] for i in bc.ITEMS}
    assert conf == {"양식": None, "논리": "최종본", "구체": "최종본", "간결": "최종본", "문체": None, "구조": None}
    assert res["wins"] == {"원본": [], "최종본": ["논리", "구체", "간결"]}
    assert res["bias"] == {"1": False, "2": True}
    md = (d / "blind.md").read_text(encoding="utf-8")
    assert "위치 편향 의심" in md and "| 양식 | 원본 | 최종본 | 미확정 |" in md


def test_tally_equal_and_missing(tmp_path):
    r = R1_81.replace("| 문체 | A |", "| 문체 | 동등 |")
    _, res = _run(tmp_path, r, r.replace("| 양식 | A |", "| 양식 | B |"))
    assert res["items"]["문체"]["confirmed"] == "동등"
    import pytest
    with pytest.raises(SystemExit):
        _run(tmp_path, R1_81, "| 양식 | A | x |\n")


@needs(os.path.join(T3, "30_proposal.hwpx"))
def test_hwpx_text_round_trips_t3():
    """조립본 hwpx 를 되돌리면 원고 md 와 제목·글머리·표 행·표 밖 줄이 같다."""
    a = open(os.path.join(T3, "30_proposal.build.md"), encoding="utf-8").read()
    b = hwpx_to_md(os.path.join(T3, "30_proposal.hwpx"))

    def lines(t):
        return [l.strip() for l in t.splitlines() if l.strip() and not l.startswith("|")]
    assert lines(a) == lines(b)
    assert len(re.findall(r"^\|", a, re.M)) == len(re.findall(r"^\|", b, re.M))


@needs(ORIG)
def test_hwpx_text_external_original():
    """외부 원본(외부 원본): 1열 제목 상자 → # 제목, 대제목 5·절 12, [표 1]~[표 5]."""
    md = hwpx_to_md(ORIG)
    assert md.startswith("# AI 물질발굴기술")
    assert len(re.findall(r"^## \d\. ", md, re.M)) == 5
    assert len(re.findall(r"^### \d-\d\. ", md, re.M)) == 12
    assert re.findall(r"^\[표 (\d)\]", md, re.M) == ["1", "2", "3", "4", "5"]


def test_insert_js_escapes_full_text(tmp_path):
    """prompt_N.js 에 전문이 JSON 문자열로 온전히 들어간다(따옴표·줄바꿈·역슬래시)."""
    d, _ = _run(tmp_path, R1_81, R2_81)
    js = (d / "prompt_1.js").read_text(encoding="utf-8")
    p1 = (d / "prompt_1.md").read_text(encoding="utf-8")
    lit = re.search(r"const T = (\".*\"); document", js, re.S).group(1)
    assert json.loads(lit) == p1
    tricky = 'a "q" \ b\n| x | y |'
    assert json.loads(re.search(r"const T = (\".*\"); document", bc.insert_js(tricky), re.S).group(1)) == tricky
    assert "ClipboardEvent('paste'" in js                        # 창 포커스가 없을 때의 대체 경로(2026-09-28)
