# -*- coding: utf-8 -*-
"""t1 종단 테스트 결함(2026-09-27): 내부 표기 누출(T-m5 check_internal) · requires 필수 요소 · 절 배정 · R4 0절 면제."""
import json
import os
import sys
import zipfile

from conftest import KORDOC_OUT, ROOT, needs

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_internal as ci  # noqa: E402
import check_rubric as cr  # noqa: E402

HANDOFF = os.path.dirname(KORDOC_OUT)
T1 = os.path.join(HANDOFF, "workspace", "proj-t1")


def test_detects_internal_markers_with_heading():
    md = ("## 0. 연구 요약문\n\n- WP3: EOS 수립(가나연구원, 사용자 답 2026-09-27)\n"
          "### 3-1. 내용\n\n- 근거팩 `10_project_title.md` 의 PRJ_PERIOD · 대장 출처 · 확신도 상 · evidence/_ws\n")
    hits = ci.find_in_text(md)
    names = {h["name"] for h in hits}
    assert {"사용자 답", "근거팩", "작업 파일명", "대장 key", "대장", "확신도", "작업 폴더"} <= names
    assert hits[0]["heading"] == "0. 연구 요약문" and hits[-1]["heading"] == "3-1. 내용"


def test_clean_proposal_text_passes():
    md = ("- 대상 냉매: R-1234yf · HFO-1234ze(E) · R134a 대비 GWP 1 미만(IPCC AR6)\n"
          "- 판정 기준: ASHRAE Standard 97, ISO 5149 · KPI 1 · WP3 · US 1,234,567 B2 · 10 MPa 이하 · COP_h\n"
          "<!-- 이 주석은 조립 전에 form_strip.py 가 지운다 -->\n")
    assert ci.find_in_text(md) == []


def test_hwpx_scan_covers_table_cells(tmp_path):
    xml = ('<hs:sec xmlns:hp="x"><hp:p><hp:run><hp:t>본문 정상</hp:t></hp:run></hp:p>'
           '<hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>NIST · 사용자 답(2026-09-27)</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl></hs:sec>')
    p = tmp_path / "t.hwpx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", xml)
    hits = ci.find_in_hwpx(str(p))
    assert len(hits) == 1 and hits[0]["in_table"] is True
    assert ci.summarize(hits) == "내부 표기 1개 (사용자 답 1)"


@needs(T1)
def test_t1_manuscript_regression_20_leaks():
    """t1 원고의 「사용자 답」 20곳을 그대로 잡는다(90_제출보고.md 기록과 같은 수)."""
    hits = ci.find_in_text(open(os.path.join(T1, "30_proposal.md"), encoding="utf-8").read())
    assert sum(h["name"] == "사용자 답" for h in hits) == 20


def test_r4_skips_summary_section_pairs():
    """0장 요약문이 낀 쌍은 세지 않는다(요약문은 본문을 되풀이하는 칸). 본문 절끼리는 그대로 잡는다."""
    slot = "  - 최종 목표: 저GWP 순물질 냉매 후보 5종을 AI 로 도출하고 실증함"
    md = f"## 0. 연구 요약문\n\n- 요약\n{slot}\n\n### 2-1. 최종 목표\n\n- 목표\n{slot}\n\n### 3-1. 내용\n\n- 내용\n{slot}\n"
    pairs = cr.r4_pairs(md)
    assert pairs and all("0. 연구 요약문" not in (a, b) for a, b, *_ in pairs)
    assert {(a, b) for a, b, *_ in pairs} == {("2-1. 최종 목표", "3-1. 내용")}


SPEC = {"outline": [
    {"id": "0", "title": "0. 연구 요약문", "guide": ["과제명 (국문/영문): 한 줄 요약", "전체 연구기간: YYYY.MM.DD ~ YYYY.MM.DD (n년 n개월)",
                                                   "최종 목표: 연구개발과제의 최종 목표"]},
    {"id": "3-1", "title": "3-1. 내용", "guide": ["x"]}]}
F_M4 = {"id": "F-m4", "impl": "check_rubric:R6", "applies_to": ["0"],
        "requires": {"from": "form_guide", "section": "0", "values": {"과제명": "@title", "전체 연구기간": "PRJ_PERIOD"}}}
C_M1 = {"id": "C-m1", "impl": "check_rubric:R3", "applies_to": ["*"],
        "requires": [{"item": "모델 구성", "section": "3-1", "key": "WP1_MODEL_ARCH"},
                     {"item": "시험 운전조건", "section": "2-3", "form": "「운전조건: …」"}]}


