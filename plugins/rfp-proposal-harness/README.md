# rfp-proposal-harness

R&D 연구계획서(국가 R&D 신청용 연구개발계획서) 작성을 자동화하는 하네스.
공고문 분석부터 조사·집필·검수까지 **14개 전문 에이전트**가 파이프라인으로 이어 쓴다.

## 파이프라인

```
Phase 0.5 공고탐색  ← 낼 공고가 미정일 때만 (별도 플러그인 rfp-scout@jinwoo-skills — 같은 마켓플레이스)
Phase 1  공고문분석 → 템플릿(양식)추출
Phase 2  기술동향(과제명·키워드 확정) → 시장 ∥ 정책 (병렬) → 특허
Phase 3  연구과제 그림작성 + HWPX 조립
Phase 4  평가위원단 6인 병렬채점 → 위원장 종합 → 전원 95점까지 개정↔재평가
```

데이터는 `_workspace/{순번}_{내용}.md` 파일로 전달(감사 추적·부분 재실행).

## 에이전트 (14)
- **자료조사·분석**: announcement-analyst, template-extractor
- **작성**: tech-trend / market / policy / patent-researcher, figure-designer, hwpx-writer
- **평가위원단 6인**: proposal-evaluator(위원장/부합성·종합), technical-merit, feasibility, impact, evidence-integrity-verifier(근거 게이트), compliance-formatting

## 95점 게이트 루프

6축(부합성·기술성·실현가능성·사업화·근거정합성·형식규정)을 각 100점으로 적대적 채점하고,
전원 ≥95가 될 때까지 hwpx-writer 개정 ↔ 재평가를 반복(최대 4회). 각 위원은 점수뿐 아니라
**Gap-to-95(섹션 단위 실행 지시)**를 남겨, 위원장이 병합·우선순위화한다.
근거·정합성 위원이 REVISE면 다른 점수와 무관하게 통과 불가(허위·무근거 방지 게이트).

## 트리거

오케스트레이터 스킬 `rnd-proposal-orchestrator`가 "연구계획서 작성", "R&D 제안서",
"평가위원단 검수", "전원 95점까지 고도화", 부분 재실행("특허조사만 다시") 등에 트리거된다.

## 공고 탐색 (Phase 0.5)

`rfp-scout`(같은 마켓플레이스의 별도 플러그인 `rfp-scout@jinwoo-skills`)가 `_workspace/00_scout_profile.md`
(관심 기술·자격·규모 선호)를 기준으로 포털을 훑는다.
수집 → 정규화(중복 제거) → **자격 하드필터**(마감 경과·주관자격 미달은 감점이 아니라 탈락) →
5축 적합도 채점(기술적합 35 / 역량정합 20 / 규모부합 15 / 경쟁강도 15 / 준비여유 15) 순으로 후보를 정렬한다.
수집 모드는 실크롤링(Playwright) / 웹검색 폴백 / 오프라인 스냅샷 3종이며, 재실행은 증분 탐색이 기본이다.
포털 목록·접근법·함정은 그 플러그인의 `skills/rfp-scouting/references/portal-sources.md`.

## 참고

- 공통 평가 루브릭: `skills/proposal-evaluation-panel/references/rnd-evaluation-rubric.md`
  (범부처 표준 연구개발계획서 6대 항목 + 정량적 기술목표표 근거)
- HWP 텍스트 추출기: `skills/proposal-evaluation-panel/references/hwp_extract.py`
