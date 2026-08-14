---
name: template-extraction
description: 연구계획서 양식(HWPX/PDF)에서 작성 목차·폰트·여백·분량·주의사항 규칙을 기계가 따를 수 있는 표로 추출하는 스킬. 양식이 지정되지 않으면 동봉된 기본 양식으로 폴백한다. "양식 분석", "템플릿 추출", "작성 규칙 정리", "목차 확인"을 요청하거나 연구계획서 서식 파일이 주어지면 반드시 사용한다.
---

# 템플릿 추출 스킬

연구계획서 양식을 분석해 **HWPX 작성 에이전트가 그대로 소비할 수 있는 규칙 표**를 만든다.

## 워크플로우

### 0. 양식 파일 결정 — ★ 이 순서를 반드시 지킨다

| 순위 | 출처 | 조건 |
|---|---|---|
| 1 | **사용자가 지정한 양식 파일** | 경로·첨부로 명시된 서식이 있으면 무조건 이것 |
| 2 | **공고 첨부 서식** | `00_announcement.md`·`00_raw/` 의 「작성/제출」 대상 서식 |
| 3 | **기본 양식(폴백)** | 위 둘이 모두 없을 때 — `assets/default-form/default_proposal_form.pdf` (규칙의 유일한 출처) |

**1·2가 없다고 멈추지 않는다.** 3으로 진행하되 아래 두 가지를 반드시 한다.

- 산출 파일 머리에 **`양식출처: 기본양식(폴백)`** 을 적는다. 어떤 서식으로 썼는지가 뒤 단계·검수에서 갈리기 때문이다.
- 사용자에게 **"공고 지정 서식이 없어 기본 양식으로 진행합니다. 지정 서식이 있으면 주세요"** 를 1회 알린다(진행은 막지 않는다).

폴백일 때는 **파싱을 새로 하지 말고** 사전 추출본 `assets/default-form/default_form_rules.md` 를 `01_template_rules.md` 로 복사한 뒤,
공고에 별도 서식 지시(분량·글꼴 등)가 있으면 그 항목만 덮어쓴다.

```bash
D="$CLAUDE_PLUGIN_ROOT/skills/template-extraction/assets/default-form"
cp "$D/default_form_rules.md" _workspace/01_template_rules.md   # 사람이 읽는 규칙
cp "$D/default_form_spec.json" _workspace/01_template_spec.json  # ★ 게이트가 읽는 기계 명세
```

기본 양식의 성격·교체 방법은 `assets/default-form/README.md` 참조. 특정 부처 공고에 실제 제출할 때는 **그 공고의 첨부 서식이 항상 우선**한다.

### 1. 제출 문서 선별
공고 첨부파일 중 "작성/제출" 대상 서식(연구계획서, 요약서, 예산서 등)을 구분해 목록화한다.

### 2. 양식 파일 파싱
- HWPX: `unzip -p 양식.hwpx 'Contents/section*.xml'`로 텍스트/구조 추출. 문단 스타일(글꼴·크기)은 `Contents/header.xml`의 charPr/paraPr 참고.
- PDF: `Read`(pages 지정)로 목차·서식 안내 페이지 확인.
- 파싱이 어려우면 텍스트만이라도 추출하고 서식 항목은 "확인 불가"로 둔다(STATUS: PARTIAL).

### 3. 규칙 추출 — 4개 섹션으로 구조화
1. **제출 문서 목록**: 문서명 · 형식 · 필수여부
2. **목차 트리**: 장/절 구조 + 각 항목별 요구 내용(무엇을 써야 하는가)
3. **서식 규칙 표**: 글꼴 · 크기 · 줄간격 · 여백 · 페이지/분량 제한 · 표·그림 규칙
4. **주의사항 체크리스트**: 붉은 글씨 안내, 작성 금지사항 등

### 4. ★ 기계판독 명세(JSON) 산출 — 게이트의 입력이다

