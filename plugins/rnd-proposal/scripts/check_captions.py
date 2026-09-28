# -*- coding: utf-8 -*-
"""표 캡션 체계 검사 (rubric F-m8, plan_v2 2026-09-28).

80_비교검증 퇴행 (a) 8: t3 는 [표 A]·[표 B] 두 개만 캡션이 있고 표 4개가 캡션 없이 들어갔다.
외부 원본은 [표 1]~[표 5] 가 연속이었고, 블라인드 두 심판 모두 이 차이를 양식 판정 근거로 들었다.

    python check_captions.py --md <30_proposal.build.md>
    python check_captions.py --hwpx <out.hwpx>

규칙:
  1) 요약문(0절) 표 밖의 모든 표 바로 위(빈 줄·안내 줄 1줄까지)에 `[표 n] 캡션` 이 있다.
  2) n 은 아라비아 숫자이고 1부터 빠짐·중복 없이 문서 순서대로 이어진다.
  3) 본문의 「표 n」 언급은 있는 번호를 가리킨다.
hwpx 는 hwpx_text 로 원고 md 꼴로 되돌려 같은 함수로 본다. 0 이면 exit 0, 하나라도 있으면 exit 2.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CAP_RX = re.compile(r"^\[표\s*([^\]]*)\]\s*(.*)$")
REF_RX = re.compile(r"(?<![\[\w])표\s*(\d+)(?=[의에를은는과와,.\s)])")


def _blocks(text: str):
    """(표 시작 줄 번호, 소속 절 id, 위쪽 캡션 원문 또는 None) 을 문서 순서대로."""
    lines = text.splitlines()
    sec, out, i = "", [], 0
    while i < len(lines):
        ln = lines[i]
        h = re.match(r"^#{2,4}\s+(\d(?:-\d+)?)\.\s", ln)
        if h:
            sec = h.group(1)
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-{3}", lines[i + 1]):
            cap, j, seen = None, i - 1, 0
            while j >= 0 and seen < 2:
                s = lines[j].strip()
                if s:
                    seen += 1
                    if CAP_RX.match(s):
                        cap = s
                        break
                    if s.startswith("#") or s.startswith("|"):
                        break
                j -= 1
            out.append((i + 1, sec, cap))
            while i < len(lines) and lines[i].startswith("|"):
                i += 1
            continue
        i += 1
    return out


def check_text(text: str) -> tuple[bool, list[str], list[str]]:
    """반환: (ok, 문제 목록, 문제가 난 절 id 목록)."""
    probs, secs, nums = [], [], []
    for line, sec, cap in _blocks(text):
        if sec == "0":
            continue                    # 요약문 표는 양식 blueprint 라 캡션을 달지 않는다
        if not cap:
            probs.append(f"{sec}절 {line}행 표에 캡션 없음")
            secs.append(sec)
            continue
        n = CAP_RX.match(cap).group(1).strip()
        if not n.isdigit():
            probs.append(f"{sec}절 캡션 번호가 숫자가 아님: {cap[:30]}")
            secs.append(sec)
            continue
        nums.append(int(n))
    if nums and nums != list(range(1, len(nums) + 1)):
        probs.append(f"캡션 번호가 1부터 이어지지 않음: {nums}")
    for m in REF_RX.finditer(text):
        if int(m.group(1)) not in nums:
            probs.append(f"본문 「표 {m.group(1)}」 언급이 없는 번호를 가리킴")
    return (not probs), probs, sorted(set(secs))


def renumber(text: str) -> tuple[str, list[tuple[str, str]]]:
    """캡션 번호를 문서 순서대로 1부터 다시 매긴다(결정적). 집필자는 절만 보므로 번호를 모른다: `[표 ?] 제목` 으로 쓰면 된다.
    숫자였던 옛 번호를 가리키는 본문 「표 n」 언급도 새 번호로 바꾼다. 반환: (새 텍스트, [(옛 캡션, 새 캡션)])."""
    lines = text.splitlines(keepends=True)
    changes, remap, k = [], {}, 0
    caps = {}
    for line, sec, cap in _blocks(text):
        if sec == "0" or not cap:
            continue
        k += 1
        old = CAP_RX.match(cap).group(1).strip()
        if old != str(k):
            caps[cap] = CAP_RX.sub(lambda m: f"[표 {k}] {m.group(2)}".rstrip(), cap, count=1)
            if old.isdigit():
                remap[old] = str(k)
    for i, ln in enumerate(lines):
        body = ln.rstrip("\r\n")
        if body.strip() in caps:
            new = caps[body.strip()]
            changes.append((body.strip(), new))
            lines[i] = ln.replace(body.strip(), new, 1)
        elif remap and not ln.lstrip().startswith("["):
            lines[i] = REF_RX.sub(lambda m: m.group(0).replace(m.group(1), remap.get(m.group(1), m.group(1))), ln)
    return "".join(lines), changes


def check_hwpx(path: str):
    from hwpx_text import hwpx_to_md
    return check_text(hwpx_to_md(path))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--md")
    ap.add_argument("--hwpx")
    a = ap.parse_args()
    if not (a.md or a.hwpx):
        ap.error("--md 또는 --hwpx")
    ok, probs, _ = check_hwpx(a.hwpx) if a.hwpx else check_text(open(a.md, encoding="utf-8").read())
    for p in probs:
        print("  " + p)
    print(("PASS" if ok else "FAIL") + f": 표 캡션 체계 (문제 {len(probs)}건)")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
