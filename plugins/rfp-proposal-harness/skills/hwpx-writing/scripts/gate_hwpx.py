#!/usr/bin/env python3
"""규율 J — 산출물 구조 게이트.

**존재 검사 단독은 거짓 통과를 발급한다.** 이 스크립트는 md가 아니라 **HWPX 산출물**을
직접 파싱해 구조를 검사한다. 규율 I(존재 검사)는 여기에 흡수됐다.

실측 계보 — 「존재는 있고 구조가 깨진」 결함 3건이 전부 존재 검사를 통과했다:
  1) 참고문헌 20건이 HWPX에서 단일 문단 2,018자로 병합       (존재 검사 통과)
  2) 표주석 [주a]~[주j]가 단일 문단 1,407자로 병합            (존재 검사 통과)
  3) 마크다운 표 중간의 빈 줄 1개가 표를 hp:tbl 2개로 쪼개
     #8행이 머리글 없는 고아 표가 됨 — 2개 판에 승계된 뒤
     평가위원 3인이 독립 적발                                  (「8행 존재」 검사 통과)

사용:
  python3 gate_hwpx.py --hwpx 30_proposal.md.hwpx \
      [--prev 30_proposal_v10.hwpx] [--expect-tables 18] \
      [--required required.txt] [--sections §목록.txt] [--json gate_result.json]

종료코드 0=PASS, 1=FAIL, 2=실행 오류.
"""
import argparse, hashlib, json, re, sys, zipfile
import xml.etree.ElementTree as ET

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
T = f"{{{HP}}}t"
P = f"{{{HP}}}p"
TBL = f"{{{HP}}}tbl"
TR = f"{{{HP}}}tr"
TC = f"{{{HP}}}tc"
PIC = f"{{{HP}}}pic"

# 금칙 — 실인쇄 사고가 확인된 문자·문자열
FORBIDDEN = {
    "두부 문자 ⚠(U+26A0)": "⚠",
    "이형 공백 U+FEFF": "﻿",
    "미치환 플레이스홀더": "[보완 필요",
    "TODO 잔존": "TODO",
}
# 이중 이스케이프 — 3패턴 전부 검사할 것(1패턴만 보면 놓친다)
ESCAPE_PATTERNS = [r"&amp;amp;", r"&amp;lt;", r"&amp;gt;"]


def local_text(elem):
    """이 hp:p 에 직접 속한 텍스트만 모은다.

    ★ 함정(실측): `.//hp:t` 로 단순 수집하면 **표 셀 텍스트가 표를 품은 문단에 합산**되어
    거짓 FAIL이 난다(818문단·최장 1,264자·1,000자 초과 2건 → 표 내부 제외 시
    154문단·최장 880자·초과 0건). 하위 hp:tbl 을 만나면 내려가지 않는다.
    """
    out = []

    def walk(node):
        for ch in node:
            if ch.tag == TBL:
                continue
            if ch.tag == T:
                out.append(ch.text or "")
            walk(ch)

    walk(elem)
    return "".join(out)


def cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(T))


def load(path):
    z = zipfile.ZipFile(path)
    parts = {n: z.read(n) for n in z.namelist()}
    return z, parts


def table_shapes(root):
    """표를 (순번, rowCnt, colCnt, 첫 셀 40자) 로 덤프."""
    shapes = []
    for i, tbl in enumerate(root.iter(TBL), 1):
        rc = tbl.get("rowCnt") or str(len(list(tbl.iter(TR))))
        cc = tbl.get("colCnt") or ""
        first = ""
        for tc in tbl.iter(TC):
            first = cell_text(tc).strip()[:40]
            break
        shapes.append((i, int(rc) if rc.isdigit() else -1,
                       int(cc) if cc.isdigit() else -1, first))
    return shapes


def grid_check(root):
    """격자 자동 재검산 — 숫자만으로 이뤄진 표의 행합·열합·총계 대조.

    마지막 행/열이 「계」인 표를 찾아, 합이 맞는지 확인한다.
    반올림 표기로 비중 합이 100이 아니면 **자진 고지 문구**가 있는지도 본다.
    """
    findings = []
    num = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

    for idx, tbl in enumerate(root.iter(TBL), 1):
        rows = []
        for tr in tbl.iter(TR):
            rows.append([cell_text(tc).strip().replace("*", "") for tc in tr.iter(TC)])
        if len(rows) < 3:
            continue
        last = rows[-1]
        if not last or not re.search(r"계|합계|총계", last[0]):
            continue
        # 열별 세로합 대조 (헤더 1행 가정, 마지막 행은 계)
        for c in range(1, min(len(last), min(len(r) for r in rows))):
            vals = []
            ok = True
            for r in rows[1:-1]:
                v = r[c].replace(",", "")
                if not num.match(v):
                    ok = False
                    break
                vals.append(float(v))
            tot = last[c].replace(",", "")
            if not ok or not vals or not num.match(tot):
                continue
            s, tv = round(sum(vals), 2), float(tot)
            if abs(s - tv) > 0.051:  # 0.1 단위 반올림 허용
                findings.append(f"표{idx} 제{c+1}열 세로합 불일치: 계산 {s} vs 표기 {tv}")
    return findings


