#!/usr/bin/env python3
"""rfp-scout 루틴 설정 확인 — 설치 후 첫 실행 전에 사람이 봐야 하는 세 가지.

  ① 연구 키워드      profile.md 의 연구주제·키워드가 채워졌는가 (양식 자리표시자가 남지 않았는가)
  ② 모니터링 주기    스케줄러에 실제로 걸린 작업이 있는가, 요일·시각이 의도와 같은가
  ③ 결과 저장 폴더   result/ 가 있고 쓸 수 있는가, 결과 링크가 어디를 가리키는가

사용법 (루틴 폴더 어디서 불러도 된다 — 자기 위치의 상위 폴더를 루틴 루트로 잡는다):
  python3 scripts/setup_check.py            세 항목 요약 출력 (= --check)
  python3 scripts/setup_check.py --confirm  요약을 보여준 뒤 setup_confirmed.txt 에 확인 기록
  python3 scripts/setup_check.py --json     같은 내용을 JSON 으로 (세션·러너가 읽을 때)

종료 코드:
  0  확인됨, 확인 시점과 변동 없음
  2  미확인 (setup_confirmed.txt 없음)
  3  확인됐지만 그 뒤 키워드·스케줄·결과 폴더 중 하나가 바뀜
  1  profile.md 없음 등 확인 자체가 불가능

러너(run_rfp_scout.sh)는 이 코드를 보고 미확인·변동 상태면 HTML 맨 위에 요약 블록을 띄우고
알림을 한 줄 보낸다. 실행을 막지는 않는다 — 막으면 확인을 잊은 채 몇 주가 조용히 지나간다.

표준 라이브러리만 쓴다. 스케줄러 조회는 Windows(WSL 포함)면 schtasks.exe, 아니면 crontab 이다.
작업 이름을 묻지 않고 "실행할 작업" 에 run_rfp_scout 가 들어간 작업을 찾는다 — 설치자가
작업 이름을 다르게 붙였거나 profile.md 에 적힌 이름이 실제와 다른 경우(실제로 있었다)에도 잡힌다.
"""
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROFILE = os.path.join(ROOT, "profile.md")
RESULT_DIR = os.path.join(ROOT, "result")
LINKFILE = os.path.join(ROOT, "result_link.txt")
CONFIRM = os.path.join(ROOT, "setup_confirmed.txt")

# schtasks /FO CSV /V 의 열 위치 (로케일과 무관하게 순서는 같다)
COL_TASK, COL_NEXT, COL_STATUS, COL_LASTRUN, COL_LASTRESULT, COL_TASKTORUN = 1, 2, 3, 5, 6, 8
COL_SCHEDTYPE, COL_STARTTIME, COL_DAYS, COL_INTERVAL = 18, 19, 22, 23  # 주간 작업은 "일"=요일, "월"=1주마다


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def section(md, heading_prefix):
    """'## <heading_prefix>' 로 시작하는 절의 본문(다음 '## ' 전까지)."""
    lines = md.splitlines()
    out, on = [], False
    for ln in lines:
        if ln.startswith("## "):
            if on:
                break
            on = ln[3:].strip().startswith(heading_prefix)
            continue
        if on:
            out.append(ln)
    return out


def split_terms(s):
    s = re.sub(r"\(.*?\)", "", s)  # 괄호 설명은 키워드가 아니다
    return [t.strip(" *`") for t in re.split(r"[,、·/]", s) if t.strip(" *`")]


def parse_keywords(md):
    """키워드 절의 '- **주요**: …' 류를 {라벨: [키워드…]} 로. 다음 '- ' 전까지의 이어지는 줄도 붙인다."""
    groups, cur = {}, None
    for ln in section(md, "키워드"):
        m = re.match(r"^\s*-\s*\*\*(.+?)\*\*[^:：]*[:：]\s*(.*)$", ln)
        if m:
            cur = m.group(1).strip()
            groups[cur] = m.group(2).strip()
        elif cur and ln.strip() and not ln.lstrip().startswith(("-", ">", "#", "|")):
            groups[cur] += " " + ln.strip()
    return {k: split_terms(v) for k, v in groups.items()}


