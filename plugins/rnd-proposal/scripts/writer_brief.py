# -*- coding: utf-8 -*-
"""집필 에이전트(rp-writer) 입력 묶음: 절 하나에 필요한 것만 한 파일로 (2026-09-27, 재설계 3단계).

    python $CLAUDE_PLUGIN_ROOT/scripts/writer_brief.py --run <workspace/run> --section 1-3 \
        --rubric criteria/rubric.yaml [--spec <run>/20_spec.md] [--evidence evidence/.../_ws] \
        [--mode submission|final] [--fix] [--out <run>/briefs/brief_1-3.md]

집필 에이전트는 이 파일 **하나**만 읽는다. 들어가는 것:
  ① 절 정보: 50_form_spec.json outline 의 제목·guide·blueprint(리드·슬롯·표 골격)·special
  ② 설계서 발췌: 20_spec.md 에서 이 절에 해당하는 표(§6 절 배정표 기준)
  ③ 이 절에 적용되는 rubric 체크: applies_to 에 이 절 또는 * 가 있는 것 전부(체크 문장 그대로)
  ④ 근거: 15_axis_conflicts.md B-1 고정 · B-2 금지 · B-3 조건부, blueprint 슬롯이 가리키는 대장 key 행
  ⑤ (--fix) 직전 채점에서 이 절이 실패한 체크 id·사유 (70_judge.json · 70_machine.json)
  ⑥ 현재 원고의 이 절 본문 (있으면)
  ⓪ 이 절이 반드시 담을 것: rubric `requires` 가 이 절에 배정한 항목·검사가 받는 형식·값 (①보다 앞)

사용자 답(16_user_answers.md)은 값만 싣는다. 출처·파일명 같은 작업용 표기는 brief 에 넣지 않는다(t1 결함 2026-09-27).

금지·교훈 규칙은 여기 없다. 그것은 검사기(check_rubric)와 채점 에이전트(rp-scorer)가 본다.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys


def load_rubric(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def outline_node(spec: dict, sid: str) -> dict | None:
    for n in spec.get("outline") or []:
        if n.get("id") == sid:
            return n
    return None


def section_text(md: str, sid: str, title: str) -> str:
    """원고에서 이 절의 본문(제목 다음 줄부터 다음 제목 전까지)."""
    if not md:
        return ""
    pat = re.compile(r"^#{2,4}\s+" + re.escape(title) + r"\s*$", re.M)
    m = pat.search(md)
    if not m:
        return ""
    rest = md[m.end():]
    n = re.search(r"^#{2,4}\s+\S", rest, re.M)
    return rest[: n.start()].strip("\n") if n else rest.strip("\n")


def section_chars(text: str) -> int:
    """분량 원단위: 공백 제외·표 포함 글자 수(page_budget.chars_per_page 와 같은 셈)."""
    return len(re.sub(r"\s", "", text))


def section_budget(spec: dict, md: str, sid: str) -> dict | None:
    """절 분량 예산. 장 배분 쪽수 × chars_per_page 를 그 장의 절들이 현재 분량 비율로 나눈다(절 예산의 합 = 장 예산).
    원고가 없으면 균등하게 나눈다. page_budget.chapters 에 그 장이 없으면 None."""
    pb = spec.get("page_budget") or {}
    chap = sid.split("-")[0]
    pages = (pb.get("chapters") or {}).get(chap)
    if not pages:
        return None
    unit = float(pb.get("chars_per_page") or 725)
    budget = float(pages) * unit
    ids = [n["id"] for n in spec.get("outline") or [] if n["id"].split("-")[0] == chap and (n.get("guide") or n.get("blueprint"))]
    ids = ids or [sid]
    cur = {s: section_chars(section_text(md, s, (outline_node(spec, s) or {}).get("title", ""))) for s in ids}
    now = sum(cur.values())
    target = round(budget * cur.get(sid, 0) / now) if now and cur.get(sid) else round(budget / len(ids))
    return {"chapter": chap, "pages": pages, "unit": unit, "chapter_budget": round(budget), "chapter_now": now,
            "sections": len(ids), "current": cur.get(sid, 0), "target": target}


def spec_sections(spec_md: str) -> dict[str, str]:
    """20_spec.md 를 `## N.` 절 번호로 나눈다."""
    out = {}
    parts = re.split(r"^## (\d+)\.\s*", spec_md, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1]
        body = re.split(r"^## (?!\d+\.)", body, maxsplit=1, flags=re.M)[0]   # 「## 승인 기록」 같은 번호 없는 절은 뺀다
        out[parts[i]] = body.strip()
    return out


# judge 체크 → 설계서 절
SPEC_FOR_CHECK = {"L-j1": ["1"], "L-j2": ["1", "2"], "L-j3": ["5"], "L-j4": ["3"], "L-j5": ["4"],
                  "L-j7": ["2"], "C-j4": ["1"], "L-f1": ["7"], "T-f1": ["7"], "T-f2": ["7"]}


# 집필자가 문장으로 좌우할 수 있는 machine 검사기. 조립·서식 검사(줄간격·글자 크기·테두리·쪽수·골격)는
# 집필자 몫이 아니라 brief 에 넣지 않는다: 그 규칙을 외우게 하지 않는 것이 이 재설계의 요점이다.
WRITER_RUNNERS = ("check_wording", "check_numbers", "check_internal", "check_captions", "check_blank", "check_preserve")
WRITER_IMPLS = {"check_rubric:R2", "check_rubric:R3", "check_rubric:R4", "check_rubric:R5",
                "check_rubric:R6", "check_rubric:R7", "check_rubric:C-m4", "check_rubric:B-m2",
                "check_rubric:S-m4"}                      # R1(줄간격)은 조립 몫


def checks_for(rubric: dict, sid: str, mode: str, writer_only: bool = True):
    rows = []
    for item, cfg in (rubric.get("items") or {}).items():
        for tier in ("floor", "ceiling"):
            for c in cfg.get(tier) or []:
                if c.get("mode") and c["mode"] != mode:
                    continue
                ap = c.get("applies_to") or ["*"]
                if not (sid in ap or "*" in ap):
                    continue
                if writer_only and c.get("by") == "machine" and sid not in ap:
                    impl = c.get("impl") or []
                    impl = [impl] if isinstance(impl, str) else impl
                    if not any(str(i) in WRITER_IMPLS or str(i).split(":")[0] in WRITER_RUNNERS
                               for i in impl):
                        continue
                rows.append((item, tier, c, "*" in ap and sid not in ap))
    return rows


def evidence_blocks(evidence_dir: str | None, keys: list[str]) -> tuple[str, str, str]:
    """(B-1/B-2/B-3 원문, 대장 key 행, 사용자 답 값)"""
    if not evidence_dir or not os.path.isdir(evidence_dir):
        return "", "", ""
    rules = ""
    ax = os.path.join(evidence_dir, "15_axis_conflicts.md")
    if os.path.exists(ax):
        t = open(ax, encoding="utf-8").read()
        m = re.search(r"^# B\. .*?(?=^# |\Z)", t, re.M | re.S)
        rules = m.group(0).strip() if m else ""
    keyrows, answers = [], []
    ua = os.path.join(evidence_dir, "16_user_answers.md")
    if os.path.exists(ua):                                   # 시작 질문의 사용자 답: 절과 무관하게 전부, 값만 싣는다
        for ln in open(ua, encoding="utf-8").read().splitlines():
            m = re.match(r"^\|\s*([A-Z][A-Z0-9_]{2,})\s*\|([^|]*)\|([^|]*)\|", ln)
            if m:                                            # 옛 대장(t1)은 값 칸에도 꼬리표가 있다: 여기서도 걷는다
                answers.append(f"- {m.group(1)}: {_clean_answer(m.group(2))} {m.group(3).strip()}".rstrip())
    if keys:
        for f in sorted(glob.glob(os.path.join(evidence_dir, "*.md"))):
            if os.path.basename(f) == "16_user_answers.md":
                continue
            for ln in open(f, encoding="utf-8").read().splitlines():
                if any(re.search(rf"\b{re.escape(k)}\b", ln) for k in keys) and ln.startswith("|"):
                    keyrows.append(strip_paths(ln.strip()))     # 파일명 접두·출처 칸의 파일 경로를 싣지 않는다
    return rules, "\n".join(dict.fromkeys(keyrows)), "\n".join(answers)


# 대장 출처 칸의 작업 파일 경로(「`00_rfp_selected.md §1`」「10_project_title.md:38」)는 원고로 새면 T-m5 실패다.
PATH_TOKEN = re.compile(r"`?[\w\-/]+\.(?:md|json|ya?ml|py|hwpx)(?::[\w\-]+)?`?\s*")


def strip_paths(s: str) -> str:
    return PATH_TOKEN.sub("", s)


def _clean_answer(v: str) -> str:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rp_run
    return rp_run.clean_answer(v)


def required_block(run: str, sid: str, rubric: dict, spec: dict, evidence_dir: str | None, mode: str) -> list[str]:
    """⓪ rubric requires 가 이 절에 배정한 필수 요소 (t1 결함 2026-09-27: 0절 과제명·연구기간, R3 모델 구성·상태영역)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import check_rubric as _cr
    import rp_run as _rr
    have = _rr.ledger_keys(evidence_dir)
    title = _rr.frontmatter(run).get("title", "")
    rows, table = [], False
    for _, _, c in _cr.iter_checks(rubric, mode):
        if c.get("by") != "machine" or not c.get("requires"):
            continue
        for r in _cr.required_elements(c, spec):
            if r["section"] != sid:
                continue
            table = table or r["form"].startswith("요약문 표")
            vals = [title if k == "@title" else _clean_answer(have.get(k, "")) for k in r["keys"]]
            if r["keys"] and all(vals):
                val = " → ".join(vals)
            elif r["keys"]:
                val = "값 없음: 값 없이 성립하는 문장으로 쓴다(지어내지 않는다)"
            else:
                val = "설계서·근거에서 찾는다"
            rows.append(f"| {c['id']} | {r['item']} | {r['form']} | {val} |")
    if not rows:
        return []
    L = ["## ⓪ 이 절이 반드시 담을 것 (기계 검사가 이 형식으로 찾는다: 빠지면 floor 실패)"]
    if table:
        L.append("이 절은 **표 하나로** 쓴다(목록 금지). 아래 칸 이름을 표 첫 열에 그대로 쓴다.")
    L += ["", "| 체크 | 항목 | 검사가 받는 형식 | 값 |", "|---|---|---|---|"] + rows + [""]
    return L


