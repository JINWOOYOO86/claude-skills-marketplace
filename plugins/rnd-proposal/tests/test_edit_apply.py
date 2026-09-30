# -*- coding: utf-8 -*-
"""외과 수정 엔진 edit_apply (plan_v2 3단계 9·11, 2026-09-28)."""
import json
import os

from conftest import KORDOC_OUT, ROOT, needs

from scripts import check_headings, check_preserve, edit_apply as ea
from scripts.hwpx_text import hwpx_to_md

HANDOFF = os.path.dirname(KORDOC_OUT)
ORIG = os.path.join(HANDOFF, "orig.hwpx")
FINAL = os.path.join(HANDOFF, "final.hwpx")
FIX82 = os.path.join(ROOT, "tests", "fixtures", "edits_82.json")

MD = """## 3. 연구 내용

### 3-2. 추진 전략

- 목표 달성·문제 해결 대응 전략
  - 100 g/day 미달이면 증류 단수·흡착 정제를 보강함(시험 결과)
  - 판정은 ASHRAE 34 등급으로 함
  - 누적 9,000시간은 1,000시간과 2대 병렬 각 4,000시간의 합임
  - 요약 9,000시간 반복 서술임

| 구분 | 값 |
|---|---|
| 가 | 1 |
"""


def _op(**k):
    return {"id": "t", "check": "S-j4", **k}


def test_replace_insert_merge_apply_and_keep_prefix():
    ops = [_op(op="replace", anchor="판정은 ASHRAE 34 등급으로 함", new="독성·가연성은 ASHRAE 34 등급으로 판정함"),
           _op(op="insert_after", anchor="증류 단수·흡착 정제를 보강함", new="정제 난이도가 높으면 촉매 조건 탐색을 병행함"),
           _op(op="replace", anchor="요약 9,000시간 반복 서술임", new="요약 반복 서술임")]   # 9,000 은 윗줄에 남는다(82 #23 꼴)
    new, rows = ea.apply_md(MD, ops)
    assert [r["status"] for r in rows] == ["applied"] * 3, rows
    assert "  - 정제 난이도가 높으면 촉매 조건 탐색을 병행함\n" in new
    assert rows[0]["section"] == "3-2"


def test_rejects_delete_token_loss_duplicates_labels_and_tables():
    cases = [
        (_op(op="delete", anchor="판정은 ASHRAE 34 등급으로 함"), "허용되지 않는 op"),
        (_op(op="replace", anchor="판정은 ASHRAE 34 등급으로 함", new="판정은 등급으로 함"), "보존 토큰 누락"),
        (_op(op="replace", anchor="9,000시간", new="9천 시간"), "2회"),
        (_op(op="replace", anchor="판정은 ASHRAE 34 등급으로 함", new="판정 기준: ASHRAE 34 등급"), "라벨"),
        (_op(op="insert_after", anchor="판정은 ASHRAE 34", new="3-1의 WP 를 따름"), "상호참조"),
        (_op(op="insert_after", anchor="| 가 | 1 |", new="나 2"), "표 행"),
        (_op(op="replace", anchor="판정은 ASHRAE 34 등급으로 함", new="첫 줄\n둘째 줄"), "여러 줄"),
        (_op(op="merge", anchor="판정은 ASHRAE 34 등급으로 함", anchor2="각 4,000시간의 합임",
             new="판정은 ASHRAE 34 등급으로 함"), "한 줄 전체"),
        (_op(op="merge", anchor="100 g/day 미달이면 증류 단수·흡착 정제를 보강함(시험 결과)",
             anchor2="판정은 ASHRAE 34 등급으로 함", new="100 g/day 미달이면 증류 단수·흡착 정제를 보강함(시험 결과)"), "보존 토큰 누락"),
    ]
    for op, why in cases:
        new, rows = ea.apply_md(MD, [op])
        assert rows[0]["status"] == "rejected" and why in rows[0]["why"], (op, rows[0]["why"])
        assert new == MD


def test_merge_keeps_both_lines_tokens():
    op = _op(op="merge", anchor="판정은 ASHRAE 34 등급으로 함", anchor2="요약 9,000시간 반복 서술임",
             new="판정은 ASHRAE 34 등급으로 하며 요약 9,000시간 반복 서술임")
    new, rows = ea.apply_md(MD, [op])
    assert rows[0]["status"] == "applied", rows
    assert "  - 판정은 ASHRAE 34 등급으로 하며 요약 9,000시간 반복 서술임\n" in new
    assert "  - 요약 9,000시간 반복 서술임\n" not in new
    assert new.count("\n") == MD.count("\n") - 1


def test_ledger_json_and_md(tmp_path):
    led = tmp_path / "74_수정원장.json"
    _, rows = ea.apply_md(MD, [_op(op="replace", anchor="판정은 ASHRAE 34 등급으로 함", new="판정은 ASHRAE 34 등급으로 정함"),
                               _op(op="delete", anchor="x")])
    ea.write_ledger(str(led), rows, 1, "editor")
    data = json.load(open(led, encoding="utf-8"))
    assert [d["status"] for d in data] == ["applied", "rejected"] and data[0]["round"] == 1
    md = (tmp_path / "74_수정원장.md").read_text(encoding="utf-8")
    assert "| 1 | 1 | editor | S-j4 |" in md and "거부: 허용되지 않는 op" in md


@needs(ORIG)
@needs(FINAL)
@needs(FIX82)
def test_82_surgical_record_reproduces_final(tmp_path):
    """82_외과수정 의 텍스트·서식 수정 23건을 외부 원본에 적용하면 원본 정보 손실 0, 제목 굵게 통과,
    각 수정 문장이 final 에 그대로 있다. (#14 새 표·#24·#27 소제목 삽입은 엔진 범위 밖)"""
    out = tmp_path / "rev.hwpx"
    author, ops = ea.load_edits(FIX82)
    rows = ea.apply_hwpx(ORIG, str(out), ops)
    assert all(r["status"] == "applied" for r in rows), [r for r in rows if r["status"] != "applied"]
    assert check_preserve.check_paths(ORIG, str(out))["ok"]
    assert check_headings.check_hwpx(str(out))[0]
    got, fin = hwpx_to_md(str(out)), hwpx_to_md(FINAL)
    for op in ops:
        if op.get("new"):
            assert op["new"] in got and op["new"] in fin, op["id"]
