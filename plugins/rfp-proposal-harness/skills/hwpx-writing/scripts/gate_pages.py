#!/usr/bin/env python3
"""규율 L — 분량 실측 게이트 (총 쪽수 + 장별 배분).

**분량은 추정으로 통과시키지 않는다.** 한컴 COM 으로 HWPX 를 열어 `PageCount` 를 읽고,
같은 문서를 PDF 로 저장해 **장 제목이 몇 쪽에서 시작하는지**를 판독한다.
그래야 「총량은 맞는데 3장이 2배로 부푼」 상태를 잡을 수 있다.

  실측 경로: HWPX ──한컴 COM──→ PageCount + PDF ──PyMuPDF──→ 장별 시작쪽 → 장별 점유 쪽수
  대조 기준: 양식 명세의 page_budget (총 10p 내외 / 상한 12p / 0:1 1:2 2:2 3:3 4:2)

★ 장별 점유 쪽수의 정의 — 다음 장이 시작하기 전까지 소모한 쪽수(= 다음 장 시작쪽 − 이 장 시작쪽,
  마지막 장은 총쪽수 − 시작쪽 + 1). 합이 총쪽수와 정확히 일치한다. 한 쪽을 두 장이 나눠 쓰면
  뒤 장이 그 쪽을 가져간다(경계 쪽 이중 계상 방지).

사용(WSL 기준):
  python3 gate_pages.py --hwpx 30_proposal.hwpx --spec .../default_form_spec.json \
      [--md 30_proposal.build.md] [--json gate_pages.json] [--allow-estimate]

전제: Windows 에 한컴오피스(HWPFrame.HwpObject) + PyMuPDF(fitz) 를 가진 파이썬.
      없으면 추정 모드로 내려가며, `--allow-estimate` 없이는 **통과를 발급하지 않는다**.

종료코드 0=PASS, 1=FAIL(또는 미측정), 2=실행 오류.
"""
import argparse, json, os, re, subprocess, sys, tempfile

PS_TEMPLATE = r"""
param([string]$src, [string]$dst)
$ErrorActionPreference = "Stop"

# ★★ 실측 사고(2026-08-14): 같은 파일이 9p / 11p 로 **번갈아** 측정됐다.
#    원인은 앞선 호출이 남긴 **머리 없는(창 없는) Hwp 인스턴스**다. New-Object 가 ROT 에 등록된
#    기존 인스턴스에 붙는데, 그 인스턴스마다 조판 상태가 달라 쪽수가 흔들린다.
#    → 창 제목이 없는(=사용자가 열어둔 문서가 아닌) 잔류 인스턴스만 정리하고 시작한다.
#    창이 있는 인스턴스는 **절대 건드리지 않는다**(사용자 문서 유실 방지).
$titled = @()
foreach ($p in (Get-Process Hwp -ErrorAction SilentlyContinue)) {
  if ([string]::IsNullOrEmpty($p.MainWindowTitle)) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  } else { $titled += $p.MainWindowTitle }
}
if ($titled.Count -gt 0) { Write-Output ("TITLED_HWP=" + ($titled -join "|")) }
Start-Sleep -Milliseconds 300

$hwp = New-Object -ComObject HWPFrame.HwpObject
try { $null = $hwp.RegisterModule("FilePathCheckDLL","FilePathCheckerModule") } catch { }
$null = $hwp.Open($src, "", "forceopen:true")
$null = $hwp.HAction.Run("MoveDocEnd")     # 조판을 끝까지 밀어 쪽수를 확정시킨다
Write-Output ("PAGECOUNT=" + $hwp.PageCount)
$null = $hwp.SaveAs($dst, "PDF", "")
Write-Output ("SAVED=" + (Test-Path -LiteralPath $dst))
$hwp.Quit()
"""

FITZ_TEMPLATE = r"""
import fitz, json, re, sys
pdf, titles_json, out = sys.argv[1], sys.argv[2], sys.argv[3]
titles = json.load(open(titles_json, encoding='utf-8'))
d = fitz.open(pdf)
pages = [re.sub(r'\s+', '', p.get_text()) for p in d]
res, cursor = [], 0
for t in titles:
    key = re.sub(r'\s+', '', t['title'])
    start, frac = None, 0.0
    for i in range(cursor, len(pages)):
        if key in pages[i]:
            start, cursor = i + 1, i
            # 쪽 안에서의 세로 위치까지 잡아야 「경계 쪽을 누가 얼마나 썼는지」가 나온다
            page = d[i]
            hits = page.search_for(t['title'])
            if hits:
                top = page.rect.y0 + 0.0
                frac = max(0.0, min(1.0, (hits[0].y0 - top) / page.rect.height))
            break
    res.append({'id': t['id'], 'title': t['title'], 'start': start, 'frac': round(frac, 3)})
json.dump({'total': d.page_count, 'chapters': res},
          open(out, 'w', encoding='utf-8'), ensure_ascii=False)
"""


def win(path):
    return subprocess.check_output(["wslpath", "-w", os.path.abspath(path)], text=True).strip()


