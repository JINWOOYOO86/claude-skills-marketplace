# -*- coding: utf-8 -*-
"""writer_brief — 집필 지시 묶음이 「그 절에 필요한 것만」 담는가."""
import os
import sys

import pytest

from conftest import KORDOC_OUT, ROOT, needs

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import writer_brief as wb  # noqa: E402

HANDOFF = os.path.dirname(KORDOC_OUT)
RUN = os.path.join(HANDOFF, "workspace", "proj")
RUBRIC = os.path.join(HANDOFF, "criteria", "rubric.yaml")
EVID = os.path.join(HANDOFF, "evidence", "workspace", "proj-pack", "_ws")


def test_spec_sections_split():
    md = "# 설계서\n\n## 1. 사슬표\n\n| a |\n\n## 2. 역추적표\n\n| b |\n\n## 8. 미확정\n\n| c |\n"
    ss = wb.spec_sections(md)
    assert set(ss) == {"1", "2", "8"} and "| b |" in ss["2"]


def test_section_text_extracts_only_that_section():
    md = "## 1. 배경\n\n### 1-1. 동향\n\n- a\n  - b\n\n### 1-2. 시장\n\n- c\n"
    assert wb.section_text(md, "1-1", "1-1. 동향").strip() == "- a\n  - b"
    assert wb.section_text(md, "1-2", "1-2. 시장").strip() == "- c"


@needs(RUBRIC)
def test_checks_for_filters_assembly_checks():
    rub = wb.load_rubric(RUBRIC)
    ids = {c["id"] for _, _, c, _ in wb.checks_for(rub, "1-3", "submission")}
    assert {"L-j1", "L-j3", "L-j6", "F-j1", "L-m1", "C-m1", "B-m1", "S-m1"} <= ids
    assert not ({"F-m1", "F-m5", "T-m2", "T-m6"} & ids), "조립·서식 검사가 집필 brief 에 섞였다"
    assert "L-f1" not in ids                                  # final 전용은 submission 에서 제외
    fin = {c["id"] for _, _, c, _ in wb.checks_for(rub, "3-2", "final")}
    assert "L-f1" in fin


@needs(RUN)
def test_build_brief_without_spec_says_so(tmp_path):
    text = wb.build(RUN, "1-3", RUBRIC, str(tmp_path / "none.md"), EVID, "submission", fix=False)
    assert "설계서 없음" in text
    assert "기존 접근의 한계" in text                        # blueprint 리드
    assert "TECH_UNSOLVED" in text                            # 대장 key 안내
    assert "B-2. 금지 표현" in text or "금지 표현" in text     # 15_axis_conflicts §B


# ── 2026-09-27 t1 종단 테스트 결함: 답은 값만 · 필수 요소는 담당 절 brief 로 ─────────────────
import json  # noqa: E402

RUBRIC_T1 = """
items:
  양식:
    points: 15
    floor:
      - {id: F-m4, by: machine, check: "요약문 칸", impl: "check_rubric:R6", applies_to: ["0"],
         requires: {from: form_guide, section: "0", values: {과제명: "@title", 전체 연구기간: PRJ_PERIOD, 기술성숙도: [PRJ_TRL_START, PRJ_TRL_END]}}}
  구체:
    points: 20
    floor:
      - {id: C-m1, by: machine, check: "실행 조건", impl: "check_rubric:R3", applies_to: ["*"],
         requires: [{item: 모델 구성, section: "3-1", key: WP1_MODEL_ARCH}, {item: 대상 상태영역, section: "3-1", key: WP3_EOS_SCOPE}]}
  구조:
    points: 20
    floor:
      - {id: T-m5, by: machine, check: "내부 용어 없음", impl: ["gate_form:F-13", "check_internal"], applies_to: ["*"]}
"""


