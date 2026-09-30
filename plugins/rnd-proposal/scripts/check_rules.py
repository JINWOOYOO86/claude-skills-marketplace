# -*- coding: utf-8 -*-
"""규칙 사이 모순 검사 (plan_t4fix 4, 2026-09-28).

t4: 근거팩 고정 표현 F10 「본 조사 범위에서 확인된 원천특허군의 청구범위 밖」·F12 「본 조사 범위에서 확인되지 않았다」가
T-m8 금지 표기 「본 조사 범위」에 걸렸다. 집필자는 고정 표현을 쓰라는 지시와 쓰지 말라는 검사 사이에서 회차를 썼다.
사용자 결정: 고정 문구 전체와 일치하는 문장만 허용(check_internal.find_form allow).

근거팩 §B-1 고정 표현을 한 줄씩 원고 기계 검사에 넣어 본다. 걸리면 모순이다.
    T-m8 절 번호·작업 메모(check_internal form) · T-m5 내부 용어(internal) · T-m7 RFP 표기(rfp)
    S-m6 「라벨: 내용」 · S-m2 미룬 티 표현(check_wording) · S-m4 메타·구어 · S-m5 대시류
§B-2 금지 표현이 §B-1 고정 표현 안에 들어 있어도 모순이다.
고정 문구 예외로 풀리는 것은 「예외로 허용」으로 따로 적는다.

    python check_rules.py --pack <근거팩 _ws> [--spec 50_form_spec.json]     # 풀리지 않은 모순이 있으면 exit 3
rp_run.py gaps 가 불러 풀리지 않은 모순을 시작 질문(key RULE_<고정 id>_<체크>)에 올린다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_internal as ci  # noqa: E402

DASH = re.compile("[\u2012-\u2015]")


def _probe_checks(line: str, spec: dict | None) -> list[tuple[str, str]]:
    """(체크 id, 걸린 까닭) 목록. 예외(allow) 없이 잰다."""
    import check_rubric
    import check_wording
    hits = [("T-m8", h["name"]) for h in ci.find_form(line, spec)]
    hits += [("T-m5", h["name"]) for h in ci.find_in_text(line)]
    hits += [("T-m7", h["name"]) for h in ci.find_in_text(line, "rfp")]
    if ci.LABEL_RX.match(line):
        hits.append(("S-m6", "「라벨: 내용」 머리"))
    hits += [("S-m2", v) for v, _ in check_wording.VAGUE if v in line]
    ok, d = check_rubric.internal_S_m4(line)
    if not ok:
        hits.append(("S-m4", d))
    if DASH.search(line):
        hits.append(("S-m5", "대시류 문자"))
    return hits


def check(pack: str, spec: dict | None = None) -> list[dict]:
    """반환: [{fixed, phrase, rule, why, resolved}] 고정 표현 × 검사·금지 표현 모순."""
    ph = ci.pack_phrases(pack)
    allow = [p for _, p in ph["fixed"]]
    out = []
    for fid, phrase in ph["fixed"]:
        line = "- " + phrase
        for rule, why in _probe_checks(line, spec):
            resolved = rule == "T-m8" and not ci.find_form(line, spec, allow)
            out.append({"fixed": fid, "phrase": phrase, "rule": rule, "why": why, "resolved": resolved})
        for xid, bad in ph["forbidden"]:
            if len(bad) >= 2 and bad in phrase:
                out.append({"fixed": fid, "phrase": phrase, "rule": xid, "why": f"금지 표현 「{bad}」", "resolved": False})
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--spec")
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8")) if a.spec and os.path.exists(a.spec) else None
    res = check(a.pack, spec)
    for r in res:
        print(f"  [{'예외로 허용' if r['resolved'] else '모순'}] {r['fixed']} 「{r['phrase'][:40]}」 ↔ {r['rule']} ({r['why']})")
    bad = [r for r in res if not r["resolved"]]
    print(f"규칙 모순 {len(bad)}건 · 고정 문구 예외로 허용 {len(res) - len(bad)}건")
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