규칙표(md)만 만들면 **지켰는지 아무도 검사하지 못한다.** 같은 내용을 `01_template_spec.json` 으로도 낸다.
스키마는 `assets/default-form/default_form_spec.json` 을 그대로 따르고, 항목을 빼거나 이름을 바꾸지 않는다.

| 키 | 내용 | 쓰는 곳 |
|---|---|---|
| `page_budget` | 총 분량·상한·**장별 배분**·허용오차 | `gate_pages.py` |
| `style` | 용지·글꼴·pt·줄간격 | 헤더 패치·`gate_hwpx.py` J-16 |
| `limits` | 산문 자수·표 개수·표 열수 상한(+양식 지정 절 예외)·그림 수 | `gate_form.py` F-6·F-7 |
| `outline[]` | 장·절 **제목 원문**, 그 절의 **`guide`(양식 설명문 원문)**, `probes`(커버리지 정규식), `special`(지정 서식) | 스캐폴드·`gate_form.py` F-1·F-3·F-4 |
| `residue_exempt` | 설명문이지만 **본문에 그대로 써야 하는 표제**(「가. 1차년도」·「[표 A]」 등) | `form_strip.py`·F-5 |
| `guide_residue_patterns` | 산출물에 남으면 안 되는 안내 문구 | F-5 |

**`guide` 는 양식 원문을 그대로 옮긴다** — 이것이 스캐폴드의 체크리스트가 되고, 동시에 「지워야 할 문장」의 목록이 된다.
양식이 「권장」이라고 쓴 항목은 `special` 에 `{"key":…,"severity":"warn"}` 으로 넣어 **통과를 막지 않게** 한다.

### 5. 불명확 항목 처리
규칙이 명시되지 않은 항목은 **추정하지 말고 "명시 없음"**으로 남긴다. 뒤에서 사람이 판단.

## 출력
- `_workspace/01_template_rules.md` — 첫 줄 `## STATUS: OK | PARTIAL`, 둘째 줄 `양식출처: <파일명> | 기본양식(폴백)`
- `_workspace/01_template_spec.json` — 기계판독 명세(§4). **이것이 없으면 양식·분량 게이트를 돌릴 수 없다.**

## 동봉 자산

| 경로 | 내용 |
|---|---|
| `assets/default-form/default_proposal_form.pdf` | **양식 원본(3쪽)**. 규칙의 유일한 출처이며 [표 A]·[표 B] 실물은 2~3쪽 |
| `assets/default-form/default_proposal_form.md` | 위 PDF의 **전사본**. 목차 골격을 복사해 작성 시작점으로 쓴다 |
| `assets/default-form/default_form_style.json` | HWPX 조립용 스타일맵 |
| `assets/default-form/default_form_rules.md` | 사전 추출 **작성 가이드라인 겸 규칙표**(폴백 시 그대로 복사) — 분량 원단위·체크리스트 포함 |
| `assets/default-form/default_form_spec.json` | **기계판독 명세**(폴백 시 `01_template_spec.json` 으로 복사) — 스캐폴드·양식 게이트·분량 게이트가 모두 이 파일을 읽는다 |
| `assets/default-form/README.md` | 양식의 성격·교체 절차·스크럽 규율 |

**기본 양식으로 쓸 때 자주 어기는 3가지**(전부 실측 적발): ⑴ **[표 B] 간트는 1차년도 월 단위 12칸**이다 — 분기×4개년 표는 위반 ⑵ KPI 표에 **평가환경** 열이 빠진다(양식은 단위·기준값·목표치·평가방법·평가환경 5요소를 요구) ⑶ 2-2는 **[표 A] 형식(구분/연차/목표)**이어야 하며 서술로 대체하지 않는다.

**왜 표로 만드나:** `hwpx-writer`가 산문을 해석하지 않고 항목/값을 직접 매핑해 서식을 적용하기 때문. 목차 항목명은 원문 그대로 유지해야 작성·검수가 어긋나지 않는다.