def _t1_ws(tmp_path):
    run = tmp_path / "workspace" / "t"
    run.mkdir(parents=True)
    (run / "requirements.md").write_text("---\ntitle: AI 소재 개발\nmode: submission\n---\n", encoding="utf-8")
    (run / "50_form_spec.json").write_text(json.dumps({"outline": [
        {"id": "0", "level": 2, "title": "0. 연구 요약문",
         "guide": ["과제명 (국문/영문): 한 줄 요약", "전체 연구기간: YYYY.MM.DD ~ YYYY.MM.DD (n년 n개월)",
                   "기술성숙도 (TRL): 착수시점(n단계) → 종료시점 목표(n단계)"]},
        {"id": "3-1", "level": 3, "title": "3-1. 내용", "guide": ["x"],
         "blueprint": [{"lead": "연차별 연구내용", "slots": [{"text": "WP3", "key": "ORG_WP3"}]}]}]}, ensure_ascii=False), encoding="utf-8")
    ev = tmp_path / "_ws"
    ev.mkdir()
    (ev / "10_project_title.md").write_text(
        "| PRJ_PERIOD | 2026.04.01 ~ 2029.12.31, 3년 9개월 | - | 2026 | 보도자료 `00_rfp_selected.md §1` [⑥] | 중 |\n"
        "| PRJ_TRL_START | 4 | 단계 | 2026 | 공고 원문 | 상 |\n| PRJ_TRL_END | 7 | 단계 | 2026 | 공고 원문 | 상 |\n"
        "| ORG_WP3 | 가나연구원 | | 2026 | 10_project_title.md:38 | 상 |\n", encoding="utf-8")
    # 옛 대장(t1): 값 칸과 출처 칸 모두에 꼬리표가 있다
    (ev / "16_user_answers.md").write_text(
        "| key | 값 | 단위 | 기준연도 | 출처 | 확신도 |\n|---|---|---|---|---|---|\n"
        "| WP3_EOS_SCOPE | 상태영역 230~400 K, 10 MPa 이하 (사용자 답 2026-09-27) |  | 2026 | 사용자 답(2026-09-27) | 상 |\n",
        encoding="utf-8")
    rub = tmp_path / "rubric.yaml"
    rub.write_text(RUBRIC_T1, encoding="utf-8")
    return str(run), str(rub), str(ev)


def test_brief_carries_answer_values_only(tmp_path):
    run, rub, ev = _t1_ws(tmp_path)
    for sid in ("0", "3-1"):
        text = wb.build(run, sid, rub, None, ev, "submission", fix=False)
        body = text.split("## ③")[0] + text.split("## ④")[1]           # ③ 체크 문장(규칙 자체)은 빼고 본다
        assert "사용자 답" not in body, sid
        assert "16_user_answers.md:" not in text and "10_project_title.md:" not in text
        assert "00_rfp_selected.md" not in text
    text = wb.build(run, "3-1", rub, None, ev, "submission", fix=False)
    assert "- WP3_EOS_SCOPE: 상태영역 230~400 K, 10 MPa 이하" in text
    assert "| ORG_WP3 | 가나연구원 |" in text


def test_brief_0_gets_required_cells_with_values_and_table_rule(tmp_path):
    run, rub, ev = _t1_ws(tmp_path)
    text = wb.build(run, "0", rub, None, ev, "submission", fix=False)
    zero = text.split("## ① ")[0]
    assert "## ⓪" in zero and "표 하나로" in zero
    assert "| F-m4 | 과제명 (국문/영문) |" in zero and "AI 소재 개발 |" in zero
    assert "2026.04.01 ~ 2029.12.31, 3년 9개월" in zero
    assert "| 4 → 7 |" in zero


def test_brief_3_1_gets_r3_items_and_missing_value_rule(tmp_path):
    run, rub, ev = _t1_ws(tmp_path)
    text = wb.build(run, "3-1", rub, None, ev, "submission", fix=False)
    zero = text.split("## ① ")[0]
    assert "| C-m1 | 모델 구성 |" in zero and "「신경망」" in zero and "값 없음" in zero
    assert "| C-m1 | 대상 상태영역 |" in zero and "「상태영역은」" in zero and "230~400 K" in zero
    assert "(사용자 답" not in zero