def failures_for(run: str, sid: str, rubric: dict, mode: str, only: set | None = None) -> list[str]:
    """only: 체크 id 집합: 주면 그 id 만, 판정 절과 무관하게 넣는다(문서 전체 체크를 여러 절에서 나눠 고칠 때)."""
    out = []
    jp = os.path.join(run, "70_judge.json")
    if os.path.exists(jp):
        j = json.load(open(jp, encoding="utf-8")).get("judgments") or {}
        for cid, v in j.items():
            if v.get("ok"):
                continue
            secs = str(v.get("section") or "")
            ap = next((c.get("applies_to") or [] for _, _, c, _ in checks_for(rubric, sid, mode) if c["id"] == cid), None)
            if ap is None:
                continue
            # 절 지정 체크(applies_to 에 이 절)는 판정 절이 달라도 넣는다: 사슬은 두 절에 걸친다(L-j1: 1-3↔3-1).
            # 문서 전체(*) 체크는 채점자가 이 절을 가장 약한 절로 찍었을 때만.
            if only is not None and cid not in only:
                continue
            if only is not None or sid in ap or sid in secs:
                out.append(f"{cid} (judge, 판정 절 {secs}): {v.get('why', '')}".rstrip(": ")
                           + (f"  인용 「{v['quote']}」" if v.get("quote") else ""))
    mp = os.path.join(run, "70_machine.json")
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8")).get("checks") or {}
        for cid, v in m.items():
            if v.get("ok") is False and v.get("severity") != "warn" and (only is None or cid in only):
                ap = next((c.get("applies_to") or [] for _, _, c, _ in checks_for(rubric, sid, mode) if c["id"] == cid), None)
                if ap is not None:
                    out.append(f"{cid} (machine): {v.get('detail', '')[:200]}")
    return out


