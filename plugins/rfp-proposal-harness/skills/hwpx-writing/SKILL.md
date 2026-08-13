---
name: hwpx-writing
description: 조사·그림 산출물과 양식 규칙을 종합해 연구계획서를 작성하고 HWPX 문서로 조립하는 스킬. "연구계획서 작성", "HWPX 작성", "계획서 조립", "본문 작성", "제안서 초안"을 요청하면 반드시 사용한다. 조립 도구는 kordoc(npx)이며 별도 플러그인 설치가 필요 없다.
---

# HWPX 작성 스킬

모든 산출물을 종합해 양식에 맞는 연구계획서를 조립한다.

## 워크플로우

### 0. ★★ 착수 전 강제 게이트 — 두 줄을 먼저 확정한다 (건너뛰면 반드시 재작업한다)

**⑴ 절 제목은 양식 원문 그대로 쓴다 — 한 글자도 바꾸지 않는다.**
`01_template_rules.md` §4 목차 트리의 문자열을 **복사해 붙여넣는다.**
- ✖ 금지: 서술형 개명(「1-3. 국내는 냉매를 만들지 못한다」), 접미 추가(「2-2. 단계별·연차별 목표 **[표 A]**」), 띄어쓰기 변형
- ✖ 금지: **양식에 없는 절 신설**(예: 「3-4. 위험요소 및 대응」). 가장 가까운 절 안의 **굵은 리드**로 넣는다
- ✔ 내용을 드러내고 싶으면 **제목은 원문 그대로, 절 첫 문장을 굵은 리드**로

**⑵ 분량 예산을 표로 확정한 뒤에 쓰기 시작한다.**
장별 배분(0:1p / 1:2p / 2:2p / 3:3p / 4:2p = **10p 내외, 상한 12p**)을 넘기지 않도록 **산문 자수·표 개수·표 열수·그림 장수**를 미리 배정한다.

| 요소 | 소모 | 상한 |
|---|---|---|
| 산문 | 1,750자/p | **≤ 15,000자** |
| 표 3~4열 | 0.4~0.6p | — |
| 표 5~6열 | 0.7~0.9p | — |
| **표 7열 이상** | ★ **1.0p 이상** | **쓰지 않는다** |
| 그림 | 사실상 1p | **≤ 1장** |

> ★ **실측(2026-08-13)**: 표 10개·셀 텍스트 3,512자뿐인 문서에서 **표가 9.3p**를 먹었다(개당 0.93p).
> 8열 KPI표·13열 간트표가 원인이었고, 열을 5 이하로 재설계하자 **18p → 15p**로 회수됐다.
> **다 쓰고 나서 줄이는 순서는 실패한다** — 지시가 아무리 많아도 **배분 안에 들어갈 형태로 먼저 설계**한다.
> 7열 이상이 필요해 보이면 열을 쪼개지 말고 **일부 열을 표 아래 각주·글머리로 이관**한다.

### 1. 양식 규칙 로드
`01_template_rules.md`의 목차·서식을 최우선 기준으로 삼는다. **목차 항목을 임의 추가/삭제/개명하지 않는다.**
둘째 줄 `양식출처:` 를 확인한다 — `기본양식(폴백)` 이면 공고 지정 서식이 없다는 뜻이므로, 분량·필수기재 판단을 사용자에게 올릴 때 이 사실을 함께 알린다.

**스타일 참조**: 공고 첨부 양식 파일이 있으면 `kordoc profile` 로 서식 프로필을 뽑아 `generate --profile` 에 넣는다(표 테두리·음영·열폭·셀 글꼴 재현).
**없으면 프리셋으로 만들고**, 기본 양식의 서식 규칙(A4 / 돋움 11pt / 줄간격 160%)을 산출물 헤더에 패치한다 — 절차와 코드는 `template-extraction` 스킬의 `assets/default-form/default_form_rules.md` §3에 있다.

