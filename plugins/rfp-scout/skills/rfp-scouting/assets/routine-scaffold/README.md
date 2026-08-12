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
| `run_rfp_scout.bat.template` | Windows 작업 스케줄러가 부르는 진입점 (wsl.exe 경유) |
| `profile.md.template` | 관심 연구주제·키워드·자격·알림 설정 |
| `owner.txt.template` | 이 루틴을 돌리는 PC 이름 — 동기화 폴더 공유 시 중복 실행 방지 |

## 설치 절차

### 1. 루틴 폴더 생성
```
<루틴폴더>/
├ result/{reports,archive}/   결과물 (latest.html · latest_candidates.md · reports/ · archive/)
├ raw/                        다운로드한 공고문·첨부 원본
├ logs/                       실행 로그 (90일 후 자동 삭제)
├ scripts/                    러너
├ profile.md                  관심사·알림 설정
├ owner.txt                   소유 PC 이름
├ result_link.txt             결과 HTML 공유 링크 (선택 — 비면 로컬 경로 사용)
├ calendar_event.json         이번 회차 확인 일정 ID (첫 실행 시 자동 생성)
└ seen_rfp.json               보고 이력 (첫 실행 시 자동 생성)
```

### 2. 템플릿 치환
- `.sh` / `.bat`의 `{{ROUTINE_ROOT}}` → 루틴 폴더의 절대경로
  (WSL에서 Windows 폴더를 쓰면 `/mnt/c/Users/<user>/.../RFP_weekly` 형식)
- `.sh`의 `{{RESULT_URL_FALLBACK}}` → 결과 HTML 기본 링크
  (예: `file:///C:/Users/<user>/.../result/latest.html`)
- `profile.md.template`의 `{{ }}` 항목을 채워 `profile.md`로 저장
- `owner.txt.template`의 `{{HOSTNAME}}` → `hostname` 출력값으로 바꿔 `owner.txt`로 저장
- `.template` 확장자를 떼고 `.sh`/`.bat`는 `scripts/`에 배치

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

## 결과 확인 흐름

밤에 돌려두고 아침에 결과만 보는 배치가 편하다(조회가 몇 분 걸리고 결과는 급하지 않다).
러너는 매 회차 **지난 확인 일정을 지우고 다음 것 하나만 새로 만든다** — 반복 일정으로 두면
지난 회차 결과를 가리키는 일정이 계속 쌓인다. 일정 본문 맨 위에 결과 HTML 링크가 들어간다.

로컬 경로(`file:///…`)는 그 PC 브라우저에서만 열린다. 휴대폰에서도 보려면 `result_link.txt`에
공유 링크를 한 번만 붙여넣는다(`latest.html`은 경로가 고정이라 링크도 계속 유효하다).
