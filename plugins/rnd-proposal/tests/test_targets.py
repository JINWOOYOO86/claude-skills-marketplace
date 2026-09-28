# -*- coding: utf-8 -*-
"""목표 하향 검사 (plan_v2 5단계 18): check_targets · edit_apply 거부 · answers → ask_down."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import check_targets as ct  # noqa: E402
import edit_apply as ea  # noqa: E402
import rp_run as rr  # noqa: E402
from test_rp_run import _ws  # noqa: E402

# t3 실제 문장: 설계서 §2 KPI 4 행과 시작 질문 SPEC8_3 답
SPEC_ROW4 = ("| 4 | 기존 중압 냉매 대비 히트펌프 성능 | % | R-134a 적용 시스템 → 1단계 오일 적합성 확보(ASHRAE Standard 97 판정) "
             "→ 4차년도 R-134a 적용 시스템 동등 이상(% 수치·성능 지표 정의 §8 #3) · 운전조건: 열원 -7/2/7/12 ℃, 열매 35/55 ℃ | WP4 | 4차년도 | x |")
ANS_8_3 = "EN 14511 조건(외기 7 °C, 출수 35 °C)에서 R-134a 적용 시스템 대비 COP 비율 95 % 이상"


def test_same_or_better_to_95_percent_is_lowered():
    low = ct.lowered(SPEC_ROW4, ANS_8_3)
    assert len(low) == 1 and low[0]["base"] == "동등 이상" and low[0]["new"] == "95 % 이상"


def test_direction_and_unit():
    assert ct.lowered("누적 운전 1,000시간 이상", "누적 운전 800시간 이상")
    assert ct.lowered("증기압 MAPE 5 % 이하", "증기압 MAPE 8 % 이하")
    assert ct.lowered("GWP < 150", "GWP < 200")
    assert not ct.lowered("누적 운전 1,000시간 이상", "누적 운전 1,200시간 이상")
    assert not ct.lowered("GWP < 150", "순도 99.5 % 이상")                    # 단위·방향이 다르면 맞대지 않는다
    assert not ct.lowered("순도 99.5 % 이상 · 정확도 90 % 이상", "COP 80 % 이상")  # 후보 여럿, 라벨 겹침 0: 비교 안 함
    assert ct.lowered("순도 99.5 % 이상 · 정확도 90 % 이상", "분류 정확도 85 % 이상")
    assert not ct.lowered("A2L급 이하", "A2L급 이하")


def test_edit_apply_rejects_lowering_op():
    text = "## 2-3. 성과지표\n\n| 4 | 성능 | % | 20 | R-134a 시스템 COP(100 %) → COP 비율 95 % 이상 | x |\n"
    op = {"op": "replace", "anchor": "COP 비율 95 % 이상", "new": "COP 비율 90 % 이상"}
    assert "목표 하향" in ea.vet(op, text)
    assert ea.vet({"op": "replace", "anchor": "COP 비율 95 % 이상", "new": "COP 비율 95 % 이상(EN 14511)"}, text) is None


def test_answers_lowering_asks_once_then_proceeds(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n\n## 2. 성과지표 역추적표\n\n| KPI # | 성과지표 | 단위 | 기준값 → 목표치 | WP | 연차 | key |\n"
                                  "|---|---|---|---|---|---|---|\n" + SPEC_ROW4 + "\n\n## 3. 외부 시점표\n", encoding="utf-8")
    (W / "21_questions.md").write_text("# q\n\n| # | 체크 | key | 묻는 것 | 찾아본 곳 | 답 |\n|---|---|---|---|---|---|\n"
                                       f"| 1 | S-m2 | SPEC8_3 | [floor] 3 | 설계서 §8-3 | {ANS_8_3} |\n", encoding="utf-8")
    c = rr.answers(run, spec_ok=True, external="no")
    assert [d["key"] for d in c["target_down"]] == ["SPEC8_3"] and "target_down_ok" not in c
    n = rr.next_step(run)
    assert n["step"] == "ask_down" and "동등 이상" in n["actions"][0]["items"][0]
    assert "--confirm-down" in n["actions"][0]["then"]
    rr.answers(run, confirm_down="yes")
    assert rr.next_step(run)["step"] != "ask_down"


def test_answers_without_lowering_does_not_ask(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n\n## 2. 성과지표\n\n" + SPEC_ROW4 + "\n", encoding="utf-8")
    (W / "21_questions.md").write_text("# q\n\n| # | 체크 | key | 묻는 것 | 찾아본 곳 | 답 |\n|---|---|---|---|---|---|\n"
                                       "| 1 | S-m2 | SPEC8_3 | [floor] 3 | 설계서 §8-3 | R-134a 대비 COP 비율 100 % 이상 |\n", encoding="utf-8")
    assert rr.answers(run, spec_ok=True, external="no")["target_down"] == []
    assert rr.next_step(run)["step"] != "ask_down"
