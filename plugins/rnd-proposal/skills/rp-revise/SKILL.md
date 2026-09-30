---
name: rp-revise
description: 이미 있는 연구계획서 hwpx(외부 원본·심사받은 판)를 수정 목록대로 고친다. 절을 다시 쓰지 않고 문장 교체·추가·합치기만 하며, 원본의 수치·규격명·출처·고유명사·위험 대응·산출식이 하나라도 사라지면 그 수정을 거부한다. 「이 hwpx 고쳐줘」「심사평 반영해서 수정」「외과 수정」「원본 살려서 고쳐」「rp-revise」 요청 시 사용한다.
---

# rp-revise: 외부 원본 hwpx 외과 수정

사람이 다듬은 원본은 정보 밀도와 문체가 이미 좋다. 자동 재작성은 이것을 잃는다
(t3: 우리 점수 94.5 였지만 외부 원본 대비 퇴행 42건 중 22건이 정보 삭제). 사람 손 외과 수정(82_외과수정, 35건)은
정보를 하나도 잃지 않고 외부 비교에서 이겼다. 이 스킬은 그 방식을 `edit_apply.py` 로 강제한다.
참조 사례: `<루트>/workspace/<과제>/82_외과수정.md` (실측 사례는 로컬에만 있다).

## 입력

| 입력 | 무엇 |
|---|---|
| 원본 hwpx | 고칠 파일. **덮어쓰지 않는다.** 결과는 새 파일로 |
| 수정 목록 | 사람이 준 항목(심사평·지적·블라인드 이유). 항목마다 번호 |
| 작업 폴더 | `<out_dir>/` : 본문 추출·op·원장·결과를 둔다 |

## 절차

```bash
S="$CLAUDE_PLUGIN_ROOT/scripts"
python "$S/hwpx_text.py" <원본.hwpx> --out <out_dir>/before.md            # 1) 본문을 md 꼴로(anchor 는 여기서 글자 그대로 복사)
```

2) **op 작성** (Claude 가 직접): 수정 목록 항목마다 `<out_dir>/edits.json` 에 op 를 쓴다.

```json
{"author": "revise", "edits": [
  {"id": "1", "check": "<목록 번호 또는 체크 id>", "op": "replace", "anchor": "<before.md 에서 복사한 문장·표 칸 글>", "new": "<바꾼 문장>", "reason": "…"},
  {"id": "2", "op": "insert_after", "anchor": "<문장>", "new": "<바로 뒤에 더할 문장 하나>"},
  {"id": "3", "op": "merge", "anchor": "<문장 A>", "anchor2": "<문장 B: 한 줄 전체>", "new": "<A·B 정보를 모두 담은 한 문장>"},
  {"id": "4", "op": "heading_bold"},
  {"id": "5", "op": "border_solid"}
]}
```

- 삭제 op 는 없다. 줄여야 하면 merge(두 항목의 수치·출처를 한 문장에). 반복을 한 곳에서 빼는 교체는 같은 사실이 다른 곳에 남아 있을 때만 통과한다.
- 새 문장에 「라벨: 내용」 머리·절 번호 참조(「1-3의」)·내부 표기·「RFP」를 넣지 않는다.
- 성능 목표를 낮추지 않는다(원본 「동등 이상」을 「95 %」로 바꾸는 식의 수정 금지: 목록이 그렇게 요구하면 사용자에게 되묻는다).
- `heading_bold`: 장·절 제목 글자에 굵은 charPr 복제본을 붙인다(11pt 통일 문서의 위계, F-m9). `border_solid`: 표 선을 실선으로(F-m5).

```bash
python "$S/edit_apply.py" --hwpx <원본.hwpx> --out <out_dir>/revised.hwpx --edits <out_dir>/edits.json --ledger <out_dir>/74_수정원장.json   # 3) 적용
```

4) 「거부」 줄이 있으면 사유대로 그 op 만 고쳐 다시 적용한다(원본에서 다시 시작: 결과 파일을 입력으로 쓰지 않는다).

5) **검사** (전부 통과해야 끝):

```bash
python "$S/check_preserve.py" --before <원본.hwpx> --after <out_dir>/revised.hwpx      # C-m5 정보 보존
python "$S/check_captions.py" --hwpx <out_dir>/revised.hwpx                           # F-m8 표 캡션
python "$S/check_headings.py" --hwpx <out_dir>/revised.hwpx                           # F-m9 제목 굵게
python "$S/check_internal.py" --group form  --hwpx <out_dir>/revised.hwpx             # T-m8 (양식 명세가 있으면 --spec)
python "$S/check_internal.py" --group label --hwpx <out_dir>/revised.hwpx             # S-m6
python "$S/check_blank.py"    --hwpx <out_dir>/revised.hwpx                           # C-m6
python "$S/check_dash.py"     --hwpx <out_dir>/revised.hwpx                           # S-m5
python "$CLAUDE_PLUGIN_ROOT/engine/hwpx/border_check.py" --hwpx <out_dir>/revised.hwpx   # F-m5
```

쪽수는 한글로 열어 실측한다(`harness_patches/gate_pages.py` 또는 한컴 COM). 넘으면 이번에 **더한 문장부터** 빼고(원장 순서의 역순),
그래도 넘으면 표 뒤·캡션 아래 빈 문단만 지운다(82 #33·34). 원래 정보는 줄이지 않는다.

6) (선택) 블라인드: 원본 대 수정본을 `rp-blind` 스킬로 비교한다. 외부 전송 동의가 없으면 Claude 심판만.

## 산출

- `<out_dir>/revised.hwpx`, `<out_dir>/74_수정원장.md`(항목·위치·전·후·판정), 검사 결과 요약.
- 보고: 적용·거부 수, 목록 항목 중 반영 못 한 것과 이유(엔진 범위 밖: 새 표·소제목 삽입·위치 이동은 사람이 한다), 검사 결과.

## 엔진 범위 밖 (82 사례 중 기계로 못 하는 것)

새 표 삽입(#14), 소제목(□) 삽입(#24·#27), 문장 위치 이동(#29·#31), 빈 문단 삭제(#33·#34). 필요하면 사용자에게 알리고 손으로 한다.
