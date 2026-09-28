# -*- coding: utf-8 -*-
"""rubric v1 보정 — 81점 심사평의 감점 위치를 floor 실패로 재현하면 채점식이 81 을 내는가.

기준 파일은 개선 빌드(양식 겸 샘플.hwpx + 30_proposal.build.md)라 결함이 이미 고쳐져 있다.
그래서 심사평이 이름을 댄 결함을 픽스처로 **되살려** 넣고, 각 결함이 어느 항목을 깎는지 본다.
    F-m1 줄간격 혼재   ← 표 안 문단을 130% 로 되돌림 (심사평 「약 절반 130%」)
    L-m1 판정 원칙 충돌 ← 「동시에 충족」 + 「절충안」 문장 추가
    C-m1 실행 조건 누락 ← 모델·학습셋·판정·운전조건·상태영역 문장 삭제
    B-m1 절 간 중복     ← 1-1 슬롯을 4-1 에 복제 (심사평 「여러 섹션에서 반복」)
    S-m1 과압축         ← 조사 분리·쉼표 절 접속 문장 추가
ceiling(judge) 은 전부 통과로 가정한다 — 심사평이 그 밖의 결함을 적지 않았다.
"""
import json
import os
import re
import shutil
import zipfile

import pytest

from conftest import KORDOC_OUT, ROOT, needs

HANDOFF = os.path.dirname(KORDOC_OUT)
# 보정 기준은 **개선본(2026-09-26 판)** 이다 — 작업 중인 원고가 아니라 prev/ 에 고정한 사본을 본다.
BUILD_MD = os.path.join(HANDOFF, "workspace", "proj", "prev", "30_proposal.build.prev.md")
SPEC = os.path.join(HANDOFF, "workspace", "proj", "50_form_spec.json")
RUBRIC = os.path.join(HANDOFF, "criteria", "rubric.yaml")

import sys
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_rubric as cr  # noqa: E402


def _r(md_text, hwpx_path, tmp):
    """R1~R7 만 (게이트·한컴 없이) 돌려 체크 id 결과를 만든다."""
    md = tmp / "b.md"
    md.write_text(md_text, encoding="utf-8")
    fails, warns = cr.check(str(md), hwpx_path, SPEC)
    return cr.r_results(fails, warns)


def _report_from_r(rubric, rres):
    """R 계열만 채운 기계 보고 — 그 밖의 machine 체크는 통과로 둔다(양식 겸 샘플 실측 기준)."""
    checks = {}
    for item, tier, c in cr.iter_checks(rubric, "submission"):
        if c.get("by") != "machine":
            continue
        impl = c.get("impl") or []
        impl = [impl] if isinstance(impl, str) else impl
        ok = True
        for im in impl:
            r, _, k = im.partition(":")
            if r == "check_rubric" and k in rres and rres[k][0] is False:
                ok = False
        checks[c["id"]] = {"item": item, "tier": tier, "ok": ok, "severity": c.get("severity", "fail"),
                           "penalty_weight": c.get("penalty_weight", 1)}
    return {"checks": checks}


