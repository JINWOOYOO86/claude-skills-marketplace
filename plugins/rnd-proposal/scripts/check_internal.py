# -*- coding: utf-8 -*-
"""내부 표기 누출 검사 (rubric T-m5, 2026-09-27 t1 종단 테스트 결함).

t1 원고에 「사용자 답(2026-09-27)」이 20곳 찍혔다. 대장 출처 열의 내부 표기를 집필자가 출처 괄호로 옮긴 것이다.
최종 원고(md)와 hwpx(본문·표 셀)에 작업용 표기가 하나라도 있으면 실패한다.

    python check_internal.py --hwpx <out.hwpx>                 [--group internal|rfp]
    python check_internal.py --md   <30_proposal.build.md>

그룹 internal(T-m5): 아래 작업용 표기. 그룹 rfp(T-m7, 2026-09-28): 공고문 추적 표시.
  제출본 2026-09-27 hwpx 에 「(공고 RFP §3.1)」「(RFP 위험 ⑵)」「RFP 필수 하한」 등 14곳, t2 원고에 「RFP 정량목표」 2곳이 남았다.
  공고 요구사항은 내용으로 반영하고 「RFP」라는 말과 공고문 절 번호는 본문·표 어디에도 쓰지 않는다.

잡는 것: 사용자 답 · 근거팩 · 대장 key/행/출처 · 확신도 · _ws · evidence/ · workspace/ · 작업 파일명(*.md|json|yaml|py|hwpx)
         · 대장 key 모양(KPI_MEASURE_3, ORG_WP3)
0 이면 exit 0, 하나라도 있으면 exit 2.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile

PATTERNS = [
    ("사용자 답", r"사용자\s*답"),
    ("근거팩", r"근거\s*팩"),
    ("대장", r"수치\s*대장|대장\s*(?:key|키|행|값|출처)"),
    ("확신도", r"확신도"),
    ("작업 폴더", r"(?<![A-Za-z0-9])_ws\b|evidence/|workspace/"),
    ("작업 파일명", r"\b[\w\-]+\.(?:md|json|ya?ml|py|hwpx)\b"),
    ("대장 key", r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9]\b"),
]
PATTERNS_RFP = [
    ("RFP", r"(?<![A-Za-z])RFP(?![A-Za-z])"),
    ("공고문 절 번호", r"공고(?:문)?\s*(?:원문\s*)?§\s*\d"),
]
# 그룹 form(T-m8, plan_v2 2026-09-28): 80_비교검증 퇴행 (a). 절 번호로 내용을 대신하거나 작업 메모가 남은 표기.
#   「1-3의 한계별 WP」「목표치 도출 근거: 2-2 목표임」「3장의 실증 결과」「2-3의 KPI 5」「본 조사 범위에서」.
#   날짜(2027-01-01)·물질명(R-134a·HFC-125)·범위(1~3)는 숫자-숫자 뒤 조사가 없어 걸리지 않는다.
PATTERNS_FORM = [
    ("절 번호 상호참조", r"(?<![\w.\-])\d-\d(?:의|에서|과|와|로|를|에|\s*(?:목표|참조|절))(?![\d가-힣]*차년도)"),
    ("장 번호 상호참조", r"(?<![\w.])\d장(?:의|에서)"),
    ("KPI 번호 참조", r"(?<![A-Za-z])KPI\s*\d"),
    ("조사 범위 메모", r"본\s*조사\s*범위"),
    ("파일 경로", r"(?<![A-Za-z])[A-Za-z]:\\|(?:\.{0,2}/)?[\w\-]+/[\w\-./]+\.[A-Za-z]{2,4}\b"),
]
GROUPS = {"internal": [(n, re.compile(p)) for n, p in PATTERNS],
          "rfp": [(n, re.compile(p)) for n, p in PATTERNS_RFP],
          "form": [(n, re.compile(p)) for n, p in PATTERNS_FORM]}
LABEL_RX = re.compile(r"^\s*-\s*([^:：|]{2,25}?)\s*[:：]\s+\S")
LABEL_MAX = 0.15     # S-m6: 「라벨: 내용」 항목 비율 상한. 보정(2026-09-28) 외부 원본 0/121 · t3 62/105(59 %)
RX = GROUPS["internal"]
CTX = 20


def _scan(t: str, group: str = "internal") -> list[tuple[str, str]]:
    out = []
    for name, rx in GROUPS[group]:
        for m in rx.finditer(t):
            s = max(0, m.start() - CTX)
            out.append((name, t[s:m.end() + CTX].strip()))
    return out


def find_in_text(text: str, group: str = "internal") -> list[dict]:
    """줄 단위. 반환: [{line, heading, name, context}]. heading 은 그 줄이 속한 ##~#### 제목."""
    out, head = [], ""
    # HTML 주석(양식 안내)은 조립 전에 form_strip 이 지운다: 줄 번호는 지키고 내용만 비운다.
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    for i, ln in enumerate(text.splitlines(), 1):
        h = re.match(r"^#{2,4}\s+(.+)$", ln)
        if h:
            head = h.group(1).strip()
        for name, ctx in _scan(ln, group):
            out.append({"line": i, "heading": head, "name": name, "context": ctx})
    return out


