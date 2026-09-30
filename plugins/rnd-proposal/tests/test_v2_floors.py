# -*- coding: utf-8 -*-
"""plan_v2 2단계 floor 검사 (2026-09-28): C-m5·C-m6·F-m8·F-m9·S-m6·T-m8 와 빈 칸 규칙.

실측 회귀: 외부 원본(원본, 통과해야 함) · t3 판(실패해야 함) · final(82 외과 수정본, 통과해야 함).
"""
import json
import os

from conftest import KORDOC_OUT, needs

from scripts import check_blank, check_captions, check_headings, check_internal, check_preserve, dash_replace

HANDOFF = os.path.dirname(KORDOC_OUT)
ORIG = os.path.join(HANDOFF, "orig.hwpx")
T3 = os.path.join(HANDOFF, "t3.hwpx")
FINAL = os.path.join(HANDOFF, "final.hwpx")
SPEC_P = os.path.join(HANDOFF, "workspace", "proj-t3", "50_form_spec.json")


def _spec():
    return json.load(open(SPEC_P, encoding="utf-8")) if os.path.exists(SPEC_P) else {}


def _md(p):
    from scripts.hwpx_text import hwpx_to_md
    return hwpx_to_md(p)


# ── T-m8 절 번호·작성 요령 ────────────────────────────────────────────────
def test_form_patterns_catch_cross_refs_not_dates_or_substances():
    bad = ["- 세계 시장 규모는 1-1의 규제로 커짐", "- 목표치 근거는 2-2 목표임", "- 3장의 실증 결과를 씀",
           "- 2-3의 KPI 5 재현은 연구원이 맡음", "- 본 조사 범위에서 확인됨", "- 파일은 C:\\temp\\a.md 에 둠"]
    good = ["- EU 시행일은 2027-01-01임", "- R-134a 대비 COP 비율", "- 1~3차년도 합산", "- HFC-125·134a 가 올라 있음",
            "- 표 1의 네 축을 모두 달성함", "- 200 g/day 생산", "- 성과지표 (KPI) 6개"]
    assert all(check_internal.find_form(s) for s in bad), [s for s in bad if not check_internal.find_form(s)]
    assert not any(check_internal.find_form(s) for s in good), [s for s in good if check_internal.find_form(s)]


def test_form_catches_slot_phrase_used_as_label():
    spec = {"outline": [{"blueprint": [{"lead": "시장 규모: 세계·국내",
                                        "slots": [{"text": "문제 정의 한 줄"}, {"text": "확장 방향 2~3개"}]}]}]}
    t = "### 1-3. 한계\n\n- 문제 정의 한 줄: 발굴~실증을 하나의 사슬로 이음\n- 시장 규모: 세계·국내\n- 시장 규모\n  - 문제 정의는 단절임\n"
    names = [h["name"] for h in check_internal.find_form(t, spec)]
    assert names == ["작성 요령 문구", "작성 요령 꼬리"]


# ── S-m6 라벨 비율 ────────────────────────────────────────────────────────
def test_label_ratio_and_repeats():
    t = "## 3-2\n\n- 기관별 역할: A\n- 기관별 역할: B\n- 서술형 문장임\n- 또 서술형 문장임\n"
    st = check_internal.label_stats(t)
    assert (st["labels"], st["total"]) == (2, 4) and st["repeats"] == ["기관별 역할"] and not st["ok"]
    assert check_internal.label_stats("- 문장임\n- 문장임\n")["ok"]


# ── F-m8 표 캡션 ──────────────────────────────────────────────────────────
def test_captions_rules():
    ok = "## 0. 요약\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n### 2-1. 목표\n\n[표 1] 목표\n\n| a |\n|---|\n| 1 |\n\n- 표 1의 목표임\n"
    assert check_captions.check_text(ok)[0]
    no_cap = ok.replace("[표 1] 목표\n\n", "")
    assert not check_captions.check_text(no_cap)[0]
    letter = ok.replace("[표 1]", "[표 A]")
    assert not check_captions.check_text(letter)[0]
    bad_ref = ok.replace("표 1의", "표 3의")
    assert not check_captions.check_text(bad_ref)[0]


# ── C-m6 0 의 해당 없음 ──────────────────────────────────────────────────
def test_blank_rule():
    t = "| # | 기준값 → 목표치 | 비고 |\n|---|---|---|\n| 1 | 해당 없음 → 4건 | 해당 없음 |\n"
    ok, probs, _ = check_blank.check_text(t)
    assert not ok and len(probs) == 1        # 비고 칸의 진짜 빈 칸은 그대로 둔다
    assert check_blank.check_text(t.replace("해당 없음 → 4건", "0 → 4건"))[0]


