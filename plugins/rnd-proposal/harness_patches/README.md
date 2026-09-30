# rfp-proposal-harness 게이트 사본 — 결함 수정 3건 + rubric 용 기능 추가

> 대상: `rfp-proposal-harness` **0.30.0** · `skills/hwpx-writing/scripts/`
> 환경: Windows 11 · **네이티브 Windows** Python 3.13 (WSL 아님) · 한글 13.0
> 원본은 건드리지 않았습니다. 이 폴더의 사본만 고쳤습니다.

`harness_patches` 는 rnd-proposal 내부에서만 쓰이며 rfp-proposal-harness 설치본을 바꾸지 않는다.
rnd-proposal 의 `scripts/check_rubric.py` 와 스킬 문서가 이 폴더의 사본을 직접 부른다.

## 0.30.0 대비 변경 전부

| 파일 | 무엇을 | 왜 | 구분 |
|---|---|---|---|
| `form_strip.py` | `main()` 첫 줄에서 stdout 을 UTF-8(`errors="replace"`)로 재설정 | cp949 콘솔에서 `—` 출력 시 `UnicodeEncodeError` 로 켜자마자 꺼짐 | 결함 ① |
| `gate_hwpx.py` | 같음 | 같음 | 결함 ① |
| `gate_regress.py` | 같음 | 같음 | 결함 ① |
| `gate_pages.py` | 같음 | 같음 | 결함 ① |
| `gate_pages.py` | `wslpath`·`which`·`cp` 를 `IS_WSL` 분기·`shutil.which`·`shutil.copy` 로 교체 | 네이티브 Windows 에서 첫 호출이 `WinError 2` 로 죽어 쪽수 게이트를 돌릴 수 없음 | 결함 ② |
| `gate_pages.py` | 고아 제목 검출 추가: 쪽의 마지막 글줄이 장·절 제목이면 실패 (`orphans`) | rubric T-m4. 제목만 쪽 끝에 남고 본문이 다음 쪽으로 넘어간 것을 쪽수 게이트가 못 잡음 | rubric 기능 |
| `gate_pages.py` | 빈 쪽 검출 추가: 글자가 하나도 없는 쪽이면 실패 (`blank_pages`) | rubric F-m3. 빈 쪽이 있어도 쪽수 게이트는 통과함 | rubric 기능 |
| `gate_pages.py` | 장별 배분 판정에서 `_` 로 시작하는 메타 키 제외, JSON 출력에 `orphans`·`blank_pages` 추가 | 빈 `orphans` 목록이 falsy 라 장별 배분 전체가 「미측정」이 됨. `check_rubric.py` 가 두 키를 읽음 | 위 기능의 부속 |
| `gate_form.py` | `main()` 첫 줄 stdout UTF-8 재설정 | 결함 ① 과 같음 | 결함 ① |
| `gate_form.py` | F-11 `norm_line()` 이 `—`·`:`·`：` 어느 것으로도 라벨을 자름 | 구분자를 콜론으로 바꾸자 슬롯 64개가 전부 「초과」로 잡힘 | 결함 ③ |
| `gate_form.py` | F-11 슬롯 기준을 축자 대조에서 **최소 개수**로 바꿈(리드는 축자 대조 유지) | 「사실 하나에 슬롯 하나」로 쪼개면 슬롯 수·문구가 바뀌어 축자 대조를 원리적으로 통과할 수 없음 | rubric 기능 |
| `gate_form.py` | F-8d 슬롯 길이 검사 신설(`slot_max_chars`, 기본 115자, `null` 이면 해제). 통계에 `bullets` 추가 | 명세에 상한이 있는데 게이트가 보지 않았음 | rubric 기능 |
| `gate_form.py` | F-9·F-10 에서 명세 `style.uniform_font_pt` 가 있으면 본문·제목·표·캡션을 그 한 값으로 잼 | rubric F-m2 「전 run 11pt」. 4단 기준(11/13/16/9)이라 11pt 로 통일한 문서를 표 9pt 위반으로 잡음 | rubric 기능 |
| `gate_form.py` | F-4 KEYWORDS5 가 0절 요약표 「핵심어」 행의 값 칸만 읽고 국문·영문을 각각 5개 이내로 셈 | 표 칸 전부를 이어 붙여 국문 5 + 영문 5 를 한 목록으로 세고 「/」까지 쪼개 11개로 거짓 실패 | 결함 수정 (rubric T-m3) |

