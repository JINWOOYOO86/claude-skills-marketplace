# -*- coding: utf-8 -*-
"""plan_t4fix 1·5: 한 칸 한 작성자(잠금)·앞 수정 되돌림 거부·trim 의 floor op 보호·수정 미적용 결함과 정지 규칙."""
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import edit_apply as ea  # noqa: E402
import rp_run as rr  # noqa: E402
from conftest import KORDOC_OUT, needs  # noqa: E402
from test_rp_run import _budget_ws  # noqa: E402

T4 = os.path.join(os.path.dirname(KORDOC_OUT), "workspace", "proj-t4")
MD = "## 1-1. 동향\n\n- 가나다 라마바 사아자 차카타\n- 하나 둘 셋 넷 다섯\n"


def test_second_author_cannot_touch_a_line_locked_this_round():
    locked = {}
    text, rows = ea.apply_md(MD, [{"id": "1", "op": "replace", "anchor": "라마바", "new": "라마바 파하"}], "writer:1-1", locked)
    assert rows[0]["status"] == "applied" and rows[0]["line_before"] == "- 가나다 라마바 사아자 차카타"
    _, rows = ea.apply_md(text, [{"id": "7", "op": "replace", "anchor": "사아자", "new": "사아자 거너"}], "editor", locked)
    assert rows[0]["status"] == "rejected" and rows[0]["why"].startswith("슬롯 잠김: 이번 회차 writer:1-1 #1")
    _, rows = ea.apply_md(text, [{"id": "2", "op": "replace", "anchor": "사아자", "new": "사아자 거너"}], "writer:1-1", locked)
    assert rows[0]["status"] == "applied"                                   # 같은 작성자는 자기 줄을 다시 고칠 수 있다
    _, rows = ea.apply_md(text, [{"id": "8", "op": "replace", "anchor": "셋 넷", "new": "셋 넷 여섯"}], "editor", locked)
    assert rows[0]["status"] == "applied"                                   # 다른 줄은 된다


def test_op_that_restores_an_earlier_edit_is_rejected():
    hist = [{"round": 1, "author": "editor", "id": "1", "status": "applied", "line_before": "- 하나 둘 셋",
             "line_after": "- 하나 둘 셋 넷 다섯"}]
    _, rows = ea.apply_md(MD, [{"id": "3", "op": "replace", "anchor": " 넷 다섯", "new": ""}], "writer:1-1", {}, hist)
    assert rows[0]["status"] == "rejected"                                  # new 가 비어 vet 이 먼저 거부
    _, rows = ea.apply_md(MD, [{"id": "3", "op": "replace", "anchor": "셋 넷 다섯", "new": "셋"}], "writer:1-1", {}, hist)
    assert rows[0]["status"] == "rejected" and rows[0]["why"].startswith("앞 수정 되돌림: r1 editor #1")
    old = [{"round": 0, "author": "editor", "id": "9", "status": "applied", "anchor": "하나 둘", "new": "하나 둘 셋 넷 다섯"}]
    _, rows = ea.apply_md(MD, [{"id": "4", "op": "replace", "anchor": "하나 둘 셋 넷 다섯", "new": "하나 둘"}], "writer:1-1", {}, old)
    assert rows[0]["why"].startswith("앞 수정 되돌림")                     # 줄 기록이 없는 옛 원장: anchor·new 맞바뀜


@needs(os.path.join(T4, "edits", "r1_editor.json"))
def test_t4_round1_overwrites_are_blocked():
    """t4 회차 1 op 를 실제 순서(편집자 → 집필자)로 r0 에 다시 적용: 편집자 줄을 덮어쓴 집필자 op 11건이 적용 전에 막힌다."""
    text = open(os.path.join(T4, "rounds", "r0", "30_proposal.md"), encoding="utf-8").read()
    files = [os.path.join(T4, "edits", "r1_editor.json")] + sorted(f for f in glob.glob(os.path.join(T4, "edits", "r1_*.json")) if "editor" not in f)
    locked, rows = {}, []
    for f in files:
        a, ops = ea.load_edits(f)
        text, rs = ea.apply_md(text, ops, a, locked, [])
        rows += [dict(r, author=a) for r in rs]
    blocked = [(r["author"], r["id"]) for r in rows if r["status"] == "rejected" and r["why"].startswith("슬롯 잠김")]
    assert len(blocked) == 11 and ("writer:0", 2) in [(a, int(i)) for a, i in blocked]   # 「(영문)」을 도로 빼던 op


