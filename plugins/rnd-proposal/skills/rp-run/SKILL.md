---
name: rp-run
description: 연구계획서를 처음부터 끝까지 사람 개입 없이 만든다(시스템 모드). 설계서 → 시작 질문 1회(설계서 승인·근거 빈칸 답·외부 전송 동의) → 절별 집필 → 조립·기계 검사·채점 → 목표 점수(rubric scoring.target)에 닿을 때까지 수정 회차(표기 통일 스크립트 → 문서 전체 편집자 → 절별 집필자) → (켜져 있으면) 외부 교정 문제 목록 → 교정 회차 → 제출 파일·보고. 메인 세션에서 도는 오케스트레이션 스킬이며 서브에이전트(rp-spec·rp-writer·rp-editor·rp-scorer)는 여기서만 한 단계 깊이로 부른다. 「계획서 만들어줘」「처음부터 돌려줘」「rp-run」 요청 시 사용한다.
---

# rp-run: 메인 세션 오케스트레이션 (시스템 모드)

이 스킬은 **판단하지 않는다.** `scripts/rp_run.py next` 가 주는 액션을 그대로 실행하고 다시 `next` 를 부른다. `[done]` 이 나올 때까지 반복한다.
사람에게 묻는 것은 `[ask]` 단계 **한 번**뿐이다. 그 뒤로는 값을 묻지 않고, 근거가 없는 체크는 「미충족」으로 남긴 채 끝까지 간다.

기준: `criteria/rubric.yaml` 이 채점·종료 조건(`scoring.target` 기본 95, `max_rounds` 6, `stall_rounds` 2)·수정 주체(`fix_by`)·질문 항목(`needs`·`requires`)의 유일한 원본이다. 보고는 6항목 이름과 체크 id 만 쓴다.

## 실행 한 줄

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/rp_run.py" next --run <run>        # <run> = workspace/<과제>/  (requirements.md · 50_form_spec.json 이 입력)
```

출력의 `[단계]` 와 액션 목록을 위에서부터 실행한다. 액션 종류는 다섯이다.

| 액션 | 하는 일 |
|---|---|
| `$ …` (cmd) | 그 명령을 그대로 실행한다. exit 2 면 멈추고 마지막 출력을 보고한다. exit 2 는 도구 오류뿐이다: 내용 위반(R1~R7·대시·내부 표기·쪽수)은 assemble 이 끝까지 조립하고 machine → fix 가 해당 절로 되돌린다 |
| `(stop)` | 멈추고 그 문구와 `90_제출보고.md` 의 정지 사유를 보고한다 |
| `Agent(rp-x)` | `Agent(rnd-proposal:rp-x)` 를 부른다. `병렬` 표시면 한 메시지에서 전부 띄운다. 목록에 그 에이전트가 없으면(세션 중 플러그인 재설치 뒤에는 사라진다) `general-purpose` 에 `agents/rp-x.md` 를 먼저 읽고 따르게 한다. 입력 경로는 출력에 적힌 것을 그대로 준다 |
| `Agent(general-purpose)` 블라인드 | adopt 단계의 Claude 심판. 출력에 적힌 두 프롬프트를 **각각 새 에이전트**에 그 문장만 준다(병렬). 문서 이름·과제 맥락·점수를 덧붙이지 않는다(rp-blind 스킬 3) |
| `Skill(rp-blind)` (adopt) | 회차 채택 블라인드를 ChatGPT 로 2회(`chatgpt_web.md`). 절차가 실패하면 액션의 `fallback` 명령(`--judge claude` 로 같은 dir 에 다시 prepare)을 실행하고 Claude 심판 2회(새 에이전트)로 답을 채운 뒤 `adopt` 를 실행한다. 보고서에 「자기 평가 편향 가능」이 붙는다 |
| `Skill(rp-proofread)` | 그 스킬을 따른다. 전송 동의는 시작 질문에서 이미 받았다. 외부 모델에게서 문제 목록만 받는다(문장 재작성 없음). 브라우저 절차가 실패하면 멈추지 않고 `60_교정문제.md` 를 「문제 0건」으로 두고 다음 액션으로 간다 |
| `★ 사용자에게 한 번에 묻는다` | 아래 「시작 질문」. 답을 받으면 출력에 적힌 `answers` 명령을 실행한다 |

## 단계 순서 (next 가 정한다)

```
requirements → spec → gaps → ask(1회) → [figures: final] → write → assemble → machine → judge → tally → adopt(회차 0: 스냅숏)
tally → adopt(회차 n: 정보 보존·쪽수·Claude 블라인드 → 채택 또는 직전 채택 판으로 되돌림)
adopt 뒤: 목표 도달 / 회차 상한 / 정체 / 고칠 것 없음 → proofread(동의 + `proofread` 가 on(기본값)일 때만: 문제 목록 → 교정 회차 rp-editor op → apply-edits → trim) → assemble → machine → judge → tally → adopt → deliver → report → done
       같은 floor 체크가 연속 두 채택 수정 회차(회차 1 이상, 수정 미적용 결함 제외)에서 실패 → report → stopped (교정·제출 복사 안 함)
       그 밖 → fix(회차 +1): unify(스크립트) → writer(절별 병렬 op) → apply-edits → editor(op, 잠긴 줄 목록) → apply-edits → trim → defects
       defects 에 결함(floor 를 고친 op 가 원고에 없음)이 있으면 → retry(회차당 1번: 결함 사유를 준 writer·editor op → apply-edits → trim → defects --retry) → assemble …
