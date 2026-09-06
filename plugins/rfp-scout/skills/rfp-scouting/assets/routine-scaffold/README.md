# routine-scaffold — 주간 공고 모니터링 설치 템플릿

`rfp-scouting`의 주간 모니터링을 **새 PC에 설치**하기 위한 템플릿 모음이다.

> ⚠️ **이건 템플릿이지 동작본이 아니다.** 실제로 도는 파일은 각 PC의 루틴 폴더에 있다.
> 운영 중 스크립트를 고쳤다면 그 변경이 여기에 자동으로 반영되지 않는다 —
> 구조가 바뀌는 수정을 했을 때만 이쪽 템플릿도 함께 갱신한다.
> (양쪽을 상시 동기화 대상으로 삼으면 드리프트가 생긴다.)

## 구성

| 파일 | 무엇 |
|------|------|
| `run_rfp_scout.sh.template` | 러너 — `claude -p`로 주간 모니터링 프롬프트 실행. 소유 PC 가드·HTML 검증 포함 |
| `run_rfp_scout.bat.template` | Windows 작업 스케줄러가 부르는 진입점 (wsl.exe 경유). 기동 시각·종료코드를 `logs/launch.log`에 남긴다 |
| `setup_check.py` | **설치 확인** — ① 연구 키워드 ② 모니터링 주기(선언 vs 스케줄러 실측) ③ 결과 저장 폴더를 요약하고, `--confirm`으로 확인 기록을 남긴다 |
| (프로파일 양식) | 한 단계 위 `assets/profile/` 에 있다 — 이 스킬의 유일한 설정 파일이라 루틴과 분리해 뒀다 |
| `owner.txt.template` | 이 루틴을 돌리는 PC 이름 — 동기화 폴더 공유 시 중복 실행 방지 |

## 설치 절차

### 1. 루틴 폴더 생성
```
<루틴폴더>/
├ result/{reports,archive}/   결과물 (latest.html · latest_candidates.md · reports/ · archive/)
├ raw/                        다운로드한 공고문·첨부 원본
├ logs/                       실행 로그 (90일 후 자동 삭제) · launch.log (bat 기동 기록)
├ scripts/                    러너 + setup_check.py
├ profile.md                  관심사·알림 설정
├ owner.txt                   소유 PC 이름
├ result_link.txt             결과 HTML 공유 링크 (선택 — 비면 로컬 경로 사용)
├ calendar_event.json         이번 회차 확인 일정 ID (첫 실행 시 자동 생성)
├ setup_confirmed.txt         설정 확인 기록 (setup_check.py --confirm 이 만든다)
└ seen_rfp.json               보고 이력 (첫 실행 시 자동 생성)
```

### 2. 템플릿 치환
- `.sh` / `.bat`의 `{{ROUTINE_ROOT}}` → 루틴 폴더의 절대경로
  (WSL에서 Windows 폴더를 쓰면 `/mnt/c/Users/<user>/.../RFP_weekly` 형식)
- `.sh`의 `{{RESULT_URL_FALLBACK}}` → 결과 HTML 기본 링크
  (예: `file:///C:/Users/<user>/.../result/latest.html`)
- `.bat`의 `{{ROUTINE_ROOT_WIN}}` → 같은 폴더의 Windows 경로 (예: `C:\Users\<user>\...\RFP_weekly`)
- (선택) `.sh` PROMPT의 6-1) 절에 HTML 디자인 규칙(팔레트·서체·모서리)을 한두 줄 덧붙인다 — 비워 두면 직전 회차 HTML을 승계한다
- `../profile/profile.template.md` 의 `{{ }}` 항목을 채워 루틴 폴더에 `profile.md`로 저장
  (작성 예시는 `../profile/profile.example.md`)
- `owner.txt.template`의 `{{HOSTNAME}}` → `hostname` 출력값으로 바꿔 `owner.txt`로 저장
- `.template` 확장자를 떼고 `.sh`/`.bat`는 `scripts/`에 배치. `setup_check.py`는 치환 없이 `scripts/`에 복사

### 3. `.bat`는 반드시 CRLF로 저장
LF로 저장하면 실행되지 않는다.
```bash
python3 -c "p='run_rfp_scout.bat';d=open(p,'rb').read().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n');open(p,'wb').write(d)"
chmod +x run_rfp_scout.sh
```