@needs(os.path.join(T4, "rounds", "r0", "70_machine.json"))
def test_t4_defects_are_s_m1_and_s_m2(tmp_path):
    """수정 당시 기계 검사(r0)·수정 뒤 원고(r1)·원장: S-m1(trim 되돌림·덮어씀)·S-m2(덮어씀)는 미적용 결함,
    B-m1·T-m3 은 op 가 원고에 남았으니 「고치려 했는데 실패」, F-m8 은 캡션 번호 매김으로 풀렸다."""
    for f in ("72_rounds.json", "74_수정원장.json"):
        shutil.copy(os.path.join(T4, f), tmp_path / f)
    shutil.copy(os.path.join(T4, "rounds", "r0", "70_machine.json"), tmp_path / "70_machine.json")
    shutil.copy(os.path.join(T4, "rounds", "r1", "30_proposal.md"), tmp_path / "30_proposal.md")
    d = rr.fix_defects(str(tmp_path), 1)
    assert sorted(d) == ["S-m1", "S-m2"] and "trim" in d["S-m1"]["state"] and "덮어씀" in d["S-m2"]["state"]


def test_repeated_floor_does_not_count_defects():
    h = {"history": [{"round": 0, "floor_fail": ["B-m1", "S-m2"]}, {"round": 1, "floor_fail": ["B-m1", "S-m2"], "defects": ["S-m2"]}]}
    assert rr.repeated_floor(h) == []                                       # 회차 0(초안)은 세지 않는다
    h["history"].append({"round": 2, "floor_fail": ["B-m1", "S-m2"]})
    assert rr.repeated_floor(h) == ["B-m1"]                                 # S-m2 는 회차 1 에서 결함이었다
    h["history"][1]["defects"] = []
    assert rr.repeated_floor(h) == ["B-m1", "S-m2"]


def test_trim_keeps_ops_that_fix_a_failing_floor(tmp_path):
    run, W = _budget_ws(tmp_path)
    t = open(W / "30_proposal.md", encoding="utf-8").read().replace("가" * 59, "가" * 59 + " 다라마")
    (W / "30_proposal.md").write_text(t, encoding="utf-8")
    (W / "70_machine.json").write_text(json.dumps({"checks": {"S-m1": {"ok": False, "severity": "fail"}}}), encoding="utf-8")
    rr.save_rounds(run, {"round": 1, "history": [], "sha": {}, "fixes": {"1": {}}})
    (W / "74_수정원장.json").write_text(json.dumps([{"round": 1, "author": "editor", "id": "3", "check": "S-m1", "section": "1-1",
                                                      "op": "replace", "anchor": "가가", "new": "가가 다라마", "status": "applied", "why": ""}]),
                                       encoding="utf-8")
    assert rr.trim(run)["reverted"] == []
    led = json.load(open(W / "74_수정원장.json", encoding="utf-8"))
    led[0]["check"] = "S-j4"                                                # judge 수정이면 되돌린다
    (W / "74_수정원장.json").write_text(json.dumps(led), encoding="utf-8")
    assert rr.trim(run)["reverted"] == ["3"]


def test_next_gives_one_retry_for_defects_then_moves_on(tmp_path):
    from test_rp_run import _ws
    run, ev = _ws(tmp_path)
    W = tmp_path / "workspace" / "t"
    (W / "20_spec.md").write_text("# s\n", encoding="utf-8")
    rr.gaps(run)
    rr.answers(run, spec_ok=True, external="no")
    (W / "30_proposal.md").write_text("# t\n", encoding="utf-8")
    d = {"S-m2": {"authors": ["editor"], "state": "editor #1 덮어씀(원고에 없음)"},
         "T-m3": {"authors": ["writer:0"], "state": "op 없음"}}
    rr.save_rounds(run, {"round": 1, "history": [], "sha": {}, "fixes": {"1": {"defects": d}}})
    n = rr.next_step(run)
    assert n["step"] == "retry" and "S-m2" in n["why"]
    ed = next(a for a in n["actions"] if a.get("agent") == "rp-editor")
    assert ed["output"].endswith("r1_editor_retry.json") and ed["reasons"] == {"S-m2": d["S-m2"]["state"]}
    wr = next(a for a in n["actions"] if a.get("agent") == "rp-writer")
    assert wr["output"] == {"0": os.path.join(run, "edits", "r1_0_retry.json")}
    assert n["actions"][-1]["cmd"][2:] == ["defects", "--run", run, "--retry"]
    x = rr.rounds(run)
    x["fixes"]["1"]["retry"] = {"before": d, "after": {}}
    rr.save_rounds(run, x)
    assert rr.next_step(run)["step"] != "retry"                             # 회차당 한 번