목표 서식값은 `assets/default-form/default_form_style.json` 이다 — 본문 11pt 돋움 / 표 9pt / 장제목 16pt **검정** / 절제목 13pt 굵게, 여백 좌우 8504·상 5668·하 4252, 줄간격 160%.
⚠️ **kordoc 프리셋은 이 값을 그대로 주지 않는다**(실측: 여백 좌우 5669=20mm, 글꼴 한양신명조·HY견고딕 등 5종 혼용). **§3의 헤더 패치가 필수**다.

### 2. 섹션-근거 매핑
각 목차 항목에 조사 산출물을 매핑해 본문을 작성한다:
| 계획서 섹션 | 근거 파일 |
|---|---|
| 기술 동향·추진 필요성 | `11_tech_trend.md`, `13_policy.md` |
| 시장·사업화 | `12_market.md` |
| 기술 차별성·특허 회피 | `14_patent.md` |
| 그림 삽입 | `20_figures/index.md` |
- **수치·특허번호를 새로 지어내지 않는다.** 근거 파일의 값과 출처만 사용한다.
- 미확보 항목은 `[보완 필요: ...]` 플레이스홀더로 남긴다.

### 3. HWPX 조립 — kordoc

조립 도구는 **kordoc**(npm, MIT)이다. `npx` 로 실행하므로 **별도 플러그인·설치가 필요 없다.**

#### 3-0. 프리플라이트 (건너뛰지 말 것)

```bash
node -v                          # v18 이상이어야 한다
npx -y kordoc@^4 --version       # 최초 1회는 패키지 내려받느라 느리다(네트워크 필요)
```

⚠️ **실패하면 조용히 Markdown 폴백으로 내려가지 말고 중단하고 사용자에게 알린다.**
"HWPX를 요청했는데 md만 나오고 이유는 로그 속에 묻히는" 사고가 실제로 있었다.
Node가 없으면 안내한 뒤, 사용자가 폴백을 선택한 경우에만 `30_proposal.md` + "HWPX 변환 필요" 표시로 마감한다.

#### 3-1. 원고 전처리 (실측 함정 — 이걸 빼면 J-5가 FAIL한다)

```bash
# ① 이미지 참조는 파일명만 남긴다 — kordoc --image-dir 은 basename 으로만 매칭한다
sed -i 's#](20_figures/#](#g' 30_proposal.md
# ② 연속된 인용문(>)은 한 문단으로 병합된다 → 사이에 빈 줄을 넣는다
python3 - <<'PY'
lines = open('30_proposal.md', encoding='utf-8').read().split('\n')
out = []
for l in lines:
    if l.startswith('>') and out and out[-1].startswith('>'):
        out.append('')
    out.append(l)
open('30_proposal.md', 'w', encoding='utf-8').write('\n'.join(out))
PY
```

#### 3-2. 생성

```bash
npx -y kordoc@^4 generate 30_proposal.md -o 30_raw.hwpx \
  --preset 계획서 --font gothic --pt 11 --line-spacing 160 --paper A4 \
  --fonts "body=돋움,heading=돋움,table=돋움" --image-dir 20_figures
```
출력의 **`이미지 임베드: N개`를 반드시 확인한다.** 0개면 경로 매칭이 실패한 것이며 **에러가 나지 않는다.**

#### 3-3. 헤더 패치 (양식값 강제 — 프리셋 기본값은 양식과 다르다)

