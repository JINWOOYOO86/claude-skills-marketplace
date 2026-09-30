# -*- coding: utf-8 -*-
"""unify_terms: 오늘(2026-09-27) 손으로 한 표기 통일 다섯 가지를 규칙이 그대로 낸다."""
import os
import sys

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import unify_terms as ut  # noqa: E402

NOTATION = {"units": {"시간": ["h"], "톤": ["t"]}, "number_formats": {"patent_us_grouping": True},
            "terms": [{"standard": "HFC", "variants": ["HFCs"], "except": ["HFCs 관리제도"]}]}


def _ev(tmp_path):
    (tmp_path / "15_axis_conflicts.md").write_text(
        "# B. 표기\n\n## B-1. 고정 표현\n\n| # | 항목 | 고정 표기 | 출처 축 |\n|---|---|---|---|\n"
        "| F1 | 특허 권리자 | **「Gana Advanced Materials(구 Dara)」** 이후 「Gana」 | 특허 |\n"
        "| F6 | 국내 전환일정 | **「일정(안)」** | 정책 |\n\n## B-2. 금지\n", encoding="utf-8")
    return str(tmp_path)


def test_units_patent_terms_and_fixed(tmp_path):
    ev = _ev(tmp_path)
    src = ("WP4 1,000 h 운전 / 약 9,000 h · | h | 열 · 소비 82,200 t − 생산 3,304 t · US 1234567 B2 · "
           "Gana(구 Dara) · HFCs 배출량 · 「HFCs 관리제도 개선방안」 · 2028년 일정(안)")
    out, log = ut.unify(src, NOTATION, ev)
    assert "1,000시간 운전 / 약 9,000시간 · | 시간 | 열" in out
    assert "82,200톤 − 생산 3,304톤" in out
    assert "US 1,234,567 B2" in out
    assert "Gana Advanced Materials(구 Dara)" in out and "Gana(구 Dara)" not in out
    assert "HFC 배출량" in out and "「HFCs 관리제도 개선방안」" in out          # 정책명 예외
    assert len(log) >= 7
    again, log2 = ut.unify(out, NOTATION, ev)
    assert again == out and log2 == []                                             # 멱등


def test_word_internal_letters_untouched(tmp_path):
    ev = _ev(tmp_path)
    out, log = ut.unify("width 3 tall · 2 hours 뒤 · 12 kWh · 1t급", NOTATION, ev)
    assert "3 tall" in out and "12 kWh" in out                                     # 낱말 안 h/t 는 그대로
    assert "2시간" in out or "2 hours" in out