def _nodash(s: str) -> str:
    """brief 에 실리는 인용문(설계서·근거팩)의 대시류를 치환한다. 원본 파일은 손대지 않는다(근거팩 동결)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import dash_replace
    return dash_replace.replace_text(s)[0]


def build(run: str, sid: str, rubric_path: str, spec_path: str | None, evidence_dir: str | None,
          mode: str, fix: bool, only: set | None = None) -> str:
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    rubric = load_rubric(rubric_path)
    node = outline_node(spec, sid)
    if node is None:
        raise SystemExit(f"50_form_spec.json outline 에 절 {sid} 가 없다")
    md_path = os.path.join(run, "30_proposal.md")
    md = open(md_path, encoding="utf-8").read() if os.path.exists(md_path) else ""

    L = []
    L.append(f"# 집필 지시: 절 {sid} {node['title']}  (mode: {mode})")
    L.append("")
    L.append("이 파일에 있는 것만으로 이 절을 쓴다. 표에 없는 주장·근거에 없는 수치는 넣지 않는다. "
             "값이 없으면 값 없이 성립하는 문장으로 쓴다(「추후 확정」 금지).")
    L.append("")
    L += required_block(run, sid, rubric, spec, evidence_dir, mode)
    # ① 절 정보
    L.append("## ① 절 정보 (50_form_spec.json)")
    if node.get("guide"):
        L.append("양식 안내문(이 절에 들어가야 하는 항목: F-j1 이 칸별로 대조한다):")
        L += [f"- {g}" for g in node["guide"]]
    if node.get("probes"):
        L.append("게이트 확인 낱말(F-3): " + " · ".join(p["key"] for p in node["probes"]))
    if node.get("special"):
        L.append("지정 서식: " + " · ".join(s if isinstance(s, str) else f"{s['key']}({s.get('severity','fail')})" for s in node["special"]))
    keys = []
    if node.get("blueprint"):
        L.append("")
        # ★ plan_v2 5단계 17 (2026-09-28): 슬롯 문구를 「이 항목에 담을 내용」으로만 준다.
        #   예전 brief 는 「슬롯은 아래 문구로 시작」과 slot_rule 「슬롯 문구: 값(출처)」로 작성 요령 문구를 본문 라벨로
        #   찍게 했다(t3 불릿 59/72 가 라벨, 「문제 정의 한 줄:」「확장 방향 2~3개:」). F-11 은 리드만 축자 대조하고
        #   슬롯은 개수만 본다(2026-09-14 패치). 리드도 콜론 뒤 안내 꼬리(「시장 규모: 세계·국내」)를 떼고 준다.
        L.append("골격(F-11 이 리드만 축자 대조한다. 리드 줄은 아래 굵은 문구 그대로 쓰고, 그 아래 항목은 「담을 내용」을 "
                 "문장으로 쓴다. 담을 내용의 문구를 본문에 옮겨 적거나 「문구: 내용」 머리를 붙이지 않는다: S-m6·T-m8):")
        for bp in node["blueprint"]:
            lead = re.split(r"\s*[:：]\s*", bp["lead"], maxsplit=1)[0]
            L.append(f"- **{lead}**")
            if bp.get("table"):
                L.append(f"  - ※ 표: {bp['table']}")
            for s in bp.get("slots") or []:
                k = s.get("key")
                if k:
                    keys.append(k)
                L.append(f"  - 담을 내용: {s['text']}" + (f"  ⟵ 대장 `{k}` 의 값·출처" if k else ""))
    ws = spec.get("writing_style") or {}
    L.append("")
    L.append(f"서술 형식: 개조식 · 마크다운 목록 2단계(`- 리드` / `  - 항목`) · 명사형 종결({', '.join(ws.get('preferred_endings', [])[:6])}) · "
             f"항목 한 줄 {ws.get('max_item_chars', 160)}자 이내 · 굵기·글머리 문자 직접 입력 금지 · 표는 마크다운 표(캡션 `[표 N] 제목` 표 위 한 줄, "
             "N 은 1부터 문서 전체에서 이어지는 숫자: F-m8)")
    L.append("항목 규칙: 한 항목은 사실 하나를 담은 문장 하나(근거 1개 이상, 출처는 끝 괄호). 「라벨: 내용」 꼴로 쓰지 않는다(S-m6). "
             "내용을 절 번호로 가리키지 않는다(「1-3의」「2-2 목표임」 금지: 필요한 사실을 그 자리에 짧게 다시 쓴다. T-m8).")
    L.append("문장 부호: 부연은 괄호로, 구분은 콜론으로, 범위는 ~로, 0 을 뜻하는 칸(기준값·실적 등)은 「0」으로, 값이 존재하지 않는 칸만 「해당 없음」으로 쓴다(C-m6). "
             "대시류 문자(U+2012~U+2015)는 어떤 자리에도 쓰지 않는다(검사기 S-m5·check_dash).")
    L.append("출처 표기: 공고 요구사항은 내용으로 반영하되 공고문 절 번호(「§3.1」)와 「RFP」라는 말은 본문·표에 쓰지 않는다. "
             "출처는 표의 출처 칸에 외부 출처(Google Patents·KHARN 등)만 적는다(검사기 T-m7). "
             "아래 설계서·근거에 적힌 「RFP §」·「§8 #2」·「KPI 1」·절 번호(「2-2 목표」)·「본 조사 범위」 같은 추적 표시는 작업용이다(근거팩 고정 표현 F10·F12 처럼 「본 조사 범위에서 …」가 고정 문구 전체로 들어간 문장만 예외: T-m8 이 허용한다): "
             "옮겨 쓰지 않는다(T-m7·T-m8). 가리키는 내용을 문장으로 쓴다.")
    # ★ plan_v2 5단계 16 (2026-09-28): 사람이 다듬은 제출본에서 고른 문장 틀(고유명사·수치를 가림).
    #   내용이 아니라 문장 구성의 기준이다. 원본과 8어절 이상 같으면 S-m7(check_copy) 실패.
    sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "rp-run", "style_patterns.md")
    if os.path.exists(sp):
        body = open(sp, encoding="utf-8").read().split("\n", 1)[1].strip()
        L.append("")
        L.append("문장 구성 예시(내용이 아니라 문장 구성의 기준. 〔 〕 자리는 이 절의 값으로 채우고, 틀의 말도 내 문장으로 바꿔 쓴다: S-m7):")
        L += [re.sub(r"^## ", "### ", ln) for ln in body.splitlines()]
    # ★ 분량: 시범 집필(2026-09-27)에서 1-3 절이 9슬롯 486자 → 19슬롯 1,934자로 네 배가 됐다.
    #   쪽수 상한은 hwpx 실측(F-m3)이 잡지만, 그때는 늦다. 절 단위 분량을 여기서 준다.
    # ★ 원단위는 **표를 포함한** 글자수/쪽이다 (실측 2026-09-27: 10쪽 제출본 7,254자 → 725자/쪽.
    #   「산문 1,000자/쪽」으로 주었더니 재집필본이 14,138자·16쪽이 됐다). 명세 page_budget.chars_per_page 가 우선.
    bud = section_budget(spec, md, sid)
    cur_txt = section_text(md, sid, node["title"])
    cur_slots = len(re.findall(r"^\s{2}-\s", cur_txt, re.M))
    if bud and not fix:                                        # 수정 회차는 ⑤ 「분량 예산」이 상한을 준다
        L.append(f"분량: {bud['chapter']}장 배분 {bud['pages']}쪽 × {bud['unit']:g}자/쪽(표 포함) = {bud['chapter_budget']:,}자를 절 {bud['sections']}개가 나눈다. "
                 + (f"현재 이 절 {bud['current']:,}자(표 포함)·슬롯 {cur_slots}개, {bud['chapter']}장 전체 {bud['chapter_now']:,}자. " if cur_txt else "")
                 + f"**이 절 목표 {bud['target']:,}자(±10%)**"
                 + (f": {bud['current'] - bud['target']:,}자를 줄여야 한다. 표 셀·슬롯 모두 줄인다." if bud['current'] > bud['target'] * 1.1 else "")
                 + " 슬롯은 사실 하나에 한 줄이다. 체크를 만족시키려고 슬롯을 늘리지 않는다: 한 슬롯이 체크 하나를 짧게 만족시키면 된다.")
    # ② 설계서
    L.append("")
    L.append("## ② 설계서 발췌 (20_spec.md)")
    if spec_path and os.path.exists(spec_path):
        ss = spec_sections(strip_paths(_nodash(open(spec_path, encoding="utf-8").read())))
        want = {"1", "6"}
        for _, _, c, _ in checks_for(rubric, sid, mode):
            want |= set(SPEC_FOR_CHECK.get(c["id"], []))
        if mode != "final":
            want.discard("7")
        if "6" in ss:
            rows = [ln for ln in ss["6"].splitlines() if ln.startswith("|") and f"| {sid} " in ln]
            L.append("절 배정(§6): " + (" ".join(rows) if rows else "(이 절의 배정 행 없음)"))
        for n in sorted(want, key=int):
            if n in ss and n != "6":
                L.append(f"### 설계서 §{n}")
                L.append(ss[n])
        if "8" in ss:
            L.append("### 설계서 §8 미확정 목록: 이 항목들은 값 없이 쓴다 (단, ④ 신청자 확정값에 SPEC8_N 답이 있는 항목은 그 값을 쓴다)")
            L.append(ss["8"])
    else:
        L.append("(설계서 없음: 20_spec.md 가 승인되기 전에는 집필하지 않는다)")
    # ③ rubric
    L.append("")
    L.append("## ③ 이 절에서 채점되는 체크 (criteria/rubric.yaml)")
    L.append("machine 은 검사기가, judge 는 채점 에이전트가 문장 인용으로 판정한다. 체크 문장을 그대로 만족시키는 문장이 이 절에 있어야 한다.")
    L.append("")
    L.append("| id | 항목 | 층 | 판정 | 체크 | 비고 |")
    L.append("|---|---|---|---|---|---|")
    for item, tier, c, global_ in checks_for(rubric, sid, mode):
        note = c.get("hint") or ("문서 전체 공통" if global_ else "")
        L.append(f"| {c['id']} | {item} | {tier} | {c.get('by')} | {c['check']} | {note} |")
    # ④ 근거
    L.append("")
    L.append("## ④ 근거")
    rules, keyrows, answers = evidence_blocks(evidence_dir, keys)
    rules, keyrows, answers = _nodash(rules), _nodash(keyrows), _nodash(answers)
    if "SPEC8_" in answers:                                    # §8 에서 온 답은 key 만으로 뜻을 모른다: 물은 항목을 붙인다
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import rp_run as _rr
        asks = {q["key"]: q["ask"].replace("[floor] ", "") for q in _rr.read_questions(run)}
        answers = re.sub(r"^- (SPEC8_\d+):", lambda m: f"- {m.group(1)} 「{asks.get(m.group(1), '')}」:", answers, flags=re.M)
    if answers:
        L.append("### 신청자 확정값 (출처 괄호 없이 값만 쓴다: 이 값의 출처 표기는 원고에 넣지 않는다)")
        L.append(answers)
    if keyrows:
        L.append("### 이 절 슬롯이 가리키는 대장 key 행 (값·출처를 여기서 인용한다. key 이름은 원고에 쓰지 않는다)")
        L.append(keyrows)
    if rules:
        L.append("### 고정·금지·조건부 표현 (15_axis_conflicts.md §B: 그대로 구속한다)")
        L.append(rules)
    if not (rules or keyrows or answers):
        L.append(f"(근거 디렉터리 없음 또는 해당 행 없음: {evidence_dir})")
    # ⑤ fix
    if fix:
        L.append("")
        L.append("## ⑤ 직전 채점에서 이 절이 실패한 체크: 이것만 고친다")
        # ★ 분량 우선 (t2 2026-09-27): 1-3 이 L-j1 을 맞추려 한계 슬롯을 반복해 477자 목표에서 1,053자가 됐고,
        #   쪽수 floor(F-m3)가 두 회차 연속 실패해 멈췄다. judge 체크보다 floor 를 먼저 지킨다.
        if bud:
            over = bud["current"] - bud["target"]
            L += ["### 분량 예산 (floor 우선: 쪽수 F-m3 를 깨지 않는다)",
                  f"- 이 절 현재 **{bud['current']:,}자** · 상한 **{bud['target']:,}자** (공백 제외·표 포함. "
                  f"{bud['chapter']}장 예산 {bud['chapter_budget']:,}자 = {bud['pages']}쪽 × {bud['unit']:g}자, 장 현재 {bud['chapter_now']:,}자를 절 분량 비율로 나눈 몫) → "
                  + (f"**{over:,}자 초과: 체크를 고치기 전에 먼저 줄인다**" if over > 0 else f"여유 {-over:,}자"),
                  "- 고친 뒤에도 상한을 넘기지 않는다. 새 문장 추가(insert_after)보다 기존 문장 교체(replace)를, "
                  "같은 뜻 두 항목은 합치기(merge: 두 항목의 수치·출처를 한 문장에 모두 담는다)를 먼저 쓴다. 문장을 지우는 op 는 없다.",
                  "- 장 예산을 넘으면 스킬이 `rp_run.py trim` 으로 이번 회차에 **새로 넣은 문장부터** 되돌린다(원래 정보는 줄이지 않는다). "
                  "그러니 체크 하나에 추가 문장 하나를 넘기지 않는다. judge 체크를 추가 없이 못 고치면 포기하고 보고한다. "
                  "floor(machine) 체크는 포기하지 않는다.",
                  ""]
        fails = failures_for(run, sid, rubric, mode, only)
        sp_ = os.path.join(run, "70_score.json")
        if os.path.exists(sp_):                                  # 미충족(답 없는 needs) 체크는 집필로 못 넘는다: ⑤에서 뺀다
            unmet = set((json.load(open(sp_, encoding="utf-8")).get("unmet") or {}).keys())
            fails = [f for f in fails if f.split(" ")[0] not in unmet]
        L += [f"- {f}" for f in fails] or ["- (없음)"]
        # R4(B-m1)·R5(S-m1) 는 문서 전체 검사라 어느 절의 어느 문장인지 여기서 찍어 준다.
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import check_rubric as _cr
            title = node["title"]
            pairs = [(a, b, ph, sa, sb) for a, b, ph, sa, sb in _cr.r4_pairs(md) if title in (a, b)]
            if pairs:
                L.append("- B-m1 (R4) 이 절과 다른 절이 4낱말 이상 겹치는 슬롯: 겹치는 사실은 **한 절에만** 남기고(절 배정표 §6 기준) 이 절에서는 그 문장을 빼거나 다른 사실로 바꾼다:")
                for a, b, ph, sa, sb in pairs[:12]:
                    other = b if a == title else a
                    mine = sa if a == title else sb
                    L.append(f"  - ↔ {other}: 겹침 「{ph}」 · 이 절 슬롯 「{mine[:70]}…」")
            items = [(t, why) for sec, t, why in _cr.r5_items(md) if sec == title]
            if items:
                L.append("- S-m1 (R5) 과압축 슬롯: 쉼표로만 이은 절은 「~이며/~하고」로 잇거나 두 슬롯으로 나누고, 떨어진 조사는 붙인다:")
                for t, why in items[:12]:
                    L.append(f"  - [{why}] 「{t[:90]}…」")
            import check_internal as _ci
            leaks = [h for h in _ci.find_in_text(md) if h["heading"] == title]
            if leaks:
                L.append("- T-m5 내부 표기: 아래 표기를 지운다(출처 괄호째 빼거나 공개 출처명으로 바꾼다):")
                for h in leaks[:12]:
                    L.append(f"  - [{h['name']}] 「…{h['context']}…」")
            rfp = [h for h in _ci.find_in_text(md, "rfp") if h["heading"] == title]
            if rfp:
                L.append("- T-m7 내부 출처 표시: 「RFP」·공고문 절 번호를 지운다(요구사항은 내용으로만 남기고, 출처 칸에는 외부 출처만):")
                for h in rfp[:12]:
                    L.append(f"  - [{h['name']}] 「…{h['context']}…」")
            # plan_v2 floor (2026-09-28): 이 절에서 걸린 줄을 찍어 준다(문서 전체 요약만으로는 anchor 를 못 잡는다)
            form = [h for h in _ci.find_form(md, spec, _ci.fixed_allow(evidence_dir)) if h["heading"] == title]
            if form and (only is None or "T-m8" in only):
                L.append("- T-m8 절 번호·작성 요령 표기: 가리키는 내용을 그 자리에 문장으로 쓰고, 작성 요령 문구·안내 꼬리를 뗀다:")
                for h in form[:15]:
                    L.append(f"  - [{h['name']}] 「{h['context']}」")
            sec_md = section_text(md, sid, title)
            labs = [ln.strip()[2:] for ln in sec_md.splitlines() if _ci.LABEL_RX.match(ln)]
            if labs and (only is None or "S-m6" in only):
                L.append(f"- S-m6 「라벨: 내용」 항목 {len(labs)}개: 라벨을 떼고 문장으로 교체한다(라벨 뜻은 문장 안에 녹인다):")
                L += [f"  - 「{x[:70]}」" for x in labs[:15]]
            import check_blank as _cb
            import check_captions as _cc
            if only is None or "F-m8" in only:
                cap = [p for p in _cc.check_text(md)[1] if p.startswith(sid + "절")]
                if cap:
                    L.append("- F-m8 표 캡션: 표 바로 위에 `[표 ?] 캡션` 줄을 둔다(표 바로 위 항목 문장을 anchor 로 insert_after, 기존 `[표 A]` 는 replace). "
                             "번호는 쓰지 않아도 된다: apply-edits 가 문서 순서대로 1부터 매긴다:")
                    L += [f"  - {p}" for p in cap]
            if only is None or "C-m6" in only:
                bl = [p for p in _cb.check_text(md)[1] if p.startswith(sid + "절")]
                if bl:
                    L.append("- C-m6 기준값 「해당 없음」: 출발값이 없다는 뜻이면 0 으로 바꾼다(칸 글 replace):")
                    L += [f"  - {p}" for p in bl]
        except Exception as e:                                   # noqa: BLE001
            L.append(f"- (R4/R5 상세 계산 실패: {e})")
    # ⑥ 현재 원고
    cur = section_text(md, sid, node["title"])
    L.append("")
    L.append("## ⑥ 현재 원고의 이 절" + (" (수정 대상)" if cur else " (없음: 새로 쓴다)"))
    if cur:
        L.append("```markdown")
        L.append(cur)
        L.append("```")
    L.append("")
    L.append("## 출력")
    if fix:
        # ★ 고치기 모드 (plan_v2 3단계 9, 2026-09-28): 수정 회차는 절을 다시 쓰지 않는다. t3 는 절 재작성으로 정보 22건을 잃었다.
        rnd = (json.load(open(os.path.join(run, "72_rounds.json"), encoding="utf-8")).get("round", 0)
               if os.path.exists(os.path.join(run, "72_rounds.json")) else 0)
        out = os.path.join(run, "edits", f"r{rnd}_{sid}.json")
        L += [f"**고치기 모드: 원고·절 파일을 고치지 않는다.** 바꿀 곳을 op 목록으로 `{out}` 에 쓴다(폴더가 없으면 만든다). "
              "스킬이 `rp_run.py apply-edits` 로 적용하고, 규칙을 어긴 op 는 거부해 원장(74_수정원장.md)에 남긴다.",
              "```json",
              '{"author": "writer:' + sid + '", "edits": [',
              '  {"id": "1", "check": "<체크 id>", "op": "replace", "anchor": "<⑥ 에서 그대로 복사한 문장 또는 표 칸 글>", "new": "<바꾼 문장>", "reason": "<한 줄>"},',
              '  {"id": "2", "check": "<체크 id>", "op": "insert_after", "anchor": "<⑥ 의 문장>", "new": "<그 바로 뒤에 더할 문장 하나>", "reason": "…"},',
              '  {"id": "3", "check": "<체크 id>", "op": "merge", "anchor": "<문장 A>", "anchor2": "<문장 B: 한 줄 전체>", "new": "<A·B 의 수치·출처를 모두 담은 한 문장>", "reason": "…"}',
              "]}",
              "```",
              "- anchor 는 ⑥ 에서 **글자 그대로** 복사한 한 줄 안의 글이고 원고 전체에 한 번만 나와야 한다(짧으면 여러 곳에 걸린다: 문장 전체를 쓴다).",
              "- 삭제 op 는 없다. 문장을 지우고 싶으면 그 뜻을 다른 문장에 합친다(merge). 수치·규격명·출처·기관명·위험 대응·산출식이 원고 어디에서도 사라지면 거부된다(C-m5).",
              "- new 는 한 줄 문장이다. 「라벨: 내용」 머리·절 번호 참조·내부 표기를 넣지 않는다(S-m6·T-m8·T-m5·T-m7). 표 행은 더하지 않는다(칸 글은 replace 로 바꾼다).",
              "- 절 구조·리드 줄은 바꾸지 않는다. 한 회차에 고치는 문장은 ⑤ 의 체크에 필요한 것만."]
        return "\n".join(L) + "\n"
    L.append(f"절 본문만 `{os.path.join(run, 'sections', sid + '.md')}` 에 쓴다(제목 줄 없이, 리드부터). 다른 절이 병렬로 쓰이므로 "
             f"`30_proposal.md` 를 직접 고치지 않는다: 스킬이 `rp_run.py merge` 로 합친다. "
             f"(단독 실행이라 병합을 직접 하려면 `{os.path.join(run, '30_proposal.md')}` 의 `{node['title']}` 절 본문만 바꾼다.) "
             f"쓰고 나서 반드시 `python $CLAUDE_PLUGIN_ROOT/scripts/rp_run.py check-section --run <run> --section {sid}` 를 돌려 "
             f"**다른 절과의 4낱말 겹침(R4)·과압축(R5)이 0** 인지 본다: 절 파일만 봐서는 알 수 없다. "
             "쓰고 나서 `python $CLAUDE_PLUGIN_ROOT/scripts/check_rubric.py --md <run>/30_proposal.md --spec <run>/50_form_spec.json` 를 한 번 돌려 "
             "R2·R3·R4·R5·R7 이 통과하는지 본다(hwpx 없이 도는 검사만).")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--section", required=True)
    ap.add_argument("--rubric", required=True)
    ap.add_argument("--spec", help="20_spec.md (기본 <run>/20_spec.md)")
    ap.add_argument("--evidence", help="근거팩 _ws 디렉터리")
    ap.add_argument("--mode", default="submission", choices=["submission", "final"])
    ap.add_argument("--fix", action="store_true", help="직전 채점 실패 체크를 ⑤에 넣는다")
    ap.add_argument("--only", help="--fix 와 함께: 쉼표로 이은 체크 id 만 ⑤에 넣는다(판정 절과 무관)")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    spec_path = a.spec or os.path.join(a.run, "20_spec.md")
    only = {x.strip() for x in a.only.split(",") if x.strip()} if a.only else None
    text = build(a.run, a.section, a.rubric, spec_path, a.evidence, a.mode, a.fix, only)
    out = a.out or os.path.join(a.run, "briefs", f"brief_{a.section}.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w", encoding="utf-8").write(text)
    print(f"→ {out}  ({len(text):,}자)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
