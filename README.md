# jinwoo-skills — 공개 Claude Code 마켓플레이스

## 설치

```
/plugin marketplace add JINWOOYOO86/claude-skills-marketplace
/plugin install kepco-tes@jinwoo-skills
```

## 수록 플러그인

### `kepco-tes` — 한전 축냉설비 설치계획서 검토

한국전력공사(KEPCO) 심야전력 축냉설비(TES) 설치계획서를 받아 지침 적합성을 단계별로 검토하고, 결과를 엑셀로 정리합니다.

- 설치계획서(PDF/HWP/스캔 이미지) 판독 → 체크리스트 검증
- 건물부하계산서·운전계획서·설비사양 산출 (수식 포함 xlsx)
- 오류 카탈로그 기반 불일치 자동 검출, 재현성 검증 스크립트 포함

설치계획서 파일을 첨부하면 스킬이 자동 트리거됩니다.

문서에 등장하는 현장명은 익명 예시(`A빌딩`)이며, `assets/forms/`의 `.hwp` 2건은 한전 공식 빈 서식입니다.

---

개인 스킬(논문 분석·특허 조사·문서 번역 등)은 별도 비공개 저장소에서 관리합니다.
