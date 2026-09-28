# -*- coding: utf-8 -*-
"""rp_run 시스템 모드: 단계 결정(next)·집계(score)·빈칸(gaps/answers)·묶음(fix-list)·분리/병합이 결정적인가."""
import json
import os
import sys
import time

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rp_run as rr  # noqa: E402

RUBRIC = """
items:
  구체:
    points: 20
    floor:
      - {id: C-m1, by: machine, applies_to: ['3-1'], impl: "check_rubric:R3"}
      - {id: C-m4, by: machine, applies_to: ['*'], severity: warn}
    ceiling:
      - {id: C-j4, by: judge, applies_to: ['3-1'], fix_by: [evidence, writer],
         needs: [{key: ORG_WP3, ask: "WP3 기관명"}, {key: ORG_WP4, ask: "WP4 기관명"}]}
      - {id: C-j2, by: judge, applies_to: ['1-1'], fix_by: writer}
  간결:
    points: 15
    floor: []
    ceiling:
      - {id: B-j3, by: judge, applies_to: ['*'], fix_by: editor}
      - {id: B-j1, by: judge, applies_to: ['*'], fix_by: editor}
  문체:
    points: 10
    floor: []
    ceiling:
      - {id: S-j1, by: judge, applies_to: ['*'], fix_by: [unify, editor]}
scoring: {formula: penalty, base_pct: 85, ceiling_pct: 15, floor_penalty_pct: 20, floor_penalty_max_pct: 40,
          target: 95, max_rounds: 6, stall_rounds: 2}
"""


