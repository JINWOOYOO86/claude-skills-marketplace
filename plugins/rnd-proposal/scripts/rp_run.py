# -*- coding: utf-8 -*-
"""rp-run 스킬의 절차를 기계로 고정한다 (2026-09-27 시스템 모드).

메인 세션(스킬)은 판단하지 않는다. `next` 가 주는 액션을 끝(done)까지 실행할 뿐이다.
사람은 시작 질문 한 번(설계서 승인·빈칸 답·외부 교정 동의)에만 답한다.

    python rp_run.py next      --run <dir> [--json]          # 다음 단계와 실행할 액션(명령·에이전트·질문)
    python rp_run.py gaps      --run <dir>                   # rubric needs 를 근거팩·설계서 §8 과 대조 → 21_questions.md
    python rp_run.py answers   --run <dir> [--spec-approved] [--external yes|no] [--figures 1,2]
                                                            # 21_questions.md 「답」열 → _ws/16_user_answers.md, 23_consent.json
    python rp_run.py sections  --run <dir>                   # 집필 대상 절 id
    python rp_run.py merge     --run <dir>                   # sections/*.md → 30_proposal.md
    python rp_run.py split     --run <dir>                   # 30_proposal.md → sections/*.md
    python rp_run.py assemble  --run <dir> [--repro]         # harness_assemble (--repro: 해시 시드 2종으로 두 번, sha 대조)
    python rp_run.py score     --run <dir>                   # 70_machine + 70_judge + rubric → 70_score.json, 72_rounds.json 기록
    python rp_run.py fix-list  --run <dir> [--begin]         # 실패 체크를 fix_by(unify·editor·writer·unmet)로 묶는다. --begin: 회차 +1
    python rp_run.py leads     --run <dir> [--md <file>]     # 리드 골격 축자·순서 검사 (편집자 자가 검사)
    python rp_run.py check-section --run <dir> --section S   # 절 파일 임시 병합 → 그 절 관련 R4·R5 · 분량 상한
    python rp_run.py budget    --run <dir> [--md <file>]     # 장별 분량 ↔ 장 예산(page_budget × chars_per_page)
    python rp_run.py apply-edits --run <dir>                 # 고치기 모드: edits/r<n>_*.json 을 원고에 적용(삭제 없음, 정보 보존) → 74_수정원장
    python rp_run.py trim      --run <dir>                   # 장 예산 초과 시 이번 회차 추가 문장부터 되돌린다
    python rp_run.py experiment-decide --out <exp>           # 교정 효과 실험 판정(blind_*/blind.json → 85_교정실험.md)
    python rp_run.py adopt     --run <dir>                   # 회차 채택: C-m5·F-m3·Claude 블라인드. 지면 직전 채택 판으로 되돌린다
    python rp_run.py figures   --run <dir>                   # final: 20_spec.md §7 승인 행
    python rp_run.py mark      --run <dir> --proofread done|skipped
    python rp_run.py deliver   --run <dir> --out <hwpx>      # 30_proposal.hwpx → 제출 파일
    python rp_run.py report    --run <dir>                   # 72_rounds·70_score·질문/답 → 90_제출보고.md 실행 기록 절
    python rp_run.py init      --from <dir> --to <dir>       # 입력만 복사한 새 워크스페이스(완료 판정 테스트용)
    python rp_run.py resume    --from <dir> --round N --to <dir>   # 채택 회차 N 스냅숏에서 회차 N+1 부터(빠른 재현, plan_t4fix 7)
    python rp_run.py plan      --run <dir>                   # 단계 목록(설명용)

경로: <run> = workspace/<과제>/. 루트 = <run> 의 두 단계 위. rubric = <루트>/criteria/rubric.yaml.
근거팩 = requirements.md 프런트매터 `evidence:`(루트 기준 상대 경로). 없으면 <루트>/evidence/workspace/*/_ws 가 하나일 때 그것.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = [
    ("requirements", "요구·모드 확인 (requirements.md)", None),
    ("spec", "설계서 (rp-spec → 20_spec.md)", None),
    ("gaps", "근거 빈칸 목록 (rubric needs ↔ 근거팩·§8 → 21_questions.md)", None),
    ("ask", "★ 시작 질문 1회 (설계서 승인 · 빈칸 답 · 외부 교정 동의 · final 그림) → answers", None),
    ("figures", "그림 (final 만: §7 승인 행 → rnd-figure)", "final"),
    ("write", "절별 집필 (writer_brief → rp-writer 병렬 → merge)", None),
    ("assemble", "조립 + 게이트 (harness_assemble --repro: 치환·테두리·대시·R1~R7·쪽수·sha 재현)", None),
    ("machine", "기계 검사 (check_rubric --rubric → 70_machine.json)", None),
    ("judge", "채점 (rp-scorer → 70_judge.json · 70_채점보고.md)", None),
    ("tally", "집계 (score → 70_score.json: 목표 도달 여부)", None),
    ("fix", "수정 회차 (unify → editor → writer, 목표 미달·상한 전·정체 전)", None),
    ("proofread", "외부 교정 (동의 + proofread: on 일 때만 · 문제 목록 → 교정 회차 편집자 op → 채택 판정)", None),
    ("deliver", "제출 파일 복사", None),
    ("report", "90_제출보고 실행 기록", None),
]
ANSWER_NONE = {"", "없음", "-", "해당 없음", "모름", "x", "X"}


# ── 경로·설정 ──────────────────────────────────────────────────────────────
def root_of(run: str) -> str:
    return os.path.abspath(os.path.join(run, os.pardir, os.pardir))


def frontmatter(run: str) -> dict:
    p = os.path.join(run, "requirements.md")
    out = {}
    if not os.path.exists(p):
        return out
    t = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---", t, re.S)
    if not m:
        return out
    for ln in m.group(1).splitlines():
        k, _, v = ln.partition(":")
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def mode_of(run: str) -> str:
    return (frontmatter(run).get("mode") or "submission").strip().lower()


def external_ai_of(run: str) -> str:
    return (frontmatter(run).get("external_ai") or "chatgpt").strip().lower()


# 외부 교정 기본값 (plan_v2 4단계 15, 2026-09-28): 효과 실험(교정 적용본 대 미적용본 블라인드)에서 교정 적용본이
# 두 심판 모두에서 확정 승 1개 이상·확정 패 0 일 때만 "on" 으로 바꾼다. 실험 기록 criteria/proofread_experiment.md.
# 2026-09-28 실험 판정 켬(Claude 논리·구체·문체, ChatGPT 양식·논리·구체·문체·구조), 사용자 승인으로 "on".
PROOFREAD_DEFAULT = "on"


def proofread_of(run: str) -> str:
    v = str(frontmatter(run).get("proofread") or PROOFREAD_DEFAULT).strip().lower()
    return "on" if v in ("on", "yes", "true", "켬") else "off"


ORG_RX = re.compile(r"[가-힣A-Za-z]{2,}(?:\(주\)|㈜|주식회사|연구원|대학교|재단|공사)|(?:\(주\)|㈜)[가-힣A-Za-z]{2,}")
MONEY_RX = re.compile(r"\d[\d,.]*\s*(?:억\s*원|억원|천원|만원|백만원)")


def sensitive_preview(run: str) -> dict:
    """외부 전송 동의 때 보여 줄 민감 정보 후보 (plan_v2 4단계 14): 설계서·빈칸 답에서 기관명·금액."""
    text = ""
    for f in ("20_spec.md", "21_questions.md", "requirements.md"):
        p = os.path.join(run, f)
        if os.path.exists(p):
            text += open(p, encoding="utf-8").read() + "\n"
    orgs = list(dict.fromkeys(m.group(0) for m in ORG_RX.finditer(text)))[:8]
    money = list(dict.fromkeys(m.group(0) for m in MONEY_RX.finditer(text)))[:5]
    return {"orgs": orgs, "money": money}


def _sensitive_note(run: str) -> str:
    s = sensitive_preview(run)
    if not (s["orgs"] or s["money"]):
        return "⚠ 원고에는 기관명·예산 같은 미공개 정보가 들어갈 수 있다."
    return ("⚠ 원고에 들어갈 민감 정보 후보: " + " · ".join(s["orgs"] + s["money"])
            + ". 외부 서비스에 남을 수 있다(임시 대화로 보내도 서비스 정책을 따른다).")


def rubric_of(run: str, override: str | None = None) -> str:
    return os.path.abspath(override) if override else os.path.join(root_of(run), "criteria", "rubric.yaml")


def evidence_of(run: str, override: str | None = None) -> str | None:
    if override:
        return os.path.abspath(override)
    fm = frontmatter(run).get("evidence")
    if fm:
        p = fm if os.path.isabs(fm) else os.path.join(root_of(run), fm)
        return os.path.abspath(p)
    cands = glob.glob(os.path.join(root_of(run), "evidence", "workspace", "*", "_ws"))
    return os.path.abspath(cands[0]) if len(cands) == 1 else None


def load_rubric(path: str) -> dict:
    import yaml
    return yaml.safe_load(open(path, encoding="utf-8")) or {}


def all_checks(rubric: dict, mode: str = "submission"):
    for item, cfg in (rubric.get("items") or {}).items():
        for tier in ("floor", "ceiling"):
            for c in cfg.get(tier) or []:
                if c.get("mode") and c["mode"] != mode:
                    continue
                yield item, tier, c


def fix_by_of(c: dict) -> list[str]:
    v = c.get("fix_by")
    if not v:
        return ["writer"]
    return [v] if isinstance(v, str) else list(v)


def plan(run: str) -> list[tuple[str, str]]:
    m = mode_of(run)
    return [(k, d) for k, d, only in STAGES if only is None or only == m]


def _mtime(p: str) -> float:
    return os.path.getmtime(p) if os.path.exists(p) else -1.0


def _jload(p: str, default=None):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def _jdump(p: str, obj) -> None:
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def today() -> str:
    return _dt.date.today().isoformat()


# ── 설계서·질문·답 ─────────────────────────────────────────────────────────
def spec_approved(run: str) -> bool:
    p = os.path.join(run, "20_spec.md")
    if not os.path.exists(p):
        return False
    t = open(p, encoding="utf-8").read()
    m = re.search(r"^## 승인 기록.*", t, re.M | re.S)
    return bool(m and re.search(r"\|\s*v[\d.]+\s*\|[^|]*\|\s*사용자\s*\|\s*승인", m.group(0)))


def ledger_keys(evidence_dir: str | None) -> dict[str, str]:
    """근거팩 `_ws/*.md` 의 `| KEY | 값 | …` 행 → {KEY: 값}. 값이 「미확인」이면 없는 것으로 본다."""
    out = {}
    if not evidence_dir or not os.path.isdir(evidence_dir):
        return out
    for f in sorted(glob.glob(os.path.join(evidence_dir, "*.md"))):
        for ln in open(f, encoding="utf-8").read().splitlines():
            m = re.match(r"^\|\s*([A-Z][A-Z0-9_]{2,})\s*\|\s*([^|]*?)\s*\|", ln)
            if m and m.group(2) and "미확인" not in m.group(2):
                out.setdefault(m.group(1), m.group(2))
    return out


CHECK_ID = re.compile(r"\b[A-Z]-[a-z]\d+\b")


def spec8_rows(run: str) -> list[dict]:
    """20_spec.md §8 표의 데이터 행 → [{id, item, text, checks}]. id 는 첫 칸의 「8-N」·「#N」, 없으면 순번 8-i.
    checks: 행에 적힌 rubric 체크 id(「막는 체크」 열). t2(2026-09-27): §8 행이 「| #17 …」 꼴이라 옛 「| 8-N」 패턴이
    한 행도 못 읽었고, floor 를 막는 #17(기술분류)이 시작 질문에 오르지 않았다."""
    p = os.path.join(run, "20_spec.md")
    if not os.path.exists(p):
        return []
    t = open(p, encoding="utf-8").read()
    m = re.search(r"^## 8\..*?(?=^## |\Z)", t, re.M | re.S)
    lines = [ln for ln in (m.group(0).splitlines() if m else []) if ln.startswith("|")]
    sep = lambda ln: re.match(r"^\|[\s:|-]+$", ln.strip()) is not None
    rows = []
    for i, ln in enumerate(lines):
        if sep(ln) or (i + 1 < len(lines) and sep(lines[i + 1])):   # 구분선과 그 위 머리 행은 뺀다
            continue
        first = ln.strip().strip("|").split("|")[0].strip().replace("**", "")
        mm = re.match(r"^(?:8-|#)(\d+)\s*", first)
        rid = f"8-{mm.group(1)}" if mm else f"8-{len(rows) + 1}"
        rows.append({"id": rid, "item": (first[mm.end():] if mm else first).strip()[:120], "text": ln,
                     "checks": list(dict.fromkeys(CHECK_ID.findall(ln)))})
    return rows


