#!/usr/bin/env python3
"""규율 K — 양식 준수 게이트.

「양식을 지켰다」는 **선언이 아니라 측정 결과**다. 이 스크립트는 양식 명세(JSON)와
**HWPX 산출물**(구조 기준)·**조립용 원고**(목차 기준)를 대조해 다음을 기계로 확인한다.

  F-1 장·절 제목 축자 일치 + 순서            [매체: hwpx]
  F-2 절 신설·누락 0 (양식 목차와 집합 일치)   [매체: md]
  F-3 절별 요구 항목 커버리지                  [매체: hwpx, 절 단위 스코프]
  F-4 지정 서식 특수검사(표 A·표 B·KPI 5요소·가중치 100%·기술분류 3순위·핵심어 5개) [매체: hwpx]
  F-5 양식 설명문 잔존 0                       [매체: hwpx + md]
  F-6 표 열수 상한 / 표·그림 개수 상한          [매체: hwpx]
  F-7 산문 자수 상한(분량 예산 사전검사)        [매체: md]

★ 쪽수 실측은 이 게이트가 하지 않는다 — `gate_pages.py`(한컴 COM)가 담당한다.
  F-7 은 착수 전 예산 점검용 **추정**이며, 실측을 대체하지 않는다.

사용:
  python3 gate_form.py --hwpx 30_proposal.hwpx --md 30_proposal.build.md \
      --spec .../default_form_spec.json [--json gate_form.json]

종료코드 0=PASS, 1=FAIL, 2=실행 오류.
"""
import argparse, json, re, sys, zipfile
import xml.etree.ElementTree as ET

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
T, P, TBL, TR, TC, PIC = (f"{{{HP}}}{x}" for x in ("t", "p", "tbl", "tr", "tc", "pic"))


def norm(s):
    """공백·마크다운 강조·괄호 안 공백 차이를 흡수한 비교용 정규화."""
    s = re.sub(r"\*\*|__", "", s or "")
    return re.sub(r"\s+", "", s)


def local_text(p):
    """이 문단에 직접 속한 텍스트(하위 표 제외) — gate_hwpx.py 와 동일 규약."""
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


def cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(T)).strip()


def harvest(tbl):
    """표 → 행렬(문자열 2차원)."""
    rows = []
    for tr in tbl.findall(TR):
        rows.append([cell_text(tc) for tc in tr.findall(TC)])
    return rows


class Doc:
    """HWPX 를 절 단위로 쪼갠 뷰. 표·그림은 소속 절에 귀속시킨다."""

    def __init__(self, path, titles):
        self.sections = {}       # id -> {"text": [...], "tables": [...], "pics": 0}
        self.order = []          # 등장 순서의 절 id
        self.title_of = {norm(t): i for i, t in titles}   # 정규화 제목 -> id
        self.cur = "_preamble"
        self._new(self.cur)
        zf = zipfile.ZipFile(path)
        self.parts = [n for n in zf.namelist() if n.startswith("Contents/section")]
        for name in sorted(self.parts):
            root = ET.fromstring(zf.read(name))
            self._walk(root)

    def _new(self, sid):
        if sid not in self.sections:
            self.sections[sid] = {"text": [], "tables": [], "pics": 0}
            self.order.append(sid)

    def _walk(self, node):
        for ch in node:
            if ch.tag == P:
                txt = local_text(ch)
                key = norm(txt)
                # 제목 문단은 제목만 담긴 문단이어야 한다(본문 중 언급과 구분)
                if key in self.title_of:
                    self.cur = self.title_of[key]
                    self._new(self.cur)
                self.sections[self.cur]["text"].append(txt)
                self._walk(ch)
            elif ch.tag == TBL:
                rows = harvest(ch)
                self.sections[self.cur]["tables"].append(rows)
                self.sections[self.cur]["text"].append(
                    " ".join(c for r in rows for c in r))
                # 표 내부로는 내려가지 않는다(셀 텍스트 이중 계상 방지)
            elif ch.tag == PIC:
                self.sections[self.cur]["pics"] += 1
                self._walk(ch)
            else:
                self._walk(ch)

    def text(self, sid):
        return " ".join(self.sections.get(sid, {}).get("text", []))

    def all_text(self):
        return " ".join(self.text(s) for s in self.order)

    def tables(self, sid):
        return self.sections.get(sid, {}).get("tables", [])


# ---------------- 특수검사 ----------------

def sp_class3(text):
    """기술분류 소분류 3순위·비중 합 100%."""
    m = [l for l in re.split(r"[|\n]", text) if re.search(r"기술\s*분류|분류", l) and "%" in l]
    if not m:
        return False, "기술분류 행에서 비중(%) 미검출"
    pcts = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", " ".join(m))]
    if len(pcts) < 3:
        return False, f"소분류 3순위 미달(비중 {len(pcts)}개)"
    tot = sum(pcts[:3])
    return abs(tot - 100) < 0.6, f"3순위 비중 합 {tot:g}%"