def have(cmd):
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def measure(hwpx, chapters, winpython):
    """(total, {id: start_page}, note) — 실패 시 (None, {}, 사유)."""
    if not have("powershell.exe"):
        return None, {}, "powershell.exe 없음(WSL/Windows 환경 아님)"
    try:
        tmp_win = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", "$env:TEMP"], text=True).strip()
    except Exception as e:
        return None, {}, f"Windows TEMP 조회 실패: {e}"
    wdir_win = tmp_win + r"\rfp_gate_pages"
    subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                    f"New-Item -ItemType Directory -Force -Path '{wdir_win}' | Out-Null"],
                   capture_output=True)
    wdir_wsl = subprocess.check_output(["wslpath", "-u", wdir_win], text=True).strip()
    src_win = wdir_win + r"\gate.hwpx"
    pdf_win = wdir_win + r"\gate.pdf"
    subprocess.run(["cp", os.path.abspath(hwpx), os.path.join(wdir_wsl, "gate.hwpx")], check=True)

    ps = os.path.join(wdir_wsl, "topdf.ps1")
    # ★ 함정(실측 2026-08-14): PowerShell 5.1 은 BOM 없는 .ps1 을 **ANSI(cp949)** 로 읽는다.
    #   한글 주석의 UTF-8 바이트가 깨지면서 그 뒤 줄이 문자열로 먹혀 `PAGECOUNT=` 출력이
    #   통째로 사라졌다(에러 없이!). **utf-8-sig(BOM)** 로 써야 한다.
    open(ps, "w", encoding="utf-8-sig").write(PS_TEMPLATE)
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", win(ps), "-src", src_win, "-dst", pdf_win],
                       capture_output=True, text=True, errors="replace")
    m = re.search(r"PAGECOUNT=(\d+)", r.stdout or "")
    if not m:
        return None, {}, f"한컴 COM 실패: {(r.stdout + r.stderr)[:200]}"
    total = int(m.group(1))
    warn = ""
    tm = re.search(r"TITLED_HWP=(.+)", r.stdout or "")
    if tm:
        warn = (f"주의: 한글 창이 열려 있다({tm.group(1).strip()[:60]}) — "
                "열린 인스턴스에 붙으면 쪽수가 흔들릴 수 있다. 닫고 재측정 권장")
    if "SAVED=True" not in r.stdout or not os.path.exists(os.path.join(wdir_wsl, "gate.pdf")):
        return total, {}, (warn + " / " if warn else "") + "PDF 저장 실패 — 총 쪽수만 실측(장별 배분 미측정)"

    if not os.path.exists(winpython):
        return total, {}, (warn + " / " if warn else "") + f"PyMuPDF 파이썬 없음({winpython}) — 장별 배분 미측정"
    tj = os.path.join(wdir_wsl, "titles.json")
    json.dump(chapters, open(tj, "w", encoding="utf-8"), ensure_ascii=False)
    fp = os.path.join(wdir_wsl, "an.py")
    open(fp, "w", encoding="utf-8").write(FITZ_TEMPLATE)
    outp = os.path.join(wdir_wsl, "spans.json")
    r2 = subprocess.run([winpython, win(fp), pdf_win, win(tj), win(outp)],
                        capture_output=True, text=True, errors="replace")
    if not os.path.exists(outp):
        return total, {}, (warn + " / " if warn else "") + f"PDF 판독 실패: {(r2.stdout + r2.stderr)[:200]}"
    data = json.load(open(outp, encoding="utf-8"))
    starts = {c["id"]: (c["start"], c.get("frac", 0.0)) for c in data["chapters"]}
    if data["total"] != total:
        # PDF 가 최종 인쇄물이므로 PDF 쪽수를 정본으로 삼는다
        return data["total"], starts, (warn + " / " if warn else "") + \
            f"주의: PageCount({total}) ≠ PDF 쪽수({data['total']}) — PDF 값을 채택"
    return total, starts, warn


def estimate(md_text, spec):
    """실측 불가 시의 추정 — 실측을 대체하지 않는다(측정 원단위는 default_form_rules.md §2)."""
    prose = len(re.sub(r"\s+", "", re.sub(r"^\|.*$", "", md_text, flags=re.M)))
    tables = re.findall(r"(?:^\|.*$\n)+", md_text, re.M)
    tp = 0.0
    for t in tables:
        cols = t.strip().split("\n")[0].count("|") - 1
        tp += 0.5 if cols <= 4 else (0.8 if cols <= 6 else 1.1)
    figs = len(re.findall(r"^!\[", md_text, re.M))
    return prose / 1750 + tp + figs


