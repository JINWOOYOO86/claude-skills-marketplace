# -*- coding: utf-8 -*-
"""본문의 정량값이 **근거팩에 있는 값인가**를 본다.

## 왜 필요한가 — 재현성의 유일한 구멍

3회 실행 실측에서 L6(결론 일치도)이 0.64 에 그친 **유일한 원인**이 이것이다.
세 회차가 **같은 게이트 항목에서 막혀 서로 다르게 풀었다.**

    기술분류 비중   c1 50/30/20 안분 · c2 총액만 · c3 미정

게이트가 「비중 합 100%」를 요구하는데 근거팩에 비중이 없으니
하나는 지어내고 하나는 비우고 하나는 얼버무렸다.

**「지어내지 마라」는 규칙은 있었으나 세는 도구가 없었다.**
`check_wording` 은 「협약 시 확정」류를 잡지만 **그럴듯한 숫자는 못 잡는다.**

## 무엇을 보는가

본문에서 **단위가 붙은 정량값**만 뽑아 근거팩(`_ws/*.md`)에 있는지 대조한다.
단위 없는 수(연차 번호·표 번호·목록 번호)는 보지 않는다 — 출처가 필요 없다.

**계산해서 나온 값은 근거팩에 없을 수 있다.** 그래서 기본은 **보고**이고,
`--strict` 를 주면 exit 2 가 된다. 산출식이 본문에 적혀 있으면 정당하다.
"""
import argparse
import glob
import io
import os
import re
import sys

# 단위가 붙은 정량값만. 단위 없는 수는 출처가 필요 없다.
UNIT = (r"℃|%|kW_?th|kW_?e|kW|MWh_?th|MWh_?e|MWh|GWh|MW|kt|톤|tCO2?|TOE|"
        r"bar|K\b|g/day|RT|억\s?달러|억원|만원|억|조원|시간|h\b|년|개월|주|"
        r"건|대|명|배|쪽|p\b|만\s?대|천원")
NUM = re.compile(r"(\d[\d,]*\.?\d*)\s*(" + UNIT + r")")

# 문서 자신이 만드는 구조값 — 출처가 필요 없다
STRUCTURAL = re.compile(r"^(1|2|3|4|5|6|7|8|9|10|100)$")


# ★ 범위 표기 `7.8~13.0%` 는 **앞 숫자에 단위가 안 붙는다.**
#   그대로 두면 앞 값이 항상 「미출처」로 잡혀 잡음이 된다(실측).
RANGE = re.compile(r"(\d[\d,]*\.?\d*)\s*[~–-]\s*(\d[\d,]*\.?\d*)\s*(" + UNIT + r")")


def values(text):
    """(정규화된 값, 단위) 집합. 범위는 양 끝을 둘 다 등록한다."""
    out = set()
    norm = lambda x: x.replace(",", "").rstrip(".")
    unorm = lambda u: re.sub(r"\s+", "", u)
    for m in RANGE.finditer(text):
        u = unorm(m.group(3))
        out.add((norm(m.group(1)), u))
        out.add((norm(m.group(2)), u))
    for m in NUM.finditer(text):
        out.add((norm(m.group(1)), unorm(m.group(2))))
    return out