def _ws(tmp_path, mode="submission"):
    """<root>/workspace/t/ 구조. root 에 criteria/rubric.yaml 과 evidence/workspace/x/_ws 를 둔다."""
    root = tmp_path
    run = root / "workspace" / "t"
    run.mkdir(parents=True)
    (root / "criteria").mkdir()
    (root / "criteria" / "rubric.yaml").write_text(RUBRIC, encoding="utf-8")
    ev = root / "evidence" / "workspace" / "x" / "_ws"
    ev.mkdir(parents=True)
    (ev / "10_ledger.md").write_text("| key | 값 | 단위 |\n|---|---|---|\n| ORG_WP3 | 가나연구원 | |\n| TECH_X | 미확인 | |\n", encoding="utf-8")
    (run / "requirements.md").write_text(f"---\ntitle: t\nmode: {mode}\nexternal_ai: chatgpt\nevidence: evidence/workspace/x/_ws\n---\n", encoding="utf-8")
    (run / "50_form_spec.json").write_text(json.dumps({"outline": [
        {"id": "0", "level": 2, "title": "0. 요약", "guide": ["a"]},
        {"id": "1", "level": 2, "title": "1. 배경", "guide": []},
        {"id": "1-1", "level": 3, "title": "1-1. 동향", "guide": ["b"], "blueprint": [{"lead": "핵심 기술: 범위", "slots": []}]},
        {"id": "3-1", "level": 3, "title": "3-1. 내용", "guide": [], "blueprint": [{"lead": "연차별 연구내용", "slots": []}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    return str(run), str(ev)


def _touch(p, dt=0.0):
    os.utime(p, (time.time() + dt, time.time() + dt))


def test_plan_and_evidence_resolution(tmp_path):
    run, ev = _ws(tmp_path)
    keys = [k for k, _ in rr.plan(run)]
    assert "figures" not in keys and keys[0] == "requirements" and keys[-1] == "report"
    assert rr.evidence_of(run) == os.path.abspath(ev)
    assert rr.rubric_of(run).endswith(os.path.join("criteria", "rubric.yaml"))


def test_gaps_finds_only_missing_keys_and_answers_write_ledger(tmp_path):
    run, ev = _ws(tmp_path)
    (tmp_path / "workspace" / "t" / "20_spec.md").write_text("# s\n\n## 8. 미확정\n\n| 항목 | 찾아본 곳 | 결정 |\n|---|---|---|\n| 8-4 **기관별 WP 배정** | x | y |\n", encoding="utf-8")
    rows = rr.gaps(run)
    assert [r["key"] for r in rows] == ["ORG_WP3", "ORG_WP4"]
    assert rows[0]["found"] and rows[0]["where"] == "근거팩 대장"
    assert not rows[1]["found"] and rows[1]["where"].startswith("설계서 §8-4")
    q = open(os.path.join(run, "21_questions.md"), encoding="utf-8").read()
    assert "| ORG_WP4 |" in q
    # t1(2026-09-27): 메인 세션이 답 끝에 꼬리표를 붙였다. answers 가 걷어 내고, 출처는 따로 둔다.
    q = q.replace("| WP4 기관명 | 설계서 §8-4 |  |", "| WP4 기관명 | 설계서 §8-4 | 다라연구원 (사용자 답 2026-09-27) |")
    open(os.path.join(run, "21_questions.md"), "w", encoding="utf-8").write(q)
    c = rr.answers(run, spec_ok=True, external="no")
    led = open(os.path.join(ev, "16_user_answers.md"), encoding="utf-8").read()
    assert "| ORG_WP4 | 다라연구원 |" in led and "사용자 답" not in led
    src = json.load(open(os.path.join(run, "22_answer_sources.json"), encoding="utf-8"))
    assert src["ORG_WP4"]["source"].startswith("사용자 답") and src["ORG_WP4"]["check"] == "C-j4"
    assert c["spec_approved"] is True and c["external_ai"] is False and c["unmet"] == []
    assert rr.spec_approved(run)
    assert rr.ledger_keys(ev)["ORG_WP4"] == "다라연구원"


def test_unmet_checks_excluded_from_fix_list(tmp_path):
    run, ev = _ws(tmp_path)
    rr.gaps(run)
    j = {"judgments": {"C-j4": {"ok": False, "section": "3-1", "why": "기관명 없음"},
                       "C-j2": {"ok": False, "section": "1-1", "why": "기준 없음"},
                       "B-j3": {"ok": False, "section": "3-1", "why": "반복"},
                       "S-j1": {"ok": False, "section": "*", "why": "표기"},
                       "B-j1": {"ok": True, "section": "1-1", "quote": "q"}}}
    (tmp_path / "workspace" / "t" / "70_judge.json").write_text(json.dumps(j), encoding="utf-8")
    (tmp_path / "workspace" / "t" / "70_machine.json").write_text(json.dumps({"checks": {
        "C-m1": {"ok": False, "severity": "fail"}, "C-m4": {"ok": False, "severity": "warn"}}}), encoding="utf-8")
    g = rr.fix_list(run)
    assert g["unmet"] == ["C-j4"]
    assert g["unify"] == ["S-j1"] and g["editor"] == ["B-j3", "S-j1"]
    assert g["writer"] == {"1-1": ["C-j2"], "3-1": ["C-m1"]}
    g2 = rr.fix_list(run, begin=True)
    assert g2["round"] == 1 and rr.rounds(run)["fixes"]["1"]["editor"] == ["B-j3", "S-j1"]


def test_score_writes_target_and_next_loops_until_reached(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n", encoding="utf-8")
    rr.gaps(run)
    rr.answers(run, spec_ok=True, external="no")
    assert rr.next_step(run)["step"] == "write"
    (W / "30_proposal.md").write_text("# t\n\n## 0. 요약\n\n- a\n\n## 1. 배경\n\n### 1-1. 동향\n\n- 핵심 기술: 범위\n  - x\n\n### 3-1. 내용\n\n- 연차별 연구내용\n  - y\n", encoding="utf-8")
    assert rr.next_step(run)["step"] == "assemble"
    for f in ("30_proposal.hwpx", "30_proposal.build.md"):
        (W / f).write_text("x", encoding="utf-8")
    _touch(W / "30_proposal.hwpx", 2); _touch(W / "30_proposal.build.md", 2)
    assert rr.next_step(run)["step"] == "machine"
    (W / "70_machine.json").write_text(json.dumps({"checks": {"C-m1": {"ok": True, "severity": "fail", "penalty_weight": 1}}}), encoding="utf-8")
    _touch(W / "70_machine.json", 4)
    assert rr.next_step(run)["step"] == "judge"
    (W / "70_judge.json").write_text(json.dumps({"judgments": {"C-j4": {"ok": False, "section": "3-1", "why": "w"}, "C-j2": {"ok": False, "section": "1-1", "why": "w"},
                                                                "B-j3": {"ok": True, "section": "*", "quote": "q"}, "B-j1": {"ok": True, "section": "*", "quote": "q"},
                                                                "S-j1": {"ok": True, "section": "*", "quote": "q"}}}), encoding="utf-8")
    _touch(W / "70_judge.json", 6)
    assert rr.next_step(run)["step"] == "tally"
    s = rr.score(run)
    assert s["target"] == 95 and s["reached"] is False and s["unmet"] == {"C-j4": ["ORG_WP4"]}
    _touch(W / "70_score.json", 8)
    assert rr.next_step(run)["step"] == "adopt"              # 회차 0: 스냅숏(plan_v2 3단계 10)
    assert rr.adopt(run)["adopted"] and (W / "rounds" / "r0" / "30_proposal.md").exists()
    n = rr.next_step(run)
    assert n["step"] == "fix" and any(a["do"] == "agent" and a["agent"] == "rp-writer" for a in n["actions"])
    assert not any(a.get("agent") == "rp-editor" for a in n["actions"])
    (W / "70_judge.json").write_text(json.dumps({"judgments": {k: {"ok": True, "section": "*", "quote": "q"} for k in ("C-j4", "C-j2", "B-j3", "B-j1", "S-j1")}}), encoding="utf-8")
    _touch(W / "70_judge.json", 10)
    rr.score(run); _touch(W / "70_score.json", 12)
    n = rr.next_step(run)
    assert n["step"] == "proofread" and "건너뜀" in n["why"]
    rr.mark(run, "skipped")
    assert rr.next_step(run)["step"] == "deliver"
    rr.deliver(run, str(tmp_path / "out.hwpx"))
    assert rr.next_step(run)["step"] == "report"
    rr.report(run)
    assert rr.next_step(run)["step"] == "done"
    rep = open(W / "90_제출보고.md", encoding="utf-8").read()
    assert "회차별 점수" in rep and "ORG_WP4" in rep


def test_stall_detection(tmp_path):
    run, ev = _ws(tmp_path)
    rr.save_rounds(run, {"round": 3, "history": [{"round": 1, "total": 90}, {"round": 2, "total": 90}, {"round": 3, "total": 89.5}], "fixes": {}, "sha": {}})
    assert rr.stalled(rr.rounds(run), 2) is True
    assert rr.stalled(rr.rounds(run), 0) is False
    rr.save_rounds(run, {"round": 3, "history": [{"round": 1, "total": 90}, {"round": 2, "total": 91}, {"round": 3, "total": 92}], "fixes": {}, "sha": {}})
    assert rr.stalled(rr.rounds(run), 2) is False


def test_split_then_merge_roundtrip_and_leads(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    md = "# t\n\n## 0. 요약\n\n- a\n  - b\n\n\n## 1. 배경\n\n### 1-1. 동향\n\n- 핵심 기술: 범위\n  - x\n\n\n### 3-1. 내용\n\n- 연차별 연구내용\n  - y\n\n\n"
    (W / "30_proposal.md").write_text(md, encoding="utf-8")
    r = rr.split(run)
    assert set(r["changed"]) == {"0", "1-1", "3-1"}
    assert open(W / "sections" / "1-1.md", encoding="utf-8").read() == "- 핵심 기술: 범위\n  - x\n"
    rr.merge(run)
    assert open(W / "30_proposal.md", encoding="utf-8").read() == md
    assert rr.leads(run)["ok"]
    (W / "30_proposal.md").write_text(md.replace("- 핵심 기술: 범위", "- 다른 리드"), encoding="utf-8")
    assert rr.leads(run)["missing"] == ["1-1: 핵심기술"]


def test_init_copies_inputs_only(tmp_path):
    run, ev = _ws(tmp_path)
    (tmp_path / "workspace" / "t" / "30_proposal.md").write_text("x", encoding="utf-8")
    dst = str(tmp_path / "workspace" / "t2")
    assert sorted(rr.init(run, dst)) == ["50_form_spec.json", "requirements.md"]
    assert not os.path.exists(os.path.join(dst, "30_proposal.md"))
    assert rr.next_step(dst)["step"] == "spec"


# ── 2026-09-27 t1 종단 테스트 결함 ────────────────────────────────────────────
RUBRIC_REQ = """
items:
  양식:
    points: 15
    floor:
      - {id: F-m4, by: machine, applies_to: ['0'], impl: "check_rubric:R6",
         requires: {from: form_guide, section: '0', values: {과제명: "@title", 전체 연구기간: PRJ_PERIOD}}}
  구체:
    points: 20
    floor:
      - {id: C-m1, by: machine, applies_to: ['*'], impl: "check_rubric:R3",
         requires: [{item: 모델 구성, section: '3-1', key: WP1_MODEL_ARCH, ask: "모델 구성"},
                    {item: 대상 상태영역, section: '3-1', key: ORG_WP3}]}
      - {id: B-m1, by: machine, applies_to: ['*'], impl: "check_rubric:R4"}
    ceiling:
      - {id: C-j4, by: judge, applies_to: ['3-1'], fix_by: writer, needs: [{key: ORG_WP3, ask: "WP3 기관명"}]}
scoring: {formula: penalty, base_pct: 85, ceiling_pct: 15, floor_penalty_pct: 20, floor_penalty_max_pct: 40,
          target: 95, max_rounds: 6, stall_rounds: 0}
"""


def test_gaps_asks_requires_keys_once(tmp_path):
    """machine 체크의 requires key 도 시작 질문에 오른다(t1: 모델 구성을 묻지 못했다). needs 와 겹치면 한 번만."""
    run, ev = _ws(tmp_path)
    (tmp_path / "criteria" / "rubric.yaml").write_text(RUBRIC_REQ, encoding="utf-8")
    rows = rr.gaps(run)
    keys = [r["key"] for r in rows]
    assert keys.count("ORG_WP3") == 1
    assert "WP1_MODEL_ARCH" in keys and "PRJ_PERIOD" in keys and "@title" not in keys
    assert not next(r for r in rows if r["key"] == "WP1_MODEL_ARCH")["found"]
    assert "C-m1" in rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))


def test_fix_list_routes_machine_failures_to_reported_sections(tmp_path):
    """applies_to 「*」 machine 실패: 보고된 sections 의 writer 로, 절을 모르면 editor 로 (t1 전에는 버려졌다)."""
    run, ev = _ws(tmp_path)
    (tmp_path / "criteria" / "rubric.yaml").write_text(RUBRIC_REQ.replace("key: WP1_MODEL_ARCH", "key: ORG_WP3"), encoding="utf-8")
    with open(os.path.join(ev, "10_ledger.md"), "a", encoding="utf-8") as f:     # 값이 있어야 미충족이 아니다
        f.write("| PRJ_PERIOD | 2026.04.01 ~ 2029.12.31, 3년 9개월 | |\n")
    (tmp_path / "workspace" / "t" / "70_machine.json").write_text(json.dumps({"checks": {
        "F-m4": {"ok": False, "severity": "fail", "sections": ["0"]},
        "C-m1": {"ok": False, "severity": "fail", "sections": ["3-1"]},
        "B-m1": {"ok": False, "severity": "fail", "sections": []}}}), encoding="utf-8")
    g = rr.fix_list(run)
    assert g["writer"] == {"0": ["F-m4"], "3-1": ["C-m1"]}
    assert g["editor"] == ["B-m1"]


def test_machine_step_does_not_stop_and_assemble_uses_loop(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n", encoding="utf-8")
    rr.gaps(run)
    rr.answers(run, spec_ok=True, external="no")
    (W / "30_proposal.md").write_text("# t\n", encoding="utf-8")
    for f in ("30_proposal.hwpx", "30_proposal.build.md"):
        (W / f).write_text("x", encoding="utf-8")
    _touch(W / "30_proposal.hwpx", 2); _touch(W / "30_proposal.build.md", 2)
    n = rr.next_step(run)
    assert n["step"] == "machine" and "--no-fail" in n["actions"][0]["cmd"]
    src = open(os.path.join(ROOT, "scripts", "rp_run.py"), encoding="utf-8").read()
    assert '"--loop"' in src and "rc == 3" in src


def test_same_floor_check_twice_stops_after_report(tmp_path):
    """같은 floor 체크가 연속 두 회차 실패하면 report 후 stopped. 교정·제출 복사로 가지 않는다."""
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n", encoding="utf-8")
    rr.gaps(run)
    rr.answers(run, spec_ok=True, external="yes")
    for f in ("30_proposal.md", "30_proposal.hwpx", "30_proposal.build.md", "70_machine.json", "70_judge.json", "70_score.json"):
        (W / f).write_text("{}", encoding="utf-8")
    for i, f in enumerate(("30_proposal.md", "30_proposal.hwpx", "30_proposal.build.md", "70_machine.json", "70_judge.json", "70_score.json")):
        _touch(W / f, 2 * i)
    (W / "70_machine.json").write_text(json.dumps({"checks": {"C-m1": {"ok": False, "severity": "fail", "detail": "모델 구성", "sections": ["3-1"]}}}), encoding="utf-8")
    _touch(W / "70_machine.json", 6)
    (W / "70_score.json").write_text(json.dumps({"total": 80, "target": 95, "reached": False, "unmet": {}}), encoding="utf-8")
    _touch(W / "70_score.json", 10)
    # 회차 0 한 번 실패: 아직 멈추지 않는다 (수정 회차로 간다)
    rr.save_rounds(run, {"round": 0, "history": [{"round": 0, "total": 80, "floor_fail": ["C-m1"]}], "fixes": {}, "sha": {},
                         "adopt": {"0": {"adopted": True}}, "adopted": 0})
    assert rr.next_step(run)["step"] == "fix"
    # 회차 0(초안)·1 실패: 회차 0 은 수정 시도가 없으므로 세지 않는다(사용자 결정 2026-09-28, plan_t4fix)
    rr.save_rounds(run, {"round": 1, "history": [{"round": 0, "total": 80, "floor_fail": ["C-m1", "B-m1"]},
                                                 {"round": 1, "total": 84, "floor_fail": ["C-m1"]}], "fixes": {}, "sha": {},
                         "adopt": {"0": {"adopted": True}, "1": {"adopted": True}}, "adopted": 1})
    assert rr.repeated_floor(rr.rounds(run)) == []
    # 수정 회차 1·2 에서 연속 실패: 보고하고 멈춘다
    rr.save_rounds(run, {"round": 2, "history": [{"round": 0, "total": 80, "floor_fail": ["C-m1", "B-m1"]},
                                                 {"round": 1, "total": 84, "floor_fail": ["C-m1"]},
                                                 {"round": 2, "total": 85, "floor_fail": ["C-m1"]}], "fixes": {}, "sha": {},
                         "adopt": {"0": {"adopted": True}, "1": {"adopted": True}, "2": {"adopted": True}}, "adopted": 2})
    assert rr.repeated_floor(rr.rounds(run)) == ["C-m1"]
    n = rr.next_step(run)
    assert n["step"] == "report" and "C-m1" in n["why"]
    rr.report(run)
    n = rr.next_step(run)
    assert n["step"] == "stopped" and n["actions"][0]["do"] == "stop"
    rep = open(W / "90_제출보고.md", encoding="utf-8").read()
    assert "정지 사유" in rep and "C-m1" in rep
    # 미충족(답 없는 key) 체크는 연속 실패로 세지 않는다
    assert rr.repeated_floor(rr.rounds(run), {"C-m1": ["X"]}) == []


# ── t2(2026-09-27) 결함: §8 의 floor 막는 항목이 질문에 없었다 · 수정 회차가 분량을 넘겨 쪽수 floor 를 깼다 ─────
SPEC8_T2 = ("# s\n\n## 8. 미확정\n\n| # | 항목 | 찾아본 곳 | 막는 체크 | 결정 |\n|---|---|---|---|---|\n"
            "| #17 기술분류 소분류 3순위·비중 | 00_rfp | C-m1 | 메인 세션 판단 필요 |\n"
            "| #5 KPI 3 측정 주체 | 대장 | C-j2 | 값 없이 |\n"
            "| **#21** 2-3 표 열 구성 | 명세 | 해당 없음 | 6열 |\n\n## 승인 기록\n")


def test_spec8_rows_read_hash_ids_and_check_column(tmp_path):
    run, ev = _ws(tmp_path)
    (tmp_path / "workspace" / "t" / "20_spec.md").write_text(SPEC8_T2, encoding="utf-8")
    rows = rr.spec8_rows(run)
    assert [r["id"] for r in rows] == ["8-17", "8-5", "8-21"]
    assert rows[0]["checks"] == ["C-m1"] and rows[1]["checks"] == ["C-j2"] and rows[2]["checks"] == []
    assert rows[0]["item"].startswith("기술분류")


def test_spec8_floor_row_becomes_question_and_unmet_when_none(tmp_path):
    """floor 체크를 막는 §8 행만 SPEC8_N 으로 묻는다. 「없음」이면 그 floor 는 시작 질문에서 미충족으로 확정된다."""
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text(SPEC8_T2, encoding="utf-8")
    rows = rr.gaps(run)
    s8 = [r for r in rows if r["key"].startswith("SPEC8_")]
    assert [r["key"] for r in s8] == ["SPEC8_17"]                       # judge(C-j2)·체크 없음 행은 묻지 않는다
    assert not next(r for r in rows if r["key"] == "ORG_WP4")["ask"].startswith("[floor]")   # judge needs 는 표시 없음
    assert s8[0]["check"] == "C-m1" and s8[0]["ask"].startswith("[floor] 기술분류") and s8[0]["where"] == "설계서 §8-17"
    rr.answers(run, spec_ok=True, external="no")                          # 답 없음
    assert rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))["C-m1"] == ["SPEC8_17"]
    assert rr.repeated_floor({"history": [{"round": 0, "floor_fail": ["C-m1"]}, {"round": 1, "floor_fail": ["C-m1"]}]},
                             rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))) == []
    # 답이 있으면 대장으로 가고 미충족이 아니다
    q = open(W / "21_questions.md", encoding="utf-8").read().replace("| 설계서 §8-17 |  |", "| 설계서 §8-17 | 에너지효율향상 60 %, 신재생 30 %, 화학 10 % |")
    open(W / "21_questions.md", "w", encoding="utf-8").write(q)
    rr.answers(run, spec_ok=True, external="no")
    assert rr.ledger_keys(ev)["SPEC8_17"].startswith("에너지효율향상 60 %")
    assert "C-m1" not in rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))


def test_floor_requires_questions_are_marked_and_not_asked_twice(tmp_path):
    """floor requires 에서 온 질문은 「[floor]」. 같은 §8 행을 rubric key 질문이 이미 가리키면 SPEC8 로 또 묻지 않는다."""
    run, ev = _ws(tmp_path)
    (tmp_path / "criteria" / "rubric.yaml").write_text(RUBRIC_REQ, encoding="utf-8")
    (tmp_path / "workspace" / "t" / "20_spec.md").write_text(
        "# s\n\n## 8. 미확정\n\n| # | 항목 | 찾아본 곳 | 막는 체크 | 결정 |\n|---|---|---|---|---|\n"
        "| #9 WP1 모델 구성 | 대장 | C-m1 | 값 없이 |\n", encoding="utf-8")
    rows = rr.gaps(run)
    arch = next(r for r in rows if r["key"] == "WP1_MODEL_ARCH")
    assert arch["ask"].startswith("[floor] ") and arch["where"] == "설계서 §8-9"
    assert not any(r["key"].startswith("SPEC8_") for r in rows)
    with open(os.path.join(ev, "10_ledger.md"), "a", encoding="utf-8") as f:     # 값이 대장에 있어도 같은 §8 행을 또 묻지 않는다
        f.write("| WP1_MODEL_ARCH | D-MPNN | |\n")
    assert not any(r["key"].startswith("SPEC8_") for r in rr.gaps(run))


def _budget_ws(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "50_form_spec.json").write_text(json.dumps({
        "page_budget": {"chapters": {"1": 1.0}, "chars_per_page": 100},
        "outline": [{"id": "1", "level": 2, "title": "1. 배경", "guide": []},
                    {"id": "1-1", "level": 3, "title": "1-1. 동향", "guide": ["a"]},
                    {"id": "1-2", "level": 3, "title": "1-2. 시장", "guide": ["b"]}]}, ensure_ascii=False), encoding="utf-8")
    (W / "30_proposal.md").write_text("# t\n\n## 1. 배경\n\n### 1-1. 동향\n\n- " + "가" * 59 + "\n\n### 1-2. 시장\n\n- " + "나" * 39 + "\n",
                                      encoding="utf-8")
    return run, W


def test_check_section_fails_when_fix_exceeds_budget(tmp_path):
    """상한은 병합 전 원고로 정한다(장 예산 100자를 60:40 으로). 절을 늘려도 상한이 따라 늘지 않는다."""
    run, W = _budget_ws(tmp_path)
    (W / "sections").mkdir()
    (W / "sections" / "1-1.md").write_text("- " + "가" * 78 + "\n", encoding="utf-8")
    r = rr.check_section(run, "1-1")
    assert r["length"] == {"current": 79, "cap": 60, "ok": False}
    (W / "sections" / "1-1.md").write_text("- " + "가" * 50 + "\n", encoding="utf-8")
    assert rr.check_section(run, "1-1")["length"]["ok"] is True
    b = rr.budget(run)
    assert b["chapters"]["1"] == {"now": 100, "budget": 100, "ok": True}
    assert [s["target"] for s in b["sections"]] == [60, 40]


# ── 2026-09-28 보완: 체크 id 없는 §8 행 · 병합 전 분량 가드 ─────────────────────────────────
RUBRIC_CLASS = """
items:
  양식:
    points: 15
    floor:
      - {id: F-m4, by: machine, applies_to: ['0'], impl: "check_rubric:R6",
         requires: {from: form_guide, section: '0', values: {기술성숙도: [PRJ_TRL_START]VALUES}}}
  구조:
    points: 20
    floor:
      - {id: T-m3, by: machine, applies_to: ['0'], impl: "gate_form:F-4"}
scoring: {formula: penalty, base_pct: 85, ceiling_pct: 15, floor_penalty_pct: 20, floor_penalty_max_pct: 40,
          target: 95, max_rounds: 6, stall_rounds: 0}
"""
SPEC8_NOID = ("# s\n\n## 8. 미확정\n\n| 항목 | 찾아본 곳 | 결정 |\n|---|---|---|\n"
              "| #17 기술분류 소분류 3순위·비중(0장 CLASS3) | 공고 | 메인 세션 판단 필요 |\n"
              "| #13 기술성숙도 TRL 7 판정 기준 | 공고 | 값 없이 |\n\n## 승인 기록\n")


def _class_ws(tmp_path, with_key):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (tmp_path / "criteria" / "rubric.yaml").write_text(
        RUBRIC_CLASS.replace("VALUES", ", 연구 분야·기술분류: CLASS3" if with_key else ""), encoding="utf-8")
    (W / "50_form_spec.json").write_text(json.dumps({"outline": [
        {"id": "0", "level": 2, "title": "0. 요약", "special": ["CLASS3", "KEYWORDS5"],
         "guide": ["연구 분야·기술분류: 소분류 3순위까지(비중 %)", "기술성숙도 (TRL): 착수시점(n단계)"]}]}, ensure_ascii=False), encoding="utf-8")
    with open(os.path.join(ev, "10_ledger.md"), "a", encoding="utf-8") as f:
        f.write("| PRJ_TRL_START | 4 | |\n")
    (W / "20_spec.md").write_text(SPEC8_NOID, encoding="utf-8")
    return run, W


def test_spec8_row_without_check_id_is_asked_via_form_code(tmp_path):
    """t2 #17 은 「막는 체크」 없이 「(0장 CLASS3)」만 적혔다. 서식 코드로 T-m3 를 찾아 SPEC8_17 로 묻는다.
    값이 대장에 있는 칸(TRL)의 §8 행(#13)은 floor 를 막지 않으므로 묻지 않는다."""
    run, W = _class_ws(tmp_path, with_key=False)
    rows = rr.gaps(run)
    s8 = [r for r in rows if r["key"].startswith("SPEC8_")]
    assert [(r["key"], r["check"]) for r in s8] == [("SPEC8_17", "T-m3")]
    rr.answers(run, spec_ok=True, external="no")
    assert rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))["T-m3"] == ["SPEC8_17"]


