#!/usr/bin/env python3
"""공고 첨부(PDF·HWPX·HWP·ZIP)에서 본문 텍스트를 뽑는다.

공고 제목만 보는 판정은 판정이 아니다. RFP 실물은 첨부 안에 있고, 국가 R&D 공고 첨부는
PDF·HWPX·HWP 가 뒤섞여 오며 여러 RFP 가 ZIP 하나로 묶여 오는 일도 잦다. 이 스크립트는
그 네 가지를 한 번에 처리한다.

사용법
  python3 extract_attachment.py <파일 또는 폴더> [...]        # 텍스트를 stdout 으로
  python3 extract_attachment.py raw/ --outdir extracted/      # 파일별 .txt 로 저장

의존 라이브러리는 형식별로 다르고, 없으면 그 파일만 건너뛰고 사유를 남긴다(전체 실패 아님).
  PDF   pypdf  또는 pymupdf  →  pip install pypdf
  HWP   olefile              →  pip install olefile
  HWPX  없음 (zip + XML)
"""

import argparse
import os
import re
import struct
import sys
import unicodedata
import zipfile

SUPPORTED = (".pdf", ".hwp", ".hwpx", ".zip", ".txt", ".md", ".xml")


# ── PDF ──────────────────────────────────────────────────────────────
def from_pdf(path):
    try:
        from pypdf import PdfReader

        pages = [(p.extract_text() or "") for p in PdfReader(path).pages]
        return "\n".join(f"===== PAGE {i + 1} =====\n{t}" for i, t in enumerate(pages))
    except ImportError:
        pass
    try:
        import pymupdf

        with pymupdf.open(path) as doc:
            return "\n".join(
                f"===== PAGE {i + 1} =====\n{pg.get_text()}" for i, pg in enumerate(doc)
            )
    except ImportError:
        raise RuntimeError("pypdf/pymupdf 없음 — pip install pypdf")


# ── HWPX (zip + XML) ─────────────────────────────────────────────────
TAG = re.compile(r"<[^>]+>")


def from_hwpx(path):
    out = []
    with zipfile.ZipFile(path) as z:
        # 섹션 파일명은 Contents/section0.xml, section1.xml … 순서를 지켜야 본문이 뒤섞이지 않는다
        names = sorted(
            (n for n in z.namelist() if re.search(r"Contents/section\d+\.xml$", n)),
            key=lambda n: int(re.search(r"section(\d+)", n).group(1)),
        )
        for n in names:
            xml = z.read(n).decode("utf-8", errors="replace")
            xml = re.sub(r"</hp:p>", "\n", xml)          # 문단 경계 보존
            xml = re.sub(r"</hp:tc>", "\t", xml)         # 표 셀 경계 보존
            xml = re.sub(r"</hp:tr>", "\n", xml)
            out.append(TAG.sub("", xml))
    text = "\n".join(out)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", text)


# ── HWP 5.x (OLE + raw deflate + 레코드 파싱) ────────────────────────
# HWPTAG_PARA_TEXT 안에는 본문 글자 사이에 컨트롤이 섞여 있다. 컨트롤을 단순히
# "코드 32 미만"으로만 거르면, 확장 컨트롤이 데이터로 물고 있는 4바이트 ID가
# 글자로 남아 본문에 `捤獥汤捯湰灧` 같은 쓰레기가 박힌다(HWP 스펙 미준수의 전형).
#   · 확장/인라인 컨트롤: 시작 코드 + 6 WCHAR + 같은 코드 = 총 8 WCHAR 를 통째로 건너뛴다
#   · 단독 컨트롤: 1 WCHAR — 줄바꿈 계열만 개행으로 바꾸고 나머지는 버린다
_CTRL_8WCHAR = frozenset([1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23] + [4, 5, 6, 7, 8, 9, 19, 20])
_CTRL_NEWLINE = frozenset([10, 13])


def _para_text(payload):
    units = payload.decode("utf-16le", errors="ignore")
    buf, i, n = [], 0, len(units)
    while i < n:
        o = ord(units[i])
        if o in _CTRL_8WCHAR:
            if o == 9:  # 탭도 8 WCHAR 인라인 컨트롤이다 — 글자만 되살린다
                buf.append("\t")
            i += 8
            continue
        if o in _CTRL_NEWLINE:
            buf.append("\n")
        elif o in (28, 29):  # 묶음빈칸·고정폭빈칸
            buf.append(" ")
        elif o == 24:  # 하이픈
            buf.append("-")
        elif o >= 32:
            buf.append(units[i])
        i += 1
    return "".join(buf)


