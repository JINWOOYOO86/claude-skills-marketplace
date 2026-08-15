#!/usr/bin/env python3
"""표 폭을 **본문 문단 폭**에 맞춘다 (조립 4.5단계 · 게이트 J-17 의 짝).

**왜 필요한가 (실측 2026-08-15)**: 조립 도구(kordoc)는 **자기 프리셋 여백**(좌우 5,669)을 기준으로
표 폭을 정한다. 그런데 우리 조립은 4단계에서 여백을 **양식값(좌우 8,504)** 으로 패치한다.
표는 그대로 남아 **본문 폭 42,519 인 문서에 46,389 짜리 표**가 들어간다 — 오른쪽 여백을 13.6mm 침범한다.
파일은 열리고, validate 도 통과하고, 게이트도 안 잡았다. **인쇄해서 눈으로 봐야 보이는 결함**이다.

  표 폭 46,389 = 프리셋 본문폭 48,189 − 1,800   ← 조립 도구가 본 세계
  본문 폭 42,519 = 59,527 − 8,504 − 8,504        ← 패치 후 실제 문서

종전 조립 경로(honeypot)의 산출물은 표 폭이 **42,520 · 바깥여백 0** 이었다 — 그쪽이 옳았고
도구를 바꾸면서 조용히 퇴행했다. 이 스크립트가 그 기준을 되돌린다.

**무엇을 하는가**
1. `hp:pagePr`/`hp:margin` 에서 본문 폭을 계산한다(= 용지폭 − 좌 − 우 − 제본).
2. 표마다 **열 폭 벡터**를 세우고(병합 셀은 `colAddr`·`colSpan` 으로 환원), 합이 정확히 본문 폭이
   되도록 비례 축소한다. 잔여 1~2 HWPUNIT 는 가장 넓은 열이 흡수한다.
3. 병합 셀의 폭은 **자기가 걸친 열들의 새 폭 합**으로 다시 계산한다(행마다 합이 표 폭과 일치).
4. 표 바깥 좌·우 여백을 0 으로 둔다 — 글자처럼 취급(`treatAsChar="1"`)이라 바깥 여백이 폭에
   더해지므로, 이걸 남기면 표가 문단보다 좌우 1mm 씩 안쪽으로 들어가 **본문과 안 맞아 보인다**.
   위·아래 여백은 문단 간격이므로 건드리지 않는다.

사용:
  python3 fix_table_width.py --hwpx 30_proposal.hwpx [--out 새파일.hwpx] [--target auto|42519]
                             [--keep-outmargin] [--check]

  --check  고치지 않고 진단만 한다(종료코드 1 = 불일치 있음). 게이트처럼 쓸 수 있다.

종료코드 0=정상(또는 이미 일치), 1=--check 에서 불일치 검출, 2=실행 오류.
"""
import argparse, re, shutil, sys, zipfile

RE_TBL_OPEN = re.compile(r"<hp:tbl\b")
RE_TBL_CLOSE = re.compile(r"</hp:tbl>")
RE_CELL = re.compile(
    r'<hp:cellAddr colAddr="(\d+)" rowAddr="(\d+)"/>\s*'
    r'<hp:cellSpan colSpan="(\d+)" rowSpan="(\d+)"/>\s*'
    r'<hp:cellSz width="(\d+)"')
RE_CELLSZ_W = re.compile(r'(<hp:cellSz width=")(\d+)(")')
RE_TBL_SZ_W = re.compile(r'(<hp:sz width=")(\d+)(")')
RE_OUTMARGIN = re.compile(r'(<hp:outMargin\b[^>]*?)left="\d+"([^>]*?)right="\d+"')


def text_width(sec):
    """본문 문단 폭(HWPUNIT) — 용지폭 − 좌여백 − 우여백 − 제본여백."""
    p = re.search(r"<hp:pagePr\b[^>]*>", sec)
    m = re.search(r"<hp:margin\b[^>]*/?>", sec)
    if not (p and m):
        return None
    def att(tag, k):
        mm = re.search(rf'{k}="(\d+)"', tag)
        return int(mm.group(1)) if mm else 0
    return att(p.group(0), "width") - att(m.group(0), "left") - att(m.group(0), "right") \
        - att(m.group(0), "gutter")


def tables(sec):
    """최상위 표의 (시작, 끝) 구간. 중첩 표는 바깥 표에 포함된 채로 넘어간다."""
    spans, depth, start = [], 0, None
    for m in re.finditer(r"<hp:tbl\b|</hp:tbl>", sec):
        if m.group(0) == "</hp:tbl>":
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return spans