def _nums_in(line):
    out = []
    for x in re.findall(r"\d[\d,]*\.?\d*", line):
        try:
            out.append(float(x.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    return out


def _close(a, b, tol=0.01):
    return b and abs(a - b) / abs(b) <= tol


def _derivable_in_line(val, body):
    """같은 문장(줄) 안의 다른 수들로 계산되는 값인가 (합·차·곱·비, 2~4개 합)."""
    try:
        v = float(val)
    except ValueError:
        return False
    from itertools import combinations
    for line in body.splitlines():
        if val not in line.replace(",", ""):
            continue
        others = [n for n in _nums_in(line) if not _close(n, v, 1e-9)]
        for a, b in combinations(others, 2):
            for c in (a + b, abs(a - b), a * b, (a / b if b else 0), (b / a if a else 0)):
                if c and _close(v, c):
                    return True
        for k in (3, 4):
            for combo in combinations(others, k):
                if _close(v, sum(combo)):
                    return True
    return False


COMPOSITE = re.compile(r"(\d[\d,]*)\s*억\s*(\d[\d,]*)\s*만")


def _composite_match(val, body, pvals):
    """「141억 3,381만」 처럼 합성된 수가 팩의 한 값(단위 다름)과 자릿수 무관하게 맞는가."""
    for m in COMPOSITE.finditer(body):
        a, b = m.group(1).replace(",", ""), m.group(2).replace(",", "")
        if val not in (a, b):
            continue
        man = int(a) * 10000 + int(b)               # 만원 단위
        for p in pvals:
            for k in range(-4, 5):
                if p and _close(man * (10.0 ** k), p, 0.0005):
                    return True
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True, help="조립용 원고(.build.md)")
    ap.add_argument("--pack", required=True, help="근거팩 디렉터리(_ws)")
    ap.add_argument("--strict", action="store_true",
                    help="미출처 수치가 있으면 exit 2 (기본은 보고만)")
    a = ap.parse_args()

    body = io.open(a.md, encoding="utf-8").read()
    pack = ""
    files = sorted(glob.glob(os.path.join(a.pack, "*.md")))
    for f in files:
        pack += io.open(f, encoding="utf-8").read()

    bv = values(body)
    pv = values(pack)
    # ★ 본문은 **단위가 붙은 값**만 본다(잡음 제거).
    #   하지만 대조는 **숫자만**으로 한다 — 근거팭은 같은 값을 다른 형식으로 적는다.
    #   실측: `2036` 은 팭에 `2036-10-13`(만료일)로, `13.0` 은 단위 없이 있었다.
    #   단위까지 맞추면 멀쌜한 값이 전부 「미출처」로 잡혔다.
    pnum = set(re.findall(r"\d[\d,]*\.?\d*", pack))
    pnum = {x.replace(",", "").rstrip(".") for x in pnum}
    missing = sorted(v for v in bv
                     if v[0] not in pnum and not STRUCTURAL.match(v[0]))
    # [PATCH 2026-09-26] 산출값·환산값 인정 (rubric C-m3 를 floor 로 쓰기 위해).
    #   실측(개선본): 미출처 4종이 전부 정당한 값이었다 —
    #     91.1억원 = 15.0+41.9+34.2 (같은 문장 안 합)   24.9배 = 82,200÷3,304 (같은 문장 안 비)
    #     141억 3,381만원 = 팩의 14,133,808천원 (단위 환산)
    #   ① 같은 문장 안의 다른 수로 +·−·×·÷·합이 되면 산출값  ② 「N억 M만」 합성수는 팩 값과
    #   자릿수 무관 비교(0.05%)로 환산값. 근거 없는 수를 지어낸 것과는 다르다.
    derived = []
    pvals = []
    for x in pnum:
        try:
            pvals.append(float(x))
        except ValueError:
            pass
    for v in list(missing):
        if _derivable_in_line(v[0], body) or _composite_match(v[0], body, pvals):
            derived.append(v)
            missing.remove(v)

    print("=" * 64)
    print("수치 출처 검사 — 본문 값이 근거팩에 있는가")
    print("=" * 64)
    print(f"  근거팩       {len(files)}개 파일 · 값 {len(pv)}종")
    print(f"  본문         값 {len(bv)}종")
    print(f"  미출처       {len(missing)}종  "
          f"{'OK' if not missing else ('★' if a.strict else '검토')}")
    if derived:
        print(f"  산출·환산    {len(derived)}종  (같은 문장 안 계산 또는 팩 값 단위 환산 — 인정)")
        for n, u in derived[:8]:
            print(f"     {n} {u}")

    if missing:
        for n, u in missing[:24]:
            # 본문에서 그 값이 처음 나오는 줄을 보여 준다
            m = re.search(r"^.*\b" + re.escape(n) + r"\s*" + re.escape(u) + r".*$",
                          body, re.M)
            ctx = (m.group(0).strip()[:62] + "…") if m else ""
            print(f"     {n} {u:<8} {ctx}")
        if len(missing) > 24:
            print(f"     … 외 {len(missing) - 24}종")

    print()
    if missing and a.strict:
        print("FAIL — 근거팩에 없는 정량값이 있다.")
        print("계산값이면 산출식을 본문에 적고, 아니면 그 값을 빼라.")
        return 2
    if missing:
        print("검토 필요 — 계산값이면 산출식이 본문에 있는지 확인하라.")
        return 0
    print("PASS — 본문 정량값이 전부 근거팩에 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
