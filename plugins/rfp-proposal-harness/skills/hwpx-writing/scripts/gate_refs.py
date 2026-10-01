#!/usr/bin/env python3
"""규율 N — 참고문헌·출처 정합성 게이트 (근거팩 ↔ 제출본 crosscheck).

**「출처를 달았다」는 선언이고, 「그 출처가 실재하고 값이 같다」는 측정이다.** 이 스크립트는
조사 단계가 남긴 **근거팩**(`_workspace/*.md` 의 「확정 수치 대장」 + 조사 본문)과
심사자가 받는 **제출본 HWPX** 를 대조해, 문서가 인쇄한 출처·수치가 근거팩에 실재하는지를 기계로 확인한다.

  근거팩 ──「확정 수치 대장」(key·값·단위·기준연도·출처(계층)·확신도) + 조사 본문 전문
     ↕ crosscheck
  제출본 ──본문·표에 인쇄된 출처 표기 · 수치 · 계층 표기 · 인용 연도

★ 왜 필요했나 (2026-08-28 실측)
  종전 하네스에서 근거를 보는 기계 검사는 `gate_form.py` **F-12 하나뿐**이었고, 그것도
  **연차별 연구내용 표의 「근거」 열 4행**만 봤다. 나머지 전 문서의 출처·수치는 아무도 대조하지
  않았다. 게다가 F-12 는 근거팩에 「확정 수치 대장」 절이 없으면 **조용히 검사를 건너뛰고
  「--ledger 미지정」이라고 오보**했다 — `--ledger .` 을 준 실행에서도 그랬다(ai_r1~r3 근거팩은
  「# 10. 출처 목록」 형식이라 대장이 없었다). 근거 정합성이 「검사됨」으로 보고됐지만
  **실제로는 한 건도 대조되지 않은 상태**였다.

검사 항목
  N-1 근거팩 대장 실재        근거팩에 「확정 수치 대장」이 있는가        [fail]  ← 미측정을 통과로 위장하지 않는다
  N-2 유령 출처 0             문서가 인쇄한 출처가 근거팩에 실재하는가    [fail]
  N-3 미근거 수치 0           근거 절의 수치가 근거팩에 실재하는가        [fail]
  N-4 대역 임의 대표값 0      대역만 있는 지표에 단일 대표값을 썼는가(R4) [fail]
  N-5 저확신 단독 인용 0      확신도 「하」 값을 추정 표기 없이 썼는가     [warn]
  N-6 출처계층 표기 정합      문서의 (①~⑥) 가 대장 계층과 같은가         [warn]
  N-7 대장 인용 커버리지      대장 항목 중 문서가 인용한 비율             [warn]

사용:
  python3 gate_refs.py --hwpx 30_proposal.hwpx --pack . --spec .../default_form_spec.json \
      [--json 50_gate_refs.json] [--strict]

  --pack  조사 산출물이 있는 워크스페이스(근거팩) 경로. 여기 있는 `*.md` 전부를 근거로 본다.
  --strict  N-5·N-6·N-7 경고도 실패로 올린다(제출 직전 최종 점검용).

종료코드 0=PASS, 1=FAIL, 2=실행 오류.
"""
import argparse, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
T, P, TBL, TR, TC = (f"{{{HP}}}{x}" for x in ("t", "p", "tbl", "tr", "tc"))

TIERS = "①②③④⑤⑥"
LEDGER_HEAD = re.compile(r"^#{1,4}\s*.*확정\s*\S*\s*대장")
LEDGER_KEY = re.compile(r"[A-Z]{3,4}_[A-Z0-9_]{2,}")
UNKNOWN_VALS = {"미확인", "미확정", "확인못함", "확인불가", "-", "—", "", "n/a", "N/A"}

# 출처 토큰으로 오인하기 쉬운 기술용어·양식 어휘. 여기 있는 말은 「출처」로 세지 않는다.
STOPWORDS = {
    "AI", "ML", "DL", "LLM", "RD", "R&D", "KPI", "TRL", "GWP", "ODP", "COP", "SCOP",
    "NBP", "LFL", "ATW", "AWHP", "HVAC", "DB", "API", "GUI", "PC", "OS", "IT", "ICT",
    "CO2", "PFAS", "HFC", "HFCs", "HCFC", "CFC", "VOC", "SI", "IP", "QC", "QA",
    "WP", "WBS", "PM", "PL", "TB", "GB", "MW", "KW", "PV", "ESS", "BEMS",
    "Work", "Package", "Development", "Technology", "System", "Model", "Data",
    "In", "On", "The", "A", "An", "Of", "And", "For", "With", "Using", "Based",
}