def needs_of(c: dict) -> list[dict]:
    """질문 대상 key: judge 의 needs + machine 의 requires(key 가 있는 항목). 2026-09-27 t1: R3 「모델 구성」을
    requires 없이 묻지 못했다. requires 의 values(양식 칸 → key)도 대장에 없으면 묻는다(「@title」 제외)."""
    out = [n for n in c.get("needs") or [] if isinstance(n, dict) and "key" in n]
    reqs = c.get("requires") or []
    for r in [reqs] if isinstance(reqs, dict) else reqs:
        if r.get("key"):
            out.append({"key": r["key"], "ask": r.get("ask") or f"{r.get('section', '')}절 {r.get('item', '')} 값"})
        for label, v in (r.get("values") or {}).items():
            for k in [v] if isinstance(v, str) else list(v):
                if not k.startswith("@"):
                    out.append({"key": k, "ask": f"{r.get('section', '')}절 요약문 「{label}」 값"})
    return out


def implicit_floor(text: str, rubric: dict, spec: dict, mode: str, have: dict | None = None) -> list[str]:
    """§8 행에 체크 id 가 없어도 그 행이 막는 floor 체크 (2026-09-28 t2 #17: 「기술분류 …(0장 CLASS3)」만 적혀 있었다).
    - 양식 지정 서식 코드(outline special: CLASS3·KEYWORDS5 …) → impl 에 gate_form:F-4 가 있는 floor 체크
    - floor 체크 requires 항목 이름의 3자 이상 낱말(「기술분류」) → 그 체크. 그 항목의 key 값이 대장(have)에 없을 때만:
      값이 있으면 그 칸은 막히지 않는다(t2 사본 실측: 「TRL 7 판정 기준」 행이 값이 있는 TRL 칸에 걸렸다)."""
    sys.path.insert(0, HERE)
    import check_rubric as cr
    specials = {(s if isinstance(s, str) else s.get("key", "")) for n in spec.get("outline") or [] for s in n.get("special") or []}
    hit_special = any(s and re.search(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", text) for s in specials)
    out = []
    for _, tier, c in all_checks(rubric, mode):
        if tier != "floor" or c.get("by") != "machine" or c.get("severity") == "warn":
            continue
        impl = " ".join([c["impl"]] if isinstance(c.get("impl"), str) else (c.get("impl") or []))
        if hit_special and "gate_form:F-4" in impl:
            out.append(c["id"])
            continue
        for r in cr.required_elements(c, spec) if c.get("requires") else []:
            keys = [k for k in r["keys"] if not k.startswith("@")]
            if not keys or all(k in (have or {}) for k in keys):
                continue
            words = [w for w in re.split(r"[\s·/()（）,]+", r["item"]) if len(w) >= 3]
            if any(w in text for w in words):
                out.append(c["id"])
                break
    return out


def gaps(run: str, rubric_path: str | None = None, evidence_dir: str | None = None) -> list[dict]:
    """rubric needs·requires 의 key 를 근거팩 대장·사용자 답·설계서 §8 과 대조해 빈칸 목록을 만든다 → 21_questions.md.
    floor 를 막는 질문(floor 체크의 requires key, §8 「막는 체크」 열에 floor 체크 id 가 있는 행)은 「[floor]」 로 표시한다.
    §8 행은 key 「SPEC8_N」 으로 묻는다: 시작 질문 뒤에 근거가 없어 floor 가 막히는 일이 없게 한다(t2 2026-09-27)."""
    rubric = load_rubric(rubric_of(run, rubric_path))
    ev = evidence_of(run, evidence_dir)
    have = ledger_keys(ev)
    s8 = spec8_rows(run)
    sp = os.path.join(run, "50_form_spec.json")
    form = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    rows = []
    floor_ids, linked = set(), {}
    for item, tier, c in all_checks(rubric, mode_of(run)):
        if tier == "floor" and c.get("severity") != "warn":
            floor_ids.add(c["id"])
        for n in needs_of(c):
            key, ask = n["key"], n.get("ask", "")
            if any(r["key"] == key for r in rows):             # needs 와 requires 가 같은 key 를 물으면 한 번만
                continue
            found = have.get(key)
            grams = {ask[i:i + 2] for i in range(len(ask) - 1)
                     if ask[i:i + 2].strip() == ask[i:i + 2] and not re.search(r"[·(),/:]", ask[i:i + 2])}
            hits = list(dict.fromkeys(r["id"] for r in s8 if sum(g in r["text"] for g in grams) >= 2))
            also = implicit_floor(key, rubric, form, mode_of(run))   # key 가 서식 코드(CLASS3)면 그 서식 검사(T-m3)도 맡는다
            for h in hits:                                      # 값이 대장에 있어도 이 §8 행의 이 체크는 이 key 가 맡는다
                linked.setdefault(h, set()).update([c["id"], *also])
            where = "근거팩 대장" if found else (("설계서 §" + "·§".join(hits)) if hits else "없음")
            rows.append({"check": c["id"], "key": key, "ask": ("[floor] " if tier == "floor" else "") + ask, "where": where,
                         "answer": found or "", "found": bool(found)})
    for r in s8:
        blocks = [x for x in r["checks"] if x in floor_ids] or implicit_floor(r["text"], rubric, form, mode_of(run), have)
        if not blocks or set(blocks) <= linked.get(r["id"], set()):   # 막는 체크를 이미 rubric key 질문이 맡으면 한 번만 묻는다
            continue
        key = "SPEC8_" + r["id"].split("-", 1)[1]
        found = have.get(key)
        rows.append({"check": "·".join(blocks), "key": key, "ask": "[floor] " + r["item"].replace("|", "｜"),
                     "where": "근거팩 대장" if found else f"설계서 §{r['id']}", "answer": found or "", "found": bool(found)})
    # plan_t4fix 4: 근거팩 고정 표현이 원고 기계 검사·금지 표현과 부딪히면 집필 전에 사람에게 묻는다(t4: F10·F12 ↔ T-m8)
    sys.path.insert(0, HERE)
    import check_rules
    for r in (check_rules.check(ev, form) if ev else []):
        if r["resolved"]:
            continue
        key = f"RULE_{r['fixed']}_{r['rule'].replace('-', '').upper()}"
        if any(x["key"] == key for x in rows):
            continue
        found = have.get(key)
        rows.append({"check": r["rule"], "key": key, "where": "근거팩 §B-1", "answer": found or "", "found": bool(found),
                     "ask": f"[규칙 충돌] 고정 표현 {r['fixed']} 「{r['phrase']}」가 {r['rule']}({r['why']})에 걸린다: "
                            "고정 표현을 따를지(고정) 금지를 따를지(금지)".replace("|", "｜")})
    write_questions(run, rows)
    return rows


def write_questions(run: str, rows: list[dict]) -> None:
    L = ["# 시작 질문: 근거가 없는 값 (한 번만 묻는다. 답이 없으면 그 체크는 「미충족」으로 남긴다)", "",
         "「답」 열에 값을 적는다(단위·출처가 있으면 함께). 모르면 「없음」. 채운 뒤 `rp_run.py answers` 가 근거팩 대장(16_user_answers.md)으로 옮긴다.", "",
         "| # | 체크 | key | 묻는 것 | 찾아본 곳 | 답 |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        L.append(f"| {i} | {r['check']} | {r['key']} | {r['ask']} | {r['where']} | {r['answer']} |")
    if not rows:
        L.append("| 해당 없음 | | | | | |")
    open(os.path.join(run, "21_questions.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def read_questions(run: str) -> list[dict]:
    p = os.path.join(run, "21_questions.md")
    rows = []
    if not os.path.exists(p):
        return rows
    for ln in open(p, encoding="utf-8").read().splitlines():
        if not ln.startswith("|") or "---" in ln:
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 6 and c[0] not in ("#", "해당 없음"):
            rows.append({"n": c[0], "check": c[1], "key": c[2], "ask": c[3], "where": c[4], "answer": c[5]})
    return rows


# 답 값에 붙은 출처 꼬리표 「(사용자 답 2026-09-27)」: t1 에서 메인 세션이 붙였고 원고 20곳으로 샜다.
ANSWER_TAG = re.compile(r"\s*[(（]\s*사용자\s*답[^)）]*[)）]|\s*,?\s*사용자\s*답\s*\(?\d{4}-\d{2}-\d{2}\)?")


def clean_answer(v: str) -> str:
    return ANSWER_TAG.sub("", v).strip()


def target_base(run: str, key: str) -> str:
    """답 key 의 목표 기준: 설계서 §2(성과지표 역추적표)에서 그 key 나 「§8 #N」(SPEC8_N)을 가리키는 행."""
    sp = os.path.join(run, "20_spec.md")
    if not os.path.exists(sp):
        return ""
    m = re.search(r"^## 2\..*?(?=^## \d)", open(sp, encoding="utf-8").read(), re.M | re.S)
    refs = [key] + ([f"§8 #{key.split('_', 1)[1]}", f"§8-{key.split('_', 1)[1]}"] if key.startswith("SPEC8_") else [])
    return "\n".join(ln for ln in (m.group(0) if m else "").splitlines()
                     if ln.startswith("|") and any(re.search(re.escape(r) + r"(?!\d)", ln) for r in refs))


def answers(run: str, evidence_dir: str | None = None, spec_ok: bool | None = None,
            external: str | None = None, figures_ok: str | None = None, confirm_down: str | None = None) -> dict:
    """21_questions.md 「답」열 → _ws/16_user_answers.md 대장 행(값만). 출처 → 22_answer_sources.json.
    동의·승인 → 23_consent.json, 20_spec.md 승인 기록.
    목표 하향(plan_v2 5단계 18): 답의 목표가 설계서 §2 기준보다 느슨하면 consent.target_down 에 적는다.
    confirm_down 이 없으면 next 가 그 항목만 한 번 더 묻는다(시작 질문 1회 원칙의 유일한 예외)."""
    import check_targets
    ev = evidence_of(run, evidence_dir)
    rows = read_questions(run)
    for r in rows:
        r["answer"] = clean_answer(r["answer"])
    answered = [r for r in rows if r["answer"] not in ANSWER_NONE]
    unmet_keys = [r["key"] for r in rows if r["answer"] in ANSWER_NONE]
    if ev and answered:
        p = os.path.join(ev, "16_user_answers.md")
        head = ["# 시작 질문 답 (rp-run, 근거팩 대장 형식: 값만)", "",
                "> 출처는 워크스페이스 22_answer_sources.json 에 따로 둔다. 이 표에는 값만 있다(출처 표기가 원고로 새지 않게).", "",
                "| key | 값 | 단위 | 기준연도 | 출처(계층①~⑥) | 확신도(상/중/하) |", "|---|---|---|---|---|---|"]
        old = {}
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8").read().splitlines():
                m = re.match(r"^\|\s*([A-Z][A-Z0-9_]{2,})\s*\|", ln)
                if m:
                    old[m.group(1)] = ln
        for r in answered:
            old[r["key"]] = f"| {r['key']} | {r['answer'].replace('|', '｜')} |  | {today()[:4]} |  | 상 |"
        open(p, "w", encoding="utf-8").write("\n".join(head + list(old.values())) + "\n")
        sp = os.path.join(run, "22_answer_sources.json")
        src = _jload(sp, {}) or {}
        for r in answered:
            src[r["key"]] = {"source": "사용자 답 (rp-run 시작 질문)", "date": today(), "check": r["check"], "ask": r["ask"]}
        _jdump(sp, src)
    consent = _jload(os.path.join(run, "23_consent.json"), {}) or {}
    consent.update({"asked": True, "date": today(), "answered": [r["key"] for r in answered], "unmet": unmet_keys})
    if spec_ok is not None:
        consent["spec_approved"] = bool(spec_ok)
    if external is not None:
        consent["external_ai"] = external.lower() in ("yes", "y", "true", "1", "동의", "예")
    if figures_ok is not None:
        consent["figures"] = [x.strip() for x in figures_ok.split(",") if x.strip()]
    consent["target_down"] = [{"key": r["key"], **d} for r in answered for d in check_targets.lowered(target_base(run, r["key"]), r["answer"])]
    if confirm_down is not None:
        consent["target_down_ok"] = confirm_down.lower() in ("yes", "y", "true", "1", "예", "유지")
    _jdump(os.path.join(run, "23_consent.json"), consent)
    if consent.get("spec_approved") and not spec_approved(run):
        sp = os.path.join(run, "20_spec.md")
        if os.path.exists(sp):
            t = open(sp, encoding="utf-8").read()
            if "## 승인 기록" not in t:
                t = t.rstrip("\n") + "\n\n## 승인 기록\n\n| 판 | 일시 | 승인자 | 바뀐 것 |\n|---|---|---|---|\n"
            n = len(re.findall(r"^\| v", t, re.M)) + 1
            t = t.rstrip("\n") + f"\n| v{n} | {today()} | 사용자 | 승인 (rp-run 시작 질문) |\n"
            open(sp, "w", encoding="utf-8").write(t)
    return consent


def unmet_checks(run: str, rubric: dict) -> dict[str, list[str]]:
    """needs 중 답이 없는 key 를 가진 체크 → {체크 id: [key…]}. 질문 전이면 needs 전부."""
    rows = {r["key"]: r["answer"] for r in read_questions(run)}
    have = ledger_keys(evidence_of(run))
    out = {}
    sp = os.path.join(run, "50_form_spec.json")
    form = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    for _, _, c in all_checks(rubric, mode_of(run)):
        miss = [n["key"] for n in needs_of(c)
                if n["key"] not in have and clean_answer(rows.get(n["key"], "")) in ANSWER_NONE]
        if miss:
            out.setdefault(c["id"], []).extend(k for k in miss if k not in out.get(c["id"], []))
            for k in miss:                                  # 서식 코드 key(CLASS3)가 비면 그 서식 검사(T-m3)도 못 넘는다
                for cid in implicit_floor(k, rubric, form, mode_of(run)):
                    if k not in out.setdefault(cid, []):
                        out[cid].append(k)
    for q in read_questions(run):                           # 설계서 §8 에서 온 floor 질문(SPEC8_N)에 「없음」: 막는 체크가 미충족
        if q["key"].startswith("SPEC8_") and q["key"] not in have and clean_answer(q["answer"]) in ANSWER_NONE:
            for cid in re.split(r"[·,\s]+", q["check"]):
                if cid:
                    out.setdefault(cid, []).append(q["key"])
    return out


# ── 절·병합·분리 ────────────────────────────────────────────────────────────
def sections(run: str) -> list[str]:
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    return [n["id"] for n in spec.get("outline") or [] if n.get("guide") or n.get("blueprint")]


def _sec_pat(title: str):
    return re.compile(r"(^#{2,4}[ \t]+" + re.escape(title) + r"[ \t]*$\n)(.*?)(?=^#{2,4}[ \t]+\S|\Z)", re.M | re.S)


def merge(run: str) -> dict:
    """sections/<sid>.md (절 본문만) → 30_proposal.md. 원고가 없으면 outline 제목만 있는 골격을 먼저 만든다."""
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    mdp = os.path.join(run, "30_proposal.md")
    if os.path.exists(mdp):
        md = open(mdp, encoding="utf-8").read()
    else:
        title = frontmatter(run).get("title", "(과제명)")
        md = f"# {title}\n\n" + "\n".join(("## " if n["level"] == 2 else "### ") + n["title"] + "\n"
                                          for n in spec.get("outline") or [])
    done, missing = [], []
    for n in spec.get("outline") or []:
        sid, title = n["id"], n["title"]
        sp = os.path.join(run, "sections", f"{sid}.md")
        if not os.path.exists(sp):
            continue
        body = open(sp, encoding="utf-8").read().strip("\n")
        body = re.sub(r"^#{2,4}\s+" + re.escape(title) + r"\s*\n", "", body)
        m = _sec_pat(title).search(md)
        if not m:
            missing.append(sid)
            continue
        md = md[:m.start()] + m.group(1) + "\n" + body + "\n\n\n" + md[m.end():]
        done.append(sid)
    open(mdp, "w", encoding="utf-8").write(md)
    return {"merged": done, "no_heading": missing}


def split(run: str) -> dict:
    """30_proposal.md → sections/<sid>.md (merge 의 역). 편집·교정·치환 뒤 절 파일을 맞춘다."""
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    md = open(os.path.join(run, "30_proposal.md"), encoding="utf-8").read()
    os.makedirs(os.path.join(run, "sections"), exist_ok=True)
    changed, missing = [], []
    for n in spec.get("outline") or []:
        if not (n.get("guide") or n.get("blueprint")):
            continue
        m = _sec_pat(n["title"]).search(md)
        if not m:
            missing.append(n["id"])
            continue
        body = m.group(2).strip("\n") + "\n"
        sp = os.path.join(run, "sections", f"{n['id']}.md")
        old = open(sp, encoding="utf-8").read() if os.path.exists(sp) else None
        if old != body:
            open(sp, "w", encoding="utf-8").write(body)
            changed.append(n["id"])
    return {"changed": changed, "no_heading": missing}


def leads(run: str, md_path: str | None = None) -> dict:
    """리드 골격(blueprint lead) 축자·순서 검사. gate_form F-11 과 같은 정규형(구분 기호 앞부분·공백 제거)."""
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    md = open(md_path or os.path.join(run, "30_proposal.md"), encoding="utf-8").read()
    norm = lambda x: re.split(r"[—:：]", re.sub(r"\s+", "", re.sub(r"\*\*|`", "", x)))[0]
    missing, order_bad = [], []
    for n in spec.get("outline") or []:
        want = [norm(bp["lead"]) for bp in n.get("blueprint") or [] if bp.get("lead")]
        if not want:
            continue
        m = _sec_pat(n["title"]).search(md)
        got = [norm(x) for x in re.findall(r"^- (.+)$", m.group(2), re.M)] if m else []
        for w in want:
            if w not in got:
                missing.append(f"{n['id']}: {w}")
        idx = [got.index(w) for w in want if w in got]
        if idx != sorted(idx):
            order_bad.append(n["id"])
    return {"missing": missing, "order": order_bad, "ok": not missing and not order_bad}


def check_section(run: str, sid: str) -> dict:
    """절 파일을 임시로 병합해 그 절이 관련된 R4(절 간 중복)·R5(과압축)와 분량 예산을 본다.
    분량 상한은 병합 **전** 원고(30_proposal.md)로 계산한다: 절을 늘린 뒤 다시 나누면 상한이 따라 늘어난다.
    원고가 있으면(수정 회차) 상한 = 예산, 없으면(초벌) 예산 +10%."""
    sys.path.insert(0, HERE)
    import check_rubric as cr
    import writer_brief as wb
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    node = next((n for n in spec.get("outline") or [] if n["id"] == sid), None)
    if node is None:
        raise SystemExit(f"절 {sid} 없음")
    mdp = os.path.join(run, "30_proposal.md")
    md = open(mdp, encoding="utf-8").read() if os.path.exists(mdp) else ""
    bud = wb.section_budget(spec, md, sid)
    sp = os.path.join(run, "sections", f"{sid}.md")
    body = open(sp, encoding="utf-8").read().strip("\n") if os.path.exists(sp) else wb.section_text(md, sid, node["title"])
    if os.path.exists(sp) and md:
        m = _sec_pat(node["title"]).search(md)
        if m:
            md = md[:m.start()] + m.group(1) + "\n" + body + "\n\n" + md[m.end():]
    title = node["title"]
    r4 = [(a, b, ph, sa, sb) for a, b, ph, sa, sb in cr.r4_pairs(md) if title in (a, b)]
    r5 = [(t, why) for sec, t, why in cr.r5_items(md) if sec == title]
    length = None
    if bud:
        cap = bud["target"] if os.path.exists(mdp) else round(bud["target"] * 1.1)
        cur = wb.section_chars(body)
        length = {"current": cur, "cap": cap, "ok": cur <= cap}
    return {"section": sid, "r4": r4, "r5": r5, "length": length}


def budget(run: str, md_path: str | None = None) -> dict:
    """장별 분량(공백 제외·표 포함)과 장 예산, 절별 현재·예산. 편집자가 원고 전체를 고친 뒤 장 합계가 예산 안인지 본다."""
    sys.path.insert(0, HERE)
    import writer_brief as wb
    spec = json.load(open(os.path.join(run, "50_form_spec.json"), encoding="utf-8"))
    mdp = md_path or os.path.join(run, "30_proposal.md")
    md = open(mdp, encoding="utf-8").read() if os.path.exists(mdp) else ""
    chaps, secs = {}, []
    for s in sections(run):
        b = wb.section_budget(spec, md, s)
        if not b:
            continue
        secs.append({"section": s, "current": b["current"], "target": b["target"]})
        chaps[b["chapter"]] = {"now": b["chapter_now"], "budget": b["chapter_budget"], "ok": b["chapter_now"] <= b["chapter_budget"]}
    return {"chapters": chaps, "sections": secs, "ok": all(c["ok"] for c in chaps.values())}


LEDGER = "74_수정원장.json"


def apply_edits(run: str) -> dict:
    """고치기 모드 (plan_v2 3단계 9, 2026-09-28): 이번 회차 edits/r<n>_*.json 가운데 아직 적용하지 않은 파일을
    edit_apply 로 30_proposal.md 에 적용한다(편집자 파일 먼저). 수정 회차 에이전트는 원고를 직접 고치지 않고 op 만 쓴다.
    t3 는 절을 다시 써서 정보 22건을 잃었다(80_비교검증). 적용 기록은 74_수정원장.json/.md, 72_rounds.fixes[n].edits."""
    sys.path.insert(0, HERE)
    import edit_apply as ea
    rr = rounds(run)
    n = str(rr.get("round", 0))
    fx = rr.setdefault("fixes", {}).setdefault(n, {})
    done = set((fx.get("edits") or {}).get("files") or [])
    # 집필자(절별) → 편집자 순 (plan_t4fix 1, 2026-09-28). 한 칸은 한 작성자만: 이번 회차에 고친 줄은 잠긴다.
    files = sorted(glob.glob(os.path.join(run, "edits", f"r{n}_*.json")), key=lambda p: ("_editor" in os.path.basename(p), p))
    mdp = os.path.join(run, "30_proposal.md")
    text = open(mdp, encoding="utf-8").read()
    st = fx.get("edits") or {"files": [], "applied": 0, "rejected": 0}
    lp = os.path.join(run, LEDGER)
    import check_internal
    allow = check_internal.fixed_allow(evidence_of(run))     # 근거팩 고정 문구는 T-m8 예외(plan_t4fix 4)
    for p in files:
        name = os.path.basename(p)
        if name in done:
            continue
        led = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []
        locked = {r["line_after"].strip(): f"{r['author']} #{r.get('id')}" for r in led
                  if r.get("round") == int(n) and r.get("status") == "applied" and r.get("line_after")}
        author, ops = ea.load_edits(p)
        text, rows = ea.apply_md(text, ops, author, locked, led, allow)
        ea.write_ledger(lp, rows, int(n), author)
        st["files"].append(name)
        st["applied"] += sum(r["status"] == "applied" for r in rows)
        st["rejected"] += sum(r["status"] == "rejected" for r in rows)
    import check_captions
    text, caps = check_captions.renumber(text)               # 캡션 번호는 문서 순서가 정한다(F-m8): 집필자는 `[표 ?]` 로 쓴다
    if caps:
        st.setdefault("captions", []).extend(f"{a} → {b}" for a, b in caps)
    open(mdp, "w", encoding="utf-8").write(text)
    fx["edits"] = st
    save_rounds(run, rr)
    split(run)
    _write_locked(run, int(n), text)
    return st


def _write_locked(run: str, n: int, text: str) -> str:
    """이번 회차에 잠긴 줄 목록(편집자 입력): edits/r<n>_locked.md. 편집자는 이 줄들을 anchor 로 쓰지 않는다."""
    lp = os.path.join(run, LEDGER)
    led = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []
    rows = [r for r in led if r.get("round") == n and r.get("status") == "applied" and r.get("line_after")
            and r["line_after"] in text]
    p = os.path.join(run, "edits", f"r{n}_locked.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    L = [f"# 회차 {n} 잠긴 줄 (한 칸 한 작성자: 이 줄을 anchor·anchor2 로 쓰는 op 는 거부된다)", ""]
    L += [f"- [{r['author']} #{r.get('id')}] {r['line_after'].strip()}" for r in rows] or ["- (없음)"]
    open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return p


def trim(run: str) -> dict:
    """분량 규칙 (plan_v2 3단계 12): 장 예산을 넘으면 이번 회차에 **새로 넣은 문장부터** 되돌린다.
    순서: insert_after(최근 것부터) → 글자를 가장 늘린 replace. 원래 있던 문장은 줄이지 않는다(merge 는 줄이는 쪽이라 두지 않는다).
    되돌린 op 는 원장에서 「되돌림」. 그래도 넘으면 멈추지 않고 기록만 한다(조립 뒤 F-m3 가 adopt 에서 판정한다)."""
    sys.path.insert(0, HERE)
    import edit_apply as ea
    rr = rounds(run)
    n = int(rr.get("round", 0))
    lp = os.path.join(run, LEDGER)
    led = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []
    mdp = os.path.join(run, "30_proposal.md")
    out = {"reverted": [], "over": None}
    b0 = budget(run)
    if b0["ok"]:
        return out
    over = {k for k, c in b0["chapters"].items() if not c["ok"]}
    text = open(mdp, encoding="utf-8").read()
    floors = floor_fails(run)
    # 예산을 넘은 장 안의 op 만 되돌린다(리허설 2026-09-28: 원래부터 넘던 1장 때문에 2장의 정당한 교체 3건이 되돌려졌다)
    # floor 를 고친 op 는 되돌리지 않는다(plan_t4fix 5: t4 는 S-m1 을 고친 편집자 #3 을 trim 이 되돌려 같은 floor 로 멈췄다)
    mine = [(i, r) for i, r in enumerate(led) if r.get("round") == n and r.get("status") == "applied"
            and str(r.get("section") or "").split("-")[0] in over and not _op_checks(r) & floors]
    order = [x for x in reversed(mine) if x[1]["op"] == "insert_after"] + \
            sorted([x for x in mine if x[1]["op"] == "replace" and len(x[1]["new"]) > len(x[1]["anchor"])],
                   key=lambda x: len(x[1]["anchor"]) - len(x[1]["new"]))
    for i, r in order:
        new = (r.get("new") or "").strip()
        if r["op"] == "insert_after":
            lines = text.split("\n")
            hit = [k for k, ln in enumerate(lines) if re.sub(r"^\s*(?:-\s+)?", "", ln).strip() == new]
            if len(hit) != 1:
                continue
            del lines[hit[0]]
            text = "\n".join(lines)
        elif text.count(new) == 1:
            text = text.replace(new, r["anchor"])
        else:
            continue
        led[i]["status"], led[i]["why"] = "reverted", "분량 초과: 이번 회차 추가분부터 되돌림(trim)"
        out["reverted"].append(r.get("id") or i)
        open(mdp, "w", encoding="utf-8").write(text)
        if budget(run)["ok"]:
            break
    ea.save_ledger(lp, led)
    b = budget(run)
    out["over"] = None if b["ok"] else {k: c for k, c in b["chapters"].items() if not c["ok"]}
    rr.setdefault("fixes", {}).setdefault(str(n), {})["trim"] = out
    save_rounds(run, rr)
    split(run)
    return out


def _ledger_rows(run: str, n: int) -> list[dict]:
    lp = os.path.join(run, LEDGER)
    return [r for r in (json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []) if r.get("round") == n]


def floor_fails(run: str) -> set:
    """지금 70_machine.json 에서 실패한 floor 체크(권장 warn 제외)."""
    m = (_jload(os.path.join(run, "70_machine.json"), {}) or {}).get("checks") or {}
    return {k for k, v in m.items() if v.get("ok") is False and v.get("severity") != "warn"}


def _op_checks(r: dict) -> set:
    return set(re.findall(r"[A-Z]-[mjf]\d+", str(r.get("check") or "")))


def fix_defects(run: str, n: int | None = None, floors: set | None = None) -> dict:
    """plan_t4fix 5: 이번 회차에 배정된 floor 체크마다 그 체크를 고친 op 가 원고에 남아 있는지 본다.
    하나도 남지 않았으면(op 없음·거부·trim 되돌림·뒤 작성자가 덮어씀) 「수정 미적용」 결함이다: 고치려다 실패한 것과 다르다.
    반환 {체크: {"authors": [...], "state": "…"}}. 남은 op 가 있으면(적용했는데 실패) 여기 넣지 않는다."""
    rr = rounds(run)
    n = int(rr.get("round", 0)) if n is None else n
    fx = (rr.get("fixes") or {}).get(str(n)) or {}
    assigned = {}
    for cid in fx.get("editor") or []:
        assigned.setdefault(cid, []).append("editor")
    for s, cids in (fx.get("writer") or {}).items():
        for cid in cids:
            assigned.setdefault(cid, []).append(f"writer:{s}")
    floors = floor_fails(run) if floors is None else floors
    text = open(os.path.join(run, "30_proposal.md"), encoding="utf-8").read()
    lp = os.path.join(run, LEDGER)
    led = [r for r in (json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []) if r.get("round") == n]
    def alive(r: dict) -> bool:
        """적용한 줄이 원고에 남았는가. 같은 작성자가 그 줄을 다시 고쳤으면(허용) 뒤 수정을 따라간다."""
        cur, seen = r, 0
        while seen < 20:
            after = (cur.get("line_after") or cur.get("new") or "").strip()
            if after and after in text:
                return True
            cur = next((q for q in led if q.get("status") == "applied" and (q.get("line_before") or "").strip() == after), None)
            if cur is None or not after:
                return False
            seen += 1
        return False

    out = {}
    for cid, authors in assigned.items():
        if cid not in floors:
            continue
        ops = [r for r in led if cid in _op_checks(r)]
        if any(r["status"] == "applied" and alive(r) for r in ops):
            continue
        mech = {"F-m8": "check_captions", "C-m6": "check_blank"}.get(cid)   # op 없이 기계가 고치는 것(캡션 번호 매김)은 원고로 다시 잰다
        if mech:
            sys.path.insert(0, HERE)
            if __import__(mech).check_text(text)[0]:
                continue
        states = []
        for r in ops:
            if r["status"] == "applied":
                states.append(f"{r['author']} #{r.get('id')} 덮어씀(원고에 없음)")
            elif r["status"] == "reverted":
                states.append(f"{r['author']} #{r.get('id')} 되돌림({r.get('why', '')[:40]})")
            else:
                states.append(f"{r['author']} #{r.get('id')} 거부({r.get('why', '')[:60]})")
        out[cid] = {"authors": authors, "state": "; ".join(states) or "op 없음"}
    return out


def record_defects(run: str, retry: bool = False) -> dict:
    """trim 뒤(retry=False)와 재적용 뒤(retry=True)에 수정 미적용 결함을 72_rounds.fixes[n] 에 적는다.
    재적용은 회차당 한 번: 재적용 뒤에도 남은 결함은 보고서에 「결함」으로 남고, 정지 규칙(연속 실패)에는 세지 않는다."""
    rr = rounds(run)
    n = str(rr.get("round", 0))
    fx = rr.setdefault("fixes", {}).setdefault(n, {})
    d = fix_defects(run, int(n))
    if retry:
        fx["retry"] = {"before": fx.get("defects") or {}, "after": d}
    fx["defects"] = d
    save_rounds(run, rr)
    return d


def figures(run: str) -> list[dict]:
    p = os.path.join(run, "20_spec.md")
    if mode_of(run) != "final" or not os.path.exists(p):
        return []
    t = open(p, encoding="utf-8").read()
    m = re.search(r"^## 7\..*?(?=^## |\Z)", t, re.M | re.S)
    if not m:
        return []
    rows = []
    for ln in m.group(0).splitlines():
        if ln.startswith("|") and "---" not in ln:
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(c) >= 6 and c[0] not in ("#",) and c[5]:
                rows.append({"#": c[0], "name": c[1], "section": c[2], "why": c[3], "tool": c[4], "approved": c[5]})
    return rows


# ── 조립·집계·회차 ────────────────────────────────────────────────────────
def _sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else ""


def rounds(run: str) -> dict:
    return _jload(os.path.join(run, "72_rounds.json"), None) or {"round": 0, "history": [], "fixes": {}, "sha": {}}


def save_rounds(run: str, r: dict) -> None:
    _jdump(os.path.join(run, "72_rounds.json"), r)


def assemble(run: str, repro: bool = False) -> int:
    """harness_assemble.py 를 부른다. --repro: PYTHONHASHSEED 1·2 로 두 번 빌드해 sha 가 같아야 한다(실측: set 순회로 달라졌다)."""
    hwpx = os.path.join(run, "30_proposal.hwpx")
    seeds = ["1", "2"] if repro else [None]
    shas, rc = [], 0
    for s in seeds:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        if s:
            env["PYTHONHASHSEED"] = s
        # --loop: 내용 위반(대시·R1~R7·쪽수 초과)은 조립을 멈추지 않고 rc 3 → 기계 검사·수정 회차가 절로 되돌린다.
        #   rc 2 는 도구 오류(원고 없음·form_strip·그림·kordoc·테두리)뿐이다 (t1 2026-09-27: R3·R6 로 회차 0 에서 멈췄다).
        r = subprocess.run([sys.executable, os.path.join(HERE, "harness_assemble.py"), "--run", run, "--loop"], env=env,
                           capture_output=True, text=True, errors="replace")
        tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-8:]
        print("\n".join("   " + ln for ln in tail))
        rc = r.returncode
        if rc == 2:
            return 2
        shas.append(_sha(hwpx))
    rr = rounds(run)
    rr.setdefault("sha", {})[str(rr.get("round", 0))] = shas[-1]
    if repro and len(set(shas)) != 1:
        print(f"   ✖ 재현성 실패: sha 가 다르다 {[s[:12] for s in shas]}")
        save_rounds(run, rr)
        return 2
    if repro:
        rr["repro"] = {"ok": True, "sha": shas[-1][:16]}
    save_rounds(run, rr)
    print(f"   sha256 {shas[-1][:16]}…" + (" (시드 2종 동일)" if repro else "") + ("  ⚠ 쪽수 미측정(기계 검사가 잰다)" if rc == 1 else "")
          + ("  ⚠ 내용 위반 있음: 기계 검사 → 수정 회차가 해당 절로 되돌린다" if rc == 3 else ""))
    return 0


def score(run: str, rubric_path: str | None = None) -> dict:
    """70_machine.json + 70_judge.json + rubric → 70_score.json. 72_rounds.json 에 이번 회차 결과를 적는다."""
    sys.path.insert(0, HERE)
    import check_rubric as cr
    rubric = load_rubric(rubric_of(run, rubric_path))
    machine = _jload(os.path.join(run, "70_machine.json"), {}) or {}
    judge = _jload(os.path.join(run, "70_judge.json"), None)
    sc = cr.score_items(rubric, machine, judge, mode_of(run))
    scoring = rubric.get("scoring") or {}
    target = float(scoring.get("target", 95))
    unmet = unmet_checks(run, rubric)
    judge_no = sorted(k for k, v in ((judge or {}).get("judgments") or {}).items() if not v.get("ok"))
    floor_fail = sorted(k for k, v in (machine.get("checks") or {}).items() if v.get("ok") is False and v.get("severity") != "warn")
    rr = rounds(run)
    out = {"date": today(), "round": rr.get("round", 0), "total": sc["total"], "target": target,
           "reached": sc["total"] >= target, "items": sc["items"], "judge_no": judge_no, "floor_fail": floor_fail,
           "unmet": {k: v for k, v in unmet.items()}, "judge_present": judge is not None}
    _jdump(os.path.join(run, "70_score.json"), out)
    hist = [h for h in rr.get("history", []) if h.get("round") != out["round"]]
    defects = sorted(((rr.get("fixes") or {}).get(str(out["round"])) or {}).get("defects") or {})
    hist.append({"round": out["round"], "total": sc["total"], "judge_no": judge_no, "floor_fail": floor_fail, "date": today(),
                 "defects": defects})
    rr["history"] = sorted(hist, key=lambda h: h["round"])
    save_rounds(run, rr)
    return out


def fix_list(run: str, rubric_path: str | None = None, begin: bool = False) -> dict:
    """실패 체크 → fix_by 묶음. unmet(답 없는 needs)은 뺀다. --begin 이면 회차를 올리고 계획을 72_rounds 에 적는다."""
    rubric = load_rubric(rubric_of(run, rubric_path))
    judge = (_jload(os.path.join(run, "70_judge.json"), {}) or {}).get("judgments") or {}
    machine = (_jload(os.path.join(run, "70_machine.json"), {}) or {}).get("checks") or {}
    unmet = unmet_checks(run, rubric)
    checks = {c["id"]: c for _, _, c in all_checks(rubric, mode_of(run))}
    groups = {"unify": [], "editor": [], "writer": {}, "unmet": sorted(unmet), "reasons": {}}
    fails = [(cid, str(v.get("section") or "*"), (v.get("why") or "")[:160], None) for cid, v in judge.items() if not v.get("ok")]
    # machine 실패는 check_rubric 이 적은 「고칠 절」(sections)로 간다. 절을 모르는 문서 전체 체크는 편집자 몫.
    #   (2026-09-27 t1 전: applies_to 가 「*」인 floor 실패는 writer["*"] 로 들어가 next 에서 버려졌다)
    fails += [(cid, "*", (v.get("detail") or "")[:160], list(v.get("sections") or [])) for cid, v in machine.items()
              if v.get("ok") is False and v.get("severity") != "warn"]
    for cid, sec, why, msecs in fails:
        if cid in unmet:
            continue
        groups["reasons"][cid] = why
        c = checks.get(cid, {})
        fb = fix_by_of(c)
        if "unify" in fb:
            groups["unify"].append(cid)
        if "editor" in fb:
            groups["editor"].append(cid)
        if "writer" in fb or ("unify" not in fb and "editor" not in fb):
            ap = [s for s in (c.get("applies_to") or ["*"]) if s != "*"]
            if msecs is not None:
                targets = msecs or ap
                if not targets:
                    groups["editor"].append(cid)
            else:
                targets = [sec] if sec != "*" else (ap or ["*"])
            for s in targets:
                groups["writer"].setdefault(s, []).append(cid)
    for k in ("unify", "editor"):
        groups[k] = sorted(set(groups[k]))
    groups["writer"] = {s: sorted(set(v)) for s, v in groups["writer"].items()}
    if begin:
        rr = rounds(run)
        rr["round"] = int(rr.get("round", 0)) + 1
        rr.setdefault("fixes", {})[str(rr["round"])] = {k: groups[k] for k in ("unify", "editor", "writer", "unmet")}
        save_rounds(run, rr)
        groups["round"] = rr["round"]
        mdp = os.path.join(run, "30_proposal.md")
        if os.path.exists(mdp):
            _write_locked(run, rr["round"], open(mdp, encoding="utf-8").read())
    return groups


def repeated_floor(rr: dict, unmet=()) -> list[str]:
    """직전 두 회차(수정 회차를 사이에 둔 연속 채점)에 모두 실패한 floor 체크. 미충족(답 없는 key)은 뺀다.
    2026-09-27 사용자 결정: 조립·기계 검사 실패는 절로 되돌려 고치고, 같은 체크가 2회 연속 실패할 때만 멈춘다."""
    # 되돌린 회차의 실패는 원고에 남아 있지 않다. 회차 0(첫 초안)은 수정을 시도하지 않았으므로 세지 않는다
    #   (사용자 결정 2026-09-28, plan_t4fix: 연속 실패는 수정을 시도한 회차끼리만. t4 는 B-m1 이 초안·1회차 실패로 한 번 고치고 멈췄다).
    h = [x for x in rr.get("history", []) if not x.get("reverted") and x.get("round", 0) >= 1]
    if len(h) < 2 or h[-1]["round"] != h[-2]["round"] + 1:
        return []
    # plan_t4fix 5: 고친 op 가 원고에 남지 않은 체크(수정 미적용 결함)는 「고치려 했는데 실패」가 아니므로 세지 않는다
    tried = lambda x: set(x.get("floor_fail") or []) - set(x.get("defects") or [])
    return sorted(tried(h[-1]) & tried(h[-2]) - set(unmet))


def stalled(rr: dict, stall_rounds: int) -> bool:
    if not stall_rounds:
        return False
    h, last = [], None
    for x in rr.get("history", []):                         # 되돌린 회차(adopt 불채택)는 오르지 않은 회차로 센다
        last = last if (x.get("reverted") and last is not None) else x["total"]
        h.append(last)
    if len(h) < stall_rounds + 1:
        return False
    tail = h[-(stall_rounds + 1):]
    return all(tail[i + 1] <= tail[i] for i in range(len(tail) - 1))


# ── 다음 단계 결정 ─────────────────────────────────────────────────────────
def next_step(run: str, rubric_path: str | None = None, evidence_dir: str | None = None) -> dict:
    """산출물의 존재·신선도(mtime)와 70_score.json 으로 다음 단계와 액션을 정한다. 멱등: 같은 상태면 같은 답."""
    P = lambda f: os.path.join(run, f)
    rub = rubric_of(run, rubric_path)
    ev = evidence_of(run, evidence_dir) or "<evidence>/_ws"
    mode = mode_of(run)
    py = sys.executable
    S = lambda name: os.path.join(HERE, name)
    root = root_of(run)

    def step(k, why, actions):
        return {"step": k, "why": why, "round": rounds(run).get("round", 0), "actions": actions, "mode": mode,
                "external_ai": external_ai_of(run), "evidence": ev, "rubric": rub}

    if not os.path.exists(P("requirements.md")):
        return step("requirements", "requirements.md 가 없다", [{"do": "stop", "text": "requirements.md(title·mode·external_ai·evidence) 를 만든다"}])
    if not os.path.exists(P("20_spec.md")):
        return step("spec", "설계서 없음", [
            {"do": "agent", "agent": "rp-spec", "inputs": {"template": os.path.join(root, "criteria", "spec_template.md"), "rubric": rub,
                                                          "requirements": P("requirements.md"), "form_spec": P("50_form_spec.json"),
                                                          "evidence": ev, "mode": mode}, "output": P("20_spec.md")}])
    if not os.path.exists(P("21_questions.md")):
        return step("gaps", "빈칸 목록 없음", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "gaps", "--run", run]}])
    consent = _jload(P("23_consent.json"), {}) or {}
    if not consent.get("asked") or not spec_approved(run):
        return step("ask", "시작 질문(1회) 전", [
            {"do": "ask", "items": ["20_spec.md 설계서 승인(§1 사슬표·§2 KPI 추적·§8 미확정 목록을 보여 준다)",
                                    "21_questions.md 의 빈칸 답(모르면 「없음」: 그 체크는 미충족으로 남긴다). "
                                    "「[floor]」 행은 답이 없으면 그 floor 체크가 미충족으로 확정되니 따로 짚어 묻는다",
                                    f"외부 전송 동의 (예/아니오): 원고 본문 전문(30_proposal.build.md)이 {external_ai_of(run)} 웹 화면으로 나간다. "
                                    "쓰는 곳: 외부 교정(문제 목록만 받음, proofread: " + proofread_of(run) + ")·완료 판정 블라인드 비교·교정 효과 실험. "
                                    "아니오면 외부 모델 단계를 모두 건너뛰고 블라인드는 Claude 심판만 쓴다. "
                                    + _sensitive_note(run)]
                             + (["final: 20_spec.md §7 그림 후보 중 승인할 번호"] if mode == "final" else []),
             "then": [py, S("rp_run.py"), "answers", "--run", run, "--spec-approved", "--external", "<yes|no>"]
                     + (["--figures", "<1,2,…>"] if mode == "final" else [])}])
    if consent.get("target_down") and "target_down_ok" not in consent:
        return step("ask_down", "시작 질문 답의 목표가 설계서 기준보다 낮다(이 항목만 한 번 확인)", [
            {"do": "ask", "items": [f"{d['key']}: 기준 「{d['base']}」 → 답 「{d['new']}」 ({d['label']}). "
                                    "그대로 둘까요(예), 답을 고칠까요(고칠 값을 21_questions.md 「답」 열에 적는다)?"
                                    for d in consent["target_down"]],
             "then": [py, S("rp_run.py"), "answers", "--run", run, "--confirm-down", "<yes|no>"]}])
    if mode == "final" and consent.get("figures") and not os.path.isdir(P("figures")):
        return step("figures", "final: 승인된 그림 후보를 만든다", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "figures", "--run", run]},
                                                               {"do": "agent", "agent": "rnd-figure:rp-figure", "rows": figures(run)}])
    if not os.path.exists(P("30_proposal.md")):
        secs = sections(run)
        return step("write", "원고 없음: 절별 집필", [
            {"do": "cmd", "cmd": [py, S("writer_brief.py"), "--run", run, "--section", s, "--rubric", rub, "--evidence", ev, "--mode", mode]} for s in secs]
            + [{"do": "agent", "agent": "rp-writer", "parallel": True, "briefs": {s: P(os.path.join("briefs", f"brief_{s}.md")) for s in secs},
                "output": {s: P(os.path.join("sections", f"{s}.md")) for s in secs}},
               {"do": "cmd", "cmd": [py, S("rp_run.py"), "merge", "--run", run]}])
    rq = rounds(run)
    nq = int(rq.get("round", 0))
    fq = (rq.get("fixes") or {}).get(str(nq)) or {}
    if fq.get("defects") and "retry" not in fq:
        # ★ plan_t4fix 5: floor 를 고친 op 가 원고에 남지 않았다(op 없음·거부·되돌림·덮어씀). 결함으로 보고하고 같은 회차에서 한 번 재적용한다.
        d = fq["defects"]
        by = {}
        for cid, v in d.items():
            for a in v["authors"]:
                by.setdefault(a, []).append(cid)
        acts = []
        wsecs = [a.split(":", 1)[1] for a in by if a.startswith("writer:")]
        for s in wsecs:
            acts.append({"do": "cmd", "cmd": [py, S("writer_brief.py"), "--run", run, "--section", s, "--rubric", rub, "--evidence", ev,
                                              "--mode", mode, "--fix", "--only", ",".join(by[f"writer:{s}"])]})
        if wsecs:
            acts.append({"do": "agent", "agent": "rp-writer", "parallel": True, "for": {s: by[f"writer:{s}"] for s in wsecs},
                         "reasons": {s: {c: d[c]["state"] for c in by[f"writer:{s}"]} for s in wsecs},
                         "briefs": {s: P(os.path.join("briefs", f"brief_{s}.md")) for s in wsecs},
                         "output": {s: P(os.path.join("edits", f"r{nq}_{s}_retry.json")) for s in wsecs}})
            acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "apply-edits", "--run", run]})
        if "editor" in by:
            acts.append({"do": "agent", "agent": "rp-editor", "for": by["editor"], "reasons": {c: d[c]["state"] for c in by["editor"]},
                         "inputs": {"md": P("30_proposal.md"), "report": P("70_채점보고.md"), "glossary": os.path.join(ev, "15_axis_conflicts.md"),
                                    "form_spec": P("50_form_spec.json"), "evidence": ev, "locked": P(os.path.join("edits", f"r{nq}_locked.md"))},
                         "output": P(os.path.join("edits", f"r{nq}_editor_retry.json"))})
            acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "apply-edits", "--run", run]})
        acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "trim", "--run", run]})
        acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "defects", "--run", run, "--retry"]})
        return step("retry", f"수정 미적용 결함 {', '.join(d)}: 같은 회차에서 한 번 재적용 "
                             + "; ".join(f"{c}: {v['state']}" for c, v in d.items())[:300], acts)
    md_t = _mtime(P("30_proposal.md"))
    if _mtime(P("30_proposal.hwpx")) < md_t or _mtime(P("30_proposal.build.md")) < md_t:
        return step("assemble", "원고가 hwpx 보다 새롭다", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "assemble", "--run", run, "--repro"]},
                                                        {"do": "cmd", "cmd": [py, S("rp_run.py"), "split", "--run", run]}])
    hw_t = _mtime(P("30_proposal.hwpx"))
    rr0 = rounds(run)
    prev_md = P(os.path.join("rounds", f"r{rr0.get('adopted')}", "30_proposal.build.md")) if rr0.get("adopted") is not None else None
    if _mtime(P("70_machine.json")) < hw_t:
        # C-m5 정보 보존: 수정 회차는 직전 채택 판을 전 판으로 잰다(plan_v2 3단계 10)
        before = ["--before", prev_md] if prev_md and rr0.get("round", 0) > rr0.get("adopted", 0) and os.path.exists(prev_md) else []
        return step("machine", "기계 검사가 hwpx 보다 오래됐다", [
            {"do": "cmd", "cmd": [py, S("check_rubric.py"), "--rubric", rub, "--md", P("30_proposal.build.md"), "--hwpx", P("30_proposal.hwpx"),
                                  "--spec", P("50_form_spec.json"), "--pack", ev, "--requirements", P("requirements.md"), "--mode", mode,
                                  "--report", P("70_machine.json"), "--no-fail"] + before}])
    if _mtime(P("70_judge.json")) < hw_t:
        return step("judge", "채점이 원고보다 오래됐다", [
            {"do": "agent", "agent": "rp-scorer", "inputs": {"rubric": rub, "machine": P("70_machine.json"), "md": P("30_proposal.build.md"),
                                                            "hwpx": P("30_proposal.hwpx"), "form_spec": P("50_form_spec.json"), "spec": P("20_spec.md"),
                                                            "glossary": os.path.join(ev, "15_axis_conflicts.md"), "mode": mode},
             "output": [P("70_judge.json"), P("70_채점보고.md")]}])
    if _mtime(P("70_score.json")) < _mtime(P("70_judge.json")):
        return step("tally", "집계 전", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "score", "--run", run]}])
    sc = _jload(P("70_score.json"), {}) or {}
    rr = rounds(run)
    n = int(rr.get("round", 0))
    if str(n) not in (rr.get("adopt") or {}):               # 교정 회차도 채택 판정을 거친다
        if n == 0 or rr.get("adopted") is None:
            return step("adopt", "회차 0: 스냅숏(rounds/r0)", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "adopt", "--run", run]}])
        bd = P(os.path.join("rounds", f"r{n}", "blind"))
        prep = [py, S("blind_compare.py"), "prepare", "--a", prev_md, "--b", P("30_proposal.build.md"),
                "--label-a", "prev", "--label-b", "cur", "--out", bd]
        if consent.get("external_ai"):
            # ★ plan_t4fix 6 (2026-09-28): 회차 채택 심판은 외부 모델(ChatGPT). 원고를 Claude 가 썼으므로 Claude 심판은
            #   동의가 없거나 ChatGPT 절차가 실패했을 때만 쓰고 「자기 평가 편향 가능」으로 표시한다(t4 회차 1: Claude 6/6 cur).
            return step("adopt", f"회차 {n} 채택 판정: 정보 보존·쪽수·ChatGPT 블라인드(직전 채택 r{rr['adopted']} 대 이번 판)", [
                {"do": "cmd", "cmd": prep + ["--judge", "chatgpt"]},
                {"do": "skill", "skill": "rp-blind", "inputs": {"dir": bd, "judge": "chatgpt"},
                 "fallback": {"text": "ChatGPT 절차가 실패하면 같은 dir 에 --judge claude 로 다시 prepare 하고 Claude 심판 2회(새 에이전트)",
                              "cmd": prep + ["--judge", "claude"]}},
                {"do": "cmd", "cmd": [py, S("rp_run.py"), "adopt", "--run", run]}])
        return step("adopt", f"회차 {n} 채택 판정: 정보 보존·쪽수·Claude 블라인드(외부 전송 동의 없음: 자기 평가 편향 가능)", [
            {"do": "cmd", "cmd": prep + ["--judge", "claude"]},
            {"do": "agent", "agent": "general-purpose", "parallel": True, "blind": True,
             "text": "rp-blind 스킬 3의 Claude 심판: 회마다 새 에이전트에 아래 두 문장만 준다(맥락·문서 이름 금지)",
             "prompts": {k: f"{os.path.join(bd, f'prompt_{k}.md')} 를 Read 로 읽고 그 지시대로 답하라. 다른 파일은 읽지 마라. "
                            f"답(표 하나)을 {os.path.join(bd, f'response_{k}.md')} 에 Write 로 저장하라." for k in ("1", "2")}},
            {"do": "cmd", "cmd": [py, S("rp_run.py"), "adopt", "--run", run]}])
    scoring = load_rubric(rub).get("scoring") or {}
    max_rounds = int(scoring.get("max_rounds", 6))
    stall_n = int(scoring.get("stall_rounds", 0))
    rep = repeated_floor(rr, sc.get("unmet") or {})
    if rep and not rr.get("proofread"):                     # 같은 floor 체크 2회 연속 실패: 보고하고 멈춘다(교정·제출 안 함)
        why = f"floor 체크 {', '.join(rep)} 2회 연속 실패 (회차 {rr.get('round', 0)}): 멈추고 보고한다"
        if not rr.get("reported"):
            return step("report", why, [{"do": "cmd", "cmd": [py, S("rp_run.py"), "report", "--run", run]}])
        return step("stopped", why, [{"do": "stop", "text": why + ". 90_제출보고.md 의 정지 사유를 사람에게 보고한다"}])
    if not rr.get("proofread"):
        reached, over, stall = bool(sc.get("reached")), rr.get("round", 0) >= max_rounds, stalled(rr, stall_n)
        if not (reached or over or stall):
            g = fix_list(run, rubric_path)
            nr = n + 1                                        # fix-list --begin 이 올릴 회차 번호
            acts = [{"do": "cmd", "cmd": [py, S("rp_run.py"), "fix-list", "--run", run, "--begin"]}]
            if g["unify"]:
                acts.append({"do": "cmd", "for": g["unify"], "cmd": [py, S("unify_terms.py"), "--md", P("30_proposal.md"), "--evidence", ev,
                                                                   "--notation", os.path.join(root, "criteria", "notation.yaml"),
                                                                   "--ledger", P("62_통일치환.md"), "--pack", ev]})
            # ★ 고치기 모드 (plan_v2 3단계 9): 편집자·집필자는 원고를 고치지 않고 op(JSON)만 쓴다. apply-edits 가 적용하고 거부한다.
            # ★ 순서 (plan_t4fix 1, 2026-09-28): 집필자(실패 위치가 정해진 절) → 편집자(문서 전체). 한 칸은 한 작성자만 고친다:
            #   편집자는 집필자가 이번 회차에 고친 줄 목록(edits/r<n>_locked.md)을 받고, 그 줄을 건드리는 op 는 apply-edits 가 거부한다.
            #   t4 는 편집자 → 집필자 순이라 편집자 수정 11건이 집필자에게 덮어써졌다(S-m2 「(영문)」 포함).
            secs = [s for s in g["writer"] if s != "*"]
            for s in secs:
                acts.append({"do": "cmd", "cmd": [py, S("writer_brief.py"), "--run", run, "--section", s, "--rubric", rub, "--evidence", ev,
                                                  "--mode", mode, "--fix", "--only", ",".join(g["writer"][s])]})
            if secs:
                acts.append({"do": "agent", "agent": "rp-writer", "parallel": True, "for": g["writer"],
                             "briefs": {s: P(os.path.join("briefs", f"brief_{s}.md")) for s in secs},
                             "output": {s: P(os.path.join("edits", f"r{nr}_{s}.json")) for s in secs}})
                acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "apply-edits", "--run", run]})
            if g["editor"]:
                acts.append({"do": "agent", "agent": "rp-editor", "for": g["editor"], "reasons": {k: g["reasons"].get(k, "") for k in g["editor"]},
                             "inputs": {"md": P("30_proposal.md"), "report": P("70_채점보고.md"), "glossary": os.path.join(ev, "15_axis_conflicts.md"),
                                        "form_spec": P("50_form_spec.json"), "evidence": ev,
                                        "locked": P(os.path.join("edits", f"r{nr}_locked.md"))},
                             "output": P(os.path.join("edits", f"r{nr}_editor.json"))})
                acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "apply-edits", "--run", run]})
            if g["editor"] or secs:
                acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "trim", "--run", run]})   # 장 예산 초과: 이번 회차 추가분부터 되돌린다
                acts.append({"do": "cmd", "cmd": [py, S("rp_run.py"), "defects", "--run", run]})  # 수정 미적용 결함(plan_t4fix 5)
            if len(acts) > 1:
                why = f"총점 {sc.get('total')} < 목표 {sc.get('target')} · 회차 {rr.get('round', 0)}/{max_rounds}" + \
                      (f" · 미충족 {list(sc.get('unmet', {}))}" if sc.get("unmet") else "")
                return step("fix", why, acts)
            reason = "수정 대상 없음(남은 실패는 전부 미충족·근거 필요)"
        else:
            reason = "목표 도달" if reached else ("회차 상한" if over else "정체")
        why = f"{reason} (총점 {sc.get('total')}, 목표 {sc.get('target')})"
        if consent.get("external_ai") and proofread_of(run) == "on":
            # ★ plan_v2 4단계 13: 외부 모델에게서는 문제 목록(위치·문제·이유)만 받는다. 고치는 것은 교정 회차의 편집자(op)이고
            #   회차 채택 판정(adopt: C-m5·F-m3·Claude 블라인드)을 거친다. 외부 모델의 문장은 원고에 들어가지 않는다.
            pr = n + 1
            return step("proofread", why + ": 외부 교정(문제 목록) → 교정 회차", [
                {"do": "skill", "skill": "rp-proofread", "inputs": {"md": P("30_proposal.build.md"), "ledger": P("60_교정문제.md"), "external_ai": external_ai_of(run)}},
                {"do": "cmd", "cmd": [py, S("check_proofread.py"), "--problems", P("60_교정문제.md"), "--md", P("30_proposal.md"), "--out", P("60_교정문제.json")]},
                {"do": "cmd", "cmd": [py, S("rp_run.py"), "mark", "--run", run, "--proofread", "done"]},
                {"do": "agent", "agent": "rp-editor", "for": ["교정 문제"], "inputs": {"md": P("30_proposal.md"), "problems": P("60_교정문제.json"),
                                                                                  "glossary": os.path.join(ev, "15_axis_conflicts.md"), "form_spec": P("50_form_spec.json")},
                 "output": P(os.path.join("edits", f"r{pr}_editor.json"))},
                {"do": "cmd", "cmd": [py, S("rp_run.py"), "apply-edits", "--run", run]},
                {"do": "cmd", "cmd": [py, S("rp_run.py"), "trim", "--run", run]}])
        skip = "외부 전송 동의 없음" if not consent.get("external_ai") else f"교정 끔(proofread: {proofread_of(run)}, 기본값은 효과 실험 결과)"
        return step("proofread", why + f": {skip}, 건너뜀", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "mark", "--run", run, "--proofread", "skipped"]}])
    if not rr.get("delivered"):
        out = os.path.join(root, f"제출본_{today()}.hwpx")
        return step("deliver", f"총점 {sc.get('total')} (목표 {sc.get('target')}): 제출 파일", [
            {"do": "cmd", "cmd": [py, S("rp_run.py"), "deliver", "--run", run, "--out", out]}])
    if not rr.get("reported"):
        return step("report", "실행 기록", [{"do": "cmd", "cmd": [py, S("rp_run.py"), "report", "--run", run]}])
    return step("done", f"끝: 총점 {sc.get('total')} (목표 {sc.get('target')}), 미충족 {list(sc.get('unmet', {}))}", [])


