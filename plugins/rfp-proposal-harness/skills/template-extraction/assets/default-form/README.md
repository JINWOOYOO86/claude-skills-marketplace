# 기본 연구계획서 양식 (default form)

**사용자가 별도 양식을 지정하지 않고 공고 첨부에도 서식이 없을 때** 하네스가 사용하는 폴백 양식이다.

| 파일 | 내용 |
|---|---|
| `default_proposal_form.pdf` | **양식 원본(3쪽)** — 규칙의 유일한 출처. [표 A]·[표 B] 실물은 2~3쪽 |
| `default_proposal_form.md` | 위 PDF의 **전사본**. 목차 골격을 그대로 복사해 작성 시작점으로 쓴다 |
| `default_form_rules.md` | PDF에서 뽑은 **작성 가이드라인 겸 규칙표**. `01_template_rules.md` 와 같은 형식 |
| `default_form_style.json` | HWPX 조립용 **스타일맵**(본문 charPr6 11pt / 표 charPr2 9pt / 장제목 charPr5 16pt 검정 / 절제목 charPr7 13pt 굵게) |

**HWPX 빈 양식 파일은 두지 않는다.** 조립은 `build_hwpx.py` 기본 템플릿으로 하고 PDF 규칙(A4 / 돋움 11pt / 160%)을 헤더 패치로 적용한다 — 기본 템플릿의 `charPr 0~6` 이 배포처 HWPX 양식과 전 항목 일치함을 실측 확인했다.

## 왜 두는가

1. **폴백**: 공고에 서식 첨부가 없거나 사용자가 양식을 안 주는 경우가 흔하다. 그때 "양식이 없어 못 씁니다"로 멈추지 않고 표준 골격으로 진행한다.
2. **규칙 재추출 비용 절감**: `default_form_rules.md` 가 이미 있으므로 폴백 경로에서는 PDF 파싱 단계를 건너뛴다.
3. **작성 시작점**: `default_proposal_form.md` 의 목차 골격을 복사해 바로 쓰기 시작할 수 있다.

## 양식의 성격

과기정통부-연구재단 연구개발계획서(PART1 요약문 + PART2 본문)와 산업부-산기평 사업계획서의 **공통(교집합) 항목만 추출해 경량화**한 구조다. 특정 부처 전용 항목(예: IRIS 전용 별지, 기관 서약서)은 들어 있지 않다.

- 특정 부처 공고에 낼 때는 **그 공고의 첨부 서식이 항상 우선**한다. 이 양식은 서식이 없을 때만 쓴다.
- 개인정보·기관 식별정보는 들어 있지 않다. 도입 시 PDF 메타데이터(`title`·`creator`·`producer`)를 제거했다.
  → **양식을 교체할 때도 반드시 같은 처리를 할 것.** 본문 텍스트만 보면 놓친다 — **문서 메타데이터**까지 검사한다.
  (참고: 함께 배포되던 HWPX 빈 양식에는 `Contents/content.hpf` 의 `creator`·`lastsaveby` 에 작성자 정보가 박혀 있었다. HWPX 를 다시 들일 일이 있으면 `.xml`·`.hpf`·`.rdf`·`Preview/PrvText.txt` 를 모두 검사할 것.)

## 교체하려면

기본 양식을 바꾸려면 `default_proposal_form.pdf` 를 새 파일로 교체하고, 전사본 `default_proposal_form.md` 와 규칙표 `default_form_rules.md` 를 다시 뽑는다.
추출 절차는 `template-extraction` 스킬 워크플로우 2~3단계와 동일하다. 교체 후 `plugin.json` 버전을 올려야 각 PC 캐시에 반영된다.