def test_dash_replace_zero_column():
    t = "| # | 기준값 → 목표치 | 비고 |\n|---|---|---|\n| 1 | \u2014 | \u2014 |\n"
    new, _ = dash_replace.replace_text(t)
    assert "| 1 | 0 | 해당 없음 |" in new
    assert dash_replace.replace_text(new)[0] == new


# ── C-m5 정보 보존 ────────────────────────────────────────────────────────
def test_preserve_synthetic_and_ledger(tmp_path):
    b = "### 3-2. 전략\n\n- 100 g/day 미달이면 증류 단수·흡착 정제를 보강함\n- ECHA 제한 목록과 ASHRAE 34 로 판정함\n- 공급 부족은 24.9배임\n"
    a = "### 3-2. 전략\n\n- 판정은 등급으로 함\n"
    res = check_preserve.compare(b, a)
    assert not res["ok"] and set(res["lost"]) >= {"수치", "규격명", "고유명사", "위험 대응"}
    # 표현만 바뀐 것은 보존으로 본다
    a2 = b.replace("보강함", "보강한다").replace("24.9배", "24.9 배")
    assert check_preserve.compare(b, a2)["ok"]
    led = tmp_path / "74_수정원장.md"
    led.write_text("| # | 회차 | 체크 | 절 | 전 | 후 | 판정 |\n|---|---|---|---|---|---|---|\n"
                   "| 1 | 1 | B-j3 | 3-2 | 공급 부족은 24.9배임 | | 의도적 제거(반복) |\n", encoding="utf-8")
    b3 = b.replace("- 100 g/day 미달이면 증류 단수·흡착 정제를 보강함\n- ECHA 제한 목록과 ASHRAE 34 로 판정함\n", "")
    assert not check_preserve.compare(b3, "### 3-2. 전략\n")["ok"]
    assert check_preserve.compare(b3, "### 3-2. 전략\n", str(led))["ok"]


@needs(ORIG)
@needs(FINAL)
def test_preserve_real_final_keeps_everything():
    """82 외과 수정본은 원본 정보를 전부 지켰다(82 검증: 숫자·영문 토큰 누락 0)."""
    assert check_preserve.check_paths(ORIG, FINAL)["ok"]


@needs(ORIG)
@needs(T3)
def test_preserve_real_t3_loses_80_regressions():
    lost = check_preserve.check_paths(ORIG, T3)["lost"]
    flat = {k: " ".join(t for t, _ in v) for k, v in lost.items()}
    for k, w in (("고유명사", "ECHA"), ("고유명사", "연구운영위원회"), ("규격명", "ASHRAE 34"), ("수치", "24.9"),
                 ("수치", "0.9971"), ("출처", "8,065,882")):
        assert w in flat.get(k, ""), (k, w)
    assert "위험 대응" in lost and "산출식" in lost


# ── 실측 세 판 ─────────────────────────────────────────────────────────────
@needs(ORIG)
@needs(T3)
@needs(FINAL)
def test_real_documents_orig_final_pass_t3_fails():
    spec = _spec()
    for path, want in ((ORIG, True), (FINAL, True), (T3, False)):
        md = _md(path)
        assert (not check_internal.find_form(md, spec)) is want, path
        assert check_internal.label_stats(md, spec)["ok"] is want, path
        assert check_captions.check_text(md)[0] is want, path
        assert check_blank.check_text(md)[0] is want, path


@needs(ORIG)
@needs(FINAL)
def test_heading_bold_real():
    assert not check_headings.check_hwpx(ORIG)[0]      # 장 제목 charPr 50 굵게 없음
    assert check_headings.check_hwpx(FINAL)[0]         # 82 #1~#5 에서 charPr 7(굵게)로 바꿈
    assert check_headings.check_hwpx(ORIG, {"style": {"heading_bold": {"h2": False}}})[0]


def test_captions_renumber_in_document_order():
    t = ("## 0. 요약\n\n| a |\n|---|\n| 1 |\n\n### 1-3. 한계\n\n[표 ?] 한계와 WP\n\n| a |\n|---|\n| 1 |\n\n"
         "### 2-2. 목표\n\n- 표 1의 목표임\n[표 A] 연차별 목표\n\n| a |\n|---|\n| 1 |\n\n### 3-3. 일정\n\n[표 1] 간트\n\n| a |\n|---|\n| 1 |\n")
    new, ch = check_captions.renumber(t)
    assert [b for _, b in ch] == ["[표 1] 한계와 WP", "[표 2] 연차별 목표", "[표 3] 간트"]
    assert "- 표 3의 목표임" in new                      # 옛 [표 1](간트)을 가리키던 언급이 따라간다
    assert check_captions.check_text(new)[0] and check_captions.renumber(new)[1] == []