# ───────────────────────── 제출본 읽기 ─────────────────────────

def norm(s):
    s = re.sub(r"\*\*|__", "", s or "")
    return re.sub(r"\s+", "", s)


def local_text(p):
    """이 문단에 직접 속한 텍스트(하위 표 제외) — gate_form.py 와 동일 규약."""
    out = []

    def walk(n):
        for ch in n:
            if ch.tag == TBL:
                continue
            if ch.tag == T:
                out.append(ch.text or "")
            walk(ch)

    walk(p)
    return "".join(out)


class Doc:
    """HWPX 를 절 단위로 쪼갠 뷰 — 표 셀도 소속 절의 텍스트에 넣는다."""

    def __init__(self, path, titles):
        self.sections, self.order = {}, []
        self.title_of = {norm(t): i for i, t in titles}
        self.cur = "_preamble"
        self._new(self.cur)
        zf = zipfile.ZipFile(path)
        for name in sorted(n for n in zf.namelist() if n.startswith("Contents/section")):
            self._walk(ET.fromstring(zf.read(name)))

    def _new(self, sid):
        if sid not in self.sections:
            self.sections[sid] = []
            self.order.append(sid)

    def _walk(self, node):
        for ch in node:
            if ch.tag == P:
                txt = local_text(ch)
                if norm(txt) in self.title_of:
                    self.cur = self.title_of[norm(txt)]
                    self._new(self.cur)
                self.sections[self.cur].append(txt)
                self._walk(ch)
            elif ch.tag == TBL:
                for tr in ch.findall(TR):
                    for tc in tr.findall(TC):
                        self.sections[self.cur].append(
                            "".join(t.text or "" for t in tc.iter(T)).strip())
            else:
                self._walk(ch)

    def text(self, sid):
        return " ".join(self.sections.get(sid, []))

    def all_text(self):
        return " ".join(self.text(s) for s in self.order)


# ───────────────────────── 근거팩 읽기 ─────────────────────────

def load_pack(pack_dir):
    """근거팩 색인 — 전문 텍스트 + 「확정 수치 대장」 행.

    대장 스키마: `| key | 값 | 단위 | 기준연도 | 출처(계층) | 확신도 |`
    """
    idx = {"text": "", "rows": [], "files": [], "ledger_files": []}
    if not pack_dir or not os.path.isdir(pack_dir):
        return idx
    chunks = []
    for fn in sorted(os.listdir(pack_dir)):
        if not fn.endswith(".md"):
            continue
        # 제출 원고 자체는 근거가 아니다 — 자기 자신을 근거로 삼으면 무엇이든 통과한다.
        if re.match(r"^3\d.*\.(build\.)?md$", fn) or "proposal" in fn:
            continue
        try:
            txt = open(os.path.join(pack_dir, fn), encoding="utf-8").read()
        except Exception:
            continue
        idx["files"].append(fn)
        chunks.append(txt)
        grab, has = False, False
        for line in txt.split("\n"):
            if LEDGER_HEAD.match(line):
                grab, has = True, True
                continue
            if grab and re.match(r"^#{1,4}\s", line):
                grab = False
            if not (grab and line.strip().startswith("|")):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or set(cells[0]) <= set("-: ") or cells[0] in ("key", "지표명"):
                continue
            idx["rows"].append({"file": fn, "key": cells[0], "value": cells[1],
                                "unit": cells[2], "year": cells[3],
                                "source": cells[4], "conf": cells[5]})
        if has:
            idx["ledger_files"].append(fn)
    idx["text"] = "\n".join(chunks)
    return idx


# ───────────────────────── 추출기 ─────────────────────────

DOCNUM = re.compile(r"arXiv[\s:]?\d{4}\.\d{4,5}|https?://[^\s()]+|"
                    r"\b\d{4}/\d{2,4}\b|\b[A-Z]{2,}[- ]?\d{4,}\b")
LATIN = re.compile(r"\b[A-Z][A-Za-z][A-Za-z0-9&.\-]{1,}\b")
QUOTED = re.compile(r"[「『]([^」』]{4,60})[」』]")
NUM_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|℃|K\b|억\s?달러|억\s?원|조\s?원|만\s?원|"
                      r"백만\s?달러|킬로톤|톤|kW|MW|GW|kg|g/day|시간|년|개월|배|명|건|종|대)")
