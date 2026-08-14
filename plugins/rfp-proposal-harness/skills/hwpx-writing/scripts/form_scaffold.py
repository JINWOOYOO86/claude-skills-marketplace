#!/usr/bin/env python3
"""양식 명세 → 원고 골격(스캐폴드) 생성.

양식이 요구하는 **장·절 제목을 원문 그대로** 박아 넣고, 각 절 밑에 그 절이 요구하는
**세부 설명(가이드)** 을 `<!--FORM-GUIDE …-->` 주석으로 넣는다.

  · 집필자는 주석을 **보면서** 그 항목을 빠짐없이 채운다.
  · 조립 직전에 `form_strip.py` 가 주석을 **전량 제거**한다(산출물에 설명문이 남으면 감점).
  · `gate_form.py` 가 ① 제목 축자 일치 ② 항목 커버리지 ③ 설명문 잔존 0 을 기계로 확인한다.

사용:
  python3 form_scaffold.py --spec <form_spec.json> -o 30_proposal.md [--force]

종료코드 0=생성, 1=거부(덮어쓰기 방지), 2=실행 오류.
"""
import argparse, json, os, sys


def build(spec):
    pb = spec.get("page_budget", {})
    ch_budget = pb.get("chapters", {})
    lim = spec.get("limits", {})
    out = []
    out.append("<!--FORM-GUIDE _budget")
    out.append(f"[분량] 전체 {pb.get('total','?')}p 내외 (상한 {pb.get('hard_max','?')}p) — {pb.get('basis','')}")
    out.append("[배분] " + " / ".join(f"{k}장 {v}p" for k, v in ch_budget.items()))
    out.append(f"[상한] 산문 {lim.get('prose_chars','?')}자 · 표 {lim.get('tables','?')}개"
               f"(열 {lim.get('table_cols_max','?')} 이하) · 그림 {lim.get('figures','?')}장")
    ws = spec.get("writing_style") or {}
    if ws.get("mode"):
        out.append(f"[서술] **{ws['mode']}** — 마크다운 중첩 목록으로 쓰면 조립 도구가 "
                   + " / ".join(f"{v}({k}단계)" for k, v in (ws.get("markers") or {}).items())
                   + " 로 조판한다. 말머리를 직접 타이핑하지 않는다.")
        out.append(f"       각 항목은 **명사형 종결**({'/'.join((ws.get('preferred_endings') or [])[:6])})로 끝내고, "
                   f"{'/'.join((ws.get('forbidden_endings') or [])[:4])} 는 쓰지 않는다. "
                   f"한 항목 {ws.get('max_item_chars', 160)}자 이내, 깊이 {ws.get('max_depth', 2)}단계까지.")
    out.append("[규율] 제목은 한 글자도 바꾸지 않는다. 절을 새로 만들지 않는다.")
    out.append("       이 주석은 조립 전에 form_strip.py 가 전부 지운다 — 지우지 않고 빌드하면 게이트가 FAIL 한다.")
    out.append("-->")
    out.append("")
    out.append("# (과제명을 여기에)")
    out.append("")

    for node in spec["outline"]:
        hashes = "#" * node["level"]
        out.append(f"{hashes} {node['title']}")
        out.append("")
        guides = node.get("guide") or []
        if guides:
            out.append(f"<!--FORM-GUIDE {node['id']}")
            for g in guides:
                out.append(f"· {g}")
            probes = node.get("probes") or []
            if probes:
                out.append("[게이트 확인 항목] " + " / ".join(p["key"] for p in probes))
            sp = [e["key"] if isinstance(e, dict) else e for e in (node.get("special") or [])]
            if sp:
                out.append("[지정 서식] " + " / ".join(sp))
            chap = node["id"].split("-")[0]
            if chap in ch_budget:
                out.append(f"[분량] {chap}장 배분 {ch_budget[chap]}p 안에서 소화한다")
            out.append("-->")
            out.append("")
        bp = node.get("blueprint") or []
        if bp:
            # ★ 골격 = 1단계(□) 리드 + 2단계(ㅇ) 슬롯까지 고정한다.
            #   실측: 리드만 고정하면 리드 38개는 100% 일치해도 ㅇ 문장이 갈려 유사도가 0.56 에 머문다.
            #   슬롯의 key 는 확정 수치 대장에서 인용할 항목이다 — 같은 값이면 같은 문장이 나온다.
            for item in bp:
                if isinstance(item, str):
                    out.append(f"- **{item}** — (한 줄 결론)")
                    out.append("  - (근거·수치·출처 — 확정 수치 대장에서만 인용)")
                    continue
                out.append(f"- **{item['lead']}** — (한 줄 결론)")
                for sl in item.get("slots", []):
                    key = sl.get("key")
                    tail = f"(대장 `{key}` 값 인용)" if key else "(근거·수치·출처)"
                    out.append(f"  - {sl['text']} — {tail}")
            out.append("")
        elif node["level"] == 3 and (spec.get("writing_style") or {}).get("mode") == "개조식":
            out.append("- **(논점을 한 줄로)** — (핵심 근거 요약)")
            out.append("  - (근거·수치·출처)")
            out.append("")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="양식 명세 JSON (default_form_spec.json 또는 01_template_spec.json)")
    ap.add_argument("-o", "--out", required=True, help="생성할 원고 골격 경로")
    ap.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    if os.path.exists(a.out) and not a.force:
        print(f"거부: {a.out} 이 이미 있다. 덮어쓰려면 --force (원고 유실 방지)")
        return 1
    open(a.out, "w", encoding="utf-8").write(build(spec))
    n_sec = sum(1 for n in spec["outline"] if n["level"] == 3)
    n_guide = sum(len(n.get("guide") or []) for n in spec["outline"])
    print(f"생성: {a.out} — 장 {sum(1 for n in spec['outline'] if n['level']==2)}개 · 절 {n_sec}개 · 가이드 항목 {n_guide}개")
    print("다음: 가이드 주석을 보며 본문을 채운 뒤 form_strip.py 로 주석을 제거하고 조립한다.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