def columns(tbl):
    """열 폭 벡터를 세운다. 병합되지 않은 셀이 기준이고, 없으면 걸친 폭을 균등 배분한다."""
    cells = [(int(c), int(r), int(cs), int(rs), int(w)) for c, r, cs, rs, w in RE_CELL.findall(tbl)]
    if not cells:
        return None, []
    ncol = max(c + cs for c, _r, cs, _rs, _w in cells)
    col = [None] * ncol
    for c, _r, cs, _rs, w in cells:
        if cs == 1 and col[c] is None:
            col[c] = w
    # 전 행이 병합인 열 — 걸친 셀의 남은 폭을 균등 배분한다
    for c, _r, cs, _rs, w in cells:
        if cs > 1:
            miss = [i for i in range(c, c + cs) if col[i] is None]
            if miss:
                known = sum(col[i] for i in range(c, c + cs) if col[i] is not None)
                for i in miss:
                    col[i] = max(1, (w - known) // len(miss))
    col = [x if x else 1 for x in col]
    return col, cells


def retarget(tbl, target, keep_outmargin=False):
    """표 하나를 목표 폭으로 다시 재단한다. (새 XML, 종전 폭, 새 폭)"""
    col, cells = columns(tbl)
    if not col:
        return tbl, None, None
    old = sum(col)
    new = [max(1, round(w * target / old)) for w in col]
    diff = target - sum(new)
    if diff:                                  # 반올림 잔여는 가장 넓은 열이 흡수한다
        i = new.index(max(new))
        new[i] = max(1, new[i] + diff)
    widths = [sum(new[c:c + cs]) for c, _r, cs, _rs, _w in cells]

    it = iter(widths)
    out = RE_CELLSZ_W.sub(lambda m: m.group(1) + str(next(it)) + m.group(3), tbl)
    out = RE_TBL_SZ_W.sub(lambda m: m.group(1) + str(target) + m.group(3), out, count=1)
    if not keep_outmargin:
        out = RE_OUTMARGIN.sub(lambda m: m.group(1) + 'left="0"' + m.group(2) + 'right="0"', out, count=1)
    return out, old, target


def process(sec, target, keep_outmargin=False, check=False):
    """섹션 XML 전체 — (새 XML, 보고 목록)."""
    report, out, cursor = [], [], 0
    for i, (a, b) in enumerate(tables(sec), 1):
        tbl = sec[a:b]
        w = RE_TBL_SZ_W.search(tbl)
        cur = int(w.group(2)) if w else None
        om = RE_OUTMARGIN.search(tbl)
        omw = 0
        if om:
            lm = re.search(r'left="(\d+)"', om.group(0))
            rm = re.search(r'right="(\d+)"', om.group(0))
            omw = (int(lm.group(1)) if lm else 0) + (int(rm.group(1)) if rm else 0)
        occupied = (cur or 0) + omw
        ok = occupied == target
        report.append({"표": i, "폭": cur, "바깥여백": omw, "점유": occupied, "목표": target, "일치": ok})
        if check or ok:
            continue
        fixed, _o, _n = retarget(tbl, target, keep_outmargin)
        out.append(sec[cursor:a]); out.append(fixed); cursor = b
    out.append(sec[cursor:])
    return "".join(out), report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--out", help="생략하면 제자리에서 고친다")
    ap.add_argument("--target", default="auto", help="목표 폭(HWPUNIT) 또는 auto(본문 폭 자동 계산)")
    ap.add_argument("--keep-outmargin", action="store_true",
                    help="표 바깥 좌·우 여백을 유지한다(그만큼 표 폭을 줄여 총 점유를 맞춘다)")
    ap.add_argument("--check", action="store_true", help="고치지 않고 진단만 한다")
    a = ap.parse_args()

    zin = zipfile.ZipFile(a.hwpx)
    secs = [n for n in zin.namelist() if re.match(r"Contents/section\d+\.xml$", n)]
    if not secs:
        print("!! Contents/sectionN.xml 미검출 — HWPX 가 아니다"); return 2

    first = zin.read(secs[0]).decode("utf-8")
    if a.target == "auto":
        target = text_width(first)
        if not target:
            print("!! hp:pagePr/hp:margin 미검출 — --target 으로 직접 지정할 것"); return 2
    else:
        target = int(a.target)
    print(f"■ 목표 표 폭 = {target} HWPUNIT ({target/283.465:.1f}mm · 본문 문단 폭)")

    changed, allrep = {}, []
    for n in secs:
        s = zin.read(n).decode("utf-8")
        new, rep = process(s, target, a.keep_outmargin, a.check)
        allrep += rep
        if new != s:
            changed[n] = new.encode("utf-8")

    bad = [r for r in allrep if not r["일치"]]
    print(f"  표 {len(allrep)}개 · 목표와 어긋난 표 {len(bad)}개")
    for r in allrep:
        mark = "OK" if r["일치"] else f'→ {target}'
        print(f'  [표{r["표"]:>2}] 폭 {r["폭"]:>6} + 바깥여백 {r["바깥여백"]:>4} = {r["점유"]:>6}  {mark}')

    if a.check:
        print("\n" + ("PASS — 전 표가 본문 폭과 일치" if not bad else
                      f"FAIL — {len(bad)}개 표가 본문 폭과 어긋난다 (--check 없이 다시 돌리면 고친다)"))
        return 1 if bad else 0

    if not changed:
        print("\n변경 없음 — 이미 본문 폭과 일치한다")
        return 0

    dst = a.out or a.hwpx
    tmp = dst + ".tmp"
    with zipfile.ZipFile(tmp, "w") as zout:
        for it in zin.infolist():
            d = changed.get(it.filename, zin.read(it.filename))
            zi = zipfile.ZipInfo(it.filename, date_time=it.date_time)
            # mimetype 은 **무압축·첫 항목**이어야 한다(OCF 규약) — 순서는 infolist 가 보존한다
            zi.compress_type = zipfile.ZIP_STORED if it.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zi.external_attr = it.external_attr
            zout.writestr(zi, d)
    zin.close()
    shutil.move(tmp, dst)
    print(f"\n완료 — {len(bad)}개 표를 본문 폭 {target} 으로 재단: {dst}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