def find_in_hwpx(path: str, group: str = "internal") -> list[dict]:
    """반환: [{para, in_table, name, context}]"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from check_dash import _para_texts
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)]
        xml = "".join(z.read(n).decode("utf-8", "replace") for n in sorted(names))
    out = []
    for i, (t, tbl) in enumerate(_para_texts(xml), 1):
        for name, ctx in _scan(t, group):
            out.append({"para": i, "in_table": tbl, "name": name, "context": ctx})
    return out


def _norm(x: str) -> str:
    return re.sub(r"[\s·,()（）\[\]「」『』/:：]", "", x)


def form_phrases(spec: dict) -> dict:
    """50_form_spec 에서 작성 요령 문구: {"slot": {정규화: 원문}, "lead_tail": {정규화: 원문}}.
    slot = blueprint 슬롯 문구(「문제 정의 한 줄」). lead_tail = 리드의 콜론 뒤 안내 꼬리(「시장 규모: 세계·국내」)."""
    slots, tails = {}, {}
    for n in spec.get("outline") or []:
        for b in n.get("blueprint") or []:
            lead = b.get("lead") or ""
            if re.search(r"[:：]", lead):
                tails[_norm(lead)] = lead
            for s in b.get("slots") or []:
                if len(_norm(s.get("text") or "")) >= 4:
                    slots[_norm(s["text"])] = s["text"]
    return {"slot": slots, "lead_tail": tails}


def pack_phrases(pack: str | None) -> dict:
    """근거팩 15_axis_conflicts.md 의 §B-1 고정 표현·§B-2 금지 표현: {"fixed": [(id, 문구)], "forbidden": [(id, 문구)]}.
    고정 표기 칸의 첫 굵은 「…」가 고정 문구, 금지 칸의 「…」(굵게 표시는 뗀다)가 금지 문구다."""
    out = {"fixed": [], "forbidden": []}
    p = os.path.join(pack or "", "15_axis_conflicts.md")
    if not pack or not os.path.exists(p):
        return out
    t = open(p, encoding="utf-8").read()
    b1 = re.search(r"^## B-1\..*?(?=^## )", t, re.M | re.S)
    b2 = re.search(r"^## B-2\..*?(?=^## |\Z)", t, re.M | re.S)
    for ln in (b1.group(0) if b1 else "").splitlines():
        m = re.match(r"^\|\s*(F\d+)\s*\|[^|]*\|\s*\*\*「([^」]+)」\*\*", ln)
        if m:
            out["fixed"].append((m.group(1), m.group(2)))
    for ln in (b2.group(0) if b2 else "").splitlines():
        m = re.match(r"^\|\s*(X\d+)\s*\|([^|]*)\|", ln)
        if m:
            out["forbidden"] += [(m.group(1), q.replace("**", "").strip()) for q in re.findall(r"「([^」]+)」", m.group(2))]
    return out


def fixed_allow(pack: str | None) -> list[str]:
    return [p for _, p in pack_phrases(pack)["fixed"]]


def _core(phrase: str) -> str:
    """고정 문구의 줄기: 개조식 종결(「않았다」→「않음」)이 달라도 같은 문구로 본다."""
    return re.sub(r"(?:았다|었다|였다|한다|된다|이다|다)$", "", phrase.strip())


def find_form(text: str, spec: dict | None = None, allow=()) -> list[dict]:
    """T-m8: PATTERNS_FORM + 양식 작성 요령 문구가 본문 라벨로 쓰인 줄(「문제 정의 한 줄: …」, 「시장 규모: 세계·국내」).
    allow: 근거팩 고정 표현(§B-1). 고정 문구 **전체**가 든 줄은 그 문구 안의 표기로 걸리지 않는다
    (사용자 결정 2026-09-28, plan_t4fix 4: F10·F12 「본 조사 범위에서 …」는 고정 문구일 때만 허용, 다른 자리의 「본 조사 범위」는 금지)."""
    hits = find_in_text(text, "form")
    cores = [c for c in (_core(a) for a in allow or ()) if c]
    if cores:
        lines = text.splitlines()

        def still(h):
            ln = lines[h["line"] - 1]
            rest = ln
            for c in cores:
                rest = rest.replace(c, " ")
            return rest == ln or any(n == h["name"] for n, _ in _scan(rest, "form"))
        hits = [h for h in hits if still(h)]
    ph = form_phrases(spec or {})
    if not (ph["slot"] or ph["lead_tail"]):
        return hits
    head = ""
    for i, ln in enumerate(text.splitlines(), 1):
        h = re.match(r"^#{2,4}\s+(.+)$", ln)
        if h:
            head = h.group(1).strip()
            continue
        if not re.match(r"^\s*-\s", ln):
            continue
        body = re.sub(r"^\s*-\s*", "", ln).strip()
        if _norm(body) in ph["lead_tail"]:
            hits.append({"line": i, "heading": head, "name": "작성 요령 꼬리", "context": body[:40]})
            continue
        m = LABEL_RX.match(ln)
        if m and _norm(m.group(1)) in ph["slot"]:
            hits.append({"line": i, "heading": head, "name": "작성 요령 문구", "context": body[:40]})
    return hits


def label_stats(text: str, spec: dict | None = None) -> dict:
    """S-m6: 개조식 항목 가운데 「라벨: 내용」 꼴 비율. 양식 리드 줄(blueprint lead)은 분모·분자에서 뺀다.
    같은 라벨이 연달아 나오는 곳(「기관별 역할:」 2회)은 repeats 로 따로 센다."""
    leads = {_norm(b.get("lead") or "") for n in (spec or {}).get("outline") or [] for b in n.get("blueprint") or []}
    total, lab, repeats, prev, heads, ex = 0, 0, [], None, set(), []
    head = ""
    for ln in text.splitlines():
        h = re.match(r"^#{2,4}\s+(.+)$", ln)
        if h:
            head, prev = h.group(1).strip(), None
            continue
        if not re.match(r"^\s*-\s", ln):
            continue
        body = re.sub(r"^\s*-\s*", "", ln).strip()
        if _norm(body) in leads:
            continue
        total += 1
        m = LABEL_RX.match(ln)
        name = _norm(m.group(1)) if m else None
        if m:
            lab += 1
            heads.add(head)
            if len(ex) < 3:
                ex.append(body[:30])
            if name == prev:
                repeats.append(m.group(1).strip())
        prev = name
    ratio = lab / total if total else 0.0
    return {"total": total, "labels": lab, "ratio": ratio, "repeats": repeats,
            "heads": sorted(heads), "examples": ex, "ok": ratio <= LABEL_MAX}


def summarize(hits: list[dict], group: str = "internal") -> str:
    label = {"internal": "내부 표기", "rfp": "내부 출처 표시(RFP)", "form": "절 번호·작성 요령 표기"}[group]
    if not hits:
        return f"{label} 0"
    by = {}
    for h in hits:
        by[h["name"]] = by.get(h["name"], 0) + 1
    return f"{label} {len(hits)}개 (" + " · ".join(f"{k} {v}" for k, v in by.items()) + ")"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx")
    ap.add_argument("--md")
    ap.add_argument("--max-show", type=int, default=30)
    ap.add_argument("--group", default="internal", choices=sorted(GROUPS) + ["label"])
    ap.add_argument("--spec", help="50_form_spec.json (form·label 그룹의 작성 요령 문구·리드)")
    a = ap.parse_args()
    if not a.hwpx and not a.md:
        ap.error("--hwpx 또는 --md")
    spec = json.load(io.open(a.spec, encoding="utf-8")) if a.spec else {}
    if a.group in ("form", "label"):
        # 제출본(hwpx)은 원고 md 꼴로 되돌려 같은 함수로 본다(hwpx_text)
        from hwpx_text import hwpx_to_md
        text = hwpx_to_md(a.hwpx) if a.hwpx else io.open(a.md, encoding="utf-8").read()
        if a.group == "label":
            st = label_stats(text, spec)
            print(f"  라벨 항목 {st['labels']}/{st['total']} ({st['ratio']:.0%}, 상한 {LABEL_MAX:.0%})"
                  + (f" · 연속 반복 {', '.join(st['repeats'])}" if st["repeats"] else "")
                  + (f" · 예: {' / '.join(st['examples'])}" if st["examples"] else ""))
            print(("PASS" if st["ok"] else "FAIL") + ": 「라벨: 내용」 비율")
            return 0 if st["ok"] else 2
        hits = find_form(text, spec)
    else:
        hits = []
        if a.hwpx:
            hits += find_in_hwpx(a.hwpx, a.group)
        if a.md:
            hits += find_in_text(io.open(a.md, encoding="utf-8").read(), a.group)
    for h in hits[: a.max_show]:
        where = (f"문단 {h['para']}" + (" (표 안)" if h.get("in_table") else "")) if "para" in h else f"{h['line']}행 {h['heading']}"
        print(f"  [{h['name']}] {where}: …{h['context']}…")
    if len(hits) > a.max_show:
        print(f"  … 외 {len(hits) - a.max_show}건")
    print(("FAIL: " if hits else "PASS: ") + summarize(hits, a.group))
    return 2 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