def sp_keywords5(text):
    seg = re.split(r"핵심어", text)
    if len(seg) < 2:
        return False, "핵심어 항목 없음"
    tail = seg[1][:400]
    ko = re.search(r"\(국문\)(.*?)(?:\(영문\)|$)", tail, re.S)
    en = re.search(r"\(영문\)(.*)", tail, re.S)
    def cnt(s):
        return len([x for x in re.split(r"[,/·;]", s) if x.strip()])
    if ko and en:
        nk, ne = cnt(ko.group(1)), cnt(en.group(1)[:200])
        return (nk <= 5 and ne <= 5), f"국문 {nk}개 / 영문 {ne}개 (각 5개 이내)"
    n = cnt(tail.split("|")[0])
    return n <= 5, f"{n}개 (5개 이내)"


def sp_table_a(tables):
    for rows in tables:
        if not rows:
            continue
        head = norm(" ".join(rows[0]))
        if len(rows[0]) == 3 and "구분" in head and "연차" in head and "목표" in head:
            return True, f"[표 A] 3열 {len(rows)}행"
    shapes = [f"{len(r)}행×{len(r[0]) if r else 0}열" for r in tables]
    return False, f"열 구성 `구분/연차/목표` 3열 표 없음 (실측 {shapes})"


def sp_table_b(tables):
    for rows in tables:
        if not rows:
            continue
        head = " ".join(rows[0])
        months = len(re.findall(r"\b(?:1[0-2]|[1-9])\b", head))
        if len(rows[0]) >= 13 and months >= 12:
            return True, f"[표 B] {len(rows[0])}열(월 12칸) {len(rows)}행"
    shapes = [f"{len(r)}행×{len(r[0]) if r else 0}열" for r in tables]
    return False, f"월 단위 12칸 간트표 없음 (실측 {shapes})"


KPI5 = ["단위", "기준값", "목표치", "평가방법", "평가환경"]


def sp_kpi5(tables, text):
    heads = norm(" ".join(" ".join(r[0]) for r in tables if r))
    miss = [k for k in KPI5 if k not in heads and k not in norm(text)]
    return not miss, ("5요소 전량" if not miss else f"누락 {miss}")


SUM_ROW = re.compile(r"\s*(계|합계|총계|소계)\s*")


def sp_weight100(tables):
    """가중치 열의 합이 100% 인지. ★ 합계 행을 함께 더하면 200% 가 나와 거짓 FAIL 한다 —
    첫 두 칸 중 첫 비어있지 않은 칸이 「계/합계/총계/소계」인 행은 제외한다."""
    for rows in tables:
        if len(rows) < 2:
            continue
        ncol = max(len(r) for r in rows)
        body = [r for r in rows[1:]
                if not SUM_ROW.fullmatch(next((c for c in r[:2] if c.strip()), ""))]
        for c in range(ncol):
            vals = []
            for r in body:
                if c < len(r):
                    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", r[c])
                    if m:
                        vals.append(float(m.group(1)))
            if len(vals) >= 3 and abs(sum(vals) - 100) < 0.6:
                return True, f"가중치 열 합 100% ({len(vals)}개 항목)"
    return False, "합이 100%인 가중치 열을 찾지 못함"


def sp_fig_or_table(doc, sid):
    s = doc.sections.get(sid, {})
    n_t, n_p = len(s.get("tables", [])), s.get("pics", 0)
    return (n_t + n_p) > 0, f"표 {n_t}개 · 그림 {n_p}장"


def style_check(doc, spec):
    """F-8 개조식 준수 — 본문 문단이 「말머리 + 명사형 종결」인지 본다.

    측정 매체는 **hwpx 본문 문단**(표 셀·제목·캡션 제외)이다. md 로 재면 목록 마커가
    조판 단계에서 어떻게 바뀌는지 못 보고, 표 안의 서술체를 본문으로 착각한다.

    ★ 함정: 「~다.」로 끝나면 서술체지만, **「~한다」로 끝나는 표제어**(예: 「…를 우선 탐색한다」)와
      숫자·단위로 끝나는 항목(「…88% 상승」)을 구분해야 한다. 종결 판정은 문단의 **마지막 어절**로만 한다.
    """
    ws = spec.get("writing_style")
    if not ws:
        return None
    markers = tuple(ws.get("markers", {}).values()) + ("○", "-", "·")
    exempt = tuple(ws.get("exempt_paragraph_prefixes", []))
    bad_end = tuple(ws.get("forbidden_endings", []))
    maxlen = int(ws.get("max_item_chars", 160))

    body, bullets, narrative, longs = [], [], [], []
    for sid in doc.order:
        for txt in doc.sections.get(sid, {}).get("text", []):
            t = (txt or "").strip()
            if len(t) < 12 or t.startswith(exempt):
                continue
            if norm(t) in doc.title_of:          # 장·절 제목
                continue
            body.append(t)
            if t.startswith(markers):
                bullets.append(t)
                if len(t) > maxlen:
                    longs.append(t[:28] + "…")
            last = re.sub(r"[)\]\s.]+$", "", t.split()[-1]) if t.split() else ""
            if any(last.endswith(e) for e in bad_end):
                narrative.append(t[:28] + "…")
    if not body:
        return None
    return {
        "n_body": len(body),
        "bullet_ratio": len(bullets) / len(body),
        "narrative": narrative,
        "narrative_ratio": len(narrative) / len(body),
        "longs": longs,
    }