### 4. 작업 스케줄러 등록 (Windows)
```cmd
schtasks /Create /TN "RFP-Scout-Weekly" /TR "\"<윈도우경로>\scripts\run_rfp_scout.bat\"" ^
         /SC WEEKLY /D SUN /ST 23:10 /F
```
리눅스·macOS라면 cron으로 대신한다: `10 23 * * 0 bash <루틴폴더>/scripts/run_rfp_scout.sh`

### 5. 기본값으로 두면 안 되는 설정 — 이걸 빼면 조용히 안 돈다
```powershell
$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
     -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Set-ScheduledTask -TaskName 'RFP-Scout-Weekly' -Settings $s
```
- `StartWhenAvailable` — 예약 시각에 PC가 꺼져 있었으면 다음 부팅 시 실행. **주간 작업에는 필수.**
- 배터리 옵션 — 노트북 기본값은 배터리 상태에서 아예 시작하지 않는다.

### 6. 등록 확인 — 생성 성공 메시지만 믿지 말 것
```cmd
schtasks /Query /TN "RFP-Scout-Weekly" /V /FO LIST
```
"다음 실행 시간"이 의도한 요일·시각인지 눈으로 확인한다.

### 7. 헤드리스 동작 확인
```bash
cd <루틴폴더>
claude -p "profile.md를 읽고 수신 메일 설정만 한 줄로 답하라." \
  --permission-mode bypassPermissions --model opus
```
프로파일을 읽어오고 `rfp-scouting` 스킬이 목록에 잡히면 준비 완료다.

수집 경로만 따로 점검하려면 스킬 동봉 스크립트를 직접 돌려본다:
```bash
python3 <플러그인>/skills/rfp-scouting/scripts/iris_fetch.py list --pages 1
```

### 8. 설치 확인 — 세 항목을 사람이 한 번 본다
```bash
python3 scripts/setup_check.py            # ① 연구 키워드 ② 모니터링 주기 ③ 결과 저장 폴더 요약
python3 scripts/setup_check.py --confirm  # 맞으면 확인 기록 (setup_confirmed.txt)
```
- ②는 `profile.md`의 「실행 이력 › 스케줄」 선언과 **스케줄러 실측**(schtasks / crontab)을 나란히 보여 준다.
  작업 이름을 묻지 않고 "실행할 작업"에 `run_rfp_scout`가 들어간 작업을 찾으므로, 이름을 다르게 붙였어도 잡힌다.
  마지막 실행 결과가 0이 아니면 경고를 띄운다(−1/0xFFFFFFFF는 대개 wsl 기동 실패).
- 확인 기록이 없으면 러너가 **매 회차 HTML 맨 위에 「설정 확인 필요」 블록**을 띄우고, 히트가 없어도 알림을 한 줄 보낸다.
  실행을 막지는 않는다 — 막으면 확인을 잊은 채 몇 주가 조용히 지나간다.
- 확인 뒤 키워드·스케줄·결과 폴더가 바뀌면 「설정 변동」 블록이 뜬다. 맞으면 다시 `--confirm`.

## 전제 조건

| 필요한 것 | 왜 |
|---|---|
| 이 플러그인 설치 | `rfp-scout@jinwoo-skills` (user scope) |
| `python3` | 동봉 수집·추출 스크립트 실행 (수집은 표준 라이브러리만 쓴다) |
| `pypdf` / `olefile` *(권장)* | 첨부 PDF·HWP 추출. 없으면 그 형식만 건너뛴다 |
| Gmail 커넥터 *(선택)* | 메일 초안 생성용. 없으면 알림·리포트만 나가고 실패로 처리하지 않는다 |
| 캘린더 커넥터 *(선택)* | 확인 일정 교체용. 없으면 `.ics` 파일로 대체 |
| PC 상시 전원 *(권장)* | 예약 시각에 꺼져 있으면 다음 부팅까지 밀린다 |

> **브라우저 자동화(Playwright)는 필요 없다.** IRIS는 목록·상세·첨부 전 구간이 평범한 HTTP다.
> 예전 판 문서에는 "Playwright 필수"라고 적혀 있었으나 실측으로 깨진 전제다.

## 두 PC가 같은 폴더를 볼 때 (중요)

