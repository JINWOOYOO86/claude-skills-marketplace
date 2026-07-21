#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재현성 검증 — 판독값 JSON으로 2회 재빌드해 기존 산출물과 셀·바이트 단위로 대조한다.

  python verify_repro.py "C:/작업/사외전문가 설치계획서 모음"     # 하위 폴더 전체
  python verify_repro.py "C:/작업/현장폴더" --spec ops_현장.json  # 한 건만

R8(판독값 분리)이 실제로 지켜지는지 확인하는 도구다. 결과가 전부 '동일'이어야 한다:
- **셀 비교**: 값·수식이 하나라도 다르면 빌더가 비결정적이라는 뜻
- **sha256**: 다르면 타임스탬프 정규화(_xlsx_det)가 빠진 것
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = {"ops_": "build_ops_plan.py", "loadcalc_": "build_load_calc.py",
           "survey_": "build_survey.py"}


def cells(path):
    wb = openpyxl.load_workbook(path)
    return {(ws.title, c.coordinate): c.value
            for ws in wb for row in ws.iter_rows() for c in row if c.value is not None}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def specs_in(folder):
    for prefix in BUILDER:
        for p in sorted(glob.glob(os.path.join(folder, prefix + "*.json"))):
            yield p


def check(spec, tmp):
    spec = os.path.abspath(spec)                 # 상대경로면 cwd가 비어 빌드가 실패한다
    name = os.path.basename(spec)
    script = next(s for p, s in BUILDER.items() if name.startswith(p))
    folder = os.path.dirname(spec) or os.getcwd()
    with open(spec, encoding="utf-8") as f:
        out_name = json.load(f).get("output")
    orig = os.path.join(folder, out_name) if out_name else None
    if not (orig and os.path.exists(orig)):
        return name, "원본없음", "-", "-"

    outs = []
    for tag in ("A", "B"):
        o = os.path.join(tmp, tag + "_" + os.path.basename(orig))
        subprocess.run([sys.executable, os.path.join(HERE, script), spec, "-o", o],
                       capture_output=True, cwd=folder)
        outs.append(o)
    if not all(os.path.exists(o) for o in outs):
        return name, "빌드실패", "-", "-"

    ca, cb, co = cells(outs[0]), cells(outs[1]), cells(orig)
    cell = "동일(%d셀)" % len(ca) if ca == cb == co else "차이"
    sa, sb, so = sha256(outs[0]), sha256(outs[1]), sha256(orig)
    return name, cell, "동일" if sa == sb else "상이", "동일" if sa == so else "상이"


def main():
    ap = argparse.ArgumentParser(description="산출물 재현성 검증 (셀·sha256)")
    ap.add_argument("path", help="작업 폴더(하위 폴더까지 훑음) 또는 단일 현장 폴더")
    ap.add_argument("--spec", help="특정 JSON 하나만 검사")
    args = ap.parse_args()

    tmp = os.path.join(tempfile.gettempdir(), "kepco_repro")
    os.makedirs(tmp, exist_ok=True)

    args.path = os.path.abspath(args.path)
    targets = []
    if args.spec:
        targets = [os.path.join(args.path, args.spec)]
    else:
        targets = list(specs_in(args.path))
        for sub in sorted(os.listdir(args.path)):
            d = os.path.join(args.path, sub)
            if os.path.isdir(d):
                targets += list(specs_in(d))

    print("%-46s %-16s %-9s %-9s" % ("입력 JSON", "셀 비교", "sha 1↔2", "sha vs원본"))
    print("-" * 86)
    ok = 0
    for spec in targets:
        name, cell, s12, so = check(spec, tmp)
        print("%-46s %-16s %-9s %-9s" % (name[:46], cell, s12, so))
        ok += (cell.startswith("동일") and s12 == "동일" and so == "동일")
    print("\n총 %d건 | 완전 일치 %d건" % (len(targets), ok))
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