# ---------------- 본체 ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--md", help="조립용 원고(.build.md) — F-2·F-7 측정 매체")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    outline = spec["outline"]
    titles = [(n["id"], n["title"]) for n in outline]
    doc = Doc(a.hwpx, titles)
    md = open(a.md, encoding="utf-8").read() if a.md else None

    results, fails, warns = [], [], []

    def check(name, ok, detail, medium, severity="fail"):
        """severity='warn' 이면 양식이 「권장」으로 쓴 항목 — 기록은 남기되 통과를 막지 않는다."""
        tag = "OK " if ok else ("WARN" if severity == "warn" else "FAIL")
        results.append({"name": name, "ok": bool(ok), "detail": detail,
                        "medium": medium, "severity": severity})
        print(f"[{tag}] {name}  ({medium})  {detail}")
        if not ok:
            (warns if severity == "warn" else fails).append(name)

    # F-1 제목 축자 일치 + 순서 -------------------------------------------------
    found = [sid for sid in doc.order if sid != "_preamble"]
    want = [sid for sid, _ in titles]
    miss = [t for i, t in titles if i not in found]
    check("F-1 제목 축자 일치", not miss,
          f"{len(want)}개 중 {len(want)-len(miss)}개 일치" + (f" · 불일치/누락 {miss}" if miss else ""),
          "hwpx")
    seq_ok = [s for s in found if s in want] == [s for s in want if s in found]
    check("F-1b 목차 순서", seq_ok,
          "양식 순서와 동일" if seq_ok else f"순서 어긋남: {found}", "hwpx")

    # F-2 절 신설·누락 0 --------------------------------------------------------
    if md:
        heads = re.findall(r"^(#{2,3})\s+(.+?)\s*$", md, re.M)
        got = [norm(h[1]) for h in heads]
        want_n = [norm(t) for _, t in titles]
        extra = [h for h in got if h not in want_n]
        lack = [t for (_, t), n in zip(titles, want_n) if n not in got]
        check("F-2 절 신설·누락 0", not extra and not lack,
              ("양식 목차와 집합 일치" if not extra and not lack
               else f"신설 {len(extra)}건 {extra[:3]} · 누락 {len(lack)}건 {[l[:20] for l in lack[:3]]}"),
              "md")

    # F-3 절별 요구 항목 커버리지 -----------------------------------------------
    gaps = []
    for n in outline:
        stext = doc.text(n["id"])
        for pr in n.get("probes") or []:
            if not re.search(pr["regex"], stext):
                gaps.append(f"{n['id']}:{pr['key']}")
    total_probe = sum(len(n.get("probes") or []) for n in outline)
    check("F-3 요구 항목 커버리지", not gaps,
          f"{total_probe}개 중 {total_probe-len(gaps)}개 충족" + (f" · 미충족 {gaps}" if gaps else ""),
          "hwpx(절 단위)")

    # F-4 지정 서식 특수검사 -----------------------------------------------------
    for n in outline:
        for entry in n.get("special") or []:
            sid = n["id"]
            sp = entry["key"] if isinstance(entry, dict) else entry
            sev = entry.get("severity", "fail") if isinstance(entry, dict) else "fail"
            tb, tx = doc.tables(sid), doc.text(sid)
            if sp == "CLASS3":
                ok, d = sp_class3(tx)
            elif sp == "KEYWORDS5":
                ok, d = sp_keywords5(tx)
            elif sp == "TABLE_A":
                ok, d = sp_table_a(tb)
            elif sp == "TABLE_B":
                ok, d = sp_table_b(tb)
            elif sp == "KPI5":
                ok, d = sp_kpi5(tb, tx)
            elif sp == "WEIGHT100":
                ok, d = sp_weight100(tb)
            elif sp == "FIG_OR_TABLE":
                ok, d = sp_fig_or_table(doc, sid)
            else:
                ok, d = False, f"미지원 특수검사 {sp}"
            check(f"F-4 {sid} {sp}", ok, d, "hwpx", sev)

    # F-5 설명문 잔존 0 ----------------------------------------------------------
    body = doc.all_text()
    res_hits = []
    for pat in spec.get("guide_residue_patterns", []):
        if re.search(pat, body):
            res_hits.append(pat)
    flat = norm(body)
    # 양식이 「본문에 그대로 쓰라」고 준 표제(가./나./다./라., [표 A] 등)는 잔존이 아니다
    exempt = [norm(e) for e in spec.get("residue_exempt", [])]
    for g in [x for n in outline for x in (n.get("guide") or [])]:
        probe = norm(g.split(":")[-1])
        if any(e in probe for e in exempt):
            continue
        if len(probe) >= 12 and probe in flat:
            res_hits.append(g[:36])
    check("F-5 양식 설명문 잔존 0", not res_hits,
          "잔존 0건" if not res_hits else f"{len(res_hits)}건 {res_hits[:3]}", "hwpx")
    if md:
        md_hits = [p for p in ("<!--", "FORM-GUIDE") if p in md]
        check("F-5b 가이드 주석 잔존 0", not md_hits,
              "0건" if not md_hits else f"{md_hits} — form_strip.py 를 돌리지 않았다", "md")

    # F-6 표·그림 상한 -----------------------------------------------------------
    lim = spec.get("limits", {})
    all_tbl = [t for sid in doc.order for t in doc.tables(sid)]
    # 양식이 열 수를 지정한 절([표 B] 간트 13열 등)은 열수 상한에서 제외한다
    exempt = set(lim.get("table_cols_exempt_sections", []))
    wide = [f"{sid}:{len(t)}행×{max(len(r) for r in t)}열"
            for sid in doc.order if sid not in exempt
            for t in doc.tables(sid)
            if t and max(len(r) for r in t) > lim.get("table_cols_max", 6)]
    check("F-6a 표 열수 상한", not wide,
          f"열수 초과 {len(wide)}개 {wide[:4]}" if wide else
          f"전 표 {lim.get('table_cols_max',6)}열 이하 (표 {len(all_tbl)}개"
          + (f", 양식 지정 절 {sorted(exempt)} 제외)" if exempt else ")"), "hwpx")
    npic = sum(doc.sections[s]["pics"] for s in doc.order)
    # 프리셋 표지 박스가 표 1개로 잡히므로 상한 비교는 +1 을 허용한다
    check("F-6b 표·그림 개수", len(all_tbl) <= lim.get("tables", 5) + 1 and npic <= lim.get("figures", 1),
          f"표 {len(all_tbl)}개(상한 {lim.get('tables',5)}+표지1) · 그림 {npic}장(상한 {lim.get('figures',1)})",
          "hwpx")

    # F-7 산문 자수(분량 예산 사전검사) -------------------------------------------
    if md:
        prose = re.sub(r"\s+", "", re.sub(r"^\|.*$", "", md, flags=re.M))
        n = len(prose)
        check("F-7 산문 자수 상한", n <= lim.get("prose_chars", 15000),
              f"{n:,}자 (상한 {lim.get('prose_chars',15000):,}자) — 추정치, 쪽수 실측은 gate_pages.py", "md")

    # F-8 개조식 준수 -----------------------------------------------------------
    ws = spec.get("writing_style") or {}
    st = style_check(doc, spec)
    if st:
        rmin = float(ws.get("bullet_ratio_min", 0.8))
        nmax = float(ws.get("narrative_ratio_max", 0.10))
        check(f"F-8a 개조식 말머리 비율(≥{rmin:.0%})", st["bullet_ratio"] >= rmin,
              f"본문 {st['n_body']}문단 중 말머리 {st['bullet_ratio']:.0%}", "hwpx")
        check(f"F-8b 서술형 종결(≤{nmax:.0%})", st["narrative_ratio"] <= nmax,
              f"{len(st['narrative'])}건 {st['narrative'][:3]}" if st["narrative"] else "0건",
              "hwpx")
        check(f"F-8c 항목 길이(≤{ws.get('max_item_chars',160)}자)", not st["longs"],
              f"초과 {len(st['longs'])}건 {st['longs'][:3]}" if st["longs"] else "전 항목 이내",
              "hwpx", "warn")

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 실패 {len(fails)}건"
          + (f" · 경고 {len(warns)}건" if warns else ""))
    for f in fails:
        print(f"  - {f}")
    for w in warns:
        print(f"  ~ (권장) {w}")
    if a.json:
        json.dump({"pass": ok, "fails": fails, "warns": warns, "checks": results},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"결과 JSON: {a.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
