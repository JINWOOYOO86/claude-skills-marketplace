#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""설치계획서 PDF 1차 스캔 — 자료 수록 위치를 빠르게 좁힌다.

  python scan_pdf.py "C:/작업/사외전문가 설치계획서 모음"                 # 부하계산서 키워드
  python scan_pdf.py "C:/작업/폴더" --keys "시간대별,운전계획,최대일냉방부하"
  python scan_pdf.py "C:/작업/폴더" --json out.json

각 PDF의 **텍스트 레이어 유무**와 키워드 적중 페이지를 보고한다.

⚠️ 적중은 '후보'일 뿐이다. 목차·간지에도 같은 문구가 있으므로 **반드시 해당 페이지를 열어
실물 표를 눈으로 확인**해야 한다(스캔 PDF는 텍스트가 0페이지로 나오니 렌더링해서 확인).
"""
import argparse
import glob
import json
import os
import sys

try:
    import fitz                                   # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF(fitz)가 필요하다. WSL이면 Windows anaconda python으로 실행할 것.")

DEFAULT_KEYS = ["부하계산", "부하 계산", "부하집계", "부하 집계", "PEAK LOAD",
                "Cooling Load", "열부하", "냉난방 부하"]


def scan(path, keys):
    rec = {"file": os.path.basename(path), "pages": 0, "text_pages": 0, "hits": []}
    d = fitz.open(path)
    rec["pages"] = d.page_count
    for i in range(d.page_count):
        t = d[i].get_text()
        if len(t.strip()) > 30:
            rec["text_pages"] += 1
        for k in keys:
            if k in t:
                line = [l.strip() for l in t.splitlines() if k in l]
                rec["hits"].append({"page": i + 1, "key": k, "line": (line[0][:60] if line else "")})
                break
    d.close()
    return rec


def main():
    ap = argparse.ArgumentParser(description="설치계획서 PDF 키워드 1차 스캔")
    ap.add_argument("path")
    ap.add_argument("--keys", help="쉼표로 구분한 키워드(기본: 부하계산서 관련)")
    ap.add_argument("--json", help="결과를 JSON으로 저장할 경로")
    args = ap.parse_args()
    keys = [k.strip() for k in args.keys.split(",")] if args.keys else DEFAULT_KEYS

    args.path = os.path.abspath(args.path)
    folders = [args.path]
    folders += [os.path.join(args.path, d) for d in sorted(os.listdir(args.path))
                if os.path.isdir(os.path.join(args.path, d))]

    out = []
    for fp in folders:
        # 대소문자 구분 없는 파일시스템에서 *.pdf·*.PDF가 중복 매칭되므로 중복 제거
        pdfs = sorted({os.path.normcase(x): x for x in
                       glob.glob(os.path.join(fp, "*.pdf")) +
                       glob.glob(os.path.join(fp, "*.PDF"))}.values())
        if not pdfs:
            continue
        print("\n## %s" % os.path.basename(fp))
        for p in pdfs:
            try:
                rec = scan(p, keys)
            except Exception as e:
                print("  - %s : 오류 %s" % (os.path.basename(p), e))
                continue
            rec["folder"] = os.path.basename(fp)
            out.append(rec)
            layer = "텍스트 %d/%d p" % (rec["text_pages"], rec["pages"])
            hits = ", ".join("p%d(%s)" % (h["page"], h["key"]) for h in rec["hits"][:6]) or "적중 없음"
            print("  - %-52s %-16s %s" % (rec["file"][:52], layer, hits))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\nJSON 저장:", args.json)
    print("\n※ 적중은 후보일 뿐이다. 목차·간지 문구일 수 있으니 해당 페이지를 반드시 눈으로 확인할 것.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
