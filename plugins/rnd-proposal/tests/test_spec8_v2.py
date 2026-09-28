# -*- coding: utf-8 -*-
"""§8 floor 질문 회귀 (plan_v2 5단계 19): 실제 rubric 과 t3 설계서 §8 로 gaps 가 SPEC8 질문을 그대로 내고,
2단계에서 들어온 새 floor(F-m8·C-m6·F-m9)를 「막는 체크」로 적은 §8 행도 시작 질문·미충족으로 이어지는지 본다."""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import rp_run as rr  # noqa: E402
from conftest import KORDOC_OUT, needs  # noqa: E402
from test_rp_run import _ws  # noqa: E402

HANDOFF = os.path.dirname(KORDOC_OUT)
RUBRIC = os.path.join(HANDOFF, "criteria", "rubric.yaml")
T3_SPEC = os.path.join(HANDOFF, "workspace", "proj-t3", "20_spec.md")
PACK = os.path.join(HANDOFF, "evidence", "workspace", "proj-pack", "_ws")
NEW_ROWS = ("| 16 | 표 캡션 번호 체계(양식 라벨 병기 여부) | 양식 | F-m8 | 값 없이 |\n"
            "| 17 | KPI 3 기준값이 0 인지 값이 없는지 | 대장 | C-m6 | 값 없이 |\n"
            "| 18 | 제목 굵게 기대값(양식) | 양식 | F-m9 | 값 없이 |\n")


def _t3_ws(tmp_path, extra=""):
    run, ev = _ws(tmp_path)
    shutil.copy(RUBRIC, tmp_path / "criteria" / "rubric.yaml")
    shutil.copy(os.path.join(os.path.dirname(T3_SPEC), "50_form_spec.json"), tmp_path / "workspace" / "t" / "50_form_spec.json")
    shutil.rmtree(ev)                                       # 근거팩 사본(answers 가 대장에 쓰므로 원본을 쓰지 않는다)
    shutil.copytree(PACK, ev)
    spec = open(T3_SPEC, encoding="utf-8").read()
    if extra:
        head = spec.index("| 15 |")
        end = spec.index("\n", head) + 1
        spec = spec[:end] + extra + spec[end:]
    (tmp_path / "workspace" / "t" / "20_spec.md").write_text(spec, encoding="utf-8")
    return run, ev


@needs(RUBRIC)
@needs(T3_SPEC)
@needs(PACK)
def test_t3_spec8_questions_unchanged(tmp_path):
    run, _ = _t3_ws(tmp_path)
    s8 = [r["key"] for r in rr.gaps(run) if r["key"].startswith("SPEC8_")]
    assert s8 == ["SPEC8_2", "SPEC8_3"]                     # t3 21_questions.md 와 같다(8-1 은 CLASS3 가 맡는다)


@needs(RUBRIC)
@needs(T3_SPEC)
@needs(PACK)
def test_new_floors_in_spec8_become_floor_questions_and_unmet(tmp_path):
    run, _ = _t3_ws(tmp_path, NEW_ROWS)
    rows = {r["key"]: r for r in rr.gaps(run)}
    for n, cid in (("16", "F-m8"), ("17", "C-m6"), ("18", "F-m9")):
        r = rows[f"SPEC8_{n}"]
        assert r["check"] == cid and r["ask"].startswith("[floor]") and r["where"] == f"설계서 §8-{n}"
    rr.answers(run, spec_ok=True, external="no")            # 답 없음
    unmet = rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))
    assert unmet["F-m8"] == ["SPEC8_16"] and unmet["C-m6"] == ["SPEC8_17"] and unmet["F-m9"] == ["SPEC8_18"]
