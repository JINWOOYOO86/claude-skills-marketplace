# -*- coding: utf-8 -*-
"""채점기 두 번째 보정점: 외부 원본(원본) 대 t3 판 (plan_v2 1-2, 2026-09-28).

보정 기준(사용자 결정 2026-09-28): 우리 채점기가
  (1) 총점 원본 > t3, (2) 양식 원본 > t3,
  (3) 80_비교검증 퇴행목록 (a) 내부 표기·(d) 정보 삭제를 floor 실패로 잡는다(원본은 통과).
외부 블라인드는 본문 텍스트만 보고 서식은 보지 않았으므로 서식 전용 floor 는 두 문서 모두 중립(통과)으로 둔다.

judge 는 rp-scorer 1회 결과를 fixture 로 고정한다(LLM 흔들림 제거).
2단계(floor 게이트, 2026-09-28)에서 통과: 서식 중립 원본 89.1 · t3 74.7, 양식 12.8 · 9.8.
"""
import json
import os

from conftest import KORDOC_OUT, ROOT, needs

from scripts import check_rubric as cr

HANDOFF = os.path.dirname(KORDOC_OUT)
CAL = os.path.join(HANDOFF, "criteria", "calibration_v2")
RUBRIC = os.path.join(HANDOFF, "criteria", "rubric.yaml")
SPEC = os.path.join(HANDOFF, "workspace", "proj-t3", "50_form_spec.json")
PACK = os.path.join(HANDOFF, "evidence", "workspace", "proj-pack", "_ws")
FIX = os.path.join(ROOT, "tests", "fixtures")
DOCS = {"orig": os.path.join(HANDOFF, "orig.hwpx"),
        "t3": os.path.join(HANDOFF, "t3.hwpx")}

# 본문 텍스트로 보이지 않는 것: 줄간격·글꼴·쪽수·장별 쪽수·표 선·제목 굵게·고아 제목·XML 무결성
FORMAT_ONLY = {"F-m1", "F-m2", "F-m3", "F-m5", "F-m7", "F-m9", "T-m4", "T-m6"}
# 새 원고에만 뜻이 있는 것: S-m7 원본 복사(원본 외부 원본은 문체 예시 원본 final 의 앞 판이라 96줄이 같다)
DRAFT_ONLY = {"S-m7"}
# 80 퇴행목록 (a)(d) 를 잡을 새 floor
NEW_FLOORS = {"C-m5", "C-m6", "F-m8", "S-m6", "T-m8"}


def _score(key: str) -> tuple[dict, dict]:
    md = os.path.join(CAL, f"{key}.md")
    before = os.path.join(CAL, "orig.md") if key == "t3" else None
    rep = cr.run_rubric(RUBRIC, md, DOCS[key], SPEC, pack=PACK, skip_pages=True, quiet=True, before=before)
    for cid in (FORMAT_ONLY | DRAFT_ONLY) & set(rep["checks"]):
        rep["checks"][cid]["ok"] = True
    judge = json.load(open(os.path.join(FIX, f"judge_{key}.json"), encoding="utf-8"))
    return rep, cr.score_items(cr.load_rubric(RUBRIC), rep, judge)


@needs(DOCS["orig"])
@needs(os.path.join(CAL, "orig.md"))
@needs(os.path.join(FIX, "judge_orig.json"))
def test_scorer_agrees_with_external_comparison():
    rep_o, sc_o = _score("orig")
    rep_t, sc_t = _score("t3")
    assert sc_o["total"] > sc_t["total"]
    assert sc_o["items"]["양식"]["score"] > sc_t["items"]["양식"]["score"]
    for cid in NEW_FLOORS:
        assert rep_t["checks"][cid]["ok"] is False, cid
        assert rep_o["checks"][cid]["ok"] is not False, cid