```bash
python3 - <<'PY'
import zipfile, re
src, dst = '30_raw.hwpx', '30_proposal.hwpx'
zin = zipfile.ZipFile(src); zout = zipfile.ZipFile(dst, 'w')
for it in zin.infolist():
    d = zin.read(it.filename)
    if it.filename.startswith('Contents/section'):
        s = d.decode('utf-8')
        n = len(re.findall(r'<hp:margin[^>]*/>', s))
        assert n >= 1, '여백 태그 미검출 — 치환 실패'
        s = re.sub(r'<hp:margin[^>]*/>',
                   '<hp:margin header="4252" footer="4252" gutter="0" '
                   'left="8504" right="8504" top="5668" bottom="4252"/>', s)
        print(f'여백 치환 {n}건')
        d = s.encode('utf-8')
    if it.filename.endswith('header.xml'):
        h = d.decode('utf-8'); cnt = 0
        for face in ['함초롬바탕', '함초롬돋움', '한양신명조', '한양중고딕', 'HY견고딕']:
            cnt += h.count(f'face="{face}"'); h = h.replace(f'face="{face}"', 'face="돋움"')
        print(f'글꼴 통일 {cnt}건 → 돋움')
        d = h.encode('utf-8')
    zi = zipfile.ZipInfo(it.filename, date_time=it.date_time)
    zi.compress_type = zipfile.ZIP_STORED if it.filename == 'mimetype' else zipfile.ZIP_DEFLATED
    zout.writestr(zi, d)
zout.close()
PY
```
⚠️ `mimetype` 은 **ZIP_STORED** 여야 한다. 이걸 놓치면 열리지 않는다.

#### 3-4. 검증

```bash
npx -y kordoc@^4 validate 30_proposal.hwpx      # 구조 검증
npx -y kordoc@^4 render   30_proposal.hwpx -o preview.svg   # 조판 눈검사(선택)
```
쪽수 실측은 한컴 COM(`references/md-to-hwpx-traps.md` §5). 한컴이 없으면 **「쪽수 미측정」으로 명시**하고 통과를 발급하지 않는다.

> **실측 근거**: 8라운드 PASS 판정본(31p·표 18개)을 이 경로로 재빌드해 규율 J **전항 PASS**, 표 18개 행×열 전부 일치, 본문 764문단·최장 880자·표주석 11·참고문헌 20으로 **구조 지표 동일**, 쪽수는 오히려 **28p**(3p 절감)였다.

### 4. 산출 매니페스트
`_workspace/30_proposal_manifest.md`에 STATUS, 채워진 섹션 / `[보완 필요]` 섹션 목록을 기록.

### 5. ★ 게이트 (개정 후 필수 — 건너뛰지 말 것)

```bash
S="$CLAUDE_PLUGIN_ROOT/skills/hwpx-writing/scripts"
python3 $S/gate_hwpx.py   --hwpx 30_proposal.hwpx --md 30_proposal.md \
                          --expect-tables <직전 판 표 개수> \
                          --prev <직전 판 hwpx> --required required.txt --sections sections.txt
python3 $S/gate_regress.py --prev <직전 판 md> --curr 30_proposal.md \
                          --required required.txt --resolved resolved.txt
```
**두 게이트가 PASS하기 전에는 개정 완료를 보고하지 않는다.** 결과를 `48_revision_log.md`에 첨부한다.

## 출력
`_workspace/30_proposal.hwpx`(가능 시) 및/또는 `_workspace/30_proposal.md` + manifest.

## 원칙
- 위원장 통합 수정지시(`49_panel_verdict.md`)가 있으면 **해당 섹션만** 개정한다(전면 재작성 금지 → 이미 95점인 축의 회귀 방지).
- 빈 섹션을 그럴듯한 말로 채우지 않는다 — 평가위원이 근거 없는 주장을 지적한다.

---

## ★ 개정 규율 (전부 실측 사고에서 도출)

> **개정은 매 라운드 신규 결함을 낳는다.** 실측: v2 9건 · v3 4~6건 · v4 4건 · v5 3~5건 · v7 21.15점.
> 아래 규율은 그 사고들의 재발 방지책이며, **지키지 않으면 같은 사고가 재현된다.**