def section_refs(root, valid_sections):
    """§ 상호참조 실존성 — 본문의 §n-m 참조가 실제 절 목록에 있는지.

    ★ 함정(실측) 2건:
      ⑴ hp:t 런을 구분자 없이 이어붙이면 `§3-3` + `45개월` 이 `§3-345` 로 붙어
         **거짓 깨진참조**가 뜬다 → 문단·셀 단위로 모아 개행으로 잇는다.
      ⑵ 미국 CFR 인용 `40 CFR §84.54(a)(10)`·`§84.7` 이 자기 문서의 절 참조로
         오인된다 → `§숫자.숫자` 형태는 외부 법령 인용으로 보고 제외한다.
    """
    chunks = [local_text(p) for p in root.iter(P)]
    for tc in root.iter(TC):
        chunks.append(cell_text(tc))
    body = "\n".join(chunks)
    refs = set(re.findall(r"§\s?\d+(?:-\d+)?(?![\d\-]|\.\d)", body))
    if not valid_sections:
        return sorted(refs), []
    broken = [r for r in refs if r.replace(" ", "") not in valid_sections]
    return sorted(refs), broken


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--prev", help="직전 판 HWPX — 형상 diff·BinData 해시 비교용")
    ap.add_argument("--expect-tables", type=int, help="기대 표 개수(선언값). 불일치면 FAIL")
    ap.add_argument("--required", help="필수 문자열 목록 파일(1줄 1항목)")
    ap.add_argument("--sections", help="실존 절 목록 파일(1줄 1항목, 예 §2-3)")
    ap.add_argument("--max-para", type=int, default=1000, help="본문 문단 자수 상한")
    ap.add_argument("--json", help="결과 JSON 출력 경로")
    a = ap.parse_args()

    try:
        z, parts = load(a.hwpx)
    except Exception as e:
        print(f"[오류] HWPX 열기 실패: {e}")
        return 2

    secs = [n for n in parts if re.match(r"Contents/section\d+\.xml$", n)]
    if not secs:
        print("[오류] Contents/section*.xml 없음")
        return 2
    root = ET.fromstring(b"".join(parts[n] for n in sorted(secs))
                         if len(secs) == 1 else parts[sorted(secs)[0]])
    raw = parts[sorted(secs)[0]].decode("utf-8", "replace")

    res, fails = {}, []

    def check(name, ok, detail=""):
        res[name] = {"pass": bool(ok), "detail": detail}
        if not ok:
            fails.append(f"{name}: {detail}")
        print(f"  {'PASS' if ok else 'FAIL':4}  {name}" + (f" — {detail}" if detail else ""))

    print(f"규율 J 산출물 구조 게이트 — {a.hwpx}\n")

    # J-1 표 전수 덤프
    shapes = table_shapes(root)
    print(f"  [표 덤프] {len(shapes)}개")
    for s in shapes:
        print(f"      #{s[0]:<3} {s[1]}행 × {s[2]}열   {s[3]}")
    print()

    # J-2 표 개수 대조 (선언 ↔ 실측)
    if a.expect_tables is not None:
        check("J-2 표 개수 선언 대조", len(shapes) == a.expect_tables,
              f"선언 {a.expect_tables} vs 실측 {len(shapes)}")

    # J-3 고아 표 (rowCnt=1)
    orphans = [s for s in shapes if s[1] == 1]
    check("J-3 고아 표(rowCnt=1) 0개", not orphans,
          f"{len(orphans)}개: {[o[0] for o in orphans]}" if orphans else "")

    # J-4 직전 판 형상 diff
    if a.prev:
        try:
            _, pparts = load(a.prev)
            proot = ET.fromstring(pparts[sorted(
                [n for n in pparts if re.match(r"Contents/section\d+\.xml$", n)])[0]])
            pshapes = table_shapes(proot)
            moved = [(p, c) for p, c in zip(pshapes, shapes)
                     if (p[1], p[2]) != (c[1], c[2])]
            check("J-4 표 형상 판 간 diff",
                  len(pshapes) == len(shapes) and not moved,
                  f"표 수 {len(pshapes)}→{len(shapes)}, 형상변동 {len(moved)}건"
                  f"{[m[1][0] for m in moved] if moved else ''}")
            # J-6 BinData 해시 (판 간 동일성 전용 — 원본 PNG와는 재인코딩으로 달라진다)
            def bd(pp):
                return {k: hashlib.md5(v).hexdigest()
                        for k, v in pp.items() if k.startswith("BinData/")}
            b1, b2 = bd(pparts), bd(parts)
            same = sum(1 for k in b2 if k in b1 and b1[k] == b2[k])
            print(f"  INFO  BinData {len(b2)}건 중 판 간 동일 {same}건 "
                  f"(다르면 재렌더가 실제로 일어난 것)")
        except Exception as e:
            print(f"  WARN  직전 판 비교 실패: {e}")

    # J-5 본문 문단 자수 (★ 표 내부 제외)
    paras = [local_text(p) for p in root.iter(P)]
    body = [t for t in paras if t.strip()]
    over = [len(t) for t in body if len(t) > a.max_para]
    check(f"J-5 본문 문단 {a.max_para}자 초과 0", not over,
          f"{len(over)}건 {over}" if over else f"본문 {len(body)}문단, 최장 {max((len(t) for t in body), default=0)}자")

    # J-6 각주·표주석 독립 문단
    notes = [t for t in body if re.match(r"^\[주[a-z]\]", t.strip())]
    refs_ = [t for t in body if re.match(r"^\[\d+\]", t.strip())]
    print(f"  INFO  표주석 독립 문단 {len(notes)}개 / 참고문헌 독립 문단 {len(refs_)}개"
          f"  ← 판 간 감소하면 병합 회귀다")

    # J-7 이중 이스케이프 (3패턴 전부)
    esc = {p: len(re.findall(p, raw)) for p in ESCAPE_PATTERNS}
    check("J-7 이중 이스케이프 0건", not any(esc.values()),
          ", ".join(f"{k}={v}" for k, v in esc.items() if v))

    # J-8 전 XML 파트의 선언 보유
    noxml = [n for n, v in parts.items()
             if n.endswith(".xml") and not v.lstrip()[:5].startswith(b"<?xml")]
    check("J-8 XML 선언 전 파트 보유", not noxml, f"누락: {noxml}" if noxml else f"{sum(1 for n in parts if n.endswith('.xml'))}개 파트")

    # J-9 금칙·플레이스홀더
    hits = {k: raw.count(v) for k, v in FORBIDDEN.items() if raw.count(v)}
    check("J-9 금칙·플레이스홀더 0건", not hits, str(hits) if hits else "")

    # J-10 그림
    npic = len(list(root.iter(PIC)))
    nbin = sum(1 for n in parts if n.startswith("BinData/"))
    check("J-10 그림 객체 ↔ BinData 정합", npic <= nbin and npic > 0 or npic == nbin,
          f"hp:pic {npic} / BinData {nbin}")

    # J-11 격자 재검산
    g = grid_check(root)
    check("J-11 격자 행·열 합 재검산", not g, "; ".join(g) if g else "")

    # J-12 § 상호참조 실존성
    valid = None
    if a.sections:
        valid = {l.strip().replace(" ", "") for l in open(a.sections, encoding="utf-8") if l.strip()}
    found, broken = section_refs(root, valid)
    if valid:
        check("J-12 § 상호참조 실존", not broken, f"깨진 참조 {broken}" if broken else f"{len(found)}종 전부 실존")
    else:
        print(f"  INFO  § 참조 {len(found)}종 검출 (--sections 미지정이라 실존성 미검증)")

    # J-13 필수 문자열 (규율 I 흡수 — 단, 단독 통과는 발급하지 않는다)
    if a.required:
        need = [l.rstrip("\n") for l in open(a.required, encoding="utf-8") if l.strip()]
        miss = [s for s in need if s not in raw]
        check("J-13 필수 문자열 실기재", not miss, f"누락 {len(miss)}건: {miss[:5]}" if miss else f"{len(need)}종 전량")

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 실패 {len(fails)}건")
    for f in fails:
        print(f"  · {f}")
    print("\n※ 측정 매체: 전 항목 hwpx(산출물). md 단독 측정 항목은 이 게이트에 없다.")

    if a.json:
        json.dump({"pass": ok, "checks": res,
                   "tables": [{"idx": s[0], "rows": s[1], "cols": s[2], "first": s[3]} for s in shapes],
                   "fails": fails},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
