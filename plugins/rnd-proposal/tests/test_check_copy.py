# -*- coding: utf-8 -*-
"""문체 예시 원본 복사 검사 S-m7 (plan_v2 5단계 16)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import check_copy as cc  # noqa: E402
from conftest import KORDOC_OUT, needs  # noqa: E402

PATTERNS = os.path.join(HERE, "..", "skills", "rp-run", "style_patterns.md")
STYLE_REF = os.path.join(os.path.dirname(KORDOC_OUT), "criteria", "style_ref.md")
REF = ("## 3-2. 추진 전략\n\n- 목표 달성\n"
       "  - 최종 목표의 판정 기준은 낮추지 않으며 후보 탐색 단계에서만 물성 우선순위를 조정해 탐색 범위를 바꿈\n")


def test_eight_word_copy_fails_and_paraphrase_passes():
    copied = "## 3-2. 추진 전략\n\n  - 판정 기준은 낮추지 않으며 후보 탐색 단계에서만 물성 우선순위를 조정해 탐색 범위를 바꿈\n"
    ok, probs, secs = cc.check_text(copied, REF)
    assert not ok and secs == ["3-2"]
    ok, _, _ = cc.check_text("## 3-2. 추진 전략\n\n  - 판정 기준은 그대로 두고 탐색 초기에만 물성 우선순위를 바꿔 범위를 넓힘\n", REF)
    assert ok


def test_evidence_and_title_runs_are_excluded():
    line = "  - 최종 목표의 판정 기준은 낮추지 않으며 후보 탐색 단계에서만 물성 우선순위를 조정해 탐색 범위를 바꿈\n"
    assert cc.check_text(line, REF, pack=line)[0]
    title = "가 나 다 라 마 바 사 아 자"
    assert cc.check_text(f"# {title}\n\n| 과제명 | {title} / English |\n", f"| 과제명 | (국문) {title} |\n")[0]


@needs(STYLE_REF)
def test_patterns_do_not_copy_the_source():
    assert cc.check_text(open(PATTERNS, encoding="utf-8").read(), open(STYLE_REF, encoding="utf-8").read())[0]
