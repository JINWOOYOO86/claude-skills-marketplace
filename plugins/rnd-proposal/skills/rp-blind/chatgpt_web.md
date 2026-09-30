# ChatGPT 웹 입력 절차 (Chrome MCP, 공통)

rp-blind·rp-proofread(그리고 7단계 그림)가 ChatGPT 에 글을 보낼 때 이 절차만 쓴다.
실측 근거: 2026-09-27 교정(10,068자 입력 확인), 2026-09-28 블라인드 비교.

| 요소 | 셀렉터 | 비고 |
|---|---|---|
| 입력창 | `div.ProseMirror[role="textbox"]` | `#prompt-textarea` 없음 |
| 보내기 | `button[aria-label="보내기"]`, 영문 화면은 `button[data-testid="send-button"]` | 글자를 넣어야 나타난다 |
| 응답 중 | `button[data-testid="stop-button"]` | 있으면 아직 생성 중 |
| 마지막 답의 표 | `document.querySelectorAll('table')` 의 마지막 요소 | `main` 밖에 그려질 때가 있다. `[data-message-author-role]` 은 없다(실측 2026-09-28) |

★ 클립보드 붙여넣기(ctrl+v)는 두 번 실패했다(빈 입력·옛 클립보드 잔존). JS `insertText` 로 넣는다.
★ 이 페이지에서 `find`·스크린샷은 타임아웃이 잦다. 요소는 `javascript_tool` 로 찾고 `.click()` 한다. 좌표 클릭 금지.
★ 회마다 **새 대화**. 계정 메모리가 앞 대화 내용을 끌어오지 않게 임시 대화 주소를 쓴다.
★ 보낸 뒤 탭 제목이 프롬프트 전문으로 바뀌어 모든 도구 결과에 따라붙는다. 입력·전송 JS 에서 `document.title` 을 짧게 바꾼다.
★ 답 모델 이름(화면 아래 「Instant」 등)을 보고서에 적는다. 두 회는 같은 모델로 한다.
★ 임시 대화를 처음 열면 「임시 채팅」 안내 창이 입력창을 가린다(설명뿐, 동의 항목 없음). `[...document.querySelectorAll('button')].find(b => b.innerText.trim() === '계속').click()` 로 닫는다(실측 2026-09-28).
★ 브라우저 창이 OS 포커스를 잃으면(`document.hasFocus()` false) `insertText` 가 조용히 실패한다. `prompt_N.js` 는 그때 합성 paste 이벤트로 넣는다(결과 `via=paste`). 입력 직후 `innerText` 는 렌더 전이라 0 일 수 있다: JS 가 잠시 기다린 뒤 잰 `ns=` 를 본다.

## 절차

```
1) tabs_context_mcp → 새 탭(tabs_create_mcp)
2) navigate https://chatgpt.com/?temporary-chat=true        ← 임시 대화(메모리·기록 없음)
   임시 대화가 막혀 있으면 https://chatgpt.com/ 새 대화로 하고 보고에 적는다
3) javascript_tool: <prompt_N.js 파일 내용 그대로(앞의 await 포함)>   ← 'via=insertText|paste ns=<공백 제외 글자 수>' 가 돌아온다
   'no-textbox' 면 2~3초 뒤 한 번 더
   검증: ns 가 prompt_N.md 의 공백 제외 글자 수와 같아야 한다(줄바꿈 수는 편집기가 바꾸므로 공백 제외로 비교)
4) javascript_tool (3) 과 **다른 호출**로. 입력과 같은 호출에서 누르면 버튼 상태가 갱신 전이라 전송되지 않는다(실측 2026-09-28):
   (document.querySelector('button[aria-label="보내기"]') || document.querySelector('button[data-testid="send-button"]')).click()
   전송 확인: 몇 초 뒤 주소가 /c/<id> 로 바뀐다. 안 바뀌면 한 번 더 누른다
5) 대기: javascript_tool 로 30초 간격 확인 (추론 모델은 3~5분, 상한 10분)
   !document.querySelector('button[data-testid="stop-button"]') 이고 table 행 수가 두 번 연달아 같으면 끝
6) 수거: javascript_tool. 도구 결과는 약 2,000자에서 잘린다: 행 수를 먼저 세고 2,000자 안에 들도록 slice 로 나눠 읽는다(교정 문제 목록은 5행씩). 잘린 칸의 뒤를 추측해 채우지 않는다:
   (() => { const t = [...document.querySelectorAll('table')].pop();
            return [...t.querySelectorAll('tr')].slice(0, 4).map(tr => '| ' + [...tr.children].map(c => c.innerText.trim().replace(/\|/g, '／').replace(/\n/g, ' ')).join(' | ') + ' |').join('\n'); })()
   → 결과를 response_N.md 로 Write (머리 행 아래 |---|---|---| 를 넣는다)
7) 탭을 닫는다(다음 회는 새 탭·새 대화)
```

## 실패 처리

- 셀렉터가 2~3회 안 맞거나 10분 안에 답이 없으면 멈추고 호출한 스킬의 실패 규칙을 따른다(무한 재시도 금지).
- 답에 표가 없으면(거부·설명문) 같은 프롬프트로 새 대화에서 한 번만 다시 한다.
