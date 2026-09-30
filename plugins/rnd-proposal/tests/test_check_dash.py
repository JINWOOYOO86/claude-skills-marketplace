# -*- coding: utf-8 -*-
"""S-m5 대시류 0 — check_dash 검출과 dash_replace 치환 규칙."""
import os
import sys
import zipfile

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_dash as cd  # noqa: E402
import dash_replace as dr  # noqa: E402


def test_detects_all_four_dashes_but_not_minus_or_hyphen():
    hits = cd.find_in_text("a \u2012 b\n\u2013 c\nd \u2014 e\nf\u2015g\n\u22127 \u2103 2026-04-01")
    assert [h["ch"] for h in hits] == ["\u2012", "\u2013", "\u2014", "\u2015"]
    assert cd.find_in_text("\u22127 \u2103 2026-04-01 a-b") == []


def test_hwpx_scan_covers_table_cells(tmp_path):
    xml = ('<hs:sec xmlns:hp="x"><hp:p><hp:run><hp:t>본문 \u2014 부연</hp:t></hp:run></hp:p>'
           '<hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>셀 \u2013 값</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl></hs:sec>')
    p = tmp_path / "t.hwpx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", xml)
    hits = cd.find_in_hwpx(str(p))
    assert len(hits) == 2 and hits[1]["in_table"] is True and hits[0]["in_table"] is False
    assert "표 안 1" in cd.summarize(hits)


def test_replace_rules_and_idempotence():
    src = "\n".join([
        "- 시장 규모 \u2014 세계·국내",                       # 3 구분(리드)
        "  - 세계 성장률 \u2014 6.21 %임",                   # 3 구분(슬롯)
        "기간 2026\u20132029 · 1,000\u20149,000 h",           # 1 범위
        "| a | \u2014 | b |",                                 # 2 빈 칸(대시만)
        "|  |  | ■ |",                                        # 진짜 빈 칸은 그대로
        "본 과제는 회피 경로임 \u2014 특허 청구범위 밖. 다음 문장",   # 4 부연
        "R1234yf\u2013압축기유 시험",                          # 5 연결
        "값 없음 \u2014",                                      # 6 잔여(줄 끝)
    ])
    out, log = dr.replace_text(src)
    lines = out.splitlines()
    assert lines[0] == "- 시장 규모: 세계·국내"
    assert lines[1] == "  - 세계 성장률: 6.21 %임"
    assert lines[2] == "기간 2026~2029 · 1,000~9,000 h"
    assert lines[3] == "| a | 해당 없음 | b |"
    assert lines[4] == "|  |  | ■ |"
    assert lines[5] == "본 과제는 회피 경로임 (특허 청구범위 밖). 다음 문장"
    assert lines[6] == "R1234yf·압축기유 시험"
    assert cd.find_in_text(out) == []
    again, log2 = dr.replace_text(out)
    assert again == out and log2 == []                  # 멱등
    assert {r["rule"] for r in log} >= {1, 2, 3, 4, 5}


def test_lead_normalization_survives_colon_form():
    """gate_form F-11 은 `[—:：]` 앞부분만 비교한다 — 콜론형 리드도 같은 정규형이어야 한다."""
    import re
    norm = lambda x: re.split(r"[—:：]", re.sub(r"\s+", "", re.sub(r"\*\*|`", "", x)))[0]
    assert norm("시장 규모 \u2014 세계·국내") == norm("시장 규모: 세계·국내") == "시장규모"