def mark(run: str, proofread: str | None = None) -> dict:
    rr = rounds(run)
    if proofread:
        rr["proofread"] = {"skipped": proofread == "skipped", "date": today()}
        if proofread == "done":                             # 교정 회차: 편집자 op 가 이 회차 번호로 쓰이고 adopt 를 거친다
            rr["round"] = int(rr.get("round", 0)) + 1
            probs = _jload(os.path.join(run, "60_교정문제.json"), []) or []
            rr.setdefault("fixes", {})[str(rr["round"])] = {"proofread": len(probs)}
            rr["proofread"]["round"] = rr["round"]
    save_rounds(run, rr)
    return rr


def experiment_decide(exp: str) -> dict:
    """교정 효과 실험 판정 (plan_v2 4단계 15). exp/blind_<심판>/blind.json (문서 이름 「교정」·「미교정」)을 읽는다.
    규칙: 결과가 있는 심판 **모두**에서 교정 적용본 확정 승 1개 이상이고 미교정본 확정 승 0 이면 「켬」, 아니면 「끔」.
    (완료 판정과 같은 이유로 ChatGPT 와 Claude 를 함께 본다: ChatGPT Instant 의 위치 편향, calibration_v2.md)
    exp/85_교정실험.md 에 표와 판정을 쓴다. 판정은 기본값 PROOFREAD_DEFAULT 를 바꿀 근거다(코드 값은 사람이 바꾼다)."""
    sys.path.insert(0, HERE)
    res = {"judges": {}, "decision": "off"}
    for d in sorted(glob.glob(os.path.join(exp, "blind_*", "blind.json"))):
        b = json.load(open(d, encoding="utf-8"))
        name = os.path.basename(os.path.dirname(d)).replace("blind_", "")
        res["judges"][name] = {"교정": b["wins"].get("교정", []), "미교정": b["wins"].get("미교정", []), "bias": b.get("bias")}
    j = res["judges"].values()
    if res["judges"] and all(v["교정"] and not v["미교정"] for v in j):
        res["decision"] = "on"
    L = ["# 교정 효과 실험 (자동 생성)", "", "| 심판 | 교정 적용본 확정 승 | 미교정본 확정 승 | 위치 편향 표시 |", "|---|---|---|---|"]
    for k, v in res["judges"].items():
        L.append(f"| {k} | {', '.join(v['교정']) or '없음'} | {', '.join(v['미교정']) or '없음'} | "
                 f"{', '.join(r for r, x in (v['bias'] or {}).items() if x) or '없음'} |")
    L += ["", f"판정: 교정 **{'켬' if res['decision'] == 'on' else '끔'}** "
              "(규칙: 모든 심판에서 교정 적용본 확정 승 1개 이상·미교정본 확정 승 0). 한 문서 한 번의 실험이라 우연일 수 있다."]
    open(os.path.join(exp, "85_교정실험.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return res


SNAP = ["30_proposal.md", "30_proposal.build.md", "30_proposal.hwpx", "70_machine.json", "70_judge.json", "70_score.json", "70_채점보고.md"]


def _snapshot(run: str, n: int) -> None:
    d = os.path.join(run, "rounds", f"r{n}")
    os.makedirs(d, exist_ok=True)
    for f in SNAP:                                          # copy2: mtime 을 지켜 next 의 신선도 판정이 흔들리지 않게 한다
        if os.path.exists(os.path.join(run, f)):
            shutil.copy2(os.path.join(run, f), os.path.join(d, f))


def _restore(run: str, n: int) -> None:
    d = os.path.join(run, "rounds", f"r{n}")
    for f in SNAP:
        if os.path.exists(os.path.join(d, f)):
            shutil.copy2(os.path.join(d, f), os.path.join(run, f))
    split(run)


def adopt(run: str) -> dict:
    """회차 채택 (plan_v2 3단계 10, 2026-09-28). 회차 0 은 스냅숏만 남긴다(rounds/r0).
    회차 n 은 아래가 모두 참일 때만 채택한다. 하나라도 거짓이면 직전 채택 판(rounds/r<p>)으로 되돌린다.
      - C-m5 정보 보존이 실패가 아님(70_machine: 직전 채택 판을 --before 로 잰 것)
      - 쪽수 floor(F-m3)가 새로 실패하지 않음
      - Claude 블라인드(rounds/r<n>/blind, 직전 판 대 이번 판 A/B 2회)에서 직전 판의 확정 승 항목 0
    되돌린 회차도 정체(stall) 회차로 센다. 기록: 72_rounds.adopt[n], history[n].reverted."""
    sys.path.insert(0, HERE)
    rr = rounds(run)
    n = int(rr.get("round", 0))
    prev = rr.get("adopted")
    res = {"round": n, "prev": prev, "adopted": True, "reasons": []}
    if n > 0 and prev is not None:
        machine = (_jload(os.path.join(run, "70_machine.json"), {}) or {}).get("checks") or {}
        if (machine.get("C-m5") or {}).get("ok") is False:
            res["reasons"].append("C-m5 정보 보존 실패: " + (machine["C-m5"].get("detail") or "")[:120])
        hist = {h["round"]: h for h in rr.get("history", [])}
        if "F-m3" in (hist.get(n, {}).get("floor_fail") or []) and "F-m3" not in (hist.get(prev, {}).get("floor_fail") or []):
            res["reasons"].append("F-m3 쪽수 초과가 새로 생김")
        bd = os.path.join(run, "rounds", f"r{n}", "blind")
        try:
            import blind_compare as bc
            b = bc.tally(bd)
            res["blind"] = b["wins"]
            res["judge"] = b.get("judge")
            res["notes"] = (["자기 평가 편향 가능(Claude 심판)"] if b.get("self_bias") else []) + \
                           ([f"편향 의심(6항목 전부 {b['sweep']})"] if b.get("sweep") else [])
            if b["wins"].get("prev"):
                res["reasons"].append("블라인드에서 직전 판 확정 승: " + ", ".join(b["wins"]["prev"]))
        except SystemExit as e:
            res["reasons"].append(f"블라인드 결과 없음({e}): 채택 근거가 없으므로 되돌린다")
        res["adopted"] = not res["reasons"]
    if res["adopted"]:
        _snapshot(run, n)
        rr["adopted"] = n
    else:
        _restore(run, prev)
        for h in rr.get("history", []):
            if h["round"] == n:
                h["reverted"] = True
        lp = os.path.join(run, LEDGER)
        if os.path.exists(lp):
            import edit_apply as ea
            led = json.load(open(lp, encoding="utf-8"))
            for r in led:
                if r.get("round") == n and r.get("status") == "applied":
                    r["status"], r["why"] = "reverted", "회차 불채택(adopt)"
            ea.save_ledger(lp, led)
    rr.setdefault("adopt", {})[str(n)] = res
    save_rounds(run, rr)
    return res


def deliver(run: str, out: str) -> str:
    src = os.path.join(run, "30_proposal.hwpx")
    if not os.path.exists(src):
        raise SystemExit("30_proposal.hwpx 가 없다: 조립 단계가 먼저다")
    shutil.copy(src, out)
    rr = rounds(run)
    rr["delivered"] = {"path": os.path.abspath(out), "sha": _sha(out)[:16], "date": today()}
    save_rounds(run, rr)
    return out


def report(run: str) -> str:
    """72_rounds·70_score·질문/답 → 90_제출보고.md 에 실행 기록 절을 붙인다."""
    rr, sc = rounds(run), _jload(os.path.join(run, "70_score.json"), {}) or {}
    qs = read_questions(run)
    consent = _jload(os.path.join(run, "23_consent.json"), {}) or {}
    L = ["", "---", "", f"# rp-run 실행 기록 ({today()}, {mode_of(run)} 모드, 자동 생성)", ""]
    L.append(f"총점 **{sc.get('total')}** / 목표 {sc.get('target')} · " + ("목표 도달" if sc.get("reached") else "목표 미달") +
             f" · 수정 회차 {rr.get('round', 0)} · floor 실패 {len(sc.get('floor_fail') or [])} · judge 아니오 {len(sc.get('judge_no') or [])}")
    L += ["", "## 회차별 점수", "", "| 회차 | 총점 | 채택 | judge 아니오 | floor 실패 | 날짜 |", "|---|---:|---|---|---|---|"]
    ad = rr.get("adopt") or {}
    for h in rr.get("history", []):
        a = ad.get(str(h["round"]))
        verdict = "" if a is None else ("채택" if a.get("adopted") else "되돌림: " + "; ".join(a.get("reasons") or [])[:80])
        if a and a.get("judge"):
            verdict += f" (심판 {a['judge']}" + "".join(f" · ★{x}" for x in a.get("notes") or []) + ")"
        L.append(f"| {h['round']} | {h['total']} | {verdict} | {', '.join(h.get('judge_no') or []) or '없음'} | "
                 f"{', '.join(h.get('floor_fail') or []) or '없음'} | {h.get('date', '')} |")
    if rr.get("fixes"):
        L += ["", "## 회차별 수정 묶음 (고치기 모드: 원장 74_수정원장.md)", ""]
        for k, v in rr["fixes"].items():
            L.append(f"- {k}회차: unify {v.get('unify') or '없음'} · editor {v.get('editor') or '없음'} · writer {v.get('writer') or '없음'} · 미충족 {v.get('unmet') or '없음'}")
            ed = v.get("edits") or {}
            if ed:
                L.append(f"  - op 적용 {ed.get('applied', 0)} · 거부 {ed.get('rejected', 0)}")
            tr = v.get("trim") or {}
            if tr.get("reverted"):
                L.append(f"  - 분량: 이번 회차 추가분 {len(tr['reverted'])}건 되돌림" + (f" · 여전히 초과 {list(tr['over'])}장" if tr.get("over") else ""))
            locked = [r for r in _ledger_rows(run, int(k)) if str(r.get("why", "")).startswith(("슬롯 잠김", "앞 수정 되돌림"))]
            if locked:
                L.append(f"  - 충돌 막음 {len(locked)}건: " + "; ".join(f"{r['author']} #{r.get('id')} {r['why'][:50]}" for r in locked)[:400])
            rt = v.get("retry")
            if rt:
                L.append(f"  - ★ 결함(수정 미적용) {', '.join(rt.get('before') or {}) or '없음'} → 한 번 재적용 → 남은 결함 "
                         + ("; ".join(f"{c}: {x['state']}" for c, x in (rt.get('after') or {}).items()) or "없음"))
    rep = repeated_floor(rr, sc.get("unmet") or {})
    if rep:
        L += ["", "## 정지 사유", "",
              f"- floor 체크 {', '.join(rep)} 가 회차 {rr['history'][-2]['round']}·{rr['history'][-1]['round']} 에 연속 실패했다. "
              "수정 회차가 절로 되돌렸으나 고치지 못했다: 외부 교정·제출 복사를 하지 않았다."]
        for cid in rep:
            d = ((_jload(os.path.join(run, "70_machine.json"), {}) or {}).get("checks") or {}).get(cid) or {}
            L.append(f"  - {cid}: {d.get('detail', '')[:200]} · 고칠 절 {d.get('sections') or '편집자'}")
    srcs = _jload(os.path.join(run, "22_answer_sources.json"), {}) or {}
    L += ["", "## 시작 질문과 답", "", "| 체크 | key | 묻는 것 | 답 | 출처 |", "|---|---|---|---|---|"]
    for q in qs:
        s = srcs.get(q["key"]) or {}
        L.append(f"| {q['check']} | {q['key']} | {q['ask']} | {clean_answer(q['answer']) or '없음'} | "
                 + (f"{s.get('source', '')} {s.get('date', '')}".strip() or ("근거팩" if q.get("where") == "근거팩 대장" else "없음")) + " |")
    if not qs:
        L.append("| 해당 없음 | | | | |")
    L += ["", f"외부 교정 동의: {'예' if consent.get('external_ai') else '아니오'} · 교정 단계: " +
          ("건너뜀" if (rr.get("proofread") or {}).get("skipped") else ("실행" if rr.get("proofread") else "미실행"))]
    if sc.get("unmet"):
        L += ["", "## 미충족 체크 (근거 없음, 집필로 해결 불가)", ""]
        for k, v in sc["unmet"].items():
            L.append(f"- {k}: {', '.join(v)}")
    if sc.get("judge_no"):
        L += ["", "## 남은 judge 아니오", "", "- " + " · ".join(sc["judge_no"])]
    d = rr.get("delivered") or {}
    L += ["", f"제출 파일: {d.get('path', '미복사')} (sha {d.get('sha', '')}) · 재현성: " + ("시드 2종 sha 동일" if (rr.get("repro") or {}).get("ok") else "미확인"), ""]
    p = os.path.join(run, "90_제출보고.md")
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n".join(L))
    rr["reported"] = today()
    save_rounds(run, rr)
    return p


RESUME_INPUTS = ["requirements.md", "50_form_spec.json", "20_spec.md", "21_questions.md", "22_answer_sources.json",
                 "23_consent.json", "30_raw.hwpx"]


def resume(src: str, n: int, dst: str) -> dict:
    """빠른 재현 (plan_t4fix 7): src 의 채택 회차 n 스냅숏에서 새 워크스페이스 dst 를 만들어 회차 n+1 부터 돌린다.
    처음부터 다시 집필하지 않고 고친 코드를 확인한다: `rp_run.py resume --from t4 --round 1 --to t4-r2` → `/rp-run t4-r2`.
      - 입력·설계서·시작 질문 답·동의, rounds/r0..rn, edits/r0..rn 을 복사하고 rn 스냅숏을 현재 원고로 복원한다.
      - 72_rounds·원장을 회차 n 까지로 자르고 제출·보고·교정 표시를 지운다.
      - 회차 n-1·n 의 기계 검사를 **지금 검사기로** 다시 재고(옛 검사기 오류가 정지 규칙에 남지 않게), 회차 n 의
        수정 미적용 결함을 계산해 history 에 넣는다. judge 는 스냅숏의 것을 그대로 쓴다."""
    rr = rounds(src)
    if str(n) not in (rr.get("adopt") or {}) or not rr["adopt"][str(n)].get("adopted"):
        raise SystemExit(f"회차 {n} 은 채택 회차가 아니다(72_rounds.adopt): 채택된 회차에서만 다시 시작한다")
    if os.path.exists(os.path.join(dst, "72_rounds.json")):
        raise SystemExit(f"{dst} 에 이미 실행 기록이 있다: 새 폴더를 준다")
    os.makedirs(dst, exist_ok=True)
    for f in RESUME_INPUTS:
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    for k in range(n + 1):
        d = os.path.join(src, "rounds", f"r{k}")
        if os.path.isdir(d):
            shutil.copytree(d, os.path.join(dst, "rounds", f"r{k}"))
    os.makedirs(os.path.join(dst, "edits"), exist_ok=True)
    for p in glob.glob(os.path.join(src, "edits", "r*_*")):
        m = re.match(r"r(\d+)_", os.path.basename(p))
        if m and int(m.group(1)) <= n:
            shutil.copy2(p, os.path.join(dst, "edits", os.path.basename(p)))
    sys.path.insert(0, HERE)
    import edit_apply as ea
    lp = os.path.join(src, LEDGER)
    if os.path.exists(lp):
        ea.save_ledger(os.path.join(dst, LEDGER), [r for r in json.load(open(lp, encoding="utf-8")) if (r.get("round") or 0) <= n])
    keep = lambda d: {k: v for k, v in (d or {}).items() if int(k) <= n}
    new = {"round": n, "adopted": n, "history": [h for h in rr.get("history", []) if h["round"] <= n],
           "fixes": keep(rr.get("fixes")), "adopt": keep(rr.get("adopt")), "sha": keep(rr.get("sha")),
           "resumed": {"from": os.path.abspath(src), "round": n, "date": today()}}
    save_rounds(dst, new)
    _restore(dst, n)
    # 지금 검사기로 회차 n-1·n 을 다시 잰다
    import check_rubric as cr
    rub, ev, mode = rubric_of(dst), evidence_of(dst), mode_of(dst)
    machine = {}
    for k in (n - 1, n):
        d = os.path.join(dst, "rounds", f"r{k}")
        if k < 0 or not os.path.isdir(d):
            continue
        before = os.path.join(dst, "rounds", f"r{k - 1}", "30_proposal.build.md") if k > 0 else None
        rep = cr.run_rubric(rub, os.path.join(d, "30_proposal.build.md"), os.path.join(d, "30_proposal.hwpx"),
                            os.path.join(dst, "50_form_spec.json"), pack=ev, requirements=os.path.join(dst, "requirements.md"),
                            mode=mode, quiet=True, before=before if before and os.path.exists(before) else None)
        json.dump(rep, open(os.path.join(d, "70_machine.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        machine[k] = {c for c, v in (rep.get("checks") or {}).items() if v.get("ok") is False and v.get("severity") != "warn"}
    shutil.copy(os.path.join(dst, "rounds", f"r{n}", "70_machine.json"), os.path.join(dst, "70_machine.json"))
    x = rounds(dst)
    for h in x["history"]:
        if h["round"] in machine:
            h["floor_fail"] = sorted(machine[h["round"]])
    if n > 0:
        fx = x.setdefault("fixes", {}).setdefault(str(n), {})
        fx["defects"] = fix_defects(dst, n, machine.get(n - 1, set())) if n - 1 in machine else {}
        fx["retry"] = {"before": fx["defects"], "after": fx["defects"], "note": "resume: 원 실행에는 재적용 단계가 없었다"}
    save_rounds(dst, x)
    sc = score(dst)
    for f in ("70_judge.json", "70_score.json"):                # 신선도: machine < judge < score (hwpx 보다 뒤)
        os.utime(os.path.join(dst, f), None)
    return {"round": n, "floor_fail": sc["floor_fail"], "defects": sorted((x["fixes"].get(str(n)) or {}).get("defects") or {}),
            "next": next_step(dst)["step"]}


def init(src: str, dst: str) -> list[str]:
    """입력만 복사한 새 워크스페이스: requirements.md · 50_form_spec.json. 산출물은 복사하지 않는다."""
    os.makedirs(dst, exist_ok=True)
    copied = []
    for f in ("requirements.md", "50_form_spec.json"):
        p = os.path.join(src, f)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(dst, f))
            copied.append(f)
    return copied


# ── CLI ────────────────────────────────────────────────────────────────────
def _print_actions(s: dict) -> None:
    print(f"[{s['step']}] {s['why']}  (회차 {s['round']}, 모드 {s['mode']})")
    for a in s["actions"]:
        if a["do"] == "cmd":
            print("  $ " + " ".join(f'"{x}"' if " " in str(x) else str(x) for x in a["cmd"]) + (f"   # {a['for']}" if a.get("for") else ""))
        elif a["do"] == "agent":
            print(f"  Agent({a['agent']}" + (", 병렬" if a.get("parallel") else "") + ")" + (f"  체크 {a['for']}" if a.get("for") else ""))
            for k, v in (a.get("briefs") or a.get("inputs") or {}).items():
                print(f"      {k}: {v}")
        elif a["do"] == "ask":
            print("  ★ 사용자에게 한 번에 묻는다:")
            for it in a["items"]:
                print("     - " + it)
            print("    답을 받은 뒤: " + " ".join(str(x) for x in a["then"]))
        elif a["do"] == "skill":
            print(f"  Skill({a['skill']}) {a.get('inputs', {})}")
        else:
            print(f"  ({a['do']}) {a.get('text', '')}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "next", "gaps", "answers", "sections", "fix-list", "figures", "merge", "split", "leads",
                                    "check-section", "budget", "apply-edits", "trim", "defects", "adopt", "experiment-decide", "assemble", "score", "mark", "deliver", "report", "init", "resume"])
    ap.add_argument("--run")
    ap.add_argument("--rubric")
    ap.add_argument("--evidence")
    ap.add_argument("--section")
    ap.add_argument("--out")
    ap.add_argument("--md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--begin", action="store_true")
    ap.add_argument("--repro", action="store_true")
    ap.add_argument("--spec-approved", action="store_true")
    ap.add_argument("--external")
    ap.add_argument("--figures")
    ap.add_argument("--confirm-down")
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--round", type=int)
    ap.add_argument("--proofread")
    ap.add_argument("--from", dest="src")
    ap.add_argument("--to", dest="dst")
    a = ap.parse_args()
    if a.cmd not in ("init", "resume", "experiment-decide") and not a.run:
        ap.error("--run")
    if a.cmd == "plan":
        print(f"mode={mode_of(a.run)} external_ai={external_ai_of(a.run)} evidence={evidence_of(a.run, a.evidence)}")
        for i, (k, d) in enumerate(plan(a.run), 1):
            print(f"  {i:>2}. {k:<13} {d}")
    elif a.cmd == "next":
        s = next_step(a.run, a.rubric, a.evidence)
        print(json.dumps(s, ensure_ascii=False, indent=1)) if a.json else _print_actions(s)
    elif a.cmd == "gaps":
        rows = gaps(a.run, a.rubric, a.evidence)
        blanks = [r for r in rows if not r["found"]]
        print(f"needs {len(rows)}건 · 근거팩에 있음 {len(rows) - len(blanks)} · 빈칸 {len(blanks)} → 21_questions.md")
        for r in blanks:
            print(f"  {r['check']:<5} {r['key']:<16} {r['ask']}  (찾아본 곳: {r['where']})")
    elif a.cmd == "answers":
        c = answers(a.run, a.evidence, True if a.spec_approved else None, a.external, a.figures, a.confirm_down)
        print(f"답 {len(c.get('answered') or [])}건 → 16_user_answers.md · 미충족 key {c.get('unmet')} · 설계서 승인 {c.get('spec_approved')} · 외부 교정 {c.get('external_ai')}")
        for d in c.get("target_down") or []:
            print(f"  목표 하향: {d['key']} 「{d['base']}」 → 「{d['new']}」")
        if c.get("target_down") and "target_down_ok" not in c:
            return 3
    elif a.cmd == "sections":
        print(" ".join(sections(a.run)))
    elif a.cmd == "fix-list":
        g = fix_list(a.run, a.rubric, a.begin)
        if a.json:
            print(json.dumps(g, ensure_ascii=False, indent=1))
        else:
            print(f"unify: {g['unify'] or '없음'}\neditor: {g['editor'] or '없음'}\nwriter: {g['writer'] or '없음'}\n미충족(제외): {g['unmet'] or '없음'}"
                  + (f"\n회차 → {g['round']}" if a.begin else ""))
    elif a.cmd == "figures":
        rows = figures(a.run)
        print(json.dumps(rows, ensure_ascii=False, indent=1) if a.json else
              ("\n".join(f"  {r['#']} {r['name']} ({r['section']}, {r['tool']}) 승인={r['approved']}" for r in rows) or "  승인된 그림 없음"))
    elif a.cmd == "merge":
        r = merge(a.run)
        print(f"병합 {len(r['merged'])}절: {' '.join(r['merged'])}" + (f"  · 제목 없음: {r['no_heading']}" if r["no_heading"] else ""))
    elif a.cmd == "split":
        r = split(a.run)
        print(f"절 파일 갱신 {len(r['changed'])}절: {' '.join(r['changed'])}" + (f"  · 제목 없음: {r['no_heading']}" if r["no_heading"] else ""))
    elif a.cmd == "leads":
        r = leads(a.run, a.md)
        print("리드 골격 OK" if r["ok"] else f"리드 누락 {r['missing']} · 순서 어긋남 {r['order']}")
        return 0 if r["ok"] else 2
    elif a.cmd == "check-section":
        r = check_section(a.run, a.section)
        for x, b, ph, sa, sb in r["r4"]:
            other = b if x.startswith(a.section) else x
            print(f"  [R4] ↔ {other[:16]} 겹침 「{ph}」  이 절: 「{(sa if x.startswith(a.section) else sb)[:80]}…」")
        for t, why in r["r5"]:
            print(f"  [R5] {why} | 「{t[:90]}…」")
        if not r["r4"] and not r["r5"]:
            print(f"  {a.section}: 절 간 중복 0 · 과압축 0")
        ln = r["length"]
        if ln:
            print(f"  분량 {ln['current']:,}자 / 상한 {ln['cap']:,}자" + ("" if ln["ok"] else
                  f" : {ln['current'] - ln['cap']:,}자 초과. 새 문장을 더하지 말고 교체·합치기(merge)로 고친다. 넘으면 trim 이 이번 회차 추가분부터 되돌린다"))
        return 2 if (r["r4"] or r["r5"] or (ln and not ln["ok"])) else 0
    elif a.cmd == "budget":
        r = budget(a.run, a.md)
        for k, c in r["chapters"].items():
            print(f"  {k}장 {c['now']:,}자 / 예산 {c['budget']:,}자" + ("" if c["ok"] else f" : {c['now'] - c['budget']:,}자 초과"))
        for s in r["sections"]:
            print(f"    {s['section']:<5} {s['current']:>6,}자 (몫 {s['target']:,}자)")
        return 0 if r["ok"] else 2
    elif a.cmd == "apply-edits":
        r = apply_edits(a.run)
        print(f"  고치기 모드: 적용 {r['applied']} · 거부 {r['rejected']} (파일 {', '.join(r['files']) or '없음'}) → {LEDGER}")
    elif a.cmd == "trim":
        r = trim(a.run)
        print(f"  분량: 되돌린 op {len(r['reverted'])}건" + (f" · 여전히 초과 {list(r['over'])}장" if r["over"] else " · 장 예산 안"))
    elif a.cmd == "defects":
        d = record_defects(a.run, a.retry)
        print(f"  수정 미적용 결함 {len(d)}건" + ("(재적용 뒤)" if a.retry else "") + "".join(f"\n    {c}: {v['state']}" for c, v in d.items()))
    elif a.cmd == "experiment-decide":
        r = experiment_decide(a.out)
        print(f"  교정 효과 실험: {r['judges']} → 교정 {'켬' if r['decision'] == 'on' else '끔'} ({os.path.join(a.out, '85_교정실험.md')})")
    elif a.cmd == "adopt":
        r = adopt(a.run)
        print(f"  회차 {r['round']}: " + ("채택" if r["adopted"] else f"불채택 → r{r['prev']} 로 되돌림 ({'; '.join(r['reasons'])})"))
    elif a.cmd == "assemble":
        return assemble(a.run, a.repro)
    elif a.cmd == "score":
        s = score(a.run, a.rubric)
        print(f"총점 {s['total']} / 목표 {s['target']} → {'도달' if s['reached'] else '미달'} · 회차 {s['round']} · judge 아니오 {s['judge_no']} · floor 실패 {s['floor_fail']} · 미충족 {list(s['unmet'])}")
    elif a.cmd == "mark":
        mark(a.run, a.proofread)
        print("기록됨")
    elif a.cmd == "deliver":
        print("→ " + deliver(a.run, a.out))
    elif a.cmd == "report":
        print("→ " + report(a.run))
    elif a.cmd == "init":
        print("복사: " + ", ".join(init(a.src, a.dst)) + f" → {a.dst}")
    elif a.cmd == "resume":
        r = resume(a.src, a.round, a.dst)
        print(f"회차 {r['round']} 스냅숏에서 시작 → {a.dst} · 지금 검사기 floor 실패 {r['floor_fail'] or '없음'} · "
              f"회차 {r['round']} 수정 미적용 결함 {r['defects'] or '없음'} · 다음 단계 [{r['next']}]")
        print(f"이어서: /rp-run {a.dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
