# -*- coding: utf-8 -*-
"""외과 수정 엔진: 수정 회차의 편집을 문장 단위 op 로만 적용한다 (plan_v2 3단계 9, 2026-09-28).

t3 는 수정 회차마다 절을 다시 써서 외부 원본 대비 정보 22건을 잃었다. 82_외과수정(사람 손, 35건)은
절을 다시 쓰지 않고 문장만 바꾸고 더해 원본 정보를 하나도 잃지 않았다. 이 스크립트가 그 방식을 기계로 강제한다.

    python edit_apply.py --md <30_proposal.md> --edits <e1.json> [<e2.json> …] --ledger <74_수정원장.json> [--round N] [--dry]
    python edit_apply.py --hwpx <in.hwpx> --out <out.hwpx> --edits <e.json> --ledger <원장.json>

edits JSON: {"author": "editor|writer:<절>|revise", "edits": [op, …]} 또는 op 목록.
  op = {"id", "check", "section", "op": "replace|insert_after|merge", "anchor", "anchor2"(merge), "new", "reason"}
       hwpx 전용: {"op": "heading_bold"} · {"op": "border_solid"} (anchor·new 없음)
규칙(어기면 그 op 만 거부하고 원장에 사유를 적는다):
  - 삭제 op 는 없다. anchor 는 원고에 **정확히 한 번** 나오는 한 줄 안의 글(문장·표 칸)이다.
  - replace: new 가 anchor 의 보존 토큰(수치·규격명·출처·고유명사·위험 대응·산출식, check_preserve)을 모두 담아야 한다.
  - insert_after: anchor 가 든 줄 바로 뒤에 같은 들여쓰기·글머리로 한 줄을 더한다(표 행 뒤에는 넣지 않는다).
  - merge: anchor 가 든 줄을 new 로 바꾸고 anchor2(한 줄 전체)를 지운다. 두 줄의 보존 토큰이 new 에 모두 있어야 한다
           (82_외과수정 #25·#28·#32: 두 항목을 정보 손실 없이 한 문장으로 합쳐 분량을 줄였다).
  - new 는 한 줄이다(줄바꿈·표 구분자 없음). 「라벨: 내용」 머리·절 번호 참조·내부 표기를 담지 않는다(S-m6·T-m8·T-m5·T-m7).
  - 목표를 낮추지 않는다: 고치기 전 줄의 방향 있는 목표보다 느슨한 목표가 new 에 있으면 거부(check_targets, plan_v2 5단계 18).
원장(JSON)은 회차·작성자·op·전·후·판정을 쌓는다. 같은 이름의 .md 에 사람이 읽는 표를 쓴다.
exit 0: 전부 적용, 3: 일부 거부(적용분은 반영됨), 2: 입력 오류.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_internal  # noqa: E402
import check_preserve  # noqa: E402
import check_targets  # noqa: E402

TEXT_OPS = ("replace", "insert_after", "merge")
HWPX_OPS = ("heading_bold", "border_solid")


def load_edits(path: str) -> tuple[str, list[dict]]:
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list):
        return os.path.splitext(os.path.basename(path))[0], d
    return d.get("author") or os.path.splitext(os.path.basename(path))[0], d.get("edits") or []


def vet(op: dict, text: str, allow=()) -> str | None:
    """거부 사유 또는 None. text 는 적용 직전의 원고 전체(hwpx 는 문단 텍스트를 줄로 이은 것)."""
    kind = op.get("op")
    if kind in HWPX_OPS:
        return None
    if kind not in TEXT_OPS:
        return f"허용되지 않는 op「{kind}」(삭제·절 재작성은 없다: replace·insert_after·merge 만)"
    anchor, new = op.get("anchor") or "", (op.get("new") or "").strip()
    if not anchor.strip() or not new:
        return "anchor·new 가 비었다"
    if "\n" in anchor or "\n" in new:
        return "여러 줄: 문장 하나(한 줄)만 바꾸거나 더한다"
    if "|" in new and kind == "insert_after":
        return "표 행은 더하지 않는다"
    n = text.count(anchor)
    if n != 1:
        return f"anchor 가 원고에 {n}회 있다(정확히 1회여야 한다)"
    if kind == "merge":
        a2 = op.get("anchor2") or ""
        if not a2.strip() or "\n" in a2 or text.count(a2) != 1:
            return "merge 의 anchor2 가 원고에 정확히 1회 있는 한 줄이 아니다"
        if not any(re.sub(r"^\s*(?:-\s+|[□○ㅇ·]\s*)", "", ln).strip() == a2.strip() for ln in text.splitlines()):
            return "merge 의 anchor2 는 한 줄 전체여야 한다(줄 일부를 지우지 않는다)"
    old = next(ln for ln in text.splitlines() if anchor in ln)
    if kind == "merge":
        old += " " + (op.get("anchor2") or "")
    low = check_targets.lowered(old, old.replace(anchor, new) if kind != "insert_after" else new)
    if low:
        return f"목표 하향 「{low[0]['base']}」 → 「{low[0]['new']}」 (고치기에서는 목표를 낮추지 않는다)"
    probe = "- " + new
    bad = check_internal.find_form(probe, None, allow) + check_internal.find_in_text(probe) + check_internal.find_in_text(probe, "rfp")
    if check_internal.LABEL_RX.match(probe):
        return "「라벨: 내용」 머리(S-m6)"
    if bad:
        return f"{bad[0]['name']} (T-m8·T-m5·T-m7)"
    return None


# ── md ────────────────────────────────────────────────────────────────────
def _section_of(text: str, pos: int) -> str:
    sec = ""
    for m in re.finditer(r"^#{2,4}\s+(\d(?:-\d+)?)\.\s", text[:pos], re.M):
        sec = m.group(1)
    return sec


def _reverts(before: str, after: str, op: dict, history: list[dict]) -> dict | None:
    """이 op 가 앞 수정(원장의 적용 행)을 되돌리는가. 줄 기록이 있으면 「전 줄 ↔ 후 줄」이 맞바뀌는지,
    없으면(옛 원장) anchor·new 가 맞바뀌는지 본다."""
    for r in history:
        if r.get("status") != "applied":
            continue
        if r.get("line_before") is not None and r.get("line_after") is not None:
            if before == r["line_after"].strip() and after == r["line_before"].strip() and before != after:
                return r
        elif (r.get("new") or "").strip() == (op.get("anchor") or "").strip() and \
                (r.get("anchor") or "").strip() == (op.get("new") or "").strip():
            return r
    return None


def apply_md(text: str, ops: list[dict], author: str = "", locked: dict | None = None,
             history: list[dict] | None = None, allow=()) -> tuple[str, list[dict]]:
    """locked: {줄 글: "작성자 #id"} 이번 회차에 다른 작성자가 이미 고친 줄. 그 줄을 건드리는 op 는 거부한다(한 칸 한 작성자).
    history: 원장의 이전 행. 앞 수정을 되돌리는 op 는 거부한다. (plan_t4fix 1, 2026-09-28: t4 에서 편집자가 넣은
    「(영문)」을 같은 회차 집필자가 도로 뺐고, 적용 op 11건이 뒤 작성자에게 덮어써졌다.)
    적용 행에는 고치기 전·후 줄(line_before·line_after)을 남긴다. locked 는 적용할 때마다 갱신된다."""
    rows = []
    locked = {} if locked is None else locked
    for op in ops:
        why = vet(op, text, allow)
        if op.get("op") in HWPX_OPS:
            why = why or "hwpx 전용 op(원고 md 에는 적용하지 않는다)"
        row = {k: op.get(k) for k in ("id", "check", "section", "op", "anchor", "anchor2", "new", "reason")}
        if why:
            rows.append({**row, "status": "rejected", "why": why})
            continue
        i = text.index(op["anchor"])
        row["section"] = row.get("section") or _section_of(text, i)
        lines0 = text.split("\n")
        a1 = text[:i].count("\n")
        touched = [lines0[a1]]
        if op["op"] == "merge":
            a2 = next(k for k, ln in enumerate(lines0)
                      if re.sub(r"^\s*(?:-\s+|[□○ㅇ·]\s*)", "", ln).strip() == op["anchor2"].strip())
            touched.append(lines0[a2])
        who = next((locked[ln.strip()] for ln in touched if ln.strip() in locked
                    and not locked[ln.strip()].startswith(author + " #")), None)
        if who:
            rows.append({**row, "status": "rejected", "why": f"슬롯 잠김: 이번 회차 {who} 가 고친 줄(한 칸 한 작성자)"})
            continue
        if op["op"] == "merge":
            lines = list(lines0)
            lines[a1] = lines[a1].replace(op["anchor"], op["new"].strip(), 1)
            del lines[a2]
            cand = "\n".join(lines)
            after = lines[a1 if a2 > a1 else a1 - 1]
        elif op["op"] == "replace":
            cand = text[:i] + op["new"].strip() + text[i + len(op["anchor"]):]
            after = cand.split("\n")[a1]
        else:
            s = text.rfind("\n", 0, i) + 1
            e = text.find("\n", i)
            e = len(text) if e < 0 else e
            line = text[s:e]
            if line.lstrip().startswith("|"):
                rows.append({**row, "status": "rejected", "why": "표 행 뒤에는 넣지 않는다"})
                continue
            prefix = re.match(r"^(\s*(?:-\s+)?)", line).group(1)
            if op["new"].strip().startswith("[표"):             # 표 캡션 줄은 목록 글머리 없이(F-m8)
                prefix = ""
            cand = text[:e] + "\n" + prefix + op["new"].strip() + text[e:]
            after = prefix + op["new"].strip()
        back = _reverts(touched[0].strip(), after.strip(), op, history or []) if op["op"] == "replace" else None
        if back:
            rows.append({**row, "status": "rejected",
                         "why": f"앞 수정 되돌림: r{back.get('round')} {back.get('author')} #{back.get('id')} 의 수정을 원래대로 돌린다"})
            continue
        lost = _lost(text, cand)
        if lost:
            rows.append({**row, "status": "rejected", "why": lost})
            continue
        text = cand
        before = touched[0] if op["op"] != "insert_after" else ""
        locked[after.strip()] = f"{author} #{op.get('id')}"
        rows.append({**row, "status": "applied", "why": "", "line_before": before, "line_after": after})
    return text, rows


def _lost(before: str, after: str) -> str | None:
    """C-m5 와 같은 정의로 문서 전체를 견준다: 다른 곳에 남아 있는 반복을 빼는 것(82 #23)은 허용된다."""
    res = check_preserve.compare(before, after)
    return None if res["ok"] else "보존 토큰 누락: " + check_preserve.summarize(res).replace("사라진 정보 ", "")


# ── hwpx ──────────────────────────────────────────────────────────────────
LEAF_P = re.compile(r"<hp:p\b[^>]*>(?:(?!<hp:p\b).)*?</hp:p>", re.S)


def _ptext(p: str) -> str:
    return html.unescape("".join(re.findall(r"<hp:t>([^<]*)</hp:t>", p)))


def _set_ptext(p: str, new: str) -> str:
    """문단 글을 new 로: 첫 hp:t 에 전부 넣고 나머지 hp:t 는 비운다. 줄 배치 캐시(linesegarray)는 지워 한글이 다시 잡게 한다."""
    seen = [False]

    def put(m):
        if seen[0]:
            return "<hp:t></hp:t>"
        seen[0] = True
        return "<hp:t>" + html.escape(new, quote=False) + "</hp:t>"
    p = re.sub(r"<hp:t>[^<]*</hp:t>", put, p)
    return re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", p, flags=re.S)


def _bold_headings(header: str, sec: str) -> tuple[str, str, int]:
    """장·절 제목 문단의 charPr 에 굵게가 없으면 굵은 복제본을 만들어 그 문단만 가리킨다(본문 굵기는 건드리지 않는다)."""
    blocks = {m.group(1): m.group(0) for m in re.finditer(r'<hh:charPr id="(\d+)".*?</hh:charPr>', header, re.S)}
    nxt = max(int(k) for k in blocks) + 1 if blocks else 0
    clone, added = {}, 0

    def fix_p(m):
        nonlocal nxt, header, added
        p = m.group(0)
        if not re.match(r"^\d(?:-\d+)?\.\s", _ptext(p).strip()):
            return p

        def fix_run(r):
            nonlocal nxt, header, added
            cid = r.group(1)
            blk = blocks.get(cid, "")
            if not blk or "<hh:bold" in blk:
                return r.group(0)
            if cid not in clone:
                new = re.sub(r'^<hh:charPr id="\d+"', f'<hh:charPr id="{nxt}"', blk).replace("</hh:charPr>", "<hh:bold/></hh:charPr>")
                header = header.replace(blk, blk + new, 1)
                blocks[str(nxt)] = new
                clone[cid] = str(nxt)
                nxt += 1
                added += 1
            return r.group(0).replace(f'charPrIDRef="{cid}"', f'charPrIDRef="{clone[cid]}"')
        return re.sub(r'<hp:run charPrIDRef="(\d+)"', fix_run, p)
    sec = LEAF_P.sub(fix_p, sec)
    if added:
        header = re.sub(r'(<hh:charProperties itemCnt=")(\d+)"', lambda m: m.group(1) + str(int(m.group(2)) + added) + '"', header)
    return header, sec, added


def apply_hwpx(src: str, out: str, ops: list[dict]) -> list[dict]:
    with zipfile.ZipFile(src) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    files = {i.filename: d for i, d in items}
    sname = "Contents/section0.xml"
    sec = files[sname].decode("utf-8")
    header = files["Contents/header.xml"].decode("utf-8")
    rows = []
    for op in ops:
        row = {k: op.get(k) for k in ("id", "check", "section", "op", "anchor", "anchor2", "new", "reason")}
        kind = op.get("op")
        if kind == "heading_bold":
            header, sec, n = _bold_headings(header, sec)
            rows.append({**row, "status": "applied", "why": f"굵은 charPr {n}개 추가"})
            continue
        if kind == "border_solid":
            before = header
            header = re.sub(r'(<hh:(?:left|right|top|bottom)Border\b[^>]*\btype=")(?!NONE")(?!SOLID")[A-Z_]+(")', r"\1SOLID\2", header)
            rows.append({**row, "status": "applied", "why": "표 선 SOLID" + ("" if before != header else " (바뀐 것 없음)")})
            continue
        paras = list(LEAF_P.finditer(sec))
        flat = "\n".join(_ptext(m.group(0)) for m in paras)
        why = vet(op, flat)
        if why:
            rows.append({**row, "status": "rejected", "why": why})
            continue
        hit = next(m for m in paras if op["anchor"] in _ptext(m.group(0)))
        p = hit.group(0)
        t = _ptext(p)
        if kind in ("replace", "merge"):
            newp = _set_ptext(p, t.replace(op["anchor"], op["new"].strip(), 1))
            cand = sec[:hit.start()] + newp + sec[hit.end():]
            if kind == "merge":
                strip = lambda x: re.sub(r"^\s*(?:-\s+|[□○ㅇ·]\s*)", "", x).strip()
                m2 = next(m for m in LEAF_P.finditer(sec)
                          if m.start() != hit.start() and strip(_ptext(m.group(0))) == op["anchor2"].strip())
                shift = len(newp) - len(p) if m2.start() > hit.start() else 0
                cand = cand[:m2.start() + shift] + cand[m2.end() + shift:]
        else:
            mark = re.match(r"^([□○ㅇ\-·]\s*)", t)
            body = op["new"].strip()
            if mark and not body.startswith(mark.group(1).strip()) and not body.startswith("[표"):
                body = mark.group(1) + body
            ids = [int(x) for x in re.findall(r'<hp:p\b[^>]*?\bid="(\d+)"', sec)]
            newp = re.sub(r'(<hp:p\b[^>]*?\bid=")\d+"', lambda m: m.group(1) + f'{(max(ids) + 1) if ids else 0}"',
                          _set_ptext(p, body), count=1)
            cand = sec[:hit.end()] + newp + sec[hit.end():]
        lost = _lost(flat, "\n".join(_ptext(m.group(0)) for m in LEAF_P.finditer(cand)))
        if lost:
            rows.append({**row, "status": "rejected", "why": lost})
            continue
        sec = cand
        rows.append({**row, "status": "applied", "why": ""})
    files[sname] = sec.encode("utf-8")
    files["Contents/header.xml"] = header.encode("utf-8")
    with zipfile.ZipFile(out, "w") as zo:
        for info, _ in items:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_STORED if info.filename == "mimetype" else zipfile.ZIP_DEFLATED
            zo.writestr(zi, files[info.filename])
    return rows


# ── 원장 ──────────────────────────────────────────────────────────────────
def write_ledger(path: str, rows: list[dict], round_no, author: str) -> list[dict]:
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    for r in rows:
        old.append({"round": round_no, "author": author, **r})
    return save_ledger(path, old)


def save_ledger(path: str, old: list[dict]) -> list[dict]:
    """원장 JSON 전체를 쓰고 같은 이름 .md 표를 다시 만든다(trim·adopt 가 상태를 「되돌림」으로 바꾼 뒤에도 부른다)."""
    json.dump(old, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cell = lambda s: (s or "").replace("|", "／").replace("\n", " ")[:120]
    L = ["# 수정 원장 (edit_apply.py, 자동 생성)", "",
         "| # | 회차 | 작성자 | 체크 | 절 | op | 전 | 후 | 판정 |", "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(old, 1):
        verdict = "적용" if r["status"] == "applied" else ("되돌림" if r["status"] == "reverted" else "거부: " + cell(r.get("why")))
        L.append(f"| {i} | {r.get('round')} | {r.get('author')} | {r.get('check') or ''} | {r.get('section') or ''} | {r.get('op')} | "
                 f"{cell(r.get('anchor'))} | {cell(r.get('new'))} | {verdict} |")
    open(os.path.splitext(path)[0] + ".md", "w", encoding="utf-8").write("\n".join(L) + "\n")
    return old


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--md")
    ap.add_argument("--hwpx")
    ap.add_argument("--out")
    ap.add_argument("--edits", nargs="+", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--round", default=None)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if bool(a.md) == bool(a.hwpx) or (a.hwpx and not a.out):
        ap.error("--md 하나, 또는 --hwpx 와 --out")
    rejected = 0
    if a.md:
        text = open(a.md, encoding="utf-8").read()
        locked = {}
        history = json.load(open(a.ledger, encoding="utf-8")) if a.ledger and os.path.exists(a.ledger) else []
        for ep in a.edits:
            author, ops = load_edits(ep)
            text, rows = apply_md(text, ops, author, locked, history)
            rejected += sum(r["status"] == "rejected" for r in rows)
            if not a.dry:
                write_ledger(a.ledger, rows, a.round, author)
            for r in rows:
                print(f"  [{'적용' if r['status'] == 'applied' else '거부'}] {author} {r.get('id') or ''} {r.get('check') or ''} "
                      f"{r.get('op')}: {(r.get('anchor') or '')[:40]}" + (f"  ← {r['why']}" if r["why"] else ""))
        if not a.dry:
            open(a.md, "w", encoding="utf-8").write(text)
    else:
        src = a.hwpx
        for k, ep in enumerate(a.edits):
            author, ops = load_edits(ep)
            rows = apply_hwpx(src, a.out, ops)
            src = a.out
            rejected += sum(r["status"] == "rejected" for r in rows)
            if not a.dry:
                write_ledger(a.ledger, rows, a.round, author)
            for r in rows:
                print(f"  [{'적용' if r['status'] == 'applied' else '거부'}] {author} {r.get('id') or ''} {r.get('op')}: "
                      f"{(r.get('anchor') or '')[:40]}" + (f"  ← {r['why']}" if r["why"] else ""))
    print(("PASS" if not rejected else "PARTIAL") + f": 거부 {rejected}건")
    return 3 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
