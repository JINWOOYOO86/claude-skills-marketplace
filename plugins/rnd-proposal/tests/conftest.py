# -*- coding: utf-8 -*-
"""플러그인 루트를 sys.path 에 올리고, 이 PC 에만 있는 실측 파일 경로를 상수로 둔다.

실측 파일이 없는 PC 에서는 해당 테스트를 skip 한다(실패가 아니다).
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FORM_DRAFT = os.path.join(ROOT, "forms", "proposal-draft")
TEMPLATE_DRAFT = os.path.join(FORM_DRAFT, "template.hwpx")

# 실측 파일 루트는 환경변수 RP_HANDOFF 로 준다. 없으면 해당 테스트는 skip 한다.
_BASE = os.environ.get("RP_HANDOFF", os.path.join(ROOT, "tests", "_local"))
# 엔진 경로 산출물 — 결함 B 가 있던 판 (셀 211개 중 99개 DASH)
OLD_ENGINE_OUT = os.path.join(_BASE, "old-engine", "proposal_final.hwpx")
# kordoc 경로 산출물 — 머리행 경계 DOUBLE_SLIM 62셀
KORDOC_OUT = os.path.join(_BASE, "양식 겸 샘플.hwpx")


def needs(path):
    return pytest.mark.skipif(not os.path.exists(path), reason=f"실측 파일 없음: {path}")
