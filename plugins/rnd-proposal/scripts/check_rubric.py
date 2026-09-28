# -*- coding: utf-8 -*-
"""심사 배점표를 기계로 재는 검사기 (2026-09-23).

## 왜 만들었나 — 81점을 맞고서야 만들었다

제출본이 AI 심사에서 **100점 만점에 81점**을 받았다. 19점이 어디서 빠졌는지
심사평에 그대로 적혀 있었고, **가장 큰 손실은 기계가 잡을 수 있는 것이었다.**

    양식 일관성      9/15  (-6)   ← 줄간격이 문서 안에서 갈렸다
    논리적 일관성   16/20  (-4)   ← 전 조건 동시 충족 vs 미달 시 절충
    구체성·명확성   16/20  (-4)   ← 핵심 실행 조건이 비었다
    간결성·전달력   12/15  (-3)   ← 같은 말이 여러 절에 반복
    단어·문체        8/10  (-2)   ← 지나치게 압축돼 의미가 모호
    구조·형식       20/20  ( 0)

심사평은 이렇게 적었다 — *「문단의 약 절반에 130% 줄간격이 적용되고 70% 줄간격도
일부 포함되어 160% 서식이 문서 전반에 일관되게 유지되지 않았습니다」*.

실측해 보니 **한 자도 틀리지 않았다.**

    160%  196문단 (48.8%)   ← 표 밖 본문
    130%  204문단 (50.7%)   ← 전부 표 안
     70%    2문단           ← 역시 표 안

우리 게이트는 **표 밖 본문만 재고 통과시켰다.** 사람 눈에도 안 보인다 —
표 안이 좁은 것은 자연스러워 보이기 때문이다. 문서 전체를 세야 보인다.

**배점이 큰 항목부터 잰다.** 이 파일의 검사 순서가 곧 우선순위다.

## 무엇을 재고 무엇을 안 재나

기계가 재는 것은 **셀 수 있는 것**뿐이다. 「설득력」은 못 잰다.
못 재는 것은 `rp-reviewer` 와 외부 검토(`rp-proofread`)로 넘긴다.

    R1 줄간격 단일성      전 문단(표 안 포함)이 규정값인가        실패
    R2 논리 충돌          상충하는 문장쌍이 같이 있는가            실패
    R3 실행 조건 명시     심사가 이름을 댄 조건이 본문에 있는가    실패
    R4 중복 서술          같은 말이 여러 절에 반복되는가           경고
    R5 과압축             조사·서술어가 빠져 뜻이 모호한가         경고
    R6 요약문 칸          양식이 수치를 요구한 칸을 채웠는가        실패
    R7 뭉개진 정량        「수천 종 규모」류로 얼버무렸는가          실패

사용:
    python $CLAUDE_PLUGIN_ROOT/scripts/check_rubric.py --md <build.md> [--hwpx <out.hwpx>]
                                   [--spec <50_form_spec.json>] [--strict]

exit: 0 통과 / 2 실패(--strict 면 경고도 실패)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter

try:                                   # 콘솔이 cp949 여도 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── R2 논리 충돌 ────────────────────────────────────────────────────────────
#   실측으로 걸린 쌍을 적는다. 「전부 만족해야 한다」와 「하나는 포기할 수 있다」가
#   같은 문서에 있으면 심사자는 판정 원칙이 없다고 본다.
CONFLICTS = [
    (r"한 조건이라도 누락|모두 충족|동시에 충족|세 가지를 모두",
     r"절충안|우선순위를 정해.{0,10}선택|일부만 달성|타협",
     "전 조건 동시 충족을 요구하면서 미달 시 절충을 허용한다 — 판정 원칙이 둘이다"),
]
#   ★ 규칙을 짐작으로 늘리지 않는다. 「여유가 없다 ↔ 순연된다」를 한 번 넣었다가
#     걷어냈다 — 「여유가 없으니 병렬 배치한다」는 모순이 아니라 대응이었다.
#     **실측으로 걸린 쌍만 적는다.** 짐작한 규칙은 거짓 양성만 만든다.

# ── R3 실행 조건 ────────────────────────────────────────────────────────────
#   심사평이 이름을 대어 「구체화가 부족하다」고 한 것들이다.
#   에너지·소재 계열 계획서의 공통 빈칸이라 기본값으로 둔다.
#   양식마다 다르면 명세 `rubric.required_conditions` 로 덮어쓴다.
CONDITIONS = {
    "모델 구성": r"생성 모델은|모델 구조|신경망|SMILES|회귀기|아키텍처",
    # ★ 「수천 종 규모」 같은 뭉개진 말이 아니라 **센 수**를 요구한다 (2026-09-23).
    #   근거팩을 뒤지니 선행 문헌이 추린 「순물질 138종·저GWP 27종」이 출처와 함께
    #   있었다. 뭉갠 표현은 찾아보지 않았다는 뜻이다.
    "학습 데이터 규모": r"\d+\s*종|\d+\s*건|\d+\s*만\s*개|출발 집합",
    "판정 기준": r"판정하며|판정 기준|등급 상당|기준으로 둠|합격 기준",
    # ★ 2026-09-27: ATW 표준 조건은 「열원/열매 ℃」로 적는다(근거팩). 옛 「증발/응축」 표기만 보던 정규식이
    #   실제로 조건이 있는 문장을 「없다」고 냈다. 슬롯 형식 「운전조건 — …」도 받는다.
    "시험 운전조건": r"운전조건\s*[은—:\-]|증발 .{0,12}℃|응축 .{0,12}℃|과열 .{0,4}K|열원\s*[-−\d/·~ ]+℃|열매\s*[-−\d/·~ ]+℃",
    "대상 상태영역": r"상태영역은|상태 영역은|포화·과열|압력 범위",
}


def _paragraph_spacing(path: str) -> tuple[Counter, Counter]:
    """(본문, 표 안) 문단의 줄간격.

    ★ 표 안을 따로 센다 (2026-09-23 사용자 결정). 규정값은 **본문까지만**
      적용하고, 표 안은 원래 값을 쓰되 **하나로 모여 있어야 한다.**
      심사가 집어낸 것은 130% 자체가 아니라 **섞여 있다는 것**이었다 —
      「70% 줄간격도 일부 포함되어」.
    """
    z = zipfile.ZipFile(path)
    hdr = z.read("Contents/header.xml").decode("utf-8")
    sec = "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist())
                  if re.fullmatch(r"Contents/section\d+\.xml", n))
    sp = {}
    for m in re.finditer(r'<hh:paraPr id="(\d+)"(.*?)</hh:paraPr>', hdr, re.S):
        ls = re.search(r'<hh:lineSpacing[^>]*type="([^"]*)"[^>]*value="(-?\d+)"',
                       m.group(2))
        if ls:
            sp[m.group(1)] = (ls.group(1), int(ls.group(2)))
    spans = [(m.start(), m.end())
             for m in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", sec, re.S)]
    body, tbl = Counter(), Counter()
    for m in re.finditer(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', sec):
        k = sp.get(m.group(1), ("?", 0))
        if any(a <= m.start() < b for a, b in spans):
            tbl[k] += 1
        else:
            body[k] += 1
    return body, tbl


# ── R6 요약문 칸 ───────────────────────────────────────────────────────────
#   양식이 「착수시점(n단계) → 종료시점 목표(n단계)」처럼 **수치를 요구한 칸**을
#   말로만 채우면 심사자에게는 빈칸으로 보인다.
#   실측(2026-09-22): TRL 칸에 「1차년도 사업계획서에서 판정기준과 함께 확정」만
#   있었다. 게이트는 전항 통과였다 — 아무도 그 칸을 보지 않았다.
#   ★ **자리표시의 모양과 개수**까지 맞춘다.
#     처음엔 「값에 숫자가 있는가」로만 봤는데, TRL 칸의 「1차년도 사업계획서에서
#     …확정. 종료 판정은 200 g/day…」가 통과했다 — 숫자는 있지만 **단계 숫자가
#     아니었다.** 자리표시가 요구하는 모양을, 요구한 횟수만큼 본다.
PLACEHOLDERS = [
    (re.compile(r"[nN]\s*단계"), re.compile(r"\d+\s*단계"), "단계 숫자"),
    (re.compile(r"[nN]\s*차년도"), re.compile(r"\d+\s*차년도"), "차년도"),
    (re.compile(r"[nN]\s*년"), re.compile(r"\d+\s*년"), "연 수"),
    (re.compile(r"[nN]\s*개월"), re.compile(r"\d+\s*개월"), "개월 수"),
    (re.compile(r"YYYY"), re.compile(r"\d{4}"), "연도"),
    (re.compile(r"%"), re.compile(r"\d+(\.\d+)?\s*%"), "비중"),
]


def _summary_cells(md: str) -> dict:
    """0장 요약문 표의 `| 라벨 | 값 |` 를 읽는다."""
    out = {}
    for ln in md.splitlines():
        if not ln.startswith("|") or "---" in ln:
            continue
        c = [x.strip() for x in ln.strip("|").split("|")]
        if len(c) >= 2 and c[0]:
            out.setdefault(c[0], c[1])
    return out


def _check_summary(md: str, spec: dict) -> list[str]:
    guide = ((spec.get("outline") or [{}])[0] or {}).get("guide") or []
    if not guide:
        return []
    cells = _summary_cells(md)
    def norm(x):
        # 「핵심어 (국문/영문)」 ↔ 「핵심어」 처럼 괄호 안내가 붙고 안 붙고가 갈린다.
        return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", x))
    bad = []
    for g in guide:
        label, _, want = g.partition(":")
        need = [(v, n, cnt) for ph, v, n in PLACEHOLDERS
                if (cnt := len(ph.findall(want)))]
        if not want or not need:
            continue                       # 자리표시가 없는 칸은 넘어간다
        key = next((k for k in cells if norm(k) == norm(label)), None)
        if key is None:
            bad.append(f"{label.strip()}: 칸이 없다")
            continue
        val = cells[key]
        for pat, name, cnt in need:
            got = len(pat.findall(val))
            if got < cnt:
                bad.append(f"{label.strip()}: {name} {cnt}개를 요구하는데 {got}개다")
    return bad



def _sections(md: str) -> dict[str, list[str]]:
    """절 제목 → 그 절의 슬롯 목록."""
    out, cur = {}, "(머리말)"
    for ln in md.split("\n"):
        h = re.match(r"^#{2,4}\s+(.+)$", ln)
        if h:
            cur = h.group(1).strip()
            out.setdefault(cur, [])
        elif ln.startswith("  - "):
            out.setdefault(cur, []).append(ln[4:].strip())
    return out


def _shingles(t: str, n: int = 4) -> set[str]:
    """이어지는 낱말 n개의 창.

    ★ 창 크기를 실측으로 골랐다(2026-09-23). 제출본(81점)에 대고 재 보니
      n=6 은 **0쌍**(심사는 중복을 지적했는데 못 잡았다), n=3 은 9쌍인데
      「HFCs 관리제도 개선방안」 같은 고유명사까지 걸렸다.
      **n=4 에서 심사가 이름을 댄 중복(1-1 ↔ 4-1 「적용처는 12 kW 미만」)만
      남았다.**

    출처·특허번호를 두 절에서 다시 인용하는 것은 중복이 아니므로 뺀다.
    """
    w = re.sub(r"[^\w가-힣]+", " ", t).split()
    out = set()
    for i in range(max(0, len(w) - n + 1)):
        win = w[i:i + n]
        if sum(bool(re.fullmatch(r"[A-Za-z0-9]+", x)) for x in win) >= n - 1:
            continue                      # 특허번호·영문 기관명 재인용
        out.add(" ".join(win))
    return out


SUMMARY_TITLE = re.compile(r"^0\.\s")


def r4_pairs(md: str) -> list[tuple]:
    """절 간 4낱말 반복: (절A, 절B, 겹친 구절, 슬롯A, 슬롯B). writer_brief 가 절별로 되돌려 준다.

    ★ 0장 요약문이 낀 쌍은 세지 않는다 (2026-09-27 사용자 결정, t1 34쌍). 요약문은 본문을 되풀이하는 칸이고
      R6 이 값 채움을 요구한다: 편집자가 지우면 R6 과 R4 가 서로 되돌린다. 본문 절끼리의 반복은 그대로 잡는다.
    """
    secs = _sections(md)
    out = []
    keys = [k for k in secs if not SUMMARY_TITLE.match(k)]
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            for sa in secs[a]:
                for sb in secs[b]:
                    if len(sa) < 20 or len(sb) < 20:
                        continue
                    sh = _shingles(sa) & _shingles(sb)
                    if sh:
                        out.append((a, b, sorted(sh)[0], sa, sb))
    return out


def r5_items(md: str) -> list[tuple]:
    """과압축 슬롯 — (절 제목, 슬롯 원문, 사유)."""
    out = []
    for sec, slots in _sections(md).items():
        for t in slots:
            why = []
            # 쉼표가 **절**을 잇는데 연결 어미가 없다.
            #   ★ 단순 열거(「A 93억, B 115억」)는 개조식에서 정상이다 — 실측에서
            #     9건이 잡혔고 대부분 정당한 열거였다. 쉼표 **양쪽이 모두 주어를
            #     가질 때만** 절 접속으로 본다.
            core = re.sub(r"\d,\d", "", t)
            if "," in core and not re.search(
                    r"(이며|하며|이고|하고|으며|되며|라서|므로|어서|지만|인데)", t):
                parts = [x for x in core.split(",") if x.strip()]
                subj = sum(bool(re.search(r"[가-힣](은|는|이|가)\s", x)) for x in parts)
                if len(parts) >= 2 and subj >= 2:
                    why.append("절이 쉼표로만 이어짐")
            # 조사 앞이 떨어졌다 (「B2 는」)
            if re.search(r"[A-Za-z0-9] (는|은|이|가|를|을)\s", t):
                why.append("조사 분리")
            if why:
                out.append((sec, t, "·".join(why)))
    return out


def check(md_path, hwpx_path=None, spec_path=None):
    md = open(md_path, encoding="utf-8").read()
    spec = json.load(open(spec_path, encoding="utf-8")) if spec_path else {}
    rub = spec.get("rubric") or {}
    fails, warns = [], []

    # ── R1 줄간격 단일성 (배점 손실 1위) ────────────────────────────────────
    want = (spec.get("style") or {}).get("line_spacing")
    if hwpx_path and want:
        body, tbl = _paragraph_spacing(hwpx_path)
        inc = bool((spec.get("style") or {}).get("line_spacing_include_tables"))
        scope = body + tbl if inc else body
        off = {k: v for k, v in scope.items() if k != ("PERCENT", int(want))}
        tot = sum(scope.values()) or 1
        if off:
            d = " · ".join(f"{k[0]} {k[1]}: {v}문단" for k, v in sorted(off.items()))
            fails.append(("R1 줄간격 단일성",
                          f"규정 {want}% 와 다른 문단 {sum(off.values())}/{tot} — {d}"))
        elif not inc and len(tbl) > 1:
            d = " · ".join(f"{k[0]} {k[1]}: {v}문단" for k, v in sorted(tbl.items()))
            fails.append(("R1 줄간격 단일성",
                          f"표 안 줄간격이 섞였다 — {d}  (본문 {want}% 는 정상)"))
        else:
            t = f" · 표 안 {list(tbl)[0][1]}%" if tbl else ""
            print(f"[OK ] R1 줄간격 단일성      본문 {tot}문단 {want}%{t}")
    elif want:
        warns.append(("R1 줄간격 단일성", "hwpx 를 주지 않아 못 쟀다"))

    # ── R2 논리 충돌 ────────────────────────────────────────────────────────
    hit = []
    for a, b, why in CONFLICTS + [tuple(x) for x in rub.get("conflicts", [])]:
        ma = [m.group(0) for m in re.finditer(a, md)]
        mb = [m.group(0) for m in re.finditer(b, md)]
        if ma and mb:
            hit.append(f"{why} ({ma[0]} ↔ {mb[0]})")
    if hit:
        fails.append(("R2 논리 충돌", " / ".join(hit)))
    else:
        print("[OK ] R2 논리 충돌          상충 쌍 0건")

    # ── R3 실행 조건 명시 ───────────────────────────────────────────────────
    conds = dict(CONDITIONS)
    conds.update(rub.get("required_conditions") or {})
    missing = [k for k, pat in conds.items() if not re.search(pat, md)]
    if missing:
        fails.append(("R3 실행 조건 명시", f"본문에 없다 — {', '.join(missing)}"))
    else:
        print(f"[OK ] R3 실행 조건 명시     {len(conds)}항목 전부 있음")

    # ── R6 요약문 칸 (양식이 수치를 요구한 칸) ──────────────────────────────
    bad = _check_summary(md, spec)
    if bad:
        fails.append(("R6 요약문 칸", " / ".join(bad)))
    elif (spec.get("outline") or [{}])[0].get("guide"):
        print("[OK ] R6 요약문 칸          수치 요구 칸 전부 채움")

    # ── R7 뭉개진 정량 표현 ─────────────────────────────────────────────────
    #   「수천 종 규모」·「다수」·「약간」은 값을 못 찾았다는 자백이다.
    #   근거팩을 뒤지면 대개 센 수가 있다 — 실측으로 두 번 그랬다.
    VAGUE = r"수천|수백|수만|다수의|여러 종|상당수|약간|일부 기관|적정 수준|충분한 수"
    vg = [m.group(0) for m in re.finditer(VAGUE, md)]
    if vg:
        fails.append(("R7 뭉개진 정량", f"{len(vg)}건 — {', '.join(sorted(set(vg))[:5])}"
                                       " (근거를 찾아 센 수로 바꿔라)"))
    else:
        print("[OK ] R7 뭉개진 정량        0건")

    # ── R4 중복 서술 ────────────────────────────────────────────────────────
    dup = sorted({f"{a} ↔ {b}: 「{ph[:34]}…」" for a, b, ph, _, _ in r4_pairs(md)})
    if dup:
        warns.append(("R4 중복 서술", f"{len(dup)}쌍 — " + " / ".join(dup[:3])))
    else:
        print("[OK ] R4 중복 서술          절 간 반복 0건")

    # ── R5 과압축 ───────────────────────────────────────────────────────────
    #   심사평: 「일부 표현이 지나치게 압축되거나 의미가 모호하여 문장 정확성이
    #   다소 떨어집니다」. 셀 수 있는 신호만 본다.
    terse = [f"{why} | {t[:40]}" for _, t, why in r5_items(md)]
    if terse:
        warns.append(("R5 과압축", f"{len(terse)}건 — " + " / ".join(terse[:3])))
    else:
        print("[OK ] R5 과압축             0건")

    for name, msg in fails:
        print(f"[FAIL] {name}  {msg}")
    for name, msg in warns:
        print(f"[WARN] {name}  {msg}")
    return fails, warns



# ═══════════════════════════════════════════════════════════════════════════
# rubric 모드 (2026-09-26, 재설계 2단계)
#
#   python check_rubric.py --rubric criteria/rubric.yaml --md <build.md> --hwpx <out.hwpx>
#          --spec <50_form_spec.json> [--pack <evidence/_ws>] [--requirements <requirements.md>]
#          [--mode submission|final] [--skip-pages] [--report 70_machine.json]
#          [--judge 70_judge.json]      ← rp-scorer 의 판정을 받아 점수를 계산한다
#
#   rubric.yaml 의 `by: machine` 체크를 impl 별로 돌려 체크 id 로 보고한다. R1~R7 은 위의
#   check() 그대로, 나머지는 harness_patches/gate_* 와 scripts/check_* 를 부른다.
#   점수 산술은 여기서만 한다 — 채점 에이전트는 예/아니오와 인용만 낸다.
# ═══════════════════════════════════════════════════════════════════════════
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES = os.path.join(ROOT, "harness_patches")
SCRIPTS = os.path.join(ROOT, "scripts")


def load_rubric(path: str) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_checks(rubric: dict, mode: str = "submission"):
    """(item, tier, check) 를 모드에 맞는 것만 순서대로."""
    for item, cfg in (rubric.get("items") or {}).items():
        for tier in ("floor", "ceiling"):
            for c in cfg.get(tier) or []:
                if c.get("mode") and c["mode"] != mode:
                    continue
                yield item, tier, c


# ── 내장 검사 (R 계열 외) ──────────────────────────────────────────────────
def _slots(md: str) -> list[str]:
    return re.findall(r"^\s*-\s+(.+)$", md, re.M)


UNIT = (r"(?:%|년|월|일|시간|개월|종|건|개|대|회|배|톤|t\b|원|억|조|달러|kW|MW|GW|kg|g|mg|h|K|℃|°C|"
        r"mm|cm|m|km|ppm|차년도|단계|층|쪽|자|명|만|천|백|점|등급|위|호|항|사|국|축|행|열|인|주|분|초|"
        r"L|mL|Pa|kPa|MPa|bar|W|J|kJ|MJ|Hz|V|A|Ω|RT|kcal|kWh|MWh|GWh|톤CO2|tCO2|㎡|㎥|㎜|㎝|ｍ|%p)")


def internal_C_m4(md: str) -> tuple[bool, str]:
    """정량값 뒤 단위 누락. 오탐이 있어 rubric 은 severity: warn 으로 둔다."""
    bad = []
    for t in _slots(md):
        core = re.sub(r"[A-Za-z]+[-\s]?\d[\d,.\w-]*(?:\s*[A-Z]\d)?", " ", t)   # US 1,234,567 B2 · R134a · WP1
        core = re.sub(r"\d{4}년|\d+차년도|\d+단계|표\s*\d|그림\s*\d|\d+\)|①|②|③|④", " ", core)
        for m in re.finditer(r"(?<![\w.\-·~/,])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d{2,})(?![\d,.\-·~/A-Za-z])", core):
            after = core[m.end():m.end() + 6]
            before = core[max(0, m.start() - 12):m.start()]
            if re.match(r"\s?" + UNIT, after):
                continue
            if re.match(r"\s*[·~\-/,]", after) or re.search(r"[·~\-/]\s*$", before):
                continue                                         # 목록·범위·식별자의 한 조각
            if re.search(r"회귀|정확도|계수|R²|비율|지수|점수|확률|R\^2|상관", before + after):
                continue                                         # 무단위가 정당한 값
            bad.append(f"{m.group(1)} ← {t[:36]}")
    return (not bad), (f"{len(bad)}건 — " + " / ".join(bad[:3]) if bad else "0건")


def internal_B_m2(md: str) -> tuple[bool, str]:
    """같은 문장(슬롯)이 두 번 이상."""
    from collections import Counter
    norm = Counter(re.sub(r"[\s·,.\-()「」]", "", t) for t in _slots(md) if len(t) >= 15)
    dup = [t for t, n in norm.items() if n > 1]
    return (not dup), (f"{len(dup)}건 — " + " / ".join(d[:30] for d in dup[:3]) if dup else "0건")


META = r"원문에는|원문 표현|원문 그대로|수정문|고친 문장|위 문장은|이 문장은|다음과 같이 고침|교정 결과"
COLLOQ = r"잘 타고|되게 |엄청|너무 |많이 |좀 |이런 |저런 |그런 식|하니까|거임|거다|같아요|해요|했어요"


def internal_S_m4(md: str) -> tuple[bool, str]:
    hits = [m.group(0) for m in re.finditer(META + "|" + COLLOQ, md)]
    return (not hits), (f"{len(hits)}건 — {sorted(set(h.strip() for h in hits))[:5]}" if hits else "0건")


# ── 외부 검사기 실행 ───────────────────────────────────────────────────────
def _run(cmd, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def run_gate_form(hwpx, md, spec, tmp) -> dict:
    """{체크명: (ok, detail, severity)}"""
    out = os.path.join(tmp, "gate_form.json")
    _run([sys.executable, os.path.join(GATES, "gate_form.py"), "--hwpx", hwpx, "--md", md,
          "--spec", spec, "--json", out])
    if not os.path.exists(out):
        return {}
    data = json.load(open(out, encoding="utf-8"))
    return {c["name"]: (bool(c["ok"]), c.get("detail", ""), c.get("severity", "fail"))
            for c in data.get("checks", [])}


def run_gate_hwpx(hwpx, tmp) -> dict:
    out = os.path.join(tmp, "gate_hwpx.json")
    _run([sys.executable, os.path.join(GATES, "gate_hwpx.py"), "--hwpx", hwpx, "--json", out])
    if not os.path.exists(out):
        return {}
    data = json.load(open(out, encoding="utf-8"))
    return {n: (bool(v["pass"]), v.get("detail", ""), "fail") for n, v in data.get("checks", {}).items()}


def run_gate_pages(hwpx, spec, md, tmp, winpython=None, repeat=1) -> dict:
    """{total|chapters|orphans: (ok|None, detail)} — 한컴이 없으면 전부 None(미측정)."""
    out = os.path.join(tmp, "gate_pages.json")
    cmd = [sys.executable, os.path.join(GATES, "gate_pages.py"), "--hwpx", hwpx, "--spec", spec,
           "--json", out, "--repeat", str(repeat), "--winpython", winpython or sys.executable]
    if md:
        cmd += ["--md", md]
    r = _run(cmd)
    if not os.path.exists(out):
        note = (r.stdout or r.stderr).strip().splitlines()
        return {"total": (None, "미측정: " + (note[0] if note else "gate_pages 출력 없음")),
                "chapters": (None, "미측정"), "orphans": (None, "미측정")}
    d = json.load(open(out, encoding="utf-8"))
    pb = d.get("budget") or {}
    total = d.get("total")
    rows = d.get("chapters") or []
    orph = d.get("orphans") or []
    rows_ok = all(x.get("ok") for x in rows) if rows else None
    blank = d.get("blank_pages") or []
    return {"total": (total is not None and total <= int(pb.get("hard_max", 10 ** 6)),
                      f"{total}쪽 (상한 {pb.get('hard_max')})"),
            "blank": ((not blank) if rows else None,
                      ("빈 쪽 " + ", ".join(f"p{b}" for b in blank)) if blank else "빈 쪽 0건"),
            "chapters": (rows_ok, (f"{len(rows)}장 배분 전부 이내" if rows_ok
                                   else ("초과 " + ", ".join(f"{x['id']}장" for x in rows if not x.get("ok"))
                                         if rows else "장별 미측정"))),
            "orphans": ((not orph) if rows else None,        # 장별 측정이 됐을 때만 PDF 를 읽은 것이다
                        (", ".join(f"p{o['page']} 「{o['text']}」" for o in orph[:4]) if orph else "0건"))}


def run_border(hwpx, spec_path) -> tuple[bool, str]:
    sys.path.insert(0, ROOT)
    from engine.hwpx import border_check
    tb = {}
    if spec_path and os.path.exists(spec_path):
        tb = (json.load(open(spec_path, encoding="utf-8")).get("table_borders") or {})
    cells, _ = border_check.check_hwpx(hwpx, allow_types=tuple(tb.get("allow_types") or ()) + ("SOLID",),
                                       allow_ids=tuple(tb.get("allow_ids") or ()))
    return (not cells), ("전 셀 SOLID" if not cells else border_check.summarize(cells))


def run_dash(hwpx) -> tuple[bool, str]:
    """S-m5 대시류 0 (사용자 고정 요건 2026-09-27) — check_dash.find_in_hwpx"""
    sys.path.insert(0, SCRIPTS)
    import check_dash
    hits = check_dash.find_in_hwpx(hwpx)
    return (not hits), check_dash.summarize(hits) + ((" 예: " + hits[0]["context"][:60]) if hits else "")


def run_internal(hwpx, md, group="internal") -> tuple[bool, str, list]:
    """T-m5 내부 표기 누출 (t1 결함 2026-09-27): check_internal. 절 배정용으로 md hit 의 절 제목을 함께 돌려준다.
    group="rfp" 는 T-m7 공고문 추적 표시(「RFP」·공고문 절 번호, 2026-09-28)."""
    sys.path.insert(0, SCRIPTS)
    import check_internal
    md_hits = check_internal.find_in_text(open(md, encoding="utf-8").read(), group) if md else []
    hits = check_internal.find_in_hwpx(hwpx, group) if hwpx else md_hits
    heads = sorted({h["heading"] for h in md_hits if h.get("heading")})
    return (not hits), check_internal.summarize(hits, group) + ((" 예: " + hits[0]["context"][:60]) if hits else ""), heads


# ── 필수 요소 (2026-09-27 t1 결함) ─────────────────────────────────────────
#   내용을 요구하는 machine 체크는 rubric 에 `requires:` 를 선언한다. writer_brief 는 요구 절 brief 에
#   「항목 · 검사가 받는 형식 · 값」을 넘기고, rp_run gaps 는 값(key)이 대장에 없으면 시작 질문에 올린다.
#     - {item, section, key?, ask?}                 항목 하나 (R3 조건 등)
#     - {from: form_guide, section, values: {칸: key | [key…] | "@title"}}   양식 안내문 칸 전부 (R6)
def _literal_alts(pat: str) -> list[str]:
    """정규식의 대안 중 메타 문자가 없는 것 (「검사가 받는 문구」로 사람에게 보여 준다)."""
    return [a for a in pat.split("|") if a and not re.search(r"[\\\[\]().*+?{}^$]", a)]


def _norm_label(x: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"\([^)]*\)", "", x))


def required_elements(check: dict, spec: dict) -> list[dict]:
    """→ [{section, item, form, keys}]. keys 는 값을 찾을 대장 key 목록(「@title」은 requirements.md 과제명)."""
    reqs = check.get("requires") or []
    reqs = [reqs] if isinstance(reqs, dict) else reqs
    impl = " ".join([check["impl"]] if isinstance(check.get("impl"), str) else (check.get("impl") or []))
    conds = dict(CONDITIONS)
    conds.update((spec.get("rubric") or {}).get("required_conditions") or {})
    out = []
    for r in reqs:
        sec = str(r.get("section", "*"))
        if r.get("from") == "form_guide":
            node = next((n for n in spec.get("outline") or [] if str(n.get("id")) == sec), None)
            vals = {_norm_label(k): v for k, v in (r.get("values") or {}).items()}
            for g in (node or {}).get("guide") or []:
                label, _, want = g.partition(":")
                label = label.strip()
                v = vals.get(_norm_label(label))
                keys = [] if v is None else ([v] if isinstance(v, str) else list(v))
                ph = any(p.search(want) for p, _, _ in PLACEHOLDERS)
                form = f"요약문 표 한 행 `| {label} | 값 |`" + (f" · 요구 형식 「{want.strip()}」" if want.strip() else "") \
                    + (" (자리표시를 실제 수로 채운다: R6 이 개수까지 센다)" if ph else "")
                out.append({"section": sec, "item": label, "form": form, "keys": keys})
            continue
        item = r.get("item", "")
        form = r.get("form", "")
        if not form and "R3" in impl and item in conds:
            alts = _literal_alts(conds[item])
            form = ("문장에 다음 문구 중 하나를 넣는다: " + " / ".join(f"「{a}」" for a in alts)) if alts else f"검사 정규식 `{conds[item]}`"
        out.append({"section": sec, "item": item, "form": form, "keys": [r["key"]] if r.get("key") else []})
    return out


def run_exit_check(script, args) -> tuple[bool, str]:
    r = _run([sys.executable, os.path.join(SCRIPTS, script)] + args)
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    tail = lines[-1] if lines else (r.stderr or "").strip()[:120]
    return r.returncode == 0, tail[:160]


def run_figures(md, requirements) -> tuple[bool, str]:
    sys.path.insert(0, SCRIPTS)
    import check_figures
    ok, msg = check_figures.check(md, requirements)
    return ok, msg.replace("\n", " · ")[:160]


def r_results(fails, warns) -> dict:
    """check() 의 (fails, warns) → {R1: (ok|None, msg)}"""
    out = {}
    for rid in ("R1", "R2", "R3", "R4", "R5", "R6", "R7"):
        f = [m for n, m in fails if n.startswith(rid + " ")]
        w = [m for n, m in warns if n.startswith(rid + " ")]
        if f:
            out[rid] = (False, f[0])
        elif w:
            out[rid] = ((None, w[0]) if "못 쟀다" in w[0] else (False, w[0]))
        else:
            out[rid] = (True, "통과")
    return out


def _match(name_map: dict, key: str, exact=False):
    """게이트 JSON 의 체크명에서 key 로 시작하는 것들."""
    if exact:
        return [v for n, v in name_map.items() if n == key]
    return [v for n, v in name_map.items() if n == key or n.startswith(key + " ")]


def resolve(impl, sig: dict, spec_path) -> tuple:
    """impl 문자열 하나 → (ok|None, detail)."""
    runner, _, key = impl.partition(":")
    if runner == "check_rubric":
        if key in sig["R"]:
            return sig["R"][key]
        fn = {"C-m4": internal_C_m4, "B-m2": internal_B_m2, "S-m4": internal_S_m4}.get(key)
        return fn(sig["md"]) if fn else (None, f"내장 검사 {key} 없음")
    if runner in ("gate_form", "gate_hwpx"):
        m = sig[runner]
        if not m:
            return None, f"{runner} 결과 없음(실행 실패)"
        exact = " " in key                      # "F-4 2-1 FIG_OR_TABLE" 처럼 이름 전체를 준 경우
        hits = _match(m, key, exact)
        if not hits:
            return None, f"{runner} 에 {key} 항목 없음"
        hard = [h for h in hits if h[2] != "warn"] if not exact else hits
        if not hard:                            # 전부 권장(warn) 항목 — 정보만
            return True, "권장 항목만 (" + hits[0][1][:80] + ")"
        bad = [h for h in hard if not h[0]]
        # 실패한 게이트 항목 이름(「F-4 0 KEYWORDS5」)을 남겨 fail_sections 가 실제 실패 절을 뽑게 한다(t4 2026-09-28)
        sig.setdefault("gate_bad", {})[impl] = [n for n, v in m.items() if any(v is h for h in bad)]
        return (not bad), (bad[0][1] if bad else hard[0][1])[:160]
    if runner == "gate_pages":
        return sig["pages"].get(key, (None, f"gate_pages 키 {key} 없음"))
    if runner == "border_check":
        return sig["border"]
    if runner == "check_dash":
        return sig["dash"]
    if runner == "check_internal":
        if key in ("form", "label"):
            return sig.get(key, (None, f"check_internal:{key} 미실행"))
        return sig["internal_rfp"] if key == "rfp" else sig["internal"]
    if runner in ("check_captions", "check_blank", "check_headings", "check_preserve", "check_copy"):
        return sig.get(runner.split("_", 1)[1], (None, f"{runner} 미실행"))
    if runner == "check_wording":
        return sig["wording"]
    if runner == "check_numbers":
        return sig["numbers"]
    if runner == "check_figures":
        return sig["figures"]
    return None, f"알 수 없는 runner {runner}"


def fail_sections(c: dict, detail: str, sig: dict, spec: dict) -> list[str]:
    """실패한 machine 체크를 고칠 절 id (rp_run fix-list 가 writer 로 돌린다). 모르면 [] → 편집자 몫.

    R4 는 겹친 쌍의 절, T-m5(check_internal) 는 표기가 나온 절, requires 가 있으면 실패 항목의 담당 절
    (항목 이름이 detail 에 없으면 requires 절 전부), 그 밖에 applies_to 가 절을 지정했으면 그 절.
    """
    ids = {n["title"]: str(n["id"]) for n in spec.get("outline") or [] if n.get("title")}
    impl = " ".join([c["impl"]] if isinstance(c.get("impl"), str) else (c.get("impl") or []))
    secs = []
    if "check_rubric:R4" in impl:
        secs += [ids[t] for a, b, _, _, _ in r4_pairs(sig["md"]) for t in (a, b) if t in ids]
    v2 = sig.get("v2_secs") or {}
    for runner, k in (("check_internal:form", "form"), ("check_internal:label", "label"),
                      ("check_captions", "captions"), ("check_blank", "blank"), ("check_preserve", "preserve"),
                      ("check_copy", "copy")):
        if runner in impl:
            secs += v2.get(k) or []
    if "check_internal:rfp" in impl:
        secs += [ids[t] for t in sig.get("internal_rfp_heads") or [] if t in ids]
    elif "check_internal:form" in impl or "check_internal:label" in impl:
        pass
    elif "check_internal" in impl:
        secs += [ids[t] for t in sig.get("internal_heads") or [] if t in ids]
    # 게이트 실패 항목 이름에 절 번호가 있으면 그 절만(「F-4 0 KEYWORDS5」 → 0).
    # t4(2026-09-28): T-m3 가 0절 핵심어 하나로 실패했는데 applies_to 다섯 절 전부로 돌아가 집필자 다섯이 헛수정했다.
    for i in ([c["impl"]] if isinstance(c.get("impl"), str) else (c.get("impl") or [])):
        for n in (sig.get("gate_bad") or {}).get(i) or []:
            m = re.match(r"^F-\d+[a-z]?\s+(\d(?:-\d+)?)(?:\s|$)", n)
            if m:
                secs.append(m.group(1))
    req = required_elements(c, spec) if c.get("requires") else []
    if req:
        hit = [r["section"] for r in req if r["item"] and r["item"] in detail]
        secs += hit or [r["section"] for r in req]
    if not secs:                                # 위치를 모르면 applies_to 가 한 절일 때만 그 절, 아니면 편집자 몫
        app = [s for s in (c.get("applies_to") or []) if s != "*"]
        secs = app if len(app) == 1 else []
    return [s for s in dict.fromkeys(secs) if s != "*"]


def run_v2_checks(sig: dict, impls: str, md_text: str, hwpx, spec_path, before=None, rubric_path=None, pack=None) -> None:
    """plan_v2 2단계 floor (2026-09-28): 80_비교검증 퇴행 (a)(d) 를 잡는 검사.
    T-m8 check_internal:form · S-m6 check_internal:label · F-m8 check_captions · C-m6 check_blank
    · F-m9 check_headings · C-m5 check_preserve · S-m7 check_copy(5단계). 원고와 제출본 판정이 같도록 hwpx 가 있으면 hwpx 를 md 꼴로 되돌려 본다.
    sig["v2_secs"][runner] 에 고칠 절 id 를 둔다(fail_sections)."""
    sys.path.insert(0, SCRIPTS)
    sig["v2_secs"] = {}
    need = [k for k in ("check_internal:form", "check_internal:label", "check_captions", "check_blank",
                        "check_headings", "check_preserve", "check_copy") if k in impls]
    if not need:
        return
    spec = json.load(open(spec_path, encoding="utf-8")) if spec_path and os.path.exists(spec_path) else {}
    ids = {n["title"]: str(n["id"]) for n in spec.get("outline") or [] if n.get("title")}
    if hwpx:
        from hwpx_text import hwpx_to_md
        text = hwpx_to_md(hwpx)
    else:
        text = md_text
    if "check_internal:form" in impls:
        import check_internal
        hits = check_internal.find_form(text, spec, check_internal.fixed_allow(pack))
        sig["form"] = ((not hits), check_internal.summarize(hits, "form")
                       + ((" 예: " + hits[0]["context"][:50]) if hits else ""))
        sig["v2_secs"]["form"] = [ids[h["heading"]] for h in hits if h.get("heading") in ids]
    if "check_internal:label" in impls:
        import check_internal
        st = check_internal.label_stats(text, spec)
        sig["label"] = (st["ok"], f"라벨 항목 {st['labels']}/{st['total']} ({st['ratio']:.0%}, 상한 "
                        f"{check_internal.LABEL_MAX:.0%})" + (f" · 연속 반복 {len(st['repeats'])}" if st["repeats"] else ""))
        sig["v2_secs"]["label"] = [ids[h] for h in st["heads"] if h in ids]
    for key, mod in (("captions", "check_captions"), ("blank", "check_blank")):
        if mod in impls:
            m = __import__(mod)
            ok, probs, secs = m.check_text(text)
            sig[key] = (ok, f"{len(probs)}건" + (": " + probs[0][:80] if probs else ""))
            sig["v2_secs"][key] = secs
    if "check_headings" in impls:
        import check_headings
        if hwpx:
            ok, probs = check_headings.check_hwpx(hwpx, spec)
            sig["headings"] = (ok, f"{len(probs)}건" + (": " + probs[0][:60] if probs else ""))
        else:
            sig["headings"] = (None, "hwpx 없음")
    if "check_preserve" in impls:
        import check_preserve
        if before:
            res = check_preserve.compare(check_preserve._text(before), text)
            first = next(iter(res["lost"].items()), None)
            sig["preserve"] = (res["ok"], check_preserve.summarize(res)
                               + (f" 예: {first[0]} {first[1][0][0][:30]}" if first else ""))
            sig["v2_secs"]["preserve"] = res["sections"]
        else:
            sig["preserve"] = (None, "전 판 없음(첫 초안)")
    if "check_copy" in impls:
        import check_copy
        ref = os.path.join(os.path.dirname(os.path.abspath(rubric_path)), "style_ref.md") if rubric_path else ""
        if os.path.exists(ref):
            ok, probs, secs = check_copy.check_text(text, open(ref, encoding="utf-8").read(), check_copy.pack_text(pack))
            sig["copy"] = (ok, f"{len(probs)}줄" + (": " + probs[0][:80] if probs else ""))
            sig["v2_secs"]["copy"] = secs
        else:
            sig["copy"] = (None, "문체 예시 원본(criteria/style_ref.md) 없음")


def run_rubric(rubric_path, md, hwpx, spec_path, pack=None, requirements=None,
               mode="submission", skip_pages=False, winpython=None, quiet=False, before=None) -> dict:
    rubric = load_rubric(rubric_path)
    md_text = open(md, encoding="utf-8").read()
    tmp = tempfile.mkdtemp(prefix="rubric_")

    # 1) R1~R7 (기존 check — 출력은 그대로 나온다)
    if not quiet:
        print("─" * 62 + "\n[R] check_rubric 내장 검사")
    fails, warns = check(md, hwpx, spec_path)
    sig = {"md": md_text, "R": r_results(fails, warns)}

    # 2) 게이트·검사기 — 필요한 것만
    impls = " ".join(str(c.get("impl") or "") for _, _, c in iter_checks(rubric, mode))
    sig["gate_form"] = run_gate_form(hwpx, md, spec_path, tmp) if "gate_form" in impls and hwpx else {}
    sig["gate_hwpx"] = run_gate_hwpx(hwpx, tmp) if "gate_hwpx" in impls and hwpx else {}
    if "gate_pages" in impls and hwpx and not skip_pages:
        if not quiet:
            print("[pages] gate_pages 실측 중 (한컴 COM) …")
        sig["pages"] = run_gate_pages(hwpx, spec_path, md, tmp, winpython)
    else:
        sig["pages"] = {k: (None, "--skip-pages") for k in ("total", "chapters", "orphans")}
    sig["border"] = run_border(hwpx, spec_path) if "border_check" in impls and hwpx else (None, "hwpx 없음")
    sig["dash"] = run_dash(hwpx) if "check_dash" in impls and hwpx else (None, "hwpx 없음")
    if "check_internal" in impls:
        ok_i, d_i, heads_i = run_internal(hwpx, md)
        sig["internal"], sig["internal_heads"] = (ok_i, d_i), heads_i
        ok_r, d_r, heads_r = run_internal(hwpx, md, "rfp")
        sig["internal_rfp"], sig["internal_rfp_heads"] = (ok_r, d_r), heads_r
    else:
        sig["internal"], sig["internal_heads"] = (None, ""), []
        sig["internal_rfp"], sig["internal_rfp_heads"] = (None, ""), []
    run_v2_checks(sig, impls, md_text, hwpx, spec_path, before, rubric_path, pack)
    sig["wording"] = run_exit_check("check_wording.py", ["--md", md]) if "check_wording" in impls else (None, "")
    if "check_numbers" in impls:
        sig["numbers"] = (run_exit_check("check_numbers.py", ["--md", md, "--pack", pack, "--strict"])
                          if pack else (None, "--pack 없음(근거팩 미지정)"))
    else:
        sig["numbers"] = (None, "")
    sig["figures"] = run_figures(md, requirements) if "check_figures" in impls else (None, "")

    # 3) 체크 id 로 정리
    spec = json.load(open(spec_path, encoding="utf-8")) if spec_path and os.path.exists(spec_path) else {}
    checks = {}
    for item, tier, c in iter_checks(rubric, mode):
        if c.get("by") != "machine":
            continue
        impl = c.get("impl") or []
        impl = [impl] if isinstance(impl, str) else list(impl)
        oks, details = [], []
        for im in impl:
            ok, d = resolve(im, sig, spec_path)
            oks.append(ok)
            details.append(f"{im}: {d}")
        if not impl:
            ok = None
        elif any(o is False for o in oks):
            ok = False
        elif all(o is True for o in oks):
            ok = True
        else:
            ok = None
        checks[c["id"]] = {"item": item, "tier": tier, "by": "machine", "impl": impl,
                           "severity": c.get("severity", "fail" if tier == "floor" else "info"),
                           "check": c["check"], "ok": ok, "detail": " | ".join(details)[:400],
                           "penalty_weight": c.get("penalty_weight", 1)}
        if ok is False:
            checks[c["id"]]["sections"] = fail_sections(c, " | ".join(details), sig, spec)
    return {"rubric": os.path.abspath(rubric_path), "rubric_version": rubric.get("version"),
            "mode": mode,
            "inputs": {"md": os.path.abspath(md), "hwpx": os.path.abspath(hwpx) if hwpx else None,
                       "spec": os.path.abspath(spec_path) if spec_path else None, "pack": pack},
            "checks": checks}


def score_items(rubric: dict, report: dict, judge: dict | None = None,
                mode: str = "submission") -> dict:
    """항목별 점수. judge 가 None 이면 ceiling 은 전부 통과로 가정한다(기계 한정 상한 추정)."""
    sc = rubric.get("scoring") or {}
    formula = sc.get("formula", "cap60")
    base, ceil = float(sc.get("base_pct", 60)), float(sc.get("ceiling_pct", 40))
    pen, pen_max = float(sc.get("floor_penalty_pct", 20)), float(sc.get("floor_penalty_max_pct", 40))
    jm = (judge or {}).get("judgments") or {}
    out, total = {}, 0.0
    for item, cfg in (rubric.get("items") or {}).items():
        pts = float(cfg["points"])
        floor_fail, floor_unmeasured, ceil_pass, ceil_total, ceil_fail_ids = [], [], 0, 0, []
        pairs = [("floor", c) for c in cfg.get("floor") or []] + \
                [("ceiling", c) for c in cfg.get("ceiling") or []]
        for tier, c in pairs:
            if c.get("mode") and c["mode"] != mode:
                continue
            cid = c["id"]
            if c.get("by") == "machine":
                rec = (report.get("checks") or {}).get(cid)
                ok = rec["ok"] if rec else None
                if c.get("severity") == "warn":
                    continue
            else:
                if judge is None:
                    ok = True
                else:
                    j = jm.get(cid)
                    ok = bool(j.get("ok")) if j else False
            if tier == "floor":
                if ok is False:
                    floor_fail.append((cid, float(c.get("penalty_weight", 1))))
                elif ok is None:
                    floor_unmeasured.append(cid)
            else:
                ceil_total += 1
                if ok:
                    ceil_pass += 1
                else:
                    ceil_fail_ids.append(cid)
        ratio = (ceil_pass / ceil_total) if ceil_total else 1.0
        pct = base + ceil * ratio
        if floor_fail:
            if formula == "penalty":
                pct -= min(pen_max, sum(pen * w for _, w in floor_fail))
            else:
                pct = min(pct, base)
        score = max(0.0, round(pts * pct / 100, 1))
        total += score
        out[item] = {"points": pts, "score": score, "floor_fail": [c for c, _ in floor_fail],
                     "floor_unmeasured": floor_unmeasured, "ceiling": f"{ceil_pass}/{ceil_total}",
                     "ceiling_fail": ceil_fail_ids}
    return {"formula": formula, "judge": judge is not None, "items": out, "total": round(total, 1)}


def print_report(report: dict, scores: dict | None):
    print("─" * 62 + "\n[rubric] 기계 검사 — 체크 id 별")
    for cid, r in report["checks"].items():
        tag = {True: "OK  ", False: "FAIL", None: "N/A "}[r["ok"]]
        if r["ok"] is False and r["severity"] == "warn":
            tag = "WARN"
        print(f"  [{tag}] {cid:<5} {r['item']} {r['tier']:<7} {r['check'][:34]:<36} {r['detail'][:70]}")
    if scores:
        print("─" * 62)
        print(f"[score] formula={scores['formula']} · judge="
              + ("있음" if scores["judge"] else "없음(ceiling 전부 통과 가정)"))
        print(f"  {'항목':<4}{'배점':>5}{'점수':>7}   floor 실패 / ceiling 통과")
        for item, v in scores["items"].items():
            ff = ",".join(v["floor_fail"]) or "—"
            um = (" (미측정 " + ",".join(v["floor_unmeasured"]) + ")") if v["floor_unmeasured"] else ""
            print(f"  {item:<4}{v['points']:>5.0f}{v['score']:>7.1f}   {ff}{um} / {v['ceiling']}")
        print(f"  {'총점':<4}{'100':>5}{scores['total']:>7.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--hwpx")
    ap.add_argument("--spec")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 본다")
    # rubric 모드
    ap.add_argument("--rubric", help="criteria/rubric.yaml — 주면 rubric 모드로 돈다")
    ap.add_argument("--report", help="기계 검사 결과 JSON 저장 경로 (rubric 모드)")
    ap.add_argument("--judge", help="rp-scorer 의 70_judge.json — 주면 점수를 계산한다")
    ap.add_argument("--pack", help="근거팩 디렉터리 (C-m3 check_numbers)")
    ap.add_argument("--requirements", help="requirements.md (T-f2 check_figures)")
    ap.add_argument("--before", help="전 판 원고(md 또는 hwpx). 주면 C-m5 정보 보존을 잰다(수정 회차 = 직전 채택 회차)")
    ap.add_argument("--mode", default="submission", choices=["submission", "final"])
    ap.add_argument("--skip-pages", action="store_true", help="한컴 실측(gate_pages)을 건너뛴다 → 미측정")
    ap.add_argument("--winpython", help="PyMuPDF 가 있는 파이썬 (기본: 현재 인터프리터)")
    ap.add_argument("--no-fail", action="store_true",
                    help="rubric 모드: floor 실패여도 exit 0 (rp_run 수정 회차가 보고서를 읽고 절로 되돌린다)")
    a = ap.parse_args()

    print("=" * 62)
    print("심사 배점 검사 — 손실이 큰 항목부터")
    print("=" * 62)
    if not a.rubric:
        fails, warns = check(a.md, a.hwpx, a.spec)
        print("=" * 62)
        if fails or (a.strict and warns):
            print(f"FAIL — 실패 {len(fails)}건 · 경고 {len(warns)}건")
            return 2
        print(f"PASS — 실패 0건 · 경고 {len(warns)}건")
        return 0

    report = run_rubric(a.rubric, a.md, a.hwpx, a.spec, pack=a.pack, requirements=a.requirements,
                        mode=a.mode, skip_pages=a.skip_pages, winpython=a.winpython, before=a.before)
    judge = json.load(open(a.judge, encoding="utf-8")) if a.judge else None
    scores = score_items(load_rubric(a.rubric), report, judge, a.mode)
    report["scores"] = scores
    print_report(report, scores)
    if a.report:
        os.makedirs(os.path.dirname(os.path.abspath(a.report)), exist_ok=True)
        json.dump(report, open(a.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  → {a.report}")
    hard_fail = [cid for cid, r in report["checks"].items()
                 if r["ok"] is False and r["tier"] == "floor" and r["severity"] != "warn"]
    print("=" * 62)
    if hard_fail:
        print(f"FAIL — floor 실패 {len(hard_fail)}건: {', '.join(hard_fail)}")
        return 0 if a.no_fail else 2
    print("PASS — floor 실패 0건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