아래는 결함 ①~③ 의 상세다.

---

## 결함 ① — 게이트 5종이 한국어 Windows 콘솔에서 켜자마자 꺼짐

### 증상

```
UnicodeEncodeError: 'cp949' codec can't encode character '—' in position 16
```

`--help` 로 도움말만 봐도 죽습니다. 출력에 든 **긴 줄표(`—`) 글자 하나** 때문입니다.
한국어 Windows 명령창은 기본 코드페이지가 cp949 라 이 글자를 표시하지 못합니다.

해당: `gate_form` · `gate_hwpx` · `gate_pages` · `gate_regress` · `form_strip`
(`form_scaffold` · `fix_table_width` 는 원래 정상)

### 수정 — `main()` 첫 줄에 한 줄

```python
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # [PATCH]
```

`errors="replace"` 까지 넣으면 콘솔 설정이 무엇이든 죽지 않습니다.

### 검증

```
$ python gate_hwpx.py --hwpx 문서.hwpx        # PYTHONIOENCODING 없이
PASS — 실패 0건
```

---

## 결함 ② — `gate_pages.py` 가 WSL 전용 (이쪽이 더 무겁습니다)

### 증상

```
$ python gate_pages.py --hwpx 문서.hwpx --spec spec.json
실행 오류: [WinError 2] 지정된 파일을 찾을 수 없습니다
```

`PYTHONIOENCODING=utf-8` 을 줘도 같습니다. **첫 호출에서 끝납니다.**

### 원인

```python
def win(path):  subprocess.check_output(["wslpath", "-w", ...])
def have(cmd):  subprocess.run(["which", cmd], ...)
subprocess.run(["cp", ...], check=True)
```

`wslpath` · `which` · `cp` 는 리눅스 명령입니다. 네이티브 Windows 에는 없어서
`measure()` 의 **첫 줄** `if not have("powershell.exe")` 에서 죽습니다.

역설적인 것은 이 줄이 **「파워셸이 있는지 확인」** 하려는 코드인데
확인하는 도구 자체가 없어서 실패한다는 점입니다. 파워셸은 멀쩡히 있습니다.

### 왜 ① 보다 무거운가

오케스트레이터 SKILL 이 *「양식·분량 게이트를 통과해야 Phase 4 로 넘어간다」* 고
규정하는데, **네이티브 Windows 에서는 그 조건을 기계로 확인할 방법이 없습니다.**

### 수정 — 경로 처리만 환경에 따라 가릅니다

```python
import shutil

IS_WSL = os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")

def win(path):
    p = os.path.abspath(path)
    if IS_WSL:
        return subprocess.check_output(["wslpath", "-w", p], text=True).strip()
    return p                                  # 네이티브는 변환이 필요 없다

def have(cmd):
    return shutil.which(cmd) is not None      # which(1) 대신 표준 라이브러리
```

`wslpath -u` 도 같은 방식으로 갈랐고, `cp` 는 `shutil.copy` 로 바꿨습니다.

**`PS_TEMPLATE` 과 PowerShell 호출부는 손대지 않았습니다** — 그쪽은 양쪽에서 똑같이 돕니다.
(오히려 배울 점이 있었습니다. 아래 참조.)

### 검증 — 이 PC 에서 처음으로 돌았습니다

```
$ python gate_pages.py --hwpx 30_proposal.hwpx --spec default_form_spec.json --allow-estimate
■ 총 쪽수 실측 = 10p  (목표 10p 내외 · 상한 12p)
PASS — 위반 0건
```

같은 문서를 `kordoc render` 로 잰 값(10페이지)과 **일치**합니다.