| 규율 | 내용 | 실측 사고 |
|---|---|---|
| **A 전수 치환** | 값을 고칠 때 `grep`으로 **전수 치환 후 0건 확인**. 치환 전 문맥을 확인하고, 치환 후 **배수·비율 표현을 정규식으로 재검산** | 표 셀만 고치고 본문·각주 4곳에 구값 잔존 → 3개 위원이 독립 치명 판정. 이를 고치려던 `"8배"→"31배"` 전역 치환이 무관한 `4.8배`·`2.8배`를 `4.31배`·`2.31배`로 **파괴**(부분문자열 오염) |
| **B 소리내어 실패** | 치환 실패를 **소리내어 알리고** 사후 건수를 검증한다. 기대 건수와 실제 건수를 대조하는 스크립트로 치환할 것 | 치환이 조용히 실패했는데 개정이력에 "정정 완료"로 기재 → 위원이 **"개정이력과 본문 불일치"**로 적발 |
| **C 산출물 검사** | 원고뿐 아니라 **HWPX 산출물에도** 기계검사를 건다 | 간트 `■`가 표 셀에서만 탈락 — 원고에는 있고 인쇄물에는 없었다 |
| **D 동일유형 전수** | 지목된 곳만 고치지 말고 **동일 유형을 전수 점검** | 하단 냉매 기준근거만 고치고 동일 결함인 상단 냉매 방치 |
| **E 신설 표 재검산** | 신설·변경한 표의 **비율·배수·단위를 재검산** | R5에서 이 규율이 실제로 결함 2건을 해소 |
| **F 매체 동기화** | 본문·그림·**생성기 원본** 3자를 동시에 고친다. 문자열 변경 시 `grep -l '<변경 전>' 20_figures/*.svg 20_figures/_src/*.py 20_figures/index.md` 실행 의무. 그림 수정은 **SVG → PNG → HWPX 재빌드까지가 1건** | SVG만 고치고 `gen_fig.py` 방치 → 재렌더 시 오류 부활. 더 위험한 사례: 존재하지 않는 절 `§1-4`를 **존재하지만 무관한** `§1-1`로 바꿔 `grep §1-4 = 0건`을 통과시키고 의미 오류를 존치 — **검사를 통과하도록 고치는 것과 옳게 고치는 것이 갈라진 첫 사례** |
| **G 조사 반영 완결** | 조사 결론을 **절반만** 옮기지 않는다. 조사파일에서 `계획서에는`·`명기해야`·`그대로 두면`·`각주 필수`·`권고`를 grep해 전량 목록화하고 체크박스로 관리 | 신규 결함 10건 중 8건이 이 표식을 가진 문장이었다(GWP 값만 옮기고 기준연도·출처 누락) |
| **H 회귀 게이트** | 새 조치를 넣기 전에 **직전 라운드 「완전 해소 확정」 항목을 전수 재검사**. `scripts/gate_regress.py` 사용 | 압축이 직전 라운드 확정분 4건을 되돌림 |
| **I → J에 흡수** | ~~필수기재 존재 검사~~ **단독 운용 폐지.** **존재 검사 단독은 거짓 통과를 발급한다** | "평가방법 8행 존재" 검사가 통과시킨 표가 산출물에서는 2개로 쪼개져 있었다 |
| **J 산출물 구조 게이트** | `scripts/gate_hwpx.py` — 표 형상 덤프·고아 표·판 간 형상 diff·표 내부 제외 문단 자수·이중 이스케이프·XML 선언·격자 재검산·§ 참조 실존·필수 문자열·**강조(굵기) 보존(J-14)**. **`--md` 를 반드시 함께 준다** — 없으면 J-14가 원고 대조 없이 INFO로만 지나간다. **모든 체크에 「측정 매체」를 명시하고, md 단독 측정 항목에는 「통과」를 발급하지 않는다** | 「존재는 있고 구조가 깨진」 결함 **4건이 전부 존재 검사를 통과**했다(references §1). 4번째는 **굵은 글씨 594 span 전량 소실** — 본문 텍스트는 멀쩡해서 자수·존재 검사로는 영원히 안 잡힌다 |

**함정 목록**: `references/md-to-hwpx-traps.md` — 마크다운 소스·빌드 파이프라인·**검사 스크립트 자체**의 함정 30여 건.
새 검사 코드를 짜기 전에 §4(검사 스크립트 함정)를 먼저 읽을 것.