RANGE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*~\s*(\d[\d,]*(?:\.\d+)?)\s*"
                   r"(%|℃|억\s?달러|억\s?원|조\s?원|킬로톤|톤|kW|MW|배|년)")
TIER_CITE = re.compile(r"(.{0,40}?)\(\s*([" + TIERS + r"])\s*\)")


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def source_tokens(text, stop):
    """출처로 셀 수 있는 고유 토큰만 뽑는다 — 문서번호·URL·라틴 고유명사·「」 인용 문서명."""
    toks = list(DOCNUM.findall(text))
    toks += [t for t in LATIN.findall(text) if t not in stop and not LEDGER_KEY.fullmatch(t)]
    toks += QUOTED.findall(text)
    return uniq(toks)


def in_pack(tok, pack_text):
    """근거팩에 실재하는가 — arXiv 는 번호만 맞아도 같은 문헌으로 본다."""
    if tok in pack_text:
        return True
    m = re.search(r"\d{4}\.\d{4,5}", tok)
    return bool(m and m.group(0) in pack_text)


def numf(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def num_in_pack(num, unit, pack_text, window=24):
    """근거팩에 「그 수치가 그 단위로」 실재하는가.

    ⚠️ 함정(실측 2026-08-28 음성시험): 처음엔 `num in pack_text` 로 봤는데, 「27종」을 「41종」으로
    바꿔 심어도 통과했다. `"41"` 이 근거팩 어딘가의 다른 숫자(2041·1.41…) 안에 부분문자열로
    들어 있었기 때문이다. **숫자는 경계를 물려 찾고, 단위가 곁에 있는지까지 봐야** 의미가 있다.
    """
    plain = num.replace(",", "")
    u = re.sub(r"\s+", "", unit)
    # ★ 「2040년」은 수량이 아니라 **날짜**다. 근거팩은 같은 사실을 「2040 50 %」처럼 연도 뒤에
    #   단위 없이 적기 때문에, 단위 인접까지 요구하면 실재하는 연도가 오탐으로 뜬다
    #   (실측 c3·c4: 정상 문서 2건이 `1-1:2040 년` 하나로 FAIL 났다). 연도는 값만 대조한다.
    if u == "년" and re.fullmatch(r"(19|20)\d\d", plain):
        u = ""
    for form in uniq([num, plain]):
        for m in re.finditer(r"(?<![\d.,])" + re.escape(form) + r"(?![\d.,])", pack_text):
            if not u:            # 연도처럼 단위 인접을 요구하지 않는 경우 — 값만 맞으면 실재다
                return True
            near = pack_text[m.end():m.end() + window]
            if u in re.sub(r"\s+", "", near):
                return True
    return False


# ───────────────────────── 검사 ─────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--pack", required=True, help="근거팩(조사 산출물) 워크스페이스 경로")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--strict", action="store_true", help="N-5·N-6·N-7 경고도 실패로 올린다")
    ap.add_argument("--json")
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    rc = spec.get("ref_check") or {}
    stop = STOPWORDS | set(rc.get("token_stopwords", []))
    ev_ids = rc.get("evidence_sections") or ["1-1", "1-2", "1-3"]
    cover_min = float(rc.get("ledger_coverage_min", 0.5))

    titles = [(n["id"], n["title"]) for n in spec["outline"]]
    doc = Doc(a.hwpx, titles)
    body = doc.all_text()
    pack = load_pack(a.pack)
    ptext = pack["text"]

    results, fails, warns = [], [], []

    def check(name, ok, detail, severity="fail", na=False):
        """na=True 면 「검사 미성립」 — 통과로 세지 않는다.

        ★ 공허한 OK 를 금지한다. 대장이 없으면 N-4~N-7 은 볼 것이 없어서 조용히 OK 가 났는데,
        그게 바로 종전 F-12 가 「--ledger 미지정」이라 찍으면서 통과를 발급하던 실패 방식이다.
        """
        if na:
            results.append({"name": name, "ok": None, "detail": detail, "severity": "na"})
            print(f"[N/A ] {name}  {detail}")
            warns.append(f"{name} — 미성립: {detail}")
            return
        sev = "fail" if (a.strict and severity == "warn") else severity
        tag = "OK " if ok else ("WARN" if sev == "warn" else "FAIL")
        results.append({"name": name, "ok": bool(ok), "detail": detail, "severity": sev})
        print(f"[{tag}] {name}  {detail}")
        if not ok:
            (warns if sev == "warn" else fails).append(f"{name} — {detail}")

    has_ledger = bool(pack["rows"])
    NA = "근거팩에 「확정 수치 대장」이 없어 대조할 기준이 없다"

    # N-1 근거팩 대장 실재 ------------------------------------------------------
    # 미측정을 통과로 위장하지 않는다. 대장이 없으면 N-4~N-7 은 아예 성립하지 않는다.
    check("N-1 근거팩 대장 실재",
          bool(pack["rows"]),
          (f"근거 파일 {len(pack['files'])}개 · 대장 {len(pack['ledger_files'])}개 파일 "
           f"{pack['ledger_files']} · 지표 {len(pack['rows'])}행")
          if pack["rows"] else
          (f"근거팩 `{a.pack}` 에 「확정 수치 대장」이 없다 (md {len(pack['files'])}개 확인). "
           "조사 산출물마다 `## 확정 수치 대장` 절을 붙여야 근거 대조가 성립한다(규율 R3)"))

    # N-2 유격 출처 0 -----------------------------------------------------------
    # 계층 표기가 붙은 인용구 + 문서번호·URL·「」 문서명을 「출처 자리」로 보고, 그 자리의
    # 고유 토큰만 대조한다. 본문 아무 단어나 세지 않으므로 오탐이 적다.
    cite_units = [m.group(0) for m in TIER_CITE.finditer(body)]
    cite_units += DOCNUM.findall(body)
    cite_units += [f"「{q}」" for q in QUOTED.findall(body)]
    ghosts = []
    for unit in cite_units:
        for tok in source_tokens(unit, stop):
            if not in_pack(tok, ptext) and tok not in ghosts:
                ghosts.append(tok)
    check("N-2 유령 출처 0", not ghosts,
          f"인용 자리 {len(cite_units)}곳 · 근거팩 실재 확인"
          if not ghosts else
          f"근거팩에 없는 출처 {len(ghosts)}건 {ghosts[:6]} — 문서에만 있는 출처는 심사에서 확인 불가다")

    # N-3 미근거 수치 0 ---------------------------------------------------------
    # 근거 절(기본 1-1·1-2·1-3)에 한정한다. 목표·일정·예산은 도출값이라 근거팩에 없는 것이 정상이다.
    orphan = []
    for sid in ev_ids:
        for num, unit in NUM_UNIT.findall(doc.text(sid)):
            token = f"{num} {unit}".strip()
            if num_in_pack(num, unit, ptext):
                continue
            if f"{sid}:{token}" not in orphan:
                orphan.append(f"{sid}:{token}")
    check("N-3 미근거 수치 0", not orphan,
          f"근거 절 {ev_ids} 의 수치 전량이 근거팩에 실재"
          if not orphan else
          f"근거팩에 없는 수치 {len(orphan)}건 {orphan[:6]} — 대장에 먼저 올리고 인용할 것(규율 R3)")

    # N-4 대역 임의 대표값 0 (규율 R4) -------------------------------------------
    # 근거팩이 「a~b」 대역만 가진 지표에 문서가 대역 안의 단일 값을 써 넣으면, 실행마다 값이 달라진다.
    picked = []
    ranges = [(numf(lo), numf(hi), re.sub(r"\s+", "", u)) for lo, hi, u in RANGE.findall(ptext)]
    ranges = [r for r in ranges if r[0] is not None and r[1] is not None]
    for num, unit in NUM_UNIT.findall(body):
        v, u = numf(num), re.sub(r"\s+", "", unit)
        if v is None or num_in_pack(num, unit, ptext):
            continue
        for lo, hi, ru in ranges:
            if u == ru and lo < v < hi:
                picked.append(f"{num} {unit} (근거팩 대역 {lo:g}~{hi:g} {ru})")
                break
    picked = uniq(picked)
    check("N-4 대역 임의 대표값 0", not picked,
          NA if not has_ledger else "대역 지표에 임의 대표값 없음"
          if not picked else
          f"{len(picked)}건 {picked[:4]} — 대역은 대역 그대로 적는다(규율 R4, 가공값 금지)",
          na=not has_ledger)

    # N-5 저확신 단독 인용 ------------------------------------------------------
    # 확신도 「하」 는 ⑤⑥ 계층·추정이다. 「추정치」 표기 없이 본문에 확정값처럼 인쇄하면 안 된다.
    # ★ 과제 설정값(PRJ_* — 연구기간·단계·TRL 등)은 「인용한 사실」이 아니라 계획서가 정하는
    #   파라미터다. 확신도가 「하」로 적혀도 추정 표기를 요구할 대상이 아니라서 제외한다
    #   (실측 c4: 이 제외가 없으면 PRJ_PERIOD·PRJ_TRL_START 등 5건이 전부 오탐으로 떴다).
    exempt = tuple(rc.get("low_conf_exempt_prefixes", ["PRJ_"]))
    bare = []
    for r in pack["rows"]:
        if r["conf"].strip() not in ("하", "低") or r["key"].startswith(exempt):
            continue
        val = r["value"].strip()
        if val in UNKNOWN_VALS or not re.search(r"\d", val):
            continue
        num = re.search(r"\d[\d,]*(?:\.\d+)?", val)
        if not num or num.group(0) not in body:
            continue
        i = body.find(num.group(0))
        if not re.search(r"추정|참고|대역|가능성", body[max(0, i - 60):i + 60]):
            bare.append(f"{r['key']}={val}")
    check("N-5 저확신 단독 인용 0", not bare,
          NA if not has_ledger else "확신도 「하」 값의 무표기 인용 없음"
          if not bare else
          f"{len(bare)}건 {bare[:4]} — 「추정치」 표기를 붙이거나 상위 계층 출처로 교체할 것",
          "warn", na=not has_ledger)

    # N-6 출처계층 표기 정합 ----------------------------------------------------
    # 문서가 `NIST 스크리닝(④)` 처럼 계층을 인쇄했으면, 대장이 같은 출처에 붙인 계층과 같아야 한다.
    tier_bad = []
    pack_tier = {}
    for r in pack["rows"]:
        for pre, tier in TIER_CITE.findall(r["source"]):
            for tok in source_tokens(pre, stop):
                pack_tier.setdefault(tok, set()).add(tier)
    for pre, tier in TIER_CITE.findall(body):
        for tok in source_tokens(pre, stop):
            known = pack_tier.get(tok)
            if known and tier not in known:
                item = f"{tok}({tier}) ≠ 대장 {sorted(known)}"
                if item not in tier_bad:
                    tier_bad.append(item)
    check("N-6 출처계층 표기 정합", not tier_bad,
          NA if not has_ledger else
          (f"계층 표기 {len(TIER_CITE.findall(body))}곳 — 대장과 일치"
           if not tier_bad else f"{len(tier_bad)}건 {tier_bad[:4]}"),
          "warn", na=not has_ledger)

    # N-7 대장 인용 커버리지 ----------------------------------------------------
    # 조사해 놓고 안 쓴 근거가 많다면 문서가 비어 있다는 뜻이다(분량 미달과 같은 신호).
    usable = [r for r in pack["rows"] if r["value"].strip() not in UNKNOWN_VALS]
    used = [r for r in usable
            if any(in_pack(t, body) for t in source_tokens(r["source"], stop))
            or (re.search(r"\d[\d,]*(?:\.\d+)?", r["value"] or "")
                and re.search(r"\d[\d,]*(?:\.\d+)?", r["value"]).group(0) in body)]
    cov = (len(used) / len(usable)) if usable else 1.0
    unused = [r["key"] for r in usable if r not in used]
    check(f"N-7 대장 인용 커버리지(≥{cover_min:.0%})", cov >= cover_min,
          NA if not has_ledger else
          (f"확정 지표 {len(usable)}개 중 {len(used)}개 인용 ({cov:.0%})"
           + (f" · 미인용 {unused[:6]}" if unused else "")),
          "warn", na=not has_ledger)

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 위반 {len(fails)}건"
          + (f" · 경고 {len(warns)}건" if warns else ""))
    for f in fails:
        print(f"  - {f}")
    for w in warns:
        print(f"  ~ {w}")
    if not pack["rows"]:
        print("\n⚠️ 근거팩에 「확정 수치 대장」이 없어 N-4~N-7 은 성립하지 않는다."
              "\n   조사 산출물(11_·12_·13_·14_*.md)마다 `## 확정 수치 대장` 절을 붙이고 다시 돌린다"
              "\n   (스키마: skills/rfp-research-axes/assets/ledger_schema.json · 규율 R3).")
    if a.json:
        json.dump({"pass": ok, "strict": a.strict,
                   "pack": {"dir": a.pack, "files": pack["files"],
                            "ledger_files": pack["ledger_files"], "rows": len(pack["rows"])},
                   "ghost_sources": ghosts, "orphan_numbers": orphan,
                   "range_picked": picked, "low_conf_bare": bare,
                   "tier_mismatch": tier_bad, "ledger_coverage": round(cov, 3),
                   "unused_ledger_keys": unused,
                   "checks": results, "fails": fails, "warns": warns},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"결과 JSON: {a.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