def test_required_elements_from_form_guide_and_items():
    r = cr.required_elements(F_M4, SPEC)
    assert [x["item"] for x in r] == ["과제명 (국문/영문)", "전체 연구기간", "최종 목표"]
    assert r[0]["keys"] == ["@title"] and r[1]["keys"] == ["PRJ_PERIOD"] and r[2]["keys"] == []
    assert "| 전체 연구기간 | 값 |" in r[1]["form"] and "R6 이 개수까지" in r[1]["form"]
    assert "R6 이 개수까지" not in r[2]["form"]                      # 자리표시 없는 칸
    c = cr.required_elements(C_M1, SPEC)
    assert c[0]["section"] == "3-1" and "「신경망」" in c[0]["form"]    # 검사 정규식의 문구를 그대로 보여 준다
    assert c[1]["form"] == "「운전조건: …」"


def test_fail_sections_routes_by_failed_item():
    sig = {"md": "", "internal_heads": []}
    assert cr.fail_sections(C_M1, "check_rubric:R3: 본문에 없다: 모델 구성", sig, SPEC) == ["3-1"]
    assert cr.fail_sections(F_M4, "check_rubric:R6: 전체 연구기간: 칸이 없다", sig, SPEC) == ["0"]
    tm5 = {"id": "T-m5", "impl": ["gate_form:F-13", "check_internal"], "applies_to": ["*"]}
    assert cr.fail_sections(tm5, "", {"md": "", "internal_heads": ["3-1. 내용"]}, SPEC) == ["3-1"]
    assert cr.fail_sections({"id": "S-m2", "impl": "check_wording", "applies_to": ["*"]}, "", sig, SPEC) == []


# ── T-m7 내부 출처 표시 (2026-09-28): 「RFP」·공고문 절 번호 ─────────────────────────────────
SUBMIT = os.path.join(HANDOFF, "submit_t2.hwpx")
T2 = os.path.join(HANDOFF, "workspace", "proj-t2")


def test_rfp_group_detects_markers_and_internal_group_does_not():
    md = ("### 2-3. 성과지표\n\n- 가중치: 15/15/10/20/10/30(RFP §3.1)으로 나눔\n"
          "- 실증: 시스템 실증은 RFP 필수 하한 1,000시간\n- 안전: 안전관리계획을 선행함(RFP 위험 ⑵)\n"
          "| 출처 | Google Patents · 공고 RFP §3.1 |\n- 요건: 공고 §2 에 따라 둠\n")
    hits = ci.find_in_text(md, "rfp")
    assert sum(h["name"] == "RFP" for h in hits) == 4 and sum(h["name"] == "공고문 절 번호" for h in hits) == 1
    assert all(h["heading"] == "2-3. 성과지표" for h in hits)
    assert ci.find_in_text(md) == []                                   # T-m5(internal) 는 그대로
    assert ci.summarize(hits, "rfp").startswith("내부 출처 표시(RFP) 5개")


def test_rfp_group_passes_clean_text():
    md = "- 근거: 과제 공고문이 요구한 1,000시간 실증을 포함함(KHARN 2026-08-08) · ISO 5149 · RFPS · xRFP\n"
    assert ci.find_in_text(md, "rfp") == []


@needs(SUBMIT)
def test_submission_2026_09_27_has_14_rfp_markers():
    hits = ci.find_in_hwpx(SUBMIT, "rfp")
    assert len(hits) == 14 and any(h["in_table"] for h in hits)
    assert ci.find_in_hwpx(SUBMIT) == []


@needs(T2)
def test_t2_manuscript_has_2_rfp_markers():
    assert len(ci.find_in_text(open(os.path.join(T2, "30_proposal.md"), encoding="utf-8").read(), "rfp")) == 2


def test_fail_sections_t_m7_uses_rfp_headings():
    tm7 = {"id": "T-m7", "impl": "check_internal:rfp", "applies_to": ["*"]}
    sig = {"md": "", "internal_heads": ["0. 연구 요약문"], "internal_rfp_heads": ["3-1. 내용"]}
    assert cr.fail_sections(tm7, "", sig, SPEC) == ["3-1"]
    sig_r = {"internal_rfp": (False, "x"), "internal": (True, "y")}
    assert cr.resolve("check_internal:rfp", sig_r, None) == (False, "x") and cr.resolve("check_internal", sig_r, None) == (True, "y")
