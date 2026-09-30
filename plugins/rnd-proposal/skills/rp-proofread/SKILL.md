---
name: rp-proofread
description: 완성된 연구계획서에 대해 외부 생성형 AI(ChatGPT·Gemini, requirements.md 의 external_ai, 기본 ChatGPT)에게서 「문제 목록」(위치·문제·이유)만 받는다. 문장을 고쳐 달라고 하지 않는다. 받은 목록은 check_proofread.py 가 인용 대조로 걸러 교정 회차 편집자(rp-editor, 고치기 모드)의 입력이 된다. "교정", "윤문", "외부 검토", "GPT 교정", "문제점 찾아줘" 요청, rp-run 의 proofread 단계, 교정 효과 실험에서 쓴다. Chrome MCP 로 웹 화면을 쓰며 API 키가 필요 없다.
---

# 외부 AI 교정 스킬 (문제 목록 받기)

## 0. 원칙: 외부 모델은 지적만 하고, 고치지 않는다

외부 모델에게 문장을 고치게 하면 사실을 바꾼다(61_검토피드백: `0.8790` 을 「주관기관의 선행연구를 통해 사전 확보함」으로 옮기라고 했다).
반대로 평가자로 쓰면 우리 채점기의 맹점을 잡았다(81_비교검증: 작성 지시 라벨·절 번호 참조·캡션 불일치). 그래서 (plan_v2 4단계, 2026-09-28)

> **외부 모델에게서는 위치(원문 인용)·문제·이유만 받는다. 원고 문장은 한 글자도 받지 않는다.**
> 고치는 것은 교정 회차의 rp-editor(고치기 모드: op, 삭제 없음, 정보 보존 C-m5)이고, 그 회차는 채택 판정(adopt: 직전 판과의 블라인드)을 거친다.

rp-run 에서의 기본값은 **교정 켬**(`requirements.md` 의 `proofread:` 가 없으면 `rp_run.PROOFREAD_DEFAULT`). 아래 7 의 효과 실험(2026-09-28)에서
교정 적용본이 두 심판 모두에서 이겨 켰다(`criteria/proofread_experiment.md`). 끄려면 `requirements.md` 에 `proofread: off`.

## 1. 어느 AI 로 보내나: 설정값

`<run>/requirements.md` 프런트매터의 `external_ai:` 를 읽는다. 없으면 **chatgpt**.

| 값 | 주소 | 입력 요소 | 전송 |
|---|---|---|---|
| `chatgpt` (기본) | `https://chatgpt.com/?temporary-chat=true` | `div.ProseMirror[role="textbox"]` | `skills/rp-blind/chatgpt_web.md` |
| `gemini` | `https://gemini.google.com/app` | `div[contenteditable="true"]` | `aria-label="메시지 보내기"` (「보내기」 부분 매칭은 `공유 및 내보내기`를 먼저 잡는다). 모델은 **Pro** 로(Flash 는 전문을 거부) |

스킬 본문에 도구 이름을 더 박지 않는다 (새 도구는 이 표에 행을 더한다).

## 2. 무엇을 보내는가

`30_proposal.build.md`(주석 제거판) 전문을 **한 번에**. `.hwpx` 는 보내지 않는다.

> ⚠️ 본문이 외부 서비스로 나간다. 전송 동의는 rp-run 시작 질문에서 한 번 받는다(`23_consent.json` 의 `external_ai`, 민감 정보 후보 경고 포함). 여기서 다시 묻지 않는다. 동의가 없으면 이 스킬을 부르지 않는다.

## 3. 요청 프롬프트: 고정 블록

```
아래는 한국 정부 R&D 연구계획서입니다. 심사위원 입장에서 문제가 있는 곳만 찾아 주세요. 고친 문장은 쓰지 마세요.

[찾을 것]
- 어색한 조사·어순·낱말 오용, 호응이 어긋난 문장, 조사가 떨어져 뜻이 모호한 곳
- 뜻이 같은 주장의 반복, 한 항목에 두 주장
- 작성 지시·메모처럼 읽히는 표현(「○○ 한 줄:」 같은 라벨, 절 번호로 내용을 대신하는 곳)
- 수치·단위·표기의 불일치(같은 것을 다르게 적은 곳), 근거 없이 단정하는 곳

[답 형식] 아래 표 하나만. 표 앞뒤에 다른 글을 쓰지 마세요. 원문 인용은 본문에서 글자 그대로 복사하세요.
| # | 절 | 원문 인용 | 문제 | 이유 |
|---|---|---|---|---|
| 1 | 1-1 | <본문 문장 그대로> | <무엇이 문제인가> | <왜 문제인가> |

--- 본문 ---
<여기에 전문>
```