def test_form_code_key_covers_its_format_check_once(tmp_path):
    """rubric 에 CLASS3 key 가 있으면 그 질문 하나가 F-m4 와 T-m3 를 함께 맡는다. 「없음」이면 둘 다 미충족."""
    run, W = _class_ws(tmp_path, with_key=True)
    rows = rr.gaps(run)
    assert [r["key"] for r in rows if not r["found"]] == ["CLASS3"]
    rr.answers(run, spec_ok=True, external="no")
    un = rr.unmet_checks(run, rr.load_rubric(rr.rubric_of(run)))
    assert un["F-m4"] == ["CLASS3"] and un["T-m3"] == ["CLASS3"]


def _edits(W, n, name, ops):
    (W / "edits").mkdir(exist_ok=True)
    (W / "edits" / f"r{n}_{name}.json").write_text(json.dumps({"author": name, "edits": ops}, ensure_ascii=False), encoding="utf-8")


def test_apply_edits_then_trim_reverts_this_rounds_additions_first(tmp_path):
    """고치기 모드: op 만 적용(거부는 원장에). 장 예산(100자)을 넘으면 이번 회차 추가 문장부터, 다음으로 가장 늘린 교체를 되돌린다."""
    run, W = _budget_ws(tmp_path)
    orig = open(W / "30_proposal.md", encoding="utf-8").read()
    rr.save_rounds(run, {"round": 1, "history": [], "sha": {}, "fixes": {"1": {"writer": {"1-1": ["C-j2"]}}}})
    _edits(W, 1, "1-1", [{"id": "a", "op": "insert_after", "anchor": "가" * 59, "new": "다" * 30},
                         {"id": "b", "op": "replace", "anchor": "나" * 39, "new": "나" * 39 + "라" * 5},
                         {"id": "c", "op": "delete", "anchor": "가" * 59}])
    st = rr.apply_edits(run)
    assert (st["applied"], st["rejected"]) == (2, 1)
    assert rr.apply_edits(run)["applied"] == 2                  # 같은 파일은 두 번 적용하지 않는다
    assert (W / "74_수정원장.md").exists() and (W / "sections" / "1-1.md").exists()
    assert not rr.budget(run)["ok"]
    tr = rr.trim(run)
    assert tr["reverted"] == ["a", "b"] and tr["over"] is None
    assert open(W / "30_proposal.md", encoding="utf-8").read() == orig
    led = json.load(open(W / "74_수정원장.json", encoding="utf-8"))
    assert [r["status"] for r in led] == ["reverted", "reverted", "rejected"]