루틴 폴더를 클라우드 동기화 폴더에 두고 **두 PC에 스케줄을 걸면 같은 시각에 함께 돈다.**
로그·첨부에 충돌 사본이 생기고, 보고 이력이 반쪽만 반영되면 다음 주에 이미 본 공고를
신규로 다시 보고하게 된다. 동기화 폴더는 잠금이 아니라 `flock`으로 막을 수 없다.

→ `owner.txt`에 소유 PC 호스트명을 적어 둔다. 러너가 맨 앞에서 대조해 다른 PC면
`logs/skipped_<PC이름>.log`에 한 줄만 남기고 즉시 빠진다.

## 예약 실행이 죽었을 때 — `logs/launch.log`부터 본다

작업 스케줄러의 마지막 결과가 `0xFFFFFFFF`(−1)인데 `logs/`에 그 회차 파일이 없으면 **wsl.exe 기동 단계에서 죽은 것**이다.
`.sh`는 소유 PC 확인을 지난 뒤에야 로그를 만들기 때문에 이 경우 흔적이 없고, 그래서 `.bat`가 `logs/launch.log`에 시각·호스트·종료코드를 먼저 남긴다.

| launch.log 상태 | 뜻 | 볼 곳 |
|---|---|---|
| `start` 줄도 없음 | 작업이 bat까지 못 옴 | 스케줄러 설정(경로·계정·"로그온 여부에 관계없이 실행")·PC 전원 |
| `start`만 있고 `exit` 없음 | WSL이 도중에 죽음 | 같은 시각의 `logs/*.log` 유무, `wsl.exe -l -v` |
| `exit=-1` 이고 `logs/`에 파일 없음 | wsl 기동 실패 | `wsl.exe -d Ubuntu -- true`를 스케줄러와 같은 계정으로 실행해 본다 |

**자동 재시도는 넣지 않는다.** −1은 스카우팅이 시작된 뒤 WSL이 죽은 경우에도 나오며, 그때 재실행하면 반쯤 쓰인 `seen_rfp.json`·`latest.html` 위에 다시 쓴다. 실패한 회차는 다음 주에 자연히 다시 돈다.

## 예약 시각에 PC가 꺼져 있는 문제

`StartWhenAvailable`은 **다음 부팅 때** 실행할 뿐 꺼진 PC를 켜지 못한다. 야간 예약이 반복해서 밀리면 전원 쪽을 본다.

```powershell
# 절전·최대절전 끄기 + 작업이 절전 상태의 PC를 깨우게 (관리자 PowerShell)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
$t = Get-ScheduledTask -TaskName 'RFP-Scout-Weekly'; $t.Settings.WakeToRun = $true; Set-ScheduledTask -InputObject $t
# 왜 꺼졌는지: 42=절전 진입, 1074=프로그램/사용자 종료(프로세스명 표시), 41·6008=정전·강제 종료
Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,42,1074,6008} -MaxEvents 30 | Format-Table TimeCreated, Id, Message -Wrap
```
- 완전히 꺼진 PC를 예약 시각에 켜려면 **BIOS의 RTC Alarm(Resume by Alarm)**과 AC Power Loss = Power On을 쓴다. 이때 자동 로그인(`netplwiz`)이 없으면 로그인 화면에서 멈춰 wsl 작업이 실패한다.
- 기관 PC에 야간 자동 종료 에이전트가 깔려 있으면(1074의 프로세스명으로 드러난다) 설정을 바꿔도 다시 꺼진다 — 전산 담당에 예외 등록을 요청한다.

## 결과 확인 흐름

밤에 돌려두고 아침에 결과만 보는 배치가 편하다(조회가 몇 분 걸리고 결과는 급하지 않다).
러너는 매 회차 **지난 확인 일정을 지우고 다음 것 하나만 새로 만든다** — 반복 일정으로 두면
지난 회차 결과를 가리키는 일정이 계속 쌓인다. 일정 본문 맨 위에 결과 HTML 링크가 들어간다.

로컬 경로(`file:///…`)는 그 PC 브라우저에서만 열린다. 휴대폰에서도 보려면 `result_link.txt`에
공유 링크를 한 번만 붙여넣는다(`latest.html`은 경로가 고정이라 링크도 계속 유효하다).
