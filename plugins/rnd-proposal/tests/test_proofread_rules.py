# -*- coding: utf-8 -*-
"""외부 교정 = 문제 목록 (plan_v2 4단계 13, 2026-09-28). 외부 모델의 문장은 원고에 들어가지 않는다."""
import json

from scripts import check_proofread as cp

MD = "### 1-3. 한계\n\n- 선행 문헌의 예측 성능은 GWP 회귀 0.8790임\n- 불에 잘 타는 물질은 제외함\n- 제외함\n"

ANSWER = """# 외부 교정 문제 목록: chatgpt (2026-09-28)

| # | 절 | 원문 인용 | 문제 | 이유 | 제안 |
|---|---|---|---|---|---|
| 1 | 1-3 | 「불에 잘 타는 물질은 제외함」 | 구어체 | 「불에 잘 타는」은 계획서 어휘가 아님 | 가연성 물질은 제외함 |
| 2 | 1-3 | 제외함 | 모호 | 무엇을 제외하는지 없음 | 주관기관이 사전 확보함 |
| 3 | 1-3 | 없는 문장 | 오류 | 원고에 없음 | x |
"""


def test_problems_keep_only_unique_quotes_and_drop_suggestions(tmp_path):
    p, md, out = tmp_path / "60_교정문제.md", tmp_path / "30.md", tmp_path / "p.json"
    p.write_text(ANSWER, encoding="utf-8")
    md.write_text(MD, encoding="utf-8")
    rows = cp.run_problems(str(p), str(md), str(out))
    assert [r["status"] for r in rows] == ["유효", "기각: 인용 2회", "기각: 인용 0회"]
    valid = json.load(open(out, encoding="utf-8"))
    assert [v["id"] for v in valid] == ["1"] and valid[0]["quote"] == "불에 잘 타는 물질은 제외함"
    ledger = p.read_text(encoding="utf-8")
    # 외부 모델이 붙인 제안 문장(출처 귀속을 바꾸는 「주관기관이 사전 확보함」 포함)은 어디에도 남지 않는다
    assert "가연성 물질은 제외함" not in ledger and "사전 확보" not in ledger and "사전 확보" not in out.read_text(encoding="utf-8")
    assert "| 판정 |" in ledger and "기각: 인용 0회" in ledger


def test_parse_problems_skips_header_and_non_numbered_rows():
    rows = cp.parse_problems("| # | 절 | 원문 인용 | 문제 | 이유 |\n|---|---|---|---|---|\n| 가 | x | y | z | w |\n| 1 | 0 | 「a」 | b | c |\n")
    assert [(r["id"], r["quote"]) for r in rows] == [("1", "a")]


def test_before_after_still_catches_loss(tmp_path):
    b, a = tmp_path / "b.md", tmp_path / "a.md"
    b.write_text("- 성능 0.8790(PMC11497627)\n", encoding="utf-8")
    a.write_text("- 성능\n", encoding="utf-8")
    assert cp.before_after(str(b), str(a)) == 2