def from_hwp(path):
    try:
        import olefile
    except ImportError:
        raise RuntimeError("olefile 없음 — pip install olefile")

    ole = olefile.OleFileIO(path)
    try:
        compressed = bool(ole.openstream("FileHeader").read()[36] & 1)
        secs = sorted(
            (e for e in ole.listdir() if e[0] == "BodyText" and e[-1].startswith("Section")),
            key=lambda e: int(e[-1].replace("Section", "")),
        )
        out = []
        for e in secs:
            data = ole.openstream(e).read()
            if compressed:
                import zlib

                try:
                    data = zlib.decompress(data, -15)  # zlib 헤더 없는 raw deflate
                except zlib.error:
                    pass
            i, n = 0, len(data)
            while i + 4 <= n:
                hdr = struct.unpack("<I", data[i : i + 4])[0]
                tag, size = hdr & 0x3FF, (hdr >> 20) & 0xFFF
                i += 4
                if size == 0xFFF:  # 확장 크기 — 다음 UINT32 가 실제 크기
                    if i + 4 > n:
                        break
                    size = struct.unpack("<I", data[i : i + 4])[0]
                    i += 4
                payload, i = data[i : i + size], i + size
                if tag != 67:  # HWPTAG_PARA_TEXT
                    continue
                s = _para_text(payload).strip()
                if s:
                    out.append(s)
        return "\n".join(out)
    finally:
        ole.close()


# ── ZIP (RFP 묶음) ───────────────────────────────────────────────────
def from_zip(path, tmp_root):
    import tempfile

    out = []
    with zipfile.ZipFile(path) as z:
        tmp = tempfile.mkdtemp(prefix="rfpzip_", dir=tmp_root)
        for info in z.infolist():
            if info.is_dir():
                continue
            name = _zip_name(info)
            if not name.lower().endswith(SUPPORTED):
                continue
            dest = os.path.join(tmp, re.sub(r"[\\/]+", "_", name))
            with open(dest, "wb") as f:
                f.write(z.read(info))
            try:
                out.append(f"########## {name}\n{extract(dest, tmp_root)}")
            except Exception as e:  # 한 건 실패가 묶음 전체를 죽이지 않게
                out.append(f"########## {name}\n[추출 실패: {e}]")
    return "\n\n".join(out)


def _zip_name(info):
    """ZIP 내부 파일명은 CP949 로 들어오는 경우가 많다(UTF-8 플래그 미설정)."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return info.filename


# ── 디스패치 ─────────────────────────────────────────────────────────
def extract(path, tmp_root="/tmp"):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        text = from_pdf(path)
    elif ext == ".hwpx":
        text = from_hwpx(path)
    elif ext == ".hwp":
        text = from_hwp(path)
    elif ext == ".zip":
        text = from_zip(path, tmp_root)
    elif ext in (".txt", ".md", ".xml"):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        raise RuntimeError(f"지원하지 않는 형식: {ext}")
    return unicodedata.normalize("NFC", text)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("paths", nargs="+", help="파일 또는 폴더")
    ap.add_argument("--outdir", help="파일별 .txt 저장 위치 (생략하면 stdout)")
    a = ap.parse_args()

    targets = []
    for p in a.paths:
        if os.path.isdir(p):
            targets += [
                os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(SUPPORTED)
            ]
        else:
            targets.append(p)

    if a.outdir:
        os.makedirs(a.outdir, exist_ok=True)

    fails = 0
    for t in targets:
        try:
            text = extract(t)
        except Exception as e:
            fails += 1
            print(f"[건너뜀] {os.path.basename(t)} — {e}", file=sys.stderr)
            continue
        if a.outdir:
            dest = os.path.join(a.outdir, os.path.basename(t) + ".txt")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"{dest}  ({len(text):,}자)", file=sys.stderr)
        else:
            print(f"########## {os.path.basename(t)}")
            print(text)
    if fails:
        print(f"\n{fails}건 추출 실패 — 위 사유 참조", file=sys.stderr)


if __name__ == "__main__":
    main()