def _spacing_130_in_tables(src, dst):
    """표 안 문단의 줄간격만 130% 로 되돌린 hwpx 를 만든다(81점 상태 재현)."""
    with zipfile.ZipFile(src) as z:
        data = {n: z.read(n) for n in z.namelist()}
        infos = {i.filename: i for i in z.infolist()}
    hdr = data["Contents/header.xml"].decode("utf-8")
    sec = data["Contents/section0.xml"].decode("utf-8")
    items = {m.group(1): m.group(0) for m in re.finditer(r'(?s)<hh:paraPr id="(\d+)".*?</hh:paraPr>', hdr)}
    spans = [(m.start(), m.end()) for m in re.finditer(r"<hp:tbl\b.*?</hp:tbl>", sec, re.S)]
    in_tbl = lambda pos: any(a <= pos < b for a, b in spans)
    used = sorted({m.group(1) for m in re.finditer(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', sec) if in_tbl(m.start())}, key=int)
    nxt = max(map(int, items)) + 1
    mapping, clones = {}, []
    for oid in used:
        clone = re.sub(r'^<hh:paraPr id="\d+"', f'<hh:paraPr id="{nxt}"', items[oid])
        clone, n = re.subn(r'(<hh:lineSpacing type="PERCENT" value=")\d+(")', r"\g<1>130\g<2>", clone)
        if n:
            clones.append(clone); mapping[oid] = str(nxt); nxt += 1
    hdr = hdr.replace("</hh:paraProperties>", "".join(clones) + "</hh:paraProperties>", 1)
    cm = re.search(r'<hh:paraProperties itemCnt="(\d+)"', hdr)
    hdr = hdr.replace(cm.group(0), f'<hh:paraProperties itemCnt="{int(cm.group(1)) + len(clones)}"', 1)
    def swap(m):
        return (m.group(0).replace(f'paraPrIDRef="{m.group(1)}"', f'paraPrIDRef="{mapping[m.group(1)]}"')
                if in_tbl(m.start()) and m.group(1) in mapping else m.group(0))
    sec = re.sub(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"', swap, sec)
    data["Contents/header.xml"] = hdr.encode("utf-8")
    data["Contents/section0.xml"] = sec.encode("utf-8")
    with zipfile.ZipFile(dst, "w") as o:
        for n in data:
            o.writestr(infos[n], data[n], zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)


@pytest.fixture(scope="module")
def rubric():
    return cr.load_rubric(RUBRIC)


@needs(BUILD_MD)
def test_baseline_r_checks_all_pass(rubric, tmp_path):
    md = open(BUILD_MD, encoding="utf-8").read()
    rres = _r(md, KORDOC_OUT if os.path.exists(KORDOC_OUT) else None, tmp_path)
    assert all(v[0] is not False for v in rres.values()), rres
    sc = cr.score_items(rubric, _report_from_r(rubric, rres))
    assert sc["total"] == 100.0        # 기계 한정 상한(ceiling 전부 통과 가정)


@needs(BUILD_MD)
@needs(KORDOC_OUT)
def test_reproduce_81_point_review(rubric, tmp_path):
    md = open(BUILD_MD, encoding="utf-8").read()
    # L-m1: 판정 원칙 둘
    md = md.replace("### 3-2. 추진 전략 및 방법론\n",
                    "### 3-2. 추진 전략 및 방법론\n\n- 판정 원칙\n  - 네 축을 동시에 충족해야 하며 미달 시 물성 간 절충안으로 대응함\n", 1)
    # C-m1: 실행 조건 5종 문장 삭제
    md = "\n".join(ln for ln in md.splitlines()
                   if not re.search(r"회귀기|138종|판정 기준|증발 5℃|과열 5K|상태영역은|포화·과열|합격선은", ln))
    # B-m1: 1-1 슬롯을 4-1 에 복제
    dup = "  - 대상은 AI 물질발굴로 도출한 저GWP·무독성 순물질 신냉매이고 적용처는 정격 능력 12 kW 미만 기기임\n"
    md = md.replace("- 활용 분야\n", "- 활용 분야\n" + dup, 1)
    # S-m1: 과압축(조사 분리 + 쉼표 절 접속)
    md = md.replace("- 후속 연구 방향\n", "- 후속 연구 방향\n  - HFO 는 제한 대상이고, 1336mzz 는 목록에 올라 있음, 절차는 2028년경 마무리됨\n", 1)
    # F-m1: 표 안 130%
    hwpx = tmp_path / "s130.hwpx"
    _spacing_130_in_tables(KORDOC_OUT, str(hwpx))

    rres = _r(md, str(hwpx), tmp_path)
    assert rres["R1"][0] is False, rres["R1"]
    assert rres["R2"][0] is False, rres["R2"]
    assert rres["R3"][0] is False, rres["R3"]
    assert rres["R4"][0] is False, rres["R4"]
    assert rres["R5"][0] is False, rres["R5"]

    sc = cr.score_items(rubric, _report_from_r(rubric, rres))
    want = rubric["scoring"]["calibration"]["review_81"]
    got = {k: v["score"] for k, v in sc["items"].items()}
    for item, pts in want.items():
        assert abs(got[item] - pts) <= 1.0, (item, got[item], pts)
    assert abs(sc["total"] - 81) <= 3, sc


@needs(RUBRIC)
def test_cap60_underestimates_logic(rubric, tmp_path):
    """v0 원안(cap60)은 논리 16 을 12 로 낸다 — penalty 를 기본으로 둔 이유의 기록."""
    r2 = {"R1": (True, ""), "R2": (False, "x"), "R3": (True, ""), "R4": (True, ""),
          "R5": (True, ""), "R6": (True, ""), "R7": (True, "")}
    rep = _report_from_r(rubric, r2)
    v0 = dict(rubric, scoring=dict(rubric["scoring"], formula="cap60", base_pct=60, ceiling_pct=40))
    assert cr.score_items(v0, rep)["items"]["논리"]["score"] == 12.0
    assert cr.score_items(rubric, rep)["items"]["논리"]["score"] == 16.0