```

**고치기 모드 (plan_v2 3단계, 2026-09-28)**: 첫 초안 뒤 모든 수정 회차는 외과 수정이다. 편집자·집필자는 원고를 고치지 않고
`edits/r<n>_*.json` 에 문장 단위 op(replace·insert_after·merge)만 쓴다. `apply-edits` 가 적용하면서 삭제·정보 소멸(C-m5)·라벨·절 번호 참조를
거부하고 `74_수정원장.md` 에 전후를 남긴다. `trim` 은 장 예산을 넘으면 이번 회차 추가 문장부터 되돌린다. `adopt` 는 회차 결과가
정보 보존(C-m5)·쪽수(F-m3)를 지키고 직전 채택 판과의 블라인드(외부 전송 동의가 있으면 ChatGPT, 없으면 Claude: 「자기 평가 편향 가능」 표시, plan_t4fix 6)에서 지지 않을 때만 채택하고, 아니면 `rounds/r<p>/` 로 되돌린다
(t3: 우리 점수는 올랐지만 외부 비교에서 원본보다 나빴다. 점수만으로 회차를 채택하지 않는다).

- `assemble` 은 `rp_run.py assemble --repro` 로 두 번 빌드해 sha 가 같아야 통과한다. 그 안에서 `harness_assemble.py --loop` 가 대시류 치환·테두리·대시 0·R1~R7·내부 표기·쪽수를 본다. 내용 위반은 exit 3(통과로 보고 다음 단계), 도구 오류만 exit 2.
- `machine` 은 `check_rubric --no-fail` 이라 floor 실패여도 exit 0 이다. 실패 체크마다 고칠 절(`sections`)을 70_machine.json 에 적는다.
- `tally` 는 `70_score.json` 을 쓴다: `total`, `target`, `reached`, `unmet`(답 없는 needs 를 가진 체크). 점수는 `check_rubric.score_items` 가 계산한다. 손으로 더하지 않는다.
- `fix` 는 실패 체크를 rubric `fix_by` 로 묶는다. machine 실패는 `sections` 의 절 writer 로, 절을 모르면 editor 로 간다. `unmet` 체크는 회차에 넣지 않는다(못 넘는 체크에 회차를 쓰지 않는다).
- 수정 회차 machine 은 `--before rounds/r<p>/30_proposal.build.md`(직전 채택 판)로 C-m5 정보 보존을 잰다.
- **한 칸 한 작성자 (plan_t4fix 1)**: 집필자 → 편집자 순. 이번 회차에 고친 줄은 잠기고(`edits/r<n>_locked.md`), 다른 작성자의 op 가 그 줄을 건드리거나 앞 수정을 되돌리면 적용 전에 거부된다(원장 「슬롯 잠김」·「앞 수정 되돌림」, 보고서 「충돌 막음」).
- **정지 규칙 구분 (plan_t4fix 5)**: floor 를 고친 op 가 원고에 남아 있는데도 다시 실패하면 「고치려 했는데 실패」로 연속 실패에 센다. op 가 없거나 거부·되돌림·덮어씀으로 남지 않았으면 「수정 미적용」 결함이다: `retry` 액션으로 같은 회차에 한 번 다시 적용하고, 그래도 남으면 보고서에 결함으로 적되 정지 규칙에는 세지 않는다. `trim` 은 floor 를 고친 op 를 되돌리지 않는다.
- **빠른 재현 (plan_t4fix 7)**: 코드를 고친 뒤에는 처음부터 돌리지 않고 `rp_run.py resume --from <run> --round <채택 회차> --to <새 폴더>` 로 그 스냅숏에서 다음 회차부터 확인한다. 회차 n-1·n 의 기계 검사를 지금 검사기로 다시 잰다.
- `retry` 의 `Agent(rp-writer|rp-editor)` 에는 액션의 `reasons`(체크별 결함 사유)를 brief·입력과 함께 준다.
- 되돌린 회차는 정체(stall) 회차로 세고, 연속 floor 실패 판정에서는 빼고 본다. 기록은 `72_rounds.json` 의 `adopt`·`history[].reverted`·`fixes[n].edits/trim`.
- 같은 floor 체크가 연속 두 채택 회차(첫 실패 → 수정 회차 → 재실패) 실패하면 `next` 가 `report` 뒤 `stopped` 를 준다. 거기서 멈추고 보고한다.
- 원고를 고친 뒤(unify·apply-edits·trim·proofread·adopt 되돌림)에는 `split` 이 절 파일을 맞춘다(apply-edits·trim·adopt 는 스스로 한다). 첫 초안 절별 집필 뒤에는 `merge`.

## 시작 질문 (한 번, `[ask]` 단계)

한 메시지에 묶어 `AskUserQuestion` 으로 묻는다. 항목은 `next` 출력에 적혀 있다.

1. **설계서 승인**: `20_spec.md` 의 §1 사슬표 행 수·§2 KPI 추적·§8 미확정 목록을 보여 주고 승인 여부.
2. **근거 빈칸 답** (「[floor]」 행은 floor 체크를 막는 값이다: rubric requires 와 설계서 §8 「막는 체크」 열에서 온다. 답이 없으면 그 floor 체크는 시작 질문에서 미충족으로 확정되니 따로 짚어 묻는다): `21_questions.md` 표(체크·key·묻는 것·찾아본 곳)를 보여 주고 값을 받는다. 채팅으로 받은 답은 그 파일의 「답」 열에 **값만** 옮겨 적는다(날짜·「사용자 답」 같은 꼬리표를 붙이지 않는다: t1 에서 원고 20곳으로 샜다). 모르면 「없음」. `answers` 가 값은 `_ws/16_user_answers.md` 대장 행으로, 출처는 `<run>/22_answer_sources.json` 으로 나눠 적는다. brief ④ 에는 값만 간다.
3. **외부 전송 동의**: `30_proposal.build.md` 전문을 `external_ai`(기본 chatgpt)에 보내도 되는지. 쓰는 곳(외부 교정 문제 목록·완료 판정 블라인드·교정 효과 실험)과 `next` 가 적어 준 **민감 정보 후보**(기관명·금액)를 함께 보여 준다. 아니오면 외부 모델 단계는 전부 건너뛰고 블라인드는 Claude 심판만 쓴다. 외부 교정은 기본값이 「켬」이다(효과 실험 2026-09-28, `requirements.md` 에 `proofread: off` 면 끔).
4. (final 만) `20_spec.md` §7 그림 후보 중 승인할 번호.

답을 받으면:
```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/rp_run.py" answers --run <run> --spec-approved --external yes|no [--figures 1,2]
```
「수정 후 재작성」이면 rp-spec 을 다시 부르고 같은 질문을 다시 한다(답을 받기 전까지는 집필하지 않는다).

### 목표 하향 확인 (`[ask_down]`, 시작 질문 1회 원칙의 유일한 예외)

`answers` 가 답의 목표가 설계서 §2 기준보다 느슨하다고 보면(예: 「동등 이상」→「95 % 이상」, `check_targets.py`) exit 3 으로 끝나고
`next` 가 `ask_down` 을 준다. **그 항목만** 한 번 묻는다: 그대로 둘지(예), 답을 고칠지. 고치면 `21_questions.md` 「답」 열을 바꾼다.
```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/rp_run.py" answers --run <run> --confirm-down yes|no
```
고치기 회차·rp-revise 에서는 묻지 않는다: `edit_apply.py` 가 목표를 낮추는 op 를 거부한다.

## 에이전트 입력 규약

| 에이전트 | 입력 | 출력 |
|---|---|---|
| rp-spec | spec_template.md · rubric.yaml · requirements.md · 50_form_spec.json · 근거팩 · 모드 | 20_spec.md |
| rp-writer (병렬) | `briefs/brief_<S>.md` 하나 | 첫 초안: `sections/<S>.md` 절 본문 · 수정 회차: `edits/r<n>_<S>.json` op 목록 |
| rp-editor | 30_proposal.md(읽기만) · 실패 체크 id 와 사유(70_채점보고.md) · 15_axis_conflicts.md §B-1 · 50_form_spec.json | `edits/r<n>_editor.json` op 목록 |
| rp-scorer | rubric · 70_machine.json · 30_proposal.build.md · hwpx · 50_form_spec.json · 20_spec.md · §B-1 · 모드 | 70_judge.json · 70_채점보고.md |

에이전트가 「집필로 해결 불가」를 보고하면 그대로 두고 다음 액션으로 간다. `tally` 가 정체·상한으로 루프를 끝낸다.

## 끝

`[done]` 이 나오면 `70_score.json` 의 총점·목표·미충족 체크와 `90_제출보고.md` 의 실행 기록(자동 생성) 위치, 제출 파일 경로를 보고한다. 「목표 미달」이면 그렇게 말한다. 목표 점수는 우리 채점기의 눈금이며 실제 심사 점수가 아니다.

## 하지 말 것

- `[ask]` 밖에서 사용자에게 값·승인·확인을 묻기. 서브에이전트가 다른 서브에이전트를 부르게 하기. 옛 `rp-orchestrator` 부르기.
- 점수를 손으로 계산하기. 체크 id 없이 「좋아졌다」고 보고하기. 실패 체크 외의 절을 다시 쓰기.
- `next` 가 주지 않은 단계로 건너뛰기. 조립 산출물을 제출 파일로 복사하는 단계를 빼먹기.
- 대시류 문자(U+2012~U+2015)를 어디에도 쓰기(보고 포함).