def unbold(s):
    return s.replace("**", "")


def parse_topic(md):
    for ln in section(md, "내 연구주제"):
        s = ln.strip()
        if s and not s.startswith((">", "RFP가", "{{")):
            return unbold(s)
    return ""


def declared_schedule(md):
    for ln in section(md, "실행 이력"):
        m = re.match(r"^\|\s*스케줄\s*\|\s*(.*?)\s*\|\s*$", ln)
        if m:
            return unbold(m.group(1))
    return ""


def wslpath_w(p):
    if shutil.which("wslpath"):
        try:
            return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception:
            pass
    return ""


def query_schtasks():
    """run_rfp_scout 를 부르는 Windows 예약 작업들. schtasks.exe 가 없으면 None."""
    exe = shutil.which("schtasks.exe") or shutil.which("schtasks")
    if not exe:
        return None
    try:
        raw = subprocess.run([exe, "/Query", "/FO", "CSV", "/V"], capture_output=True, timeout=60).stdout
    except Exception:
        return None
    text = None
    for enc in ("cp949", "utf-8", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("cp949", errors="replace")
    found = []
    for ln in text.splitlines():
        if "run_rfp_scout" not in ln.lower():
            continue
        # "실행할 작업" 칸의 따옴표가 CSV 규칙대로 이스케이프되지 않아 csv 모듈이 깨진다.
        # '","' 로 자르면 열 순서는 그대로 보존된다.
        cols = ln.strip().strip('"').split('","')
        if len(cols) <= COL_INTERVAL:
            continue
        found.append({
            "task": cols[COL_TASK], "next_run": cols[COL_NEXT], "status": cols[COL_STATUS],
            "last_run": cols[COL_LASTRUN], "last_result": cols[COL_LASTRESULT],
            "type": cols[COL_SCHEDTYPE].strip(), "start_time": cols[COL_STARTTIME].strip(),
            "days": cols[COL_DAYS].strip(), "interval": cols[COL_INTERVAL].strip(),
            "command": cols[COL_TASKTORUN].strip().strip('"').strip(),
        })
    return found


def query_crontab():
    if not shutil.which("crontab"):
        return []
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    return [ln.strip() for ln in out.splitlines() if "run_rfp_scout" in ln and not ln.lstrip().startswith("#")]


def check_result_dir():
    info = {"path": RESULT_DIR, "path_win": wslpath_w(RESULT_DIR), "exists": os.path.isdir(RESULT_DIR), "writable": False}
    if info["exists"]:
        try:
            fd, tmp = tempfile.mkstemp(prefix=".setup_check_", dir=RESULT_DIR)
            os.close(fd)
            os.remove(tmp)
            info["writable"] = True
        except OSError:
            pass
    latest = os.path.join(RESULT_DIR, "latest.html")
    if os.path.isfile(latest):
        st = os.stat(latest)
        info["latest_html"] = f"{datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M} ({st.st_size // 1024} KB)"
    else:
        info["latest_html"] = ""
    for sub in ("reports", "archive"):
        d = os.path.join(RESULT_DIR, sub)
        info[sub] = len(os.listdir(d)) if os.path.isdir(d) else -1
    for sub in ("raw", "logs"):
        d = os.path.join(ROOT, sub)
        info[sub] = len(os.listdir(d)) if os.path.isdir(d) else -1
    link = ""
    if os.path.isfile(LINKFILE):
        for ln in read_text(LINKFILE).splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                link = s
                break
    info["link"] = link
    win = info["path_win"].replace("\\", "/") if info["path_win"] else ""
    info["link_fallback"] = f"file:///{win}/latest.html" if win else f"file://{RESULT_DIR}/latest.html"
    return info


def fingerprint(obj):
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def collect():
    if not os.path.isfile(PROFILE):
        return None
    md = read_text(PROFILE)
    kw = parse_keywords(md)
    tasks = query_schtasks()
    crons = query_crontab()
    res = check_result_dir()
    data = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "host": socket.gethostname(),
        "root": ROOT, "root_win": wslpath_w(ROOT),
        "topic": parse_topic(md),
        "keywords": kw,
        "placeholders_left": md.count("{{"),
        "schedule_declared": declared_schedule(md),
        "schtasks_available": tasks is not None,
        "schtasks": tasks or [],
        "crontab": crons,
        "result": res,
    }
    sched_fp = [(t["type"], t["days"], t["start_time"], t["task"]) for t in data["schtasks"]] + crons
    data["fp"] = {
        "keywords": fingerprint(kw), "schedule": fingerprint(sched_fp), "result_dir": fingerprint(RESULT_DIR),
    }
    return data


