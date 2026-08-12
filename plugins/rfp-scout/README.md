# rfp-scout — 국가 R&D 공고 탐색·주간 모니터링

> **Korean R&D funding-call scout for Claude Code.** Sweeps IRIS (Korea's integrated national
> R&D portal), downloads each call's attached RFP documents, and judges relevance **against the
> full RFP text** — not the call title — using a research-profile written in plain prose.
> Ships a weekly-monitoring routine scaffold, a dependency-free IRIS fetcher, and an
> HWP/HWPX/PDF/ZIP text extractor. Documentation and prompts are in Korean, because the
> portals, the RFPs, and the judgements all are.

## 설치

```
/plugin marketplace add JINWOOYOO86/claude-skills-marketplace
/plugin install rfp-scout@jinwoo-skills
```

## 이게 푸는 문제

국가 R&D 공고는 **제목이 포괄적이다.** "2026년도 ○○기술개발사업 신규지원 대상과제 공고" 안에
품목요구서 수십 건이 첨부로 들어있고, 내 연구주제와 맞는 과제는 그 안 어딘가에 한 줄로 있다.
제목만 보는 알림은 RSS로 충분하고, 그래서 대부분 무시하게 된다.

이 스킬은 **첨부 RFP 원문을 열어 읽고 판정한다.** 판정마다 RFP 원문 문장을 인용하므로 사후 검증이 된다.

```
공고 목록 수집 → 기보고 제외 → 하드필터(자격·규모·기간) → 첨부 RFP 전문 추출
   → 연구주제 서술과 의미 대조 → 직접/간접/무관 3등급 → 히트만 알림·메일·리포트
```

## 구성

```
skills/rfp-scouting/
├ SKILL.md                       워크플로우 7단계 + 채점 기준 + 출력 규약
├ references/portal-sources.md   포털별 접근 경로·검증 상태·함정 (IRIS HTTP 경로 실측)
├ references/weekly-monitor.md   주간 모니터링 절차·리포트/알림 템플릿·상태 파일 스키마
├ scripts/iris_fetch.py          IRIS 목록·상세·첨부 수집 (표준 라이브러리만)
├ scripts/extract_attachment.py  PDF·HWPX·HWP·ZIP → 텍스트
├ assets/profile/                연구주제·키워드 등록양식 (빈 양식 + 작성 예시)  ← 사용자가 고치는 곳
└ assets/routine-scaffold/       주 1회 자동 실행 루틴 설치 템플릿
agents/rfp-scout.md              탐색 전담 에이전트
```

## 쓰는 법

**등록양식부터** — `skills/rfp-scouting/assets/profile/profile.template.md` 를 복사해 `profile.md` 로 채운다.
연구주제 서술 3~5줄, 키워드, 자격·규모 하한, 알림 설정이 전부다. 채워진 예시가 같은 폴더에 있다.
**이 파일 하나가 설정의 전부이며, 언제든 직접 고칠 수 있다** — 스킬은 맨 아래 「실행 이력」 표만 자동 갱신하고
사용자가 쓴 내용은 요청 없이 건드리지 않는다.

**온디맨드** — "우리 분야 낼 만한 공고 있나", "IRIS 공고 훑어줘"라고 하면 스킬이 트리거된다.
프로파일이 없으면 위 양식대로 항목을 물어 만들어 주고, 이후에는 그 파일을 기준으로 돈다.

**주간 자동 모니터링** — `assets/routine-scaffold/`의 템플릿으로 루틴 폴더를 만들고 스케줄러에 건다.
밤에 돌려두고 다음날 아침 결과 HTML 한 파일만 확인하는 흐름이다. 히트가 없으면 알림도 오지 않는다.

**수집 경로만 확인** —
```bash
python3 skills/rfp-scouting/scripts/iris_fetch.py list --pages 1
python3 skills/rfp-scouting/scripts/iris_fetch.py attachments 023398
python3 skills/rfp-scouting/scripts/extract_attachment.py raw/ --outdir extracted/
```

## 설계에서 중요한 것들

- **연구주제 서술문이 키워드보다 중요하다.** 판정은 문자열 매칭이 아니라 의미 대조다.
- **자격 미달 공고를 상위에 올리는 것이 가장 큰 실패다.** 하드필터가 적합도 점수보다 우선한다.
- **애매하면 간접관련으로 올린다.** 놓친 공고는 다음 해까지 기다려야 하므로 누락이 오탐보다 비싸다.
- **히트가 없어도 리포트는 만든다.** 모니터링이 죽은 것과 조용한 주를 구분할 수 있어야 한다.
- **브라우저 자동화는 필요 없다.** IRIS는 목록·상세·첨부 전 구간이 평범한 HTTP다(2026-08-12 실측).

## 라이선스·주의

- 포털 엔드포인트는 사이트 개편으로 바뀔 수 있다. 깨지면 `references/portal-sources.md`를 갱신하는 것이 이 스킬의 유지보수다.
- 수집은 공개 페이지에 대한 통상적인 조회다. 과도한 동시 요청을 보내지 않는다(주 1회 20~30건 수준).
- 예시로 등장하는 연구주제·프로파일은 전부 채워 넣기용 자리표시자다.

<!-- autopush 훅 동작 확인용 임시 줄 -->