## 4. Chrome MCP 절차

**ChatGPT**: `skills/rp-blind/chatgpt_web.md` 절차를 그대로 쓴다(임시 대화, JS insertText, 입력과 전송은 다른 호출, `document.title` 축약, 공백 제외 글자 수 검증). 입력 JS 는
`python -c "import sys; sys.path.insert(0, r'$CLAUDE_PLUGIN_ROOT/scripts'); from blind_compare import insert_js; print(insert_js(open(r'<프롬프트 파일>', encoding='utf-8').read()))"` 로 만든다.

**Gemini**: 클립보드 붙여넣기 + 실제 클릭.

```
1) tabs_context_mcp → 새 탭
2) navigate <설정값의 주소> ; 모델을 Pro 로
3) PowerShell Set-Clipboard 로 프롬프트 적재
4) find("<입력 요소>") → ref ; computer left_click ref ; computer key ctrl+v
5) find("전송 버튼") → ref ; computer left_click ref
6) 응답 대기 (추론 모델은 3~5분) ; 「| # |」 표 구간만 수거
```

★ Gemini 는 JS 입력·합성 이벤트가 먹지 않는다(실측 2026-09-09). ChatGPT 는 반대(클립보드 실패, JS 입력만).
★ 좌표 클릭 금지(`ref` 로만). 셀렉터가 2~3회 안 맞으면 멈추고, 사용자에게 묻지 않고 `60_교정문제.md` 를 「문제 0건」으로 둔 채 다음 액션으로 간다(사유는 파일 머리에 한 줄).

## 5. 원장에 적재

받은 표를 `<run>/60_교정문제.md` 에 그대로 넣는다(머리 줄 `# 외부 교정 문제 목록: <도구> (<날짜>)`). 모델이 「제안」 열을 붙여 와도 손대지 않는다: 다음 단계가 버린다.

## 6. 걸러서 편집자에게

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/check_proofread.py" --problems <run>/60_교정문제.md --md <run>/30_proposal.md --out <run>/60_교정문제.json
```

- 행마다 원문 인용이 원고에 **정확히 한 번** 있는지만 본다. 있으면 「유효」, 없거나 여러 번이면 「기각: 인용 n회」. 원장의 판정 열을 채워 다시 쓴다.
- 유효 행만 `60_교정문제.json` 으로 나가고, rp-run 이 교정 회차(rp-editor 고치기 모드 → apply-edits → trim → 조립 → 채점 → adopt)를 돈다.
- 판정을 손으로 바꾸지 않는다. 외부 모델의 문장을 원고에 붙여 넣지 않는다.

## 7. 교정 효과 실험 (기본값을 정한다)

같은 초안 D 에서 교정 적용본 A 와 미적용본 B 를 블라인드로 비교한다. 결과는 `rp_run.PROOFREAD_DEFAULT` 를 바꿀 근거다.

```bash
X=<실험 폴더>; mkdir -p $X
cp <run>/30_proposal.md $X/A.md ; cp <run>/30_proposal.md $X/B.md        # D
```
1. D 로 3~5 절차를 돌려 `$X/60_교정문제.md` 를 받고 `check_proofread.py --problems $X/60_교정문제.md --md $X/A.md --out $X/problems.json`.
2. rp-editor(고치기 모드)에 `$X/A.md` 와 `$X/problems.json` 을 주고 `$X/edits_A.json` 을 받는다.
   `python "$CLAUDE_PLUGIN_ROOT/scripts/edit_apply.py" --md $X/A.md --edits $X/edits_A.json --ledger $X/74_수정원장.json`
3. 블라인드 두 심판(`rp-blind` 스킬):
   `blind_compare.py prepare --a $X/A.md --b $X/B.md --label-a 교정 --label-b 미교정 --judge chatgpt --out $X/blind_chatgpt` (Claude 는 `--judge claude --out $X/blind_claude`), 각 2회 답 → `tally`.
4. `python "$CLAUDE_PLUGIN_ROOT/scripts/rp_run.py" experiment-decide --out $X` → `$X/85_교정실험.md`.
   판정 규칙: **두 심판 모두**에서 교정 적용본 확정 승 1개 이상·미교정본 확정 승 0 이면 「켬」, 아니면 「끔」.
5. 결과를 `criteria/proofread_experiment.md` 에 옮겨 적고, 「켬」일 때만 사람이 `PROOFREAD_DEFAULT` 를 바꾼다.

## 8. 하지 말 것

- 외부 모델에게 문장 재작성·윤문 결과를 요청하기, 받은 제안 문장을 원고에 반영하기, `.hwpx` 보내기, 판정을 손으로 고치기, 셀렉터 무한 재시도
