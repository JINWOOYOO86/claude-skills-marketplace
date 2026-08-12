# jinwoo-skills — 공개 Claude Code 마켓플레이스

## 설치

```
/plugin marketplace add JINWOOYOO86/claude-skills-marketplace
/plugin install rfp-scout@jinwoo-skills
/plugin install rfp-proposal-harness@jinwoo-skills
```

## 수록 플러그인

### `rfp-scout` — 국가 R&D 공고 탐색·주간 모니터링

IRIS 등 국가 R&D 공고 포털을 등록해 둔 연구주제로 훑고, **공고 첨부 RFP 원문을 열어 읽어** 관련 건만 걸러냅니다.

- 공고 제목이 아니라 첨부 RFP 본문으로 판정 — 판정마다 원문 문장 인용
- 자격·규모·기간 하드필터 → 적합도 100점 채점 → 상위 후보 보고
- 주 1회 자동 모니터링 루틴 설치 템플릿(러너·스케줄러·소유 PC 가드) 포함
- 동봉 스크립트: IRIS 수집기(표준 라이브러리만), HWP/HWPX/PDF/ZIP 텍스트 추출기

"우리 분야 낼 만한 공고 있나", "IRIS 공고 훑어줘"로 트리거됩니다.

### `rfp-proposal-harness` — R&D 연구계획서 자동화 하네스

공고문 분석부터 기술·시장·정책·특허 조사, 그림·HWPX 작성, 평가위원단 검수까지 14개 전문 에이전트가 이어 쓰는 파이프라인입니다.

- 6인 평가위원단(기술성·실현가능성·사업화·근거정합성·형식규정 + 위원장)이 100점 척도로 채점
- 전원 95점이 될 때까지 개정 ↔ 재평가를 반복
- 공고 탐색 단계(Phase 0.5)는 `rfp-scout` 이 담당 — 함께 설치하면 이어집니다

"연구계획서 작성해줘", "평가위원단 검수", "95점까지 고도화"로 트리거됩니다.

---

## 기여

이 저장소는 편집 원본이자 배포 원본입니다. main 직접 push는 막혀 있으며(저장소 관리자만 예외), 모든 변경은 브랜치 → PR → 리뷰 승인 → squash 머지로 들어옵니다. 작업 전 [CONTRIBUTING.md](CONTRIBUTING.md)를 읽어 주세요.

---

개인 스킬(논문 분석·특허 조사·문서 번역 등)은 별도 비공개 저장소에서 관리합니다.