def read_confirm():
    if not os.path.isfile(CONFIRM):
        return None
    d = {}
    for ln in read_text(CONFIRM).splitlines():
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            d[k.strip()] = v.strip()
    return d


LABEL = {"keywords": "키워드", "schedule": "스케줄", "result_dir": "결과 폴더"}


def drift(data, conf):
    return [LABEL[k] for k in ("keywords", "schedule", "result_dir") if conf.get("fp_" + k) and conf["fp_" + k] != data["fp"][k]]


def render(data, conf):
    L = []
    root_disp = data["root"] + (f"  ({data['root_win']})" if data["root_win"] else "")
    L.append(f"=== rfp-scout 설정 확인 ({data['checked_at']}, {data['host']}) ===")
    L.append(f"루틴 폴더: {root_disp}")
    L.append("")
    # ① 키워드
    L.append("① 연구 키워드 — profile.md")
    topic = data["topic"]
    L.append(f"   연구주제: {topic[:110] + ('…' if len(topic) > 110 else '') if topic else '[경고] 연구주제 서술이 비어 있음'}")
    if data["keywords"]:
        for label, terms in data["keywords"].items():
            shown = ", ".join(terms[:12]) + (f" … 외 {len(terms) - 12}개" if len(terms) > 12 else "")
            L.append(f"   {label}({len(terms)}): {shown}")
    else:
        L.append("   [경고] '## 키워드' 절에서 '- **주요**: …' 형식의 줄을 찾지 못함")
    if data["placeholders_left"]:
        L.append(f"   [경고] 양식 자리표시자 {{{{ }}}} 가 {data['placeholders_left']}곳 남아 있음 — 채우지 않은 항목이 있다")
    L.append("")
    # ② 주기
    L.append("② 모니터링 주기")
    L.append(f"   선언(profile.md › 실행 이력 › 스케줄): {data['schedule_declared'] or '(없음)'}")
    if data["schtasks"]:
        for t in data["schtasks"]:
            L.append(f"   실측(Windows 작업 스케줄러): {t['task']}")
            every = f" ({t['interval']})" if t["interval"] not in ("", "N/A") else ""
            L.append(f"     {t['type']} {t['days']}{every} {t['start_time']} · 상태 {t['status']} · 다음 {t['next_run']}")
            L.append(f"     마지막 {t['last_run']} → 결과 {t['last_result']}")
            if t["last_result"] not in ("0", "267009", "267011", "N/A", ""):
                # 267009 = 실행 중, 267011 = 아직 실행 안 됨. 그 밖의 값은 대개 실패다(-1/0xFFFFFFFF: wsl 기동 실패 등).
                L.append(f"     [경고] 마지막 결과가 {t['last_result']} — 직전 예약 실행이 실패했다. logs/launch.log 와 logs/ 를 확인")
    elif data["schtasks_available"]:
        L.append("   실측(Windows 작업 스케줄러): [경고] run_rfp_scout 를 부르는 작업이 없음 — README 4절대로 등록 필요")
    if data["crontab"]:
        for c in data["crontab"]:
            L.append(f"   실측(crontab): {c}")
    elif not data["schtasks_available"]:
        L.append("   실측(crontab): [경고] run_rfp_scout 항목 없음 — `crontab -e` 로 등록 필요")
    L.append("")
    # ③ 결과 폴더
    r = data["result"]
    L.append("③ 결과 저장 폴더")
    state = "쓰기 가능" if r["writable"] else ("[경고] 쓰기 불가" if r["exists"] else "[경고] 폴더 없음 — 러너가 첫 실행 때 만들지만 경로를 확인할 것")
    L.append(f"   result/ → {r['path']}" + (f"  ({r['path_win']})" if r["path_win"] else "") + f"  — {state}")
    L.append(f"     latest.html {r['latest_html'] or '(아직 없음 — 첫 회차가 만든다)'} · reports {max(r['reports'], 0)}개 · archive {max(r['archive'], 0)}개")
    L.append(f"   raw/ {max(r['raw'], 0)}개 · logs/ {max(r['logs'], 0)}개")
    L.append(f"   결과 링크(result_link.txt): {r['link'] or '(비어 있음 → ' + r['link_fallback'] + ')'}")
    L.append("")
    # 확인 상태
    if conf is None:
        L.append("확인 상태: 미확인 — 위 세 항목이 의도와 맞으면  python3 scripts/setup_check.py --confirm")
    else:
        ch = drift(data, conf)
        where = f"{conf.get('confirmed_at', '?')} {conf.get('host', '')}".strip()
        if ch:
            L.append(f"확인 상태: {where} 에서 확인됨 — 그 뒤 변동: {', '.join(ch)}. 맞으면 다시  --confirm")
        else:
            L.append(f"확인 상태: {where} 에서 확인됨 (변동 없음)")
    return "\n".join(L)