def _adopt_ws(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    for i, f in enumerate(rr.SNAP):
        (W / f).write_text("{}" if f.endswith(".json") else f"{f} r0\n", encoding="utf-8")
        _touch(W / f, i)
    (W / "30_proposal.build.md").write_text("### 1-1. 동향\n\n- 판정은 ASHRAE 34 등급임\n", encoding="utf-8")
    rr.save_rounds(run, {"round": 0, "history": [{"round": 0, "total": 80, "floor_fail": []}], "fixes": {}, "sha": {}})
    assert rr.adopt(run)["adopted"]
    return run, W


def _blind(W, n, pick1, pick2):
    """직전 판(prev) 대 이번 판(cur). 1회 A=prev, 2회 A=cur."""
    import blind_compare as bc
    d = W / "rounds" / f"r{n}" / "blind"
    bc.prepare(str(W / "rounds" / "r0" / "30_proposal.build.md"), str(W / "30_proposal.build.md"), str(d), "prev", "cur", "claude")
    for k, pick in (("1", pick1), ("2", pick2)):
        rows = "".join(f"| {i} | {pick} | x |\n" for i in bc.ITEMS)
        (d / f"response_{k}.md").write_text("| 항목 | 우위 | 이유 |\n|---|---|---|\n" + rows, encoding="utf-8")


def test_adopt_reverts_when_previous_wins_blind_and_counts_as_stall(tmp_path):
    run, W = _adopt_ws(tmp_path)
    (W / "30_proposal.md").write_text("round1\n", encoding="utf-8")
    (W / "30_proposal.build.md").write_text("### 1-1. 동향\n\n- 판정은 ASHRAE 34 등급으로 정함\n", encoding="utf-8")
    rr.save_rounds(run, {**rr.rounds(run), "round": 1,
                         "history": [{"round": 0, "total": 80, "floor_fail": []}, {"round": 1, "total": 90, "floor_fail": []}]})
    _blind(W, 1, "A", "B")                                      # 두 번 모두 prev 가 이김
    res = rr.adopt(run)
    assert not res["adopted"] and "직전 판 확정 승" in res["reasons"][0]
    assert open(W / "30_proposal.md", encoding="utf-8").read() == "30_proposal.md r0\n"
    h = rr.rounds(run)
    assert h["adopted"] == 0 and h["history"][1]["reverted"]
    assert rr.stalled(h, 1)                                      # 되돌린 회차는 오르지 않은 회차


def test_adopt_accepts_when_not_losing_and_rejects_info_loss(tmp_path):
    run, W = _adopt_ws(tmp_path)
    (W / "30_proposal.build.md").write_text("### 1-1. 동향\n\n- 판정은 ASHRAE 34 등급으로 정함\n", encoding="utf-8")
    rr.save_rounds(run, {**rr.rounds(run), "round": 1})
    _blind(W, 1, "동등", "A")                                    # 2회 A=cur: prev 확정 승 없음
    assert rr.adopt(run)["adopted"] and (W / "rounds" / "r1" / "30_proposal.build.md").exists()
    (W / "70_machine.json").write_text(json.dumps({"checks": {"C-m5": {"ok": False, "detail": "고유명사 1"}}}), encoding="utf-8")
    rr.save_rounds(run, {**rr.rounds(run), "round": 2})
    _blind(W, 2, "동등", "동등")
    res = rr.adopt(run)
    assert not res["adopted"] and res["reasons"][0].startswith("C-m5") and rr.rounds(run)["adopted"] == 1


def test_fix_actions_editor_ops_then_writer_ops_then_trim(tmp_path):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n", encoding="utf-8")
    rr.gaps(run)
    rr.answers(run, spec_ok=True, external="no")
    names = ("30_proposal.md", "30_proposal.hwpx", "30_proposal.build.md", "70_machine.json", "70_judge.json", "70_score.json")
    for i, f in enumerate(names):
        (W / f).write_text("{}", encoding="utf-8")
        _touch(W / f, 2 * i)
    (W / "70_machine.json").write_text(json.dumps({"checks": {"C-m1": {"ok": False, "severity": "fail", "sections": ["3-1"]}}}), encoding="utf-8")
    (W / "70_judge.json").write_text(json.dumps({"judgments": {"B-j1": {"ok": False, "section": "*", "why": "w"}}}), encoding="utf-8")
    _touch(W / "70_machine.json", 6)
    _touch(W / "70_judge.json", 8)
    (W / "70_score.json").write_text(json.dumps({"total": 80, "target": 95, "reached": False, "unmet": {}}), encoding="utf-8")
    _touch(W / "70_score.json", 10)
    rr.save_rounds(run, {"round": 0, "history": [{"round": 0, "total": 80, "floor_fail": ["C-m1"]}], "fixes": {}, "sha": {},
                         "adopt": {"0": {"adopted": True}}, "adopted": 0})
    n = rr.next_step(run)
    seq = [a.get("agent") or os.path.basename(a["cmd"][1]) + ":" + a["cmd"][2] for a in n["actions"] if a["do"] in ("agent", "cmd")]
    last_apply = len(seq) - 1 - seq[::-1].index("rp_run.py:apply-edits")
    # plan_t4fix 1: 집필자 → 편집자 (편집자는 잠긴 줄 목록을 받는다) → trim → 결함 기록
    assert seq.index("writer_brief.py:--run") < seq.index("rp-writer") < seq.index("rp_run.py:apply-edits") \
        < seq.index("rp-editor") < last_apply < seq.index("rp_run.py:trim") < seq.index("rp_run.py:defects")
    ed = next(a for a in n["actions"] if a.get("agent") == "rp-editor")
    assert ed["output"].endswith(os.path.join("edits", "r1_editor.json"))
    assert ed["inputs"]["locked"].endswith(os.path.join("edits", "r1_locked.md"))
    assert "merge" not in " ".join(seq) and "budget-guard" not in " ".join(seq)


def test_trim_leaves_ops_outside_over_budget_chapters(tmp_path):
    """리허설(2026-09-28): 원래부터 예산을 넘던 장 때문에 다른 장의 교체가 되돌려지면 안 된다."""
    run, W = _budget_ws(tmp_path)
    (W / "30_proposal.md").write_text(open(W / "30_proposal.md", encoding="utf-8").read().replace("가" * 59, "가" * 80), encoding="utf-8")
    rr.save_rounds(run, {"round": 1, "history": [], "sha": {}, "fixes": {"1": {}}})
    (W / "74_수정원장.json").write_text(json.dumps([{"round": 1, "author": "writer:2-1", "id": "x", "section": "2-1", "op": "insert_after",
                                                      "anchor": "a", "new": "b", "status": "applied", "why": ""}]), encoding="utf-8")
    tr = rr.trim(run)
    assert tr["reverted"] == [] and tr["over"] == {"1": rr.budget(run)["chapters"]["1"]}


# ── plan_v2 4단계 (2026-09-28): 외부 교정 = 문제 목록 → 교정 회차 · 동의 경고 · 효과 실험 ─────────────
def _tallied(tmp_path, external="yes", proofread=None):
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    if proofread:
        req = open(W / "requirements.md", encoding="utf-8").read().replace("---\n", f"---\nproofread: {proofread}\n", 1)
        (W / "requirements.md").write_text(req, encoding="utf-8")
    (W / "20_spec.md").write_text("# s\n\n- 수행: 가나연구원 · 예산 120억원\n", encoding="utf-8")
    rr.gaps(run)
    rr.answers(run, spec_ok=True, external=external)
    for i, f in enumerate(("30_proposal.md", "30_proposal.hwpx", "30_proposal.build.md", "70_machine.json", "70_judge.json", "70_score.json")):
        (W / f).write_text("{}", encoding="utf-8")
        _touch(W / f, 2 * i)
    (W / "70_score.json").write_text(json.dumps({"total": 96, "target": 95, "reached": True, "unmet": {}}), encoding="utf-8")
    _touch(W / "70_score.json", 12)
    rr.save_rounds(run, {"round": 2, "history": [], "fixes": {}, "sha": {}, "adopt": {"2": {"adopted": True}}, "adopted": 2})
    return run, W


def test_proofread_off_skips_even_with_consent(tmp_path):
    run, W = _tallied(tmp_path, "yes", "off")
    n = rr.next_step(run)
    assert n["step"] == "proofread" and "교정 끔" in n["why"] and n["actions"][0]["cmd"][-1] == "skipped"


def test_proofread_on_gets_problem_list_then_editor_round(tmp_path):
    run, W = _tallied(tmp_path, "yes", "on")
    n = rr.next_step(run)
    kinds = [a.get("skill") or a.get("agent") or a["cmd"][2] for a in n["actions"]]
    assert kinds[0] == "rp-proofread" and "--problems" in n["actions"][1]["cmd"] and "--apply" not in n["actions"][1]["cmd"]
    assert kinds[2:] == ["mark", "rp-editor", "apply-edits", "trim"]
    assert n["actions"][3]["output"].endswith("r3_editor.json")
    (W / "60_교정문제.json").write_text(json.dumps([{"id": "1"}, {"id": "2"}]), encoding="utf-8")
    rr.mark(run, "done")
    h = rr.rounds(run)
    assert h["round"] == 3 and h["fixes"]["3"] == {"proofread": 2}


def test_proofread_default_on_with_consent(tmp_path):
    run, W = _tallied(tmp_path, "yes")
    assert rr.PROOFREAD_DEFAULT == "on" and rr.next_step(run)["actions"][0].get("skill") == "rp-proofread"


def test_no_consent_skips_and_ask_warns_sensitive_items(tmp_path):
    run, W = _tallied(tmp_path, "no", "on")
    assert "외부 전송 동의 없음" in rr.next_step(run)["why"]
    note = rr._sensitive_note(run)
    assert "가나연구원" in note and "120억원" in note


def test_experiment_decide_needs_all_judges(tmp_path):
    import blind_compare as bc
    exp = tmp_path / "exp"
    for judge, picks in (("chatgpt", ("A", "B")), ("claude", ("A", "동등"))):      # 1회 A=교정, 2회 A=미교정
        d = exp / f"blind_{judge}"
        (tmp_path / "a.md").write_text("a", encoding="utf-8")
        (tmp_path / "b.md").write_text("b", encoding="utf-8")
        bc.prepare(str(tmp_path / "a.md"), str(tmp_path / "b.md"), str(d), "교정", "미교정", judge)
        for k, p in zip(("1", "2"), picks):
            (d / f"response_{k}.md").write_text("| 항목 | 우위 | 이유 |\n|---|---|---|\n" + "".join(f"| {i} | {p} | x |\n" for i in bc.ITEMS), encoding="utf-8")
        bc.tally(str(d))
    res = rr.experiment_decide(str(exp))
    assert res["judges"]["chatgpt"]["교정"] and not res["judges"]["claude"]["교정"]
    assert res["decision"] == "off" and "끔" in (exp / "85_교정실험.md").read_text(encoding="utf-8")