def test_fix_brief_points_to_internal_leaks_in_this_section(tmp_path):
    run, rub, ev = _t1_ws(tmp_path)
    (tmp_path / "workspace" / "t" / "30_proposal.md").write_text(
        "# t\n\n## 0. 연구 요약문\n\n| 과제명 | x |\n\n### 3-1. 내용\n\n- 연차별 연구내용\n"
        "  - WP3: EOS 수립(가나연구원, 사용자 답 2026-09-27)\n", encoding="utf-8")
    (tmp_path / "workspace" / "t" / "70_machine.json").write_text(json.dumps({"checks": {
        "T-m5": {"ok": False, "severity": "fail", "detail": "check_internal: 내부 표기 1개", "sections": ["3-1"]}}},
        ensure_ascii=False), encoding="utf-8")
    text = wb.build(run, "3-1", rub, None, ev, "submission", fix=True, only={"T-m5"})
    fix = text.split("## ⑤")[1].split("## ⑥")[0]
    assert "T-m5 (machine)" in fix and "[사용자 답]" in fix and "가나연구원, 사용자 답" in fix


# ── t2(2026-09-27): 수정 회차가 분량을 넘겨 쪽수 floor 를 깼다 · §8 floor 질문의 답을 brief 에 싣는다 ─────
def _budget_spec(tmp_path, body):
    run, rub, ev = _t1_ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    spec = json.load(open(W / "50_form_spec.json", encoding="utf-8"))
    spec["page_budget"] = {"chapters": {"3": 1.0}, "chars_per_page": 100}
    (W / "50_form_spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    (W / "30_proposal.md").write_text("# t\n\n## 0. 연구 요약문\n\n| 과제명 | x |\n\n### 3-1. 내용\n\n- 연차별 연구내용\n  - " + body + "\n",
                                      encoding="utf-8")
    return run, rub, ev


def test_fix_brief_carries_length_budget_and_priority_rule(tmp_path):
    run, rub, ev = _budget_spec(tmp_path, "가" * 120)                  # 절 129자 · 장 예산 100자
    text = wb.build(run, "3-1", rub, None, ev, "submission", fix=True, only={"C-m1"})
    fix = text.split("## ⑤")[1].split("## ⑥")[0]
    assert "분량 예산" in fix and "현재 **129자**" in fix and "상한 **100자**" in fix and "29자 초과" in fix
    assert "문장을 지우는 op 는 없다" in fix and "rp_run.py trim" in fix and "새로 넣은 문장부터" in fix   # 고치기 모드(plan_v2 3단계)
    assert "포기" in fix and "floor(machine) 체크는 포기하지 않는다" in fix
    out = text.split("## 출력")[1]
    assert "고치기 모드" in out and '"op": "merge"' in out and os.path.join("edits", "r0_3-1.json") in out
    assert "이 절 목표" not in text                                     # 수정 회차는 ① 목표 줄 대신 ⑤ 상한
    assert "이 절 목표 100자" in wb.build(run, "3-1", rub, None, ev, "submission", fix=False)


def test_section_budget_splits_chapter_by_current_share(tmp_path):
    spec = {"page_budget": {"chapters": {"1": 2.0}, "chars_per_page": 100},
            "outline": [{"id": "1-1", "title": "1-1. a", "guide": ["x"]}, {"id": "1-2", "title": "1-2. b", "guide": ["y"]}]}
    md = "### 1-1. a\n\n- " + "가" * 149 + "\n\n### 1-2. b\n\n- " + "나" * 49 + "\n"
    a, b = wb.section_budget(spec, md, "1-1"), wb.section_budget(spec, md, "1-2")
    assert (a["current"], a["target"], b["current"], b["target"]) == (150, 150, 50, 50)
    assert a["target"] + b["target"] == a["chapter_budget"] == 200
    assert wb.section_budget(spec, "", "1-1")["target"] == 100             # 원고 없음: 균등
    assert wb.section_budget({"outline": spec["outline"]}, md, "1-1") is None


