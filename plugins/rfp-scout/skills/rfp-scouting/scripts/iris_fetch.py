#!/usr/bin/env python3
"""IRIS(범부처통합연구지원시스템) 공고 수집기 — 표준 라이브러리만 사용.

목록·상세·첨부 전 구간이 평범한 HTTP다. 로그인·쿠키·세션·브라우저 자동화가 모두 불필요하다
(2026-08-04 최초 실측, 2026-08-12 재확인 — 목록 POST 200, 상세 POST 200, 첨부 GET 200).

사용법
  python3 iris_fetch.py list [--status ancmIng] [--pages 3] [--out list.json]
  python3 iris_fetch.py detail 023398 [--out detail.html]
  python3 iris_fetch.py attachments 023398
  python3 iris_fetch.py download 023398 --dest raw/ [--index 0,1]

status: ancmIng=접수중(기본) / ancmPre=접수예정 / ancmEnd=마감
  ⚠️ ancmPre 는 과거분을 포함한 전체 아카이브(수천 건)라 증분 탐색에 쓰지 말 것.
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.iris.go.kr"
LIST_API = BASE + "/contents/retrieveBsnsAncmBtinSituList.do"
LIST_VIEW = BASE + "/contents/retrieveBsnsAncmBtinSituListView.do"
DETAIL_API = BASE + "/contents/retrieveBsnsAncmView.do"
FILE_API = BASE + "/comm/file/fileDownload.do"

# 사람이 열어보는 링크(리포트에 그대로 붙인다) — GET 으로 열린다
VIEW_LINK = BASE + "/contents/retrieveBsnsAncmView.do?ancmId={}"
PRNTC_LINK = BASE + "/contents/retrieveAncmPrntcView.do?bsnsPrntcNo={}"

UA = "Mozilla/5.0 (compatible; rfp-scout/1.0)"
TIMEOUT = 30


def _post(url, data, referer=LIST_VIEW, ajax=False):
    body = urllib.parse.urlencode(data).encode()
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": referer,
    }
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def fetch_list(status="ancmIng", pages=1):
    """공고 목록. 페이지당 10건. 반환: (총건수, [레코드])"""
    total, rows = None, []
    for page in range(1, pages + 1):
        raw = _post(LIST_API, {"ancmPrg": status, "pageIndex": page}, ajax=True)
        d = json.loads(raw.decode("utf-8"))
        if total is None:
            total = d.get("paginationInfo", {}).get("totalRecordCount")
        page_rows = d.get("listBsnsAncmBtinSitu", [])
        if not page_rows:
            break
        for r in page_rows:
            r["viewUrl"] = VIEW_LINK.format(r.get("ancmId", ""))
        rows.extend(page_rows)
    return total, rows


def fetch_detail(ancm_id, status="ancmIng"):
    """상세 HTML. 접수기간·지원규모·주관자격·첨부는 목록에 없고 여기에만 있다."""
    raw = _post(DETAIL_API, {"ancmId": ancm_id, "ancmPrg": status})
    return raw.decode("utf-8", errors="replace")


ATCH_RE = re.compile(
    r"f_bsnsAncm_downloadAtchFile\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'?(\d*)'?"
)


def parse_attachments(html):
    """상세 HTML 에서 첨부 목록을 뽑는다. 두 ID 는 onclick 인자에 그대로 박혀 있다."""
    out, seen = [], set()
    for doc_id, file_id, name, size in ATCH_RE.findall(html):
        if doc_id == "atchDocId" or file_id in seen:  # 첫 매치는 함수 정의부
            continue
        seen.add(file_id)
        out.append(
            {
                "atchDocId": doc_id,
                "atchFileId": file_id,
                "fileName": name.strip(),
                "fileSize": int(size) if size.isdigit() else None,
                "url": FILE_API
                + "?"
                + urllib.parse.urlencode({"atchDocId": doc_id, "atchFileId": file_id}),
            }
        )
    return out


def download(att, dest_dir):
    """첨부 1건 저장. 선행 호출 retrieveCheckFileDownload.do 는 불필요하다(응답만 느려진다)."""
    os.makedirs(dest_dir, exist_ok=True)
    req = urllib.request.Request(att["url"], headers={"User-Agent": UA, "Referer": DETAIL_API})
    with urllib.request.urlopen(req, timeout=TIMEOUT * 4) as r:
        name = att.get("fileName") or _name_from_headers(r) or att["atchFileId"]
        data = r.read()
    path = os.path.join(dest_dir, _safe(name))
    with open(path, "wb") as f:
        f.write(data)
    return path, len(data)


def _name_from_headers(resp):
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    if not m:
        return None
    name = urllib.parse.unquote(m.group(1))
    if all(ord(c) < 256 for c in name):  # CP949 가 latin-1 로 잘못 디코딩된 경우
        try:
            name = name.encode("latin-1").decode("cp949")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    return name


def _safe(name):
    return re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip() or "attachment"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("--status", default="ancmIng", choices=["ancmIng", "ancmPre", "ancmEnd"])
    p.add_argument("--pages", type=int, default=3)
    p.add_argument("--out")

    for name in ("detail", "attachments", "download"):
        q = sub.add_parser(name)
        q.add_argument("ancm_id")
        q.add_argument("--status", default="ancmIng")
        if name == "detail":
            q.add_argument("--out")
        if name == "download":
            q.add_argument("--dest", default=".")
            q.add_argument("--index", help="쉼표로 구분한 0-기반 번호. 생략하면 전부")

    a = ap.parse_args()

    if a.cmd == "list":
        total, rows = fetch_list(a.status, a.pages)
        print(f"총 {total}건 / 수집 {len(rows)}건", file=sys.stderr)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump({"total": total, "rows": rows}, f, ensure_ascii=False, indent=2)
            print(a.out, file=sys.stderr)
        else:
            for r in rows:
                print(
                    "\t".join(
                        [
                            r.get("ancmId", ""),
                            r.get("rcveStrDe", ""),
                            r.get("rcveEndDe", ""),
                            str(r.get("dDay", "")),
                            r.get("sorgnNm", ""),
                            r.get("ancmTl", ""),
                        ]
                    )
                )
        return

    html = fetch_detail(a.ancm_id, a.status)

    if a.cmd == "detail":
        if getattr(a, "out", None):
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(html)
            print(a.out, file=sys.stderr)
        else:
            sys.stdout.write(html)
        return

    atts = parse_attachments(html)
    if a.cmd == "attachments":
        for i, x in enumerate(atts):
            print(f"[{i}] {x['fileName']}  ({x['fileSize']}B)")
            print(f"     {x['url']}")
        return

    idxs = range(len(atts)) if not a.index else [int(i) for i in a.index.split(",")]
    for i in idxs:
        path, n = download(atts[i], a.dest)
        print(f"[{i}] {path}  {n}B")


if __name__ == "__main__":
    main()
