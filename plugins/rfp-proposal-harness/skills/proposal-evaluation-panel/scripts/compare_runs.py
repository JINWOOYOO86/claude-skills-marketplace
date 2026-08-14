#!/usr/bin/env python3
"""재현성 측정 — 같은 입력으로 돌린 두 실행의 산출물이 얼마나 일치하는지 잰다.

「하네스가 재현 가능하다」는 **느낌이 아니라 수치**여야 한다. 이 스크립트는 두 워크스페이스를
받아 다섯 층위로 일치도를 잰다. 층위를 나누는 이유는 **어디가 흔들리는지**가 개선점이기 때문이다.

  L1 산출 구성   : 같은 파일들이 만들어졌는가
  L2 문서 구조   : 계획서 장·절 집합이 같은가            (양식 고정이면 1.00 이어야 정상)
  L3 정량 수치   : 「확정 수치 대장」의 지표·값이 같은가   ★ 가장 중요한 층 — 여기가 흔들리면 결론이 흔들린다
  L4 근거 개체   : 특허번호·기관명·분류코드·규제 기준값 집합이 같은가
  L5 서술 유사도 : 문자 3-gram 코사인 (표현 차이는 허용되므로 참고값)

사용:
  python3 compare_runs.py --a <워크스페이스A> --b <워크스페이스B> \
      [--out 재현성_보고서.md] [--json 재현성.json]

종료코드 0=정상 산출(판정은 보고서에서), 2=실행 오류.
"""
import argparse, json, math, os, re, sys
from collections import Counter, defaultdict

# ── 정규식 --------------------------------------------------------------------
RE_PATENT = re.compile(r"\b(?:US|KR|EP|JP|CN|WO)\s?\d{1,4}[\d,/\-]{3,}\s?(?:[AB]\d?)?\b")
RE_CPC = re.compile(r"\b[A-HY]\d{2}[A-Z]\s?\d+/\d+\b")
RE_DOCNO = re.compile(r"제?\s?\d{4}-\d{1,4}\s?호")
UNITS = r"%|억\s?달러|백만\s?달러|조\s?원|억\s?원|만원|kt|t|kg|g/day|g|시간|h|℃|kW|pt|년|개월|건|종|명|만대|대|tCO₂|MWh|FTE|M/Y"
RE_NUMUNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?(" + UNITS + r")")
RE_ORG = re.compile(r"\b[A-Z][A-Za-z]{2,}(?:\s[A-Z][A-Za-z]{2,})?\b")
STOP_ORG = {"The", "This", "For", "And", "With", "From", "STATUS", "OK", "PARTIAL",
            "AI", "GWP", "TRL", "KPI", "URL", "PDF", "HWPX"}


def norm_num(v):
    """1,234.0 → 1234 ; 값 비교는 문자열이 아니라 수치로."""
    try:
        f = float(v.replace(",", ""))
        return str(int(f)) if f == int(f) else f"{f:g}"
    except ValueError:
        return v


