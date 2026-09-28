# -*- coding: utf-8 -*-
"""규칙 충돌 (plan_t4fix 4): 고정 문구 예외(T-m8) · check_rules 모순 검사 · gaps 시작 질문."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import check_internal as ci  # noqa: E402
import check_rules as cru  # noqa: E402
import edit_apply as ea  # noqa: E402
import rp_run as rr  # noqa: E402
from conftest import KORDOC_OUT, needs  # noqa: E402
from test_rp_run import _ws  # noqa: E402

PACK = os.path.join(os.path.dirname(KORDOC_OUT), "evidence", "workspace", "proj-pack", "_ws")
AXIS = """# 대조

## B-1. 고정 표현 (반드시 이 형태로 쓴다)

| # | 항목 | 고정 표기 | 출처 축 |
|---|---|---|---|
| F10 | 백색공간 | **「본 조사 범위에서 확인된 원천특허군의 청구범위 밖」** 한정 필수 | 특허 |
| F12 | 선행사례 | **「본 조사 범위에서 확인되지 않았다」** | 기술동향 |
{extra}
## B-2. 금지 표현 (어떤 맥락에서도 쓰지 않는다)

| # | 금지 | 왜 |
|---|---|---|
| X1 | **「세계 최초」** (모든 맥락) | 부존재가 아니다 |
| X2 | 「선행 연구 **전무**」·「**국내외 유일**」 | X1 과 같다 |
"""
F10, F12 = "본 조사 범위에서 확인된 원천특허군의 청구범위 밖", "본 조사 범위에서 확인되지 않았다"


def _pack(tmp_path, extra=""):
    p = tmp_path / "pack"
    p.mkdir(exist_ok=True)
    (p / "15_axis_conflicts.md").write_text(AXIS.replace("{extra}", extra), encoding="utf-8")
    return str(p)


def test_pack_phrases_reads_fixed_and_forbidden(tmp_path):
    ph = ci.pack_phrases(_pack(tmp_path))
    assert ph["fixed"] == [("F10", F10), ("F12", F12)]
    assert ("X2", "선행 연구 전무") in ph["forbidden"] and ("X1", "세계 최초") in ph["forbidden"]


def test_fixed_phrase_is_allowed_only_whole():
    allow = [F10, F12]
    assert ci.find_form(f"- 완전불소화 탄소 비함유 공정은 {F10}임\n", None, allow) == []
    assert ci.find_form("- 장기운전 공개 검증은 본 조사 범위에서 확인되지 않음\n", None, allow) == []    # 개조식 종결
    assert ci.find_form("- 본 조사 범위에서 확인된 바 없음\n", None, allow)                            # 고정 문구가 아님
    assert ci.find_form(f"- {F10}이며 본 조사 범위 밖 자료는 쓰지 않음\n", None, allow)               # 다른 자리의 메모는 걸린다
    assert ci.find_form(f"- {F10}임\n")                                                              # 예외 없이는 걸린다


def test_edit_apply_accepts_fixed_phrase_with_allow():
    text = "## 1-3. 한계\n\n- 완전불소화 탄소 비함유 공정은 청구범위 밖임\n"
    op = {"id": "1", "op": "replace", "anchor": "청구범위 밖임", "new": F10 + "임"}
    assert "T-m8" in (ea.vet(op, text) or "")
    assert ea.vet(op, text, [F10]) is None


def test_check_rules_marks_known_conflicts_as_resolved(tmp_path):
    res = cru.check(_pack(tmp_path))
    assert {(r["fixed"], r["rule"], r["resolved"]) for r in res} == {("F10", "T-m8", True), ("F12", "T-m8", True)}


def test_check_rules_finds_unresolved_conflicts(tmp_path):
    extra = ("| F20 | 지표 | **「KPI 1 기준 세계 최초 달성」** | 과제설계 |\n"
             "| F21 | 일정 | **「추후 확정」** | 과제설계 |\n")
    res = cru.check(_pack(tmp_path, extra))
    got = {(r["fixed"], r["rule"]) for r in res if not r["resolved"]}
    assert got == {("F20", "X1"), ("F21", "S-m2")}                          # 금지 표현·S-m2 는 예외가 없다
    assert ("F20", "T-m8", True) in {(r["fixed"], r["rule"], r["resolved"]) for r in res}   # T-m8 은 고정 문구 예외


def test_gaps_asks_unresolved_conflicts_once(tmp_path):
    run, ev = _ws(tmp_path)
    (tmp_path / "workspace" / "t" / "20_spec.md").write_text("# s\n", encoding="utf-8")
    (open(os.path.join(ev, "15_axis_conflicts.md"), "w", encoding="utf-8")
     .write(AXIS.replace("{extra}", "| F21 | 일정 | **「추후 확정」** | 과제설계 |\n")))
    rows = [r for r in rr.gaps(run) if r["key"].startswith("RULE_")]
    assert [r["key"] for r in rows] == ["RULE_F21_SM2"] and rows[0]["ask"].startswith("[규칙 충돌] 고정 표현 F21")


@needs(PACK)
def test_real_pack_has_no_unresolved_conflict():
    res = cru.check(PACK)
    assert not [r for r in res if not r["resolved"]]
    assert {r["fixed"] for r in res} == {"F10", "F12"}