def chapter_stats(md_text, chapters):
    """장별 산문 자수·표 개수·최대 열수·그림 수 — 초과 원인 분해용."""
    idx, stats = [], {}
    for c in chapters:
        m = re.search(r"^#{2}\s+" + re.escape(c["title"]) + r"\s*$", md_text, re.M)
        idx.append((c["id"], m.start() if m else None))
    for i, (cid, pos) in enumerate(idx):
        if pos is None:
            continue
        nxt = next((p for _, p in idx[i + 1:] if p is not None), len(md_text))
        seg = md_text[pos:nxt]
        tbls = re.findall(r"(?:^\|.*$\n)+", seg, re.M)
        cols = [t.strip().split("\n")[0].count("|") - 1 for t in tbls]
        stats[cid] = {
            "prose": len(re.sub(r"\s+", "", re.sub(r"^\|.*$", "", seg, flags=re.M))),
            "tables": len(tbls),
            "max_cols": max(cols) if cols else 0,
            "figs": len(re.findall(r"^!\[", seg, re.M)),
        }
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hwpx", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--md", help="조립용 원고 — 초과 원인 분해·추정 폴백용")
    ap.add_argument("--winpython", default="/mnt/c/ProgramData/anaconda3/python.exe",
                    help="PyMuPDF(fitz)를 가진 Windows 파이썬")
    ap.add_argument("--allow-estimate", action="store_true",
                    help="한컴이 없을 때 추정치로 통과를 발급(기본: 미측정은 통과 불가)")
    ap.add_argument("--json")
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    pb = spec["page_budget"]
    chapters = [{"id": n["id"], "title": n["title"]} for n in spec["outline"] if n["level"] == 2]
    md_text = open(a.md, encoding="utf-8").read() if a.md and os.path.exists(a.md) else ""

    total, starts, note = measure(a.hwpx, chapters, a.winpython)
    fails, rows = [], []

    if total is None:
        est = estimate(md_text, spec) if md_text else None
        print(f"[미측정] 쪽수 실측 불가 — {note}")
        if est:
            print(f"  추정 {est:.1f}p (원단위 기반, 실측 아님)")
        if not a.allow_estimate:
            print("\nFAIL — 쪽수 미측정 상태에서는 통과를 발급하지 않는다(규율 L).")
            return 1
        print("\nWARN — 추정치로 진행(--allow-estimate). 보고서에 「쪽수 미측정」을 명시할 것.")
        return 0

    print(f"■ 총 쪽수 실측 = {total}p  (목표 {pb['total']}p 내외 · 상한 {pb['hard_max']}p)")
    if note:
        print(f"  {note}")
    if total > pb["hard_max"]:
        fails.append(f"총 분량 {total}p > 상한 {pb['hard_max']}p ({total-pb['hard_max']}p 초과)")
    elif total > pb["total"]:
        print(f"  주의: 목표 {pb['total']}p 를 {total-pb['total']}p 초과(상한 이내)")

    if starts and all(v[0] for v in starts.values()):
        stats = chapter_stats(md_text, chapters) if md_text else {}
        ids = [c["id"] for c in chapters]
        # 연속 위치(쪽 + 쪽 안 세로 비율) 로 점유량을 잰다 — 경계 쪽을 나눠 쓰는 실제를 반영한다.
        # 합은 총 쪽수와 정확히 일치한다.
        pos = {cid: (starts[cid][0] - 1) + starts[cid][1] for cid in ids}
        TOL = float(pb.get("chapter_tolerance", 0.25))
        print(f"\n■ 장별 점유 쪽수 (연속 측정 · 허용오차 ±{TOL}p)")
        print(f"{'장':<4}{'시작':>7}{'점유':>7}{'배분':>6}{'판정':>9}   원인 분해")
        for i, cid in enumerate(ids):
            occ = (pos[ids[i + 1]] - pos[cid]) if i + 1 < len(ids) else (total - pos[cid])
            bud = pb["chapters"].get(cid)
            ok = bud is None or occ <= bud + TOL
            st = stats.get(cid, {})
            cause = (f"산문 {st['prose']:,}자 · 표 {st['tables']}개(최대 {st['max_cols']}열) · 그림 {st['figs']}장"
                     if st else "")
            start_lbl = f"p{starts[cid][0]}+{starts[cid][1]:.2f}"
            print(f"{cid:<4}{start_lbl:>7}{occ:>7.1f}{(bud if bud is not None else '-'):>6}"
                  f"{('OK' if ok else f'+{occ-bud:.1f}p'):>9}   {cause}")
            rows.append({"id": cid, "start_page": starts[cid][0], "start_frac": starts[cid][1],
                         "occupied": round(occ, 2), "budget": bud, "ok": ok, **st})
            if not ok:
                fails.append(f"{cid}장 {occ:.1f}p > 배분 {bud}p ({occ-bud:.1f}p 초과)")
    else:
        print("  장별 배분 미측정 — 총량만 판정한다")

    ok = not fails
    print(f"\n{'='*60}\n{'PASS' if ok else 'FAIL'} — 위반 {len(fails)}건")
    for f in fails:
        print(f"  - {f}")
    if not ok:
        print("\n감축 순서(실측): ① 7열 이상 표의 열 축소·각주 이관 → ② 표 개수 통합 →"
              " ③ 그림 축소 → ④ 산문. 행을 줄이는 것은 효과가 가장 작다.")
    if a.json:
        json.dump({"pass": ok, "total": total, "budget": pb, "chapters": rows,
                   "fails": fails, "note": note},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"결과 JSON: {a.json}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"실행 오류: {e}")
        sys.exit(2)