def read_all(root):
    """워크스페이스의 .md 를 전부 읽어 {상대경로: 내용}."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".md"):
                p = os.path.join(dirpath, f)
                try:
                    out[os.path.relpath(p, root)] = open(p, encoding="utf-8").read()
                except Exception:
                    pass
    return out


def jaccard(a, b):
    return (len(a & b) / len(a | b)) if (a | b) else 1.0


def ledger(text):
    """「확정 수치 대장」 표에서 (지표, 값) 추출. 표 형식이 조금 달라도 앞 두 칸만 본다."""
    out = {}
    grab = False
    for line in text.split("\n"):
        if re.match(r"^#{1,4}\s*.*확정\s*수치\s*대장", line):
            grab = True
            continue
        if grab and re.match(r"^#{1,4}\s", line):
            break
        if grab and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or set(cells[0]) <= set("-: "):
                continue
            key = re.sub(r"\*\*|`", "", cells[0]).strip()
            val = re.sub(r"\*\*|`", "", cells[1]).strip()
            if key and val and key not in ("지표명", "항목", "규제명", "지표"):
                m = RE_NUMUNIT.search(val)
                out[key] = norm_num(m.group(1)) + " " + m.group(2) if m else val[:40]
    return out


def entities(text):
    """근거 개체 — 특허번호·분류코드·공고번호·기관명·수치+단위."""
    e = set()
    e |= {re.sub(r"\s+", "", x) for x in RE_PATENT.findall(text)}
    e |= {re.sub(r"\s+", "", x) for x in RE_CPC.findall(text)}
    e |= {re.sub(r"\s+", "", x) for x in RE_DOCNO.findall(text)}
    e |= {x for x in RE_ORG.findall(text) if x not in STOP_ORG}
    e |= {norm_num(n) + u.replace(" ", "") for n, u in RE_NUMUNIT.findall(text)}
    return e


def cosine3(a, b):
    """문자 3-gram 코사인 — 표현 차이를 흡수한 서술 유사도."""
    def grams(s):
        s = re.sub(r"\s+", "", s)
        return Counter(s[i:i + 3] for i in range(len(s) - 2))
    ca, cb = grams(a), grams(b)
    if not ca or not cb:
        return 0.0
    dot = sum(ca[k] * cb[k] for k in ca.keys() & cb.keys())
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


def outline(text):
    return {re.sub(r"\s+", "", h) for h in re.findall(r"^#{2,3}\s+(.+?)\s*$", text, re.M)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="실행 A 워크스페이스")
    ap.add_argument("--b", required=True, help="실행 B 워크스페이스")
    ap.add_argument("--proposal", default="30_proposal", help="계획서 파일명 접두어")
    ap.add_argument("--out", help="보고서 md 경로")
    ap.add_argument("--json", help="결과 JSON 경로")
    a = ap.parse_args()

    A, B = read_all(a.a), read_all(a.b)
    L = []

    # L1 산출 구성 ------------------------------------------------------------
    fa, fb = set(A), set(B)
    l1 = jaccard(fa, fb)
    L.append(("L1 산출 구성", l1, f"공통 {len(fa & fb)} / A만 {sorted(fa - fb)} / B만 {sorted(fb - fa)}"))

    # L2 문서 구조 ------------------------------------------------------------
    pa = "\n".join(v for k, v in A.items() if k.startswith(a.proposal))
    pb = "\n".join(v for k, v in B.items() if k.startswith(a.proposal))
    oa, ob = outline(pa), outline(pb)
    l2 = jaccard(oa, ob) if (oa or ob) else None
    L.append(("L2 문서 구조(장·절)", l2,
              f"공통 {len(oa & ob)} · 불일치 {sorted(oa ^ ob)[:6]}" if l2 is not None else "계획서 없음"))

    # L3 정량 수치 ------------------------------------------------------------
    la = {}; lb = {}
    for k, v in A.items():
        la.update(ledger(v))
    for k, v in B.items():
        lb.update(ledger(v))
    keys = set(la) & set(lb)
    same = {k for k in keys if la[k] == lb[k]}
    conflict = sorted((k, la[k], lb[k]) for k in keys - same)
    l3_key = jaccard(set(la), set(lb))
    l3_val = (len(same) / len(keys)) if keys else None
    L.append(("L3-a 수치 대장 지표 일치", l3_key, f"A {len(la)}개 · B {len(lb)}개 · 공통 {len(keys)}개"))
    L.append(("L3-b 공통 지표의 값 일치", l3_val,
              f"일치 {len(same)} / 충돌 {len(conflict)}" if keys else "공통 지표 없음"))

    # L4 근거 개체 ------------------------------------------------------------
    ea = set().union(*(entities(v) for v in A.values())) if A else set()
    eb = set().union(*(entities(v) for v in B.values())) if B else set()
    l4 = jaccard(ea, eb)
    L.append(("L4 근거 개체", l4, f"A {len(ea)} · B {len(eb)} · 공통 {len(ea & eb)}"))

    # L5 서술 유사도 ----------------------------------------------------------
    l5 = cosine3("\n".join(A.values()), "\n".join(B.values()))
    L.append(("L5 서술 유사도(3-gram)", l5, "표현 차이는 허용 — 참고값"))

    # 종합: 핵심 3층(L2·L3-b·L4)의 가중 평균
    core = [x for x in (l2, l3_val, l4) if x is not None]
    overall = sum(core) / len(core) if core else 0.0

    lines = ["# 재현성 측정 보고서", "",
             f"- 실행 A: `{a.a}`", f"- 실행 B: `{a.b}`", "",
             "## 층위별 일치도", "", "| 층위 | 일치도 | 상세 |", "|---|---:|---|"]
    for name, val, det in L:
        lines.append(f"| {name} | {'—' if val is None else f'{val:.2f}'} | {det} |")
    lines += ["", f"**종합 재현성(L2·L3-b·L4 평균) = {overall:.2f}**", ""]

    if conflict:
        lines += ["## ★ 값이 갈린 지표 — 재현성을 깨는 지점", "",
                  "| 지표 | 실행 A | 실행 B |", "|---|---|---|"]
        lines += [f"| {k} | {x} | {y} |" for k, x, y in conflict[:40]]
        lines += ["", "> 이 표가 **하네스 개선의 작업 목록**이다. 값이 갈리는 원인은 대개",
                  "> ① 출처 선택이 자유롭거나 ② 편차 대역에서 대표값을 임의로 고르거나",
                  "> ③ 검색어가 고정돼 있지 않기 때문이다.", ""]

    only_a = sorted(ea - eb)[:25]
    only_b = sorted(eb - ea)[:25]
    lines += ["## 한쪽에만 나온 근거 개체(상위)", "",
              f"- A만: {', '.join(only_a) if only_a else '없음'}", "",
              f"- B만: {', '.join(only_b) if only_b else '없음'}", ""]

    report = "\n".join(lines)
    print(report[:4000])
    if a.out:
        open(a.out, "w", encoding="utf-8").write(report)
        print(f"\n보고서: {a.out}")
    if a.json:
        json.dump({"levels": [{"name": n, "score": v, "detail": d} for n, v, d in L],
                   "overall": overall, "conflicts": conflict,
                   "only_a": sorted(ea - eb), "only_b": sorted(eb - ea)},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"JSON: {a.json}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
