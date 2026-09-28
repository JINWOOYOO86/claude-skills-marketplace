# -*- coding: utf-8 -*-
"""표기 통일 치환 (F-j2 단위·번호 형식, S-j1 고정 용어). 결정적·멱등. rubric fix_by: unify 의 실행기.

    python unify_terms.py --md <30_proposal.md> --evidence <_ws> [--notation <criteria/notation.yaml>]
                          [--ledger <62_통일치환.md>] [--pack <_ws>] [--dry]

규칙 원천 두 곳:
  1. <_ws>/15_axis_conflicts.md §B-1 「고정 표기」 열 (F1~F15): 「A」→B 꼴이면 A 를 B 로, 「X(구 Y)」꼴이면 「X(구 Y)」 앞의 짧은 표기 X 를 전체 표기로
  2. criteria/notation.yaml: 숫자 뒤 단위 표준형, 특허번호 자릿수, 일반명사 변형(예외 문구 있음)
끝에 check_numbers --strict 를 돌려 값이 깨졌으면 전부 되돌린다(--pack 을 주면).
2026-09-27 실측: 시간 h/시간 · 질량 t/톤 · US 특허번호 · 권리자 약칭 · HFC/HFCs 를 손으로 고쳤다. 그 다섯을 규칙으로 옮겼다.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_notation(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {}
    import yaml
    return yaml.safe_load(io.open(path, encoding="utf-8").read()) or {}


def fixed_terms(evidence_dir: str | None) -> list[tuple[str, str, str]]:
    """15_axis_conflicts.md §B-1 에서 (규칙 이름, 변형, 표준) 목록. 표준 표기 안의 「X(구 Y)」는 X 단독 표기를 전체로 바꾼다."""
    out = []
    if not evidence_dir:
        return out
    p = os.path.join(evidence_dir, "15_axis_conflicts.md")
    if not os.path.exists(p):
        return out
    t = io.open(p, encoding="utf-8").read()
    m = re.search(r"^## B-1\..*?(?=^## |\Z)", t, re.M | re.S)
    if not m:
        return out
    for ln in m.group(0).splitlines():
        if not ln.startswith("| F"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        fid, fixed = cells[0], cells[2]
        std = re.findall(r"「([^」]+)」", fixed)
        if not std:
            continue
        std0 = std[0]
        # 「Gana Advanced Materials(구 Dara)」: 「Gana(구 Dara)」 를 전체 표기로
        mm = re.match(r"^(\S+)(?: \S+)+\((구 [^)]+)\)$", std0)
        if mm:
            short = f"{mm.group(1)}({mm.group(2)})"
            out.append((f"{fid} 고정 표기", short, std0))
    return out


def apply_units(text: str, units: dict) -> tuple[str, list]:
    log = []
    for std, variants in (units or {}).items():
        for v in variants:
            pat = re.compile(r"(\d[\d,.]*)\s?" + re.escape(v) + r"(?![A-Za-z가-힣0-9])")
            def rep(m):
                log.append(("단위 " + v + "→" + std, m.group(0), m.group(1) + std))
                return m.group(1) + std
            text = pat.sub(rep, text)
            # 표 단위 열의 낱 단위(| h |)
            pat2 = re.compile(r"(\|\s*)" + re.escape(v) + r"(\s*\|)")
            text = pat2.sub(lambda m: (log.append(("단위 열 " + v + "→" + std, m.group(0), m.group(1) + std + m.group(2))) or (m.group(1) + std + m.group(2))), text)
    return text, log


def apply_patent(text: str) -> tuple[str, list]:
    log = []
    pat = re.compile(r"\bUS (\d{7,8}) ([AB]\d)\b")
    def rep(m):
        num = m.group(1)
        g = f"{int(num):,}"
        s = f"US {g} {m.group(2)}"
        log.append(("특허번호 자릿수", m.group(0), s))
        return s
    return pat.sub(rep, text), log


def apply_terms(text: str, terms: list) -> tuple[str, list]:
    log = []
    for tm in terms or []:
        std, variants, ex = tm.get("standard"), tm.get("variants") or [], tm.get("except") or []
        for v in variants:
            pat = re.compile(r"(?<![A-Za-z])" + re.escape(v) + r"(?![A-Za-z])")
            def rep(m):
                tail = text_after(text_ref[0], m.end())
                for e in ex:
                    if (m.group(0) + tail).startswith(e) or text_ref[0][max(0, m.start() - 0):m.end() + len(e)].startswith(e):
                        return m.group(0)
                log.append((f"용어 {v}→{std}", m.group(0), std))
                return std
            text_ref = [text]
            text = pat.sub(rep, text)
    return text, log


def text_after(t: str, pos: int, n: int = 12) -> str:
    return t[pos:pos + n]


def apply_fixed(text: str, rules: list) -> tuple[str, list]:
    log = []
    for name, short, full in rules:
        if short in text and full not in text.replace(short, ""):
            pass
        # 이미 전체 표기가 있는 곳은 두고, 짧은 표기만 전체로
        cnt = text.count(short)
        if cnt:
            text = text.replace(short, full)
            log.append((name, short, full))
    return text, log


def unify(text: str, notation: dict, evidence_dir: str | None) -> tuple[str, list]:
    log = []
    text, l1 = apply_units(text, notation.get("units") or {})
    log += l1
    if (notation.get("number_formats") or {}).get("patent_us_grouping"):
        text, l2 = apply_patent(text)
        log += l2
    text, l3 = apply_terms(text, notation.get("terms") or [])
    log += l3
    text, l4 = apply_fixed(text, fixed_terms(evidence_dir))
    log += l4
    return text, log


def write_ledger(path: str, log: list) -> None:
    lines = ["# 표기 통일 원장 (unify_terms.py)", "", "| # | 규칙 | 전 | 후 |", "|---|---|---|---|"]
    for i, (rule, a, b) in enumerate(log, 1):
        lines.append(f"| {i} | {rule} | {a.replace('|', '｜')} | {b.replace('|', '｜')} |")
    if not log:
        lines.append("| 해당 없음 | | | |")
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--evidence")
    ap.add_argument("--notation")
    ap.add_argument("--ledger")
    ap.add_argument("--pack", help="check_numbers --strict 로 값 보존을 확인. 실패하면 되돌린다")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    src = io.open(a.md, encoding="utf-8").read()
    new, log = unify(src, load_notation(a.notation), a.evidence)
    print(f"표기 통일: {len(log)}건")
    for rule, x, y in log[:20]:
        print(f"  [{rule}] {x} → {y}")
    if a.dry or new == src:
        return 0
    io.open(a.md, "w", encoding="utf-8", newline="").write(new)
    if a.pack:
        r = subprocess.run([sys.executable, os.path.join(HERE, "check_numbers.py"), "--md", a.md, "--pack", a.pack, "--strict"],
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            io.open(a.md, "w", encoding="utf-8", newline="").write(src)
            print("check_numbers --strict 실패: 되돌렸다\n" + (r.stdout or "")[-400:])
            return 2
    if a.ledger:
        write_ledger(a.ledger, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