def _blind(tmp_path, judge, picks):
    import blind_compare as bc
    d = tmp_path / f"b_{judge}"
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    bc.prepare(str(tmp_path / "a.md"), str(tmp_path / "b.md"), str(d), "prev", "cur", judge)
    for k, p in zip(("1", "2"), picks):
        (d / f"response_{k}.md").write_text("| 항목 | 우위 | 이유 |\n|---|---|---|\n" + "".join(f"| {i} | {p} | x |\n" for i in bc.ITEMS),
                                            encoding="utf-8")
    return bc.tally(str(d)), d


def test_tally_flags_sweep_and_claude_self_bias(tmp_path):
    res, d = _blind(tmp_path, "claude", ("B", "A"))                        # 두 회 모두 cur: 6/6
    assert res["sweep"] == "cur" and res["self_bias"] is True
    md = (d / "blind.md").read_text(encoding="utf-8")
    assert "6항목 전부 cur 확정: 편향 의심" in md and "자기 평가 편향 가능" in md
    res, _ = _blind(tmp_path, "chatgpt", ("B", "B"))
    assert res["sweep"] is None and res["self_bias"] is False


def test_adopt_uses_chatgpt_when_consented(tmp_path):
    from test_rp_run import _tallied
    run, W = _tallied(tmp_path, "yes")
    x = rr.rounds(run)
    x.update({"round": 3, "adopted": 2, "adopt": {"2": {"adopted": True}}})
    rr.save_rounds(run, x)
    n = rr.next_step(run)
    assert n["step"] == "adopt" and "ChatGPT" in n["why"]
    assert n["actions"][0]["cmd"][-2:] == ["--judge", "chatgpt"] and n["actions"][1]["skill"] == "rp-blind"
    assert n["actions"][1]["fallback"]["cmd"][-2:] == ["--judge", "claude"]
    run2, _ = _tallied(tmp_path / "no", "no")
    y = rr.rounds(run2)
    y.update({"round": 3, "adopted": 2, "adopt": {"2": {"adopted": True}}})
    rr.save_rounds(run2, y)
    n2 = rr.next_step(run2)
    assert "자기 평가 편향 가능" in n2["why"] and n2["actions"][0]["cmd"][-2:] == ["--judge", "claude"]


@needs(os.path.join(T4, "rounds", "r1", "30_proposal.hwpx"))
def test_resume_from_t4_round1_rescored_with_current_checkers(tmp_path):
    """빠른 재현(plan_t4fix 7): t4 회차 1 스냅숏에서 새 워크스페이스. 지금 검사기로 다시 재면 T-m3·S-m2(검사기 오류)는 풀리고
    S-m1 은 수정 미적용 결함(trim 되돌림)으로 남는다."""
    H = os.path.dirname(os.path.dirname(T4))
    root = tmp_path / "root"
    (root / "criteria").mkdir(parents=True)
    for f in ("rubric.yaml", "notation.yaml", "style_ref.md"):
        if os.path.exists(os.path.join(H, "criteria", f)):
            shutil.copy(os.path.join(H, "criteria", f), root / "criteria" / f)
    shutil.copytree(os.path.join(H, "evidence", "workspace", "proj-pack", "_ws"), root / "evidence" / "workspace" / "proj-pack" / "_ws")
    dst = root / "workspace" / "t4-r2"
    r = rr.resume(T4, 1, str(dst))
    assert "T-m3" not in r["floor_fail"] and "S-m2" not in r["floor_fail"] and r["defects"] == ["S-m1"]
    x = rr.rounds(str(dst))
    assert x["round"] == 1 and x["adopted"] == 1 and x["resumed"]["round"] == 1
    assert open(dst / "30_proposal.md", encoding="utf-8").read() == open(os.path.join(T4, "rounds", "r1", "30_proposal.md"), encoding="utf-8").read()
    assert all(row["round"] <= 1 for row in json.load(open(dst / "74_수정원장.json", encoding="utf-8")))
