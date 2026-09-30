---
name: rp-blind
description: 연구계획서 두 판을 블라인드로 비교한다. 본문 텍스트만 A/B 로 심판(ChatGPT 웹 또는 Claude 새 서브에이전트)에게 보내고, 순서를 바꿔 두 번 물어 두 번 모두 같은 쪽을 고른 항목만 확정한다. 「블라인드 비교」「두 판 비교」「어느 쪽이 나은지 외부에 물어봐」「원본 대 수정본」 요청, 또는 rp-run 의 회차 채택·완료 판정에서 쓴다.
---

# 블라인드 비교 스킬

우리 채점기는 「있는가」만 보고 「사라졌는가」를 보지 않았다(t3: 우리 점수 94.5, 외부 비교에서는 원본보다 나쁨).
그래서 판과 판의 우열은 채점기 점수가 아니라 이 비교로 정한다.

## 0. 원칙

- 심판에게는 **본문 텍스트만** 간다(`hwpx_text.py` 추출). 파일 이름·문서 이름(원본/최종본)·과제 기록·점수는 보내지 않는다.
- 순서를 바꿔 **두 번**, 매번 **새 대화(새 인스턴스)**. 두 번 모두 같은 문서를 고른 항목만 「확정」.
- 한 회가 6항목 중 5개 이상 같은 위치(A 또는 B)를 고르면 「위치 편향 의심」으로 표시된다(81 2회차 사례). 그 회는 새 대화로 한 번만 다시 묻고, 두 결과를 모두 보고한다.
- 집계는 `blind_compare.py tally` 만 한다. 손으로 세지 않는다.

## 1. 심판 고르기

| 심판 | 언제 | 조건 |
|---|---|---|
| ChatGPT 웹 | rp-run 회차 채택, 채점기 보정, 교정 효과 실험, 완료 판정 | 외부 전송 동의(`23_consent.json.external_ai`)가 있거나 사용자가 직접 요청 |
| Claude | 동의가 없을 때, 또는 ChatGPT 절차가 실패했을 때 | 원고를 Claude 가 썼으므로 결과에 「자기 평가 편향 가능」이 붙는다 |

회차 채택 심판을 Claude 에서 ChatGPT 로 바꾼 것은 plan_t4fix 6(2026-09-28): t4 회차 1 에서 Claude 심판이 6항목 전부 cur 를 골랐다.
확정 승 6항목이 모두 한쪽이면 `tally` 가 「편향 의심」(`sweep`)을 표시한다. 판정은 바꾸지 않고 보고서에 남긴다.

## 2. 준비

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/blind_compare.py" prepare --a <X.hwpx|md> --b <Y.hwpx|md> \
    --out <dir> --label-a <이름> --label-b <이름> --judge chatgpt|claude
```

`<dir>` 에 `prompt_1.md`(A=X)·`prompt_2.md`(A=Y)·`prompt_N.js`·`meta.json` 이 생긴다.

## 3. 묻기

**ChatGPT**: `chatgpt_web.md` 절차를 회마다 새 탭·새 대화로 두 번(N = 1, 2). 입력은 `prompt_N.js` 를 `javascript_tool` 에 그대로 넘긴다. 답의 표를 `<dir>/response_N.md` 로 저장.

**Claude**: 회마다 새 `Agent(general-purpose)` 를 부른다. 프롬프트는 아래 문장만:

```
<dir>/prompt_N.md 를 Read 로 읽고 그 지시대로 답하라. 다른 파일은 읽지 마라.
답(표 하나)을 <dir>/response_N.md 에 Write 로 저장하라.
```

대화 맥락·문서 이름·과제 이야기를 덧붙이지 않는다. 두 회를 한 에이전트에게 맡기지 않는다.

## 4. 집계

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/blind_compare.py" tally --dir <dir>
```

`blind.md`(1회·2회·확정 표, 문서별 확정 승 항목, 편향 표시)·`blind.json` 이 생긴다. exit 2 면 답 표를 못 읽은 것이다: 그 회만 새 대화로 다시 묻는다.

## 5. 하지 말 것

- 서식(글꼴·줄간격·표 선)을 판정에 넣기, 두 회를 같은 대화에서 묻기, 확정이 아닌 항목을 승패로 보고하기, 우리 채점기 점수를 심판에게 보여주기