> 남은 경고 2건은 이 PC 환경 탓이지 코드 문제가 아닙니다 —
> ⑴ 「규격 줄간격으로 조판된 회차 없음」(한글의 "글꼴에 어울리는 줄 높이" 설정)
> ⑵ 「PyMuPDF 파이썬 없음(`/mnt/c/ProgramData/anaconda3/python.exe`)」 →
>    `--winpython` 기본값이 WSL 경로입니다. 네이티브에서는 `sys.executable` 을
>    기본으로 두시면 장별 배분까지 측정됩니다. (그 부분은 고치지 않았습니다)

---

## 결함 ③ — 골격 게이트가 구분자에 묶여 있습니다

### 증상

연구계획서 개조식에 em-dash 를 쓰지 않기로 하고 슬롯 구분자를
`문구 — 값` 에서 `문구: 값` 으로 바꾸자 **슬롯 64개가 전부 「초과」로 잡혔습니다.**

```
[FAIL] F-11 골격(리드·슬롯) 준수  슬롯 64/64 · 초과 슬롯 64개
```

### 원인

`sp_blueprint()` 의 `norm_line()` 이 **em-dash 로만 잘라** 라벨을 냅니다.

```python
return re.sub(r"\s+", "", re.sub(r"\*\*|`", "", x)).split("—")[0]
```

구분자가 콜론이 되면 자를 곳이 없어 **라벨+값 전체**가 비교 대상이 됩니다.
명세의 라벨과 절대 안 맞습니다.

### 수정 — 구분자에 의존하지 않게 합니다

```python
return re.split(r"[—:：]",
                re.sub(r"\s+", "", re.sub(r"\*\*|`", "", x)))[0]
```

게이트가 보려는 것은 **라벨**이지 구두점이 아닙니다.
전각 콜론(`：`)까지 넣었습니다.

### 검증

```
[OK ] F-11 골격(리드·슬롯) 준수  (md)  리드 33/33 · 슬롯 64/62
PASS — 실패 0건
```

> 참고로 `blueprint_extra_tolerance` 기본값이 **2** 라는 것도 이번에 알았습니다.
> 초과가 2개까지는 통과하고 3개부터 실패합니다. 문서에 적어 두시면
> 「왜 이건 통과하고 저건 실패하나」를 덜 헤맵니다.

---

## 덧붙임 — 이 코드 덕분에 저희 결함 두 개를 찾았습니다

`gate_pages.py` 를 읽다가 나온 것입니다.

### ① 저희는 한글을 통째로 강제 종료하고 있었습니다

```python
subprocess.run(["taskkill", "/F", "/IM", "Hwp.exe"])   # 사용자 문서까지 죽는다
```

rfp-proposal-harness 관리자 쪽은 **창 제목이 없는 잔류 인스턴스만** 정리하고 사용자가 보고 있는 문서는
건드리지 않습니다. *「머리 없는 인스턴스에 붙어 9p/11p 가 번갈아 측정됐다」*는
주석이 정확한 진단이었습니다. 저희 코드를 그쪽 방식으로 바꿨습니다.

### ② 한글 연동이 안 될 때 다른 길이 있었습니다

이 PC 에서 `win32com.gencache.EnsureDispatch` 가 `-2147023170` 으로 계속 실패했는데
**같은 순간 `New-Object -ComObject` 는 정상**이었습니다. 차이가 셋이라
(늦은 바인딩 / 보안모듈 2번째 인자가 `FilePathCheckerModule` — 저희는 `FilePathChecker` /
잔류 인스턴스 처리) 어느 것이 결정적인지 못 가려 PowerShell 경로를 폴백으로 넣었습니다.

**덕분에 두 번이나 측정 못 하던 저희 분량 실측이 됐습니다.**

---

## 고치지 않은 것

| 항목 | 왜 |
|---|---|
| `--winpython` 기본값 | WSL 경로(`/mnt/c/...`)가 기본입니다. 네이티브면 `sys.executable` 이 맞으나 **WSL 사용자의 기존 동작을 바꾸게 되어** 판단을 남겨 둡니다 |
| `J-17` 본문 폭 2 HWPUNIT 차 | 계산값 48190 vs 원본 문단 실측 48188. 정의 차이라 **어느 쪽이 옳은지는 저희가 정할 일이 아닙니다** |
