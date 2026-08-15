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
        if re.match(r"^#{1,4}\s*.*확정\s*\S*\s*대장", line):   # 「수치/근거」 등 표기 흔들림 흡수
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
            unit = re.sub(r"\*\*|`", "", cells[2]).strip() if len(cells) > 2 else ""
            if key and val and key not in ("지표명", "항목", "규제명", "지표", "key"):
                # ★ 값 칸에서 첫 숫자만 뽑으면 「2024년 기준…」의 연도를 값으로 오독한다.
                #   숫자를 전부 모아 집합으로 두고, 단위 칸을 함께 붙여 비교 단위를 맞춘다.
                if "미확인" in val:
                    out[key] = "미확인"
                    continue
                body = re.sub(r"\([^)]*\)", "", val)          # 괄호 주석 제거
                nums = [norm_num(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", body)]
                out[key] = (" ".join(nums) + (" " + unit if unit and unit != "-" else "")).strip() \
                    if nums else re.sub(r"\s+", " ", body)[:40]
    return out


ORGY = re.compile(r"\((?:[^()]*)\)")          # 괄호 안(조사기관·비고)은 지표명에서 뺀다
KEY_STOP = {"규모", "시장", "값", "수치", "기준", "대역", "추정", "약", "및", "등",
            "세계", "글로벌", "국내", "한국", "연", "년", "기준값", "목표"}


def key_tokens(k):
    """지표명을 비교용 토큰 집합으로. 「세계 냉매시장 규모(GVR)」와 「세계 냉매시장 규모(대역)」이 같아지도록."""
    k = ORGY.sub("", k)
    k = re.sub(r"[^\w가-힣%℃/]+", " ", k)
    toks = {t for t in k.split() if len(t) > 1 and t not in KEY_STOP}
    return toks


def match_keys(la, lb, thr=0.5):
    """A·B 지표명을 주제 단위로 짝짓는다(그리디 최대 유사도). 반환: [(ka, kb, 유사도)]"""
    ta = {k: key_tokens(k) for k in la}
    tb = {k: key_tokens(k) for k in lb}
    pairs = []
    for ka, sa in ta.items():
        best, score = None, 0.0
        for kb, sb in tb.items():
            if not (sa | sb):
                continue
            j = len(sa & sb) / len(sa | sb)
            if j > score:
                best, score = kb, j
        if best and score >= thr:
            pairs.append((ka, best, round(score, 2)))
    used = set()
    out = []
    for ka, kb, sc in sorted(pairs, key=lambda x: -x[2]):
        if kb in used:
            continue
        used.add(kb)
        out.append((ka, kb, sc))
    return out


def val_equal(x, y):
    """값 동등성 — 목록은 집합, 숫자는 5% 오차, 그 밖은 문자열 정규화로 비교."""
    lx = [t.strip() for t in re.split(r"[,·/]", x or "") if t.strip()]
    ly = [t.strip() for t in re.split(r"[,·/]", y or "") if t.strip()]
    if len(lx) >= 2 and len(ly) >= 2 and not re.search(r"\d", x or ""):
        return {t.lower() for t in lx} == {t.lower() for t in ly}   # 나열 순서는 차이가 아니다
    nx = re.search(r"-?\d[\d,]*(?:\.\d+)?", x or "")
    ny = re.search(r"-?\d[\d,]*(?:\.\d+)?", y or "")
    if nx and ny:
        try:
            a, b = float(nx.group(0).replace(",", "")), float(ny.group(0).replace(",", ""))
            if a == b:
                return True
            return abs(a - b) <= max(abs(a), abs(b)) * 0.05      # 5% 이내는 같은 값으로 본다
        except ValueError:
            pass
    return re.sub(r"\s+", "", (x or "")) == re.sub(r"\s+", "", (y or ""))


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


def conclusions(md_text):
    """L6 — 계획서의 **결론**만 뽑는다: 표의 (행 라벨 → 값).

    ★ 왜 표인가: 계획서에서 심사자가 채점하는 결론(연구기간·TRL·최종목표·KPI 목표치·연차 목표·일정)은
      전부 표에 산다. 문장 유사도(L5)는 **표현이 닮았는지**를 재지만, 재현성이 실제로 물어야 하는 것은
      **같은 결론에 닿았는지**다. 실측(2026-08-15): 문장 유사도를 0.80 까지 올려도 KPI 목표치는
      4,300h / 1대 / 1대 로 갈려 있었다 — 표현은 같고 결론이 다른 문서였다.
    """
    out = {}
    for block in re.findall(r"(?:^\|.*$\n?)+", md_text, re.M):
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")]
                for ln in block.strip().split("\n")]
        for r in rows:
            if len(r) < 2 or set(r[0]) <= set("-: ") or not r[0]:
                continue
            key = re.sub(r"\s+", "", re.sub(r"\*\*|`", "", re.sub(r"\((?:[^()]*)\)", "", r[0])))
            if len(key) < 2 or key in ("항목", "구분", "key", "성과지표"):
                continue
            val = " ".join(c for c in r[1:] if c.strip())
            val = re.sub(r"\s+", " ", re.sub(r"\*\*|`", "", val)).strip()
            if val and key not in out:
                out[key] = val[:120]
    return out


def concl_equal(x, y):
    """결론 동등성 — 숫자가 있으면 숫자 집합으로, 없으면 토큰 자카드 0.6 이상."""
    nx = [norm_num(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", x or "")]
    ny = [norm_num(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", y or "")]
    if nx and ny:
        sx, sy = set(nx), set(ny)
        return len(sx & sy) / len(sx | sy) >= 0.5
    tx = {t for t in re.split(r"[^\w가-힣]+", x or "") if len(t) > 1}
    ty = {t for t in re.split(r"[^\w가-힣]+", y or "") if len(t) > 1}
    if not (tx or ty):
        return True
    return len(tx & ty) / len(tx | ty) >= 0.6


def measure_pair(dir_a, dir_b, proposal_prefix):
    """두 워크스페이스의 층위별 일치도를 dict 로 돌려준다(다자 비교용)."""
    A, B = read_all(dir_a), read_all(dir_b)

    def is_body(k):
        return k.startswith(proposal_prefix) and not re.search(r"manifest|prev|_v\d", k)

    pa = "\n".join(v for k, v in A.items() if is_body(k))
    pb = "\n".join(v for k, v in B.items() if is_body(k))
    oa, ob = outline(pa), outline(pb)
    la, lb = {}, {}
    for v in A.values():
        la.update(ledger(v))
    for v in B.values():
        lb.update(ledger(v))
    pairs = match_keys(la, lb)
    same = [(ka, kb) for ka, kb, _ in pairs if val_equal(la[ka], lb[kb])]
    ea = set().union(*(entities(v) for v in A.values())) if A else set()
    eb = set().union(*(entities(v) for v in B.values())) if B else set()
    ca, cb = conclusions(pa), conclusions(pb)
    ckeys = set(ca) & set(cb)
    csame = [k for k in ckeys if concl_equal(ca[k], cb[k])]
    return {
        "L6": (len(csame) / len(ckeys)) if ckeys else None,
        "L6_n": len(ckeys),
        "L6_diff": sorted((k, ca[k][:44], cb[k][:44]) for k in ckeys - set(csame))[:12],
        "L2": jaccard(oa, ob) if (oa or ob) else None,
        "L3a": (2 * len(pairs) / (len(la) + len(lb))) if (la or lb) else None,
        "L3b": (len(same) / len(pairs)) if pairs else None,
        "L4": jaccard(ea, eb),
        "L5": cosine3(pa, pb) if (pa and pb) else cosine3("\n".join(A.values()), "\n".join(B.values())),
        "conflicts": [(f"{ka} ↔ {kb}", la[ka], lb[kb]) for ka, kb, _ in pairs
                      if not val_equal(la[ka], lb[kb])],
    }


def multi(dirs, proposal_prefix, out=None, jsonp=None):
    """3회 이상 실행의 **쌍별** 일치도와 평균 — 재현성은 두 번이 아니라 여러 번으로 말해야 한다."""
    import itertools
    names = [os.path.basename(d.rstrip("/")) for d in dirs]
    rows, acc = [], defaultdict(list)
    for (i, a), (j, b) in itertools.combinations(list(enumerate(dirs)), 2):
        m = measure_pair(a, b, proposal_prefix)
        rows.append((f"{names[i]} ↔ {names[j]}", m))
        for k in ("L6", "L2", "L3a", "L3b", "L4", "L5"):
            if m[k] is not None:
                acc[k].append(m[k])
    lines = ["# 재현성 다자 측정 (쌍별)", "",
             "> **주지표는 L6(결론 일치도)** — 표에 담긴 결론(연구기간·TRL·최종목표·KPI 목표치·연차 목표)이",
             "> 같은지를 본다. L5(서술)는 표현이 닮았는지일 뿐이라 참고값이다.", "",
             "| 쌍 | **L6 결론** | L2 구조 | L3-a 지표 | L3-b 값 | L4 근거 | L5 서술 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, m in rows:
        f = lambda v: "—" if v is None else f"{v:.2f}"
        lines.append(f"| {name} | **{f(m['L6'])}**({m['L6_n']}행) | {f(m['L2'])} | {f(m['L3a'])} "
                     f"| {f(m['L3b'])} | {f(m['L4'])} | {f(m['L5'])} |")
    lines.append("")
    means = {k: (sum(v) / len(v) if v else None) for k, v in acc.items()}
    fm = lambda k: "—" if means.get(k) is None else f"{means[k]:.2f}"
    lines += [f"**평균** — **결론 {fm('L6')}** · 구조 {fm('L2')} · 지표 {fm('L3a')} · 값 {fm('L3b')} "
              f"· 근거 {fm('L4')} · 서술 {fm('L5')}", ""]
    worst6 = min((m["L6"] for _, m in rows if m["L6"] is not None), default=None)
    worst = min((m["L5"] for _, m in rows if m["L5"] is not None), default=None)
    if worst6 is not None:
        lines += [f"**최저 쌍 결론 일치 = {worst6:.2f}** (목표 0.90) · 서술 {worst:.2f} (참고, 목표 0.65~0.75)",
                  "", "재현성은 **최악 쌍**으로 말한다.", ""]
    diffs = [d for _, m in rows for d in m.get("L6_diff", [])]
    if diffs:
        seen, uniq = set(), []
        for k, x, y in diffs:
            if k not in seen:
                seen.add(k); uniq.append((k, x, y))
        lines += ["## ★ 결론이 갈린 항목 — 재현성의 실제 구멍", "",
                  "| 항목 | 값 A | 값 B |", "|---|---|---|"]
        lines += [f"| {k} | {x} | {y} |" for k, x, y in uniq[:20]]
        lines += [""]
    allc = [c for _, m in rows for c in m["conflicts"]]
    if allc:
        seen, uniq = set(), []
        for k, x, y in allc:
            if k not in seen:
                seen.add(k)
                uniq.append((k, x, y))
        lines += ["## 값이 갈린 지표", "", "| 지표 | 값 A | 값 B |", "|---|---|---|"]
        lines += [f"| {k} | {x} | {y} |" for k, x, y in uniq[:30]]
    report = "\n".join(lines)
    print(report)
    if out:
        open(out, "w", encoding="utf-8").write(report)
        print(f"\n보고서: {out}")
    if jsonp:
        json.dump({"pairs": [{"pair": n, **{k: v for k, v in m.items() if k != "conflicts"}} for n, m in rows],
                   "means": means, "worst_L5": worst},
                  open(jsonp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", help="실행 A 워크스페이스")
    ap.add_argument("--b", help="실행 B 워크스페이스")
    ap.add_argument("--runs", nargs="+", help="3회 이상 실행 — 쌍별 비교와 평균을 낸다")
    ap.add_argument("--proposal", default="30_proposal", help="계획서 파일명 접두어")
    ap.add_argument("--out", help="보고서 md 경로")
    ap.add_argument("--json", help="결과 JSON 경로")
    a = ap.parse_args()

    if a.runs:
        return multi(a.runs, a.proposal, a.out, a.json)
    if not (a.a and a.b):
        print("--a/--b 또는 --runs 가 필요하다")
        return 2

    A, B = read_all(a.a), read_all(a.b)
    L = []

    # L1 산출 구성 ------------------------------------------------------------
    fa, fb = set(A), set(B)
    l1 = jaccard(fa, fb)
    L.append(("L1 산출 구성", l1, f"공통 {len(fa & fb)} / A만 {sorted(fa - fb)} / B만 {sorted(fb - fa)}"))

    # L2 문서 구조 ------------------------------------------------------------
    # ★ 접두어만 보면 `30_proposal_manifest.md`·`_prev` 같은 부속 파일이 딸려 들어와
    #   L2(문서 구조)가 거짓으로 낮아진다. 계획서 본문만 고른다.
    def is_body(k):
        return k.startswith(a.proposal) and not re.search(r"manifest|prev|_v\d", k)
    pa = "\n".join(v for k, v in A.items() if is_body(k))
    pb = "\n".join(v for k, v in B.items() if is_body(k))
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
    # 지표명이 실행마다 달라지므로 **주제 단위로 짝지어** 비교한다
    # (「세계 냉매시장 규모(GVR)」 ↔ 「세계 냉매시장 규모(대역)」은 같은 주제로 본다)
    pairs = match_keys(la, lb)
    same = [(ka, kb) for ka, kb, _ in pairs if val_equal(la[ka], lb[kb])]
    conflict = sorted((f"{ka} ↔ {kb}", la[ka], lb[kb])
                      for ka, kb, _ in pairs if not val_equal(la[ka], lb[kb]))
    exact = len(set(la) & set(lb))
    l3_key = (2 * len(pairs) / (len(la) + len(lb))) if (la or lb) else None
    l3_val = (len(same) / len(pairs)) if pairs else None
    L.append(("L3-a 수치 대장 주제 일치", l3_key,
              f"A {len(la)}개 · B {len(lb)}개 · 주제 짝 {len(pairs)}개 (지표명 완전일치 {exact}개)"))
    L.append(("L3-b 짝지은 주제의 값 일치", l3_val,
              f"일치 {len(same)} / 충돌 {len(conflict)}" if pairs else "짝지어진 주제 없음"))

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