def write_confirm(data):
    kw_n = sum(len(v) for v in data["keywords"].values())
    sched = "; ".join(f"{t['task']} {t['type']} {t['days']} {t['start_time']}" for t in data["schtasks"]) or "; ".join(data["crontab"]) or "(스케줄 미등록)"
    body = [
        "# rfp-scout 설정 확인 기록 — setup_check.py --confirm 이 쓴다. 손으로 고칠 일은 없다.",
        "# 이 파일이 없으면 러너가 매 회차 HTML 맨 위에 설정 요약을 띄우고 알림을 보낸다.",
        "# 키워드·스케줄·결과 폴더가 확인 시점과 달라지면 러너가 '설정 변동' 으로 알린다.",
        f"confirmed_at={datetime.now():%Y-%m-%d %H:%M:%S}",
        f"host={data['host']}",
        f"keywords={kw_n}개 · {', '.join(list(data['keywords'].get('주요', []))[:5])}",
        f"schedule={sched}",
        f"result_dir={data['result']['path']}",
        f"fp_keywords={data['fp']['keywords']}",
        f"fp_schedule={data['fp']['schedule']}",
        f"fp_result_dir={data['fp']['result_dir']}",
    ]
    with open(CONFIRM, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")


def main(argv):
    mode = "--check"
    for a in argv:
        if a in ("--check", "--confirm", "--json"):
            mode = a
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
    data = collect()
    if data is None:
        print(f"[오류] profile.md 가 없습니다: {PROFILE}\n  assets/profile/profile.template.md 를 채워 저장한 뒤 다시 실행하세요.")
        return 1
    conf = read_confirm()
    if mode == "--json":
        out = dict(data)
        out["confirmed"] = conf
        out["drift"] = drift(data, conf) if conf else []
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(render(data, conf))
    if mode == "--confirm":
        write_confirm(data)
        print(f"\n확인 기록: {CONFIRM}")
        return 0
    if conf is None:
        return 2
    return 3 if drift(data, conf) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