def test_brief_labels_spec8_answer_with_its_question(tmp_path):
    run, rub, ev = _t1_ws(tmp_path)
    (tmp_path / "workspace" / "t" / "21_questions.md").write_text(
        "| # | 체크 | key | 묻는 것 | 찾아본 곳 | 답 |\n|---|---|---|---|---|---|\n"
        "| 1 | F-m4 | SPEC8_17 | [floor] 기술분류 소분류 3순위·비중 | 설계서 §8-17 | 에너지효율향상 60 % |\n", encoding="utf-8")
    with open(os.path.join(ev, "16_user_answers.md"), "a", encoding="utf-8") as f:
        f.write("| SPEC8_17 | 에너지효율향상 60 % |  | 2026 |  | 상 |\n")
    text = wb.build(run, "0", rub, None, ev, "submission", fix=False)
    assert "- SPEC8_17 「기술분류 소분류 3순위·비중」: 에너지효율향상 60 %" in text


def test_brief_forbids_rfp_markers_and_fix_lists_them(tmp_path):
    """T-m7 (2026-09-28): 집필 brief 에 「RFP」·공고문 절 번호 금지 규칙, 수정 brief ⑤ 에 이 절의 표시 목록."""
    run, rub, ev = _t1_ws(tmp_path)
    with open(rub, "a", encoding="utf-8") as f:
        f.write('      - {id: T-m7, by: machine, check: "내부 출처 표시 없음", impl: "check_internal:rfp", applies_to: ["*"]}\n')
    text = wb.build(run, "3-1", rub, None, ev, "submission", fix=False)
    assert "「RFP」라는 말은 본문·표에 쓰지 않는다" in text and "| T-m7 |" in text
    (tmp_path / "workspace" / "t" / "30_proposal.md").write_text(
        "# t\n\n## 0. 연구 요약문\n\n| 과제명 | x |\n\n### 3-1. 내용\n\n- 연차별 연구내용\n"
        "  - WP4: 실증은 RFP 필수 하한 1,000시간(공고 RFP §3.1)\n", encoding="utf-8")
    (tmp_path / "workspace" / "t" / "70_machine.json").write_text(json.dumps({"checks": {
        "T-m7": {"ok": False, "severity": "fail", "detail": "check_internal:rfp: 2개", "sections": ["3-1"]}}}), encoding="utf-8")
    fix = wb.build(run, "3-1", rub, None, ev, "submission", fix=True, only={"T-m7"}).split("## ⑤")[1].split("## ⑥")[0]
    assert "T-m7 (machine)" in fix and "T-m7 내부 출처 표시" in fix and "RFP 필수 하한" in fix


# ── plan_v2 5단계 17 (2026-09-28): 슬롯 문구가 본문 라벨로 새지 않게 ─────────────────
T3 = os.path.join(HANDOFF, "workspace", "proj-t3")


@needs(T3)
def test_brief_gives_slots_as_content_not_labels(tmp_path):
    text = wb.build(T3, "1-2", RUBRIC, os.path.join(T3, "20_spec.md"), EVID, "submission", fix=False)
    assert "슬롯 문구: 값" not in text and "슬롯은 아래 문구로 시작" not in text
    skel = text[text.index("골격(F-11"):text.index("서술 형식:")]      # ⑥ 현재 원고(옛 t3 본문)는 제외
    assert "- **시장 규모**" in skel and "시장 규모: 세계" not in skel   # 리드는 안내 꼬리 없이
    assert "  - 담을 내용: 세계 시장 규모" in skel
    assert "S-m6" in text and "T-m8" in text and "F-m8" in text
    assert "문장 구성 예시(내용이 아니라 문장 구성의 기준" in text and "### 위험과 대체 경로" in text   # 5단계 16
