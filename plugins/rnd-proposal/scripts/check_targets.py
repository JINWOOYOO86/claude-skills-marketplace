# -*- coding: utf-8 -*-
"""목표 하향 검사 (plan_v2 5단계 18, 2026-09-28).

t3: 공고·설계서의 KPI 4 목표 「R-134a 적용 시스템 동등 이상」이 시작 질문 답 「COP 비율 95 % 이상」으로 들어가
목표가 100 % 에서 95 % 로 내려갔는데 아무도 묻지 않았다.

기준 문장과 새 문장에서 방향이 있는 목표(수치 + 이상·이하·미만·초과·이내, 부등호, 「동등 이상」= 100 % 이상)를
뽑아, 같은 방향·같은 단위의 기준 목표보다 느슨해진 새 목표를 보고한다. 방향 없는 수치는 목표로 보지 않는다.

    python check_targets.py --base <기준 md> --new <새 md>      # 하향 있으면 exit 3

쓰는 곳: rp_run.py answers(기준 = 설계서 §2 에서 그 key 를 가리키는 행) · edit_apply.vet(기준 = 고치기 전 줄).
"""
from __future__ import annotations

import argparse
import re
import sys

NUM = r"([-−]?\d[\d,]*(?:\.\d+)?)"
UNIT = r"\s*(%|g/day|kg/day|시간|h|kW|MPa|K|°C|℃|건|종|점|배|억원|천원|원|톤|mgKOH/g|단계)?"
UP, DOWN = {"이상", "초과", ">", "≥", ">="}, {"이하", "미만", "이내", "<", "≤", "<="}
WORD = re.compile(NUM + UNIT + r"\s*(이상|이하|미만|초과|이내)")
SIGN = re.compile(r"(<=|>=|≤|≥|<|>)\s*" + NUM + UNIT)
SAME = re.compile(r"동등\s*(?:수준\s*)?이상")


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("−", "-"))


def _unit(u: str | None) -> str:
    return {"℃": "°C", "h": "시간"}.get(u or "", u or "")


def targets(text: str) -> list[dict]:
    """방향 있는 목표 목록: {val, unit, up(높을수록 엄격), label(앞 20자), at}."""
    out = []
    for m in WORD.finditer(text):
        out.append({"val": _num(m.group(1)), "unit": _unit(m.group(2)), "up": m.group(3) in UP,
                    "label": text[max(0, m.start() - 20):m.start()], "at": m.group(0)})
    for m in SIGN.finditer(text):
        out.append({"val": _num(m.group(2)), "unit": _unit(m.group(3)), "up": m.group(1) in UP,
                    "label": text[max(0, m.start() - 20):m.start()], "at": m.group(0)})
    for m in SAME.finditer(text):
        out.append({"val": 100.0, "unit": "%", "up": True, "same": True,
                    "label": text[max(0, m.start() - 20):m.start()], "at": m.group(0)})
    return out


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"[\s\d.,·()~:|→%]", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def lowered(base: str, new: str) -> list[dict]:
    """new 의 목표 중 base 의 같은 방향·단위 목표보다 느슨한 것. 후보가 여럿이면 앞 글자(라벨)가 가장 많이 겹치는 것과
    비교하고, 겹침이 0 이면 후보가 하나일 때만 비교한다(엉뚱한 지표와 맞대지 않게)."""
    bt = targets(base)
    out = []
    for t in targets(new):
        if t.get("same"):
            continue
        cand = [b for b in bt if b["up"] == t["up"] and b["unit"] == t["unit"]]
        if not cand:
            continue
        score = [(len(_bigrams(b["label"]) & _bigrams(t["label"])), i) for i, b in enumerate(cand)]
        best, i = max(score)
        if best == 0 and len(cand) > 1:
            continue
        b = cand[i]
        if (t["up"] and t["val"] < b["val"]) or (not t["up"] and t["val"] > b["val"]):
            out.append({"base": b["at"], "new": t["at"], "label": t["label"].strip()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    base = open(a.base, encoding="utf-8").read()
    new = open(a.new, encoding="utf-8").read()
    low = lowered(base, new)
    for d in low:
        print(f"목표 하향: 「{d['base']}」 → 「{d['new']}」 ({d['label']})")
    print(f"목표 하향 {len(low)}건")
    return 3 if low else 0


if __name__ == "__main__":
    sys.exit(main())
