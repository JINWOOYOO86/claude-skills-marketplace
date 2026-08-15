#!/bin/bash
# 표준 조립 스크립트 — 원고(md) → HWPX + 3게이트(J·K·L)
#
# 왜 스크립트인가: 조립은 「전처리 → 생성 → 헤더 패치 → 게이트」 4단이고 각 단계에 실측 함정이 있다.
# 워크스페이스마다 손으로 옮겨 적으면 그때마다 한두 개씩 빠진다(실제로 빠졌다).
#
# 사용:
#   build_hwpx.sh <워크스페이스> <원고.md> [표 개수]
#   예) build_hwpx.sh _workspace/ai_refrigerant 30_proposal.md 5
#
# 전제: Node.js 18+ (kordoc), 플러그인 스킬 경로($CLAUDE_PLUGIN_ROOT 또는 -s 로 지정)
set -e
WS="${1:?워크스페이스 경로가 필요하다}"
SRC="${2:-30_proposal.md}"
NTBL="${3:-}"
# 스킬 경로 — CLAUDE_PLUGIN_ROOT 가 있으면 그것을, 없으면 **설치된 최신 버전**을 쓴다.
# (버전을 하드코딩하면 플러그인을 올린 뒤에도 옛 스킬로 조립된다 — 실측으로 겪었다.)
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then S="$CLAUDE_PLUGIN_ROOT/skills"; else
  CACHE="$HOME/.claude/plugins/cache/jinwoo-skills/rfp-proposal-harness"
  LATEST=$(ls -1 "$CACHE" 2>/dev/null | sort -V | tail -1)
  S="$CACHE/$LATEST/skills"
fi
[ -d "$S" ] || { echo "!! 스킬 경로를 찾지 못했다: $S"; exit 1; }
SPEC="$WS/01_template_spec.json"
[ -f "$SPEC" ] || SPEC="$S/template-extraction/assets/default-form/default_form_spec.json"

command -v node >/dev/null || { echo "!! Node.js 18+ 필요 — 조용한 md 폴백 금지, 여기서 중단한다"; exit 1; }
W=$(mktemp -d); cd "$W"

# 1) 양식 설명문(가이드 주석) 제거 — 원본은 그대로 두고 조립용 사본을 만든다
python3 "$S/hwpx-writing/scripts/form_strip.py" --in "$WS/$SRC" --out 30_proposal.md --spec "$SPEC"

# 2) 전처리 — 이미지 경로(basename 매칭)·연속 인용문 병합 회피
if [ -d "$WS/20_figures" ]; then mkdir -p 20_figures && cp "$WS/20_figures"/*.png 20_figures/ 2>/dev/null || true; fi
sed -i 's#](20_figures/#](#g' 30_proposal.md
python3 -c "
L=open('30_proposal.md',encoding='utf-8').read().split('\n'); o=[]
for l in L:
    if l.startswith('>') and o and o[-1].startswith('>'): o.append('')
    o.append(l)
open('30_proposal.md','w',encoding='utf-8').write('\n'.join(o))"

# 3) 생성 — --h2-marker none(장 제목 번호 보존) · --bullet2 ○(개조식 2단계 말머리)
npx -y kordoc@^4 generate 30_proposal.md -o 30_raw.hwpx \
  --preset 계획서 --font gothic --pt 11 --line-spacing 160 --paper A4 \
  --h2-marker none --bullet2 ○ --fonts "body=돋움,heading=돋움,table=돋움" --image-dir 20_figures

# 4) 헤더 패치 — 여백·글꼴·글자크기·절제목·목록 들여쓰기/간격
python3 - <<'PY'
import zipfile, re
zin=zipfile.ZipFile('30_raw.hwpx')
sec0=zin.read('Contents/section0.xml').decode('utf-8')
ptxt=lambda p: "".join(re.findall(r'<hp:t>([^<]*)</hp:t>', p)).strip()
h2,h3,body=set(),set(),set()
for para in re.findall(r'<hp:p\b.*?</hp:p>', sec0, re.S):
    cr=re.search(r'charPrIDRef="(\d+)"', para)
    if not cr: continue
    t=ptxt(para)
    (h2 if re.match(r'^\d+\.\s',t) else h3 if re.match(r'^\d+-\d+\.\s',t) else body).add(cr.group(1))
h2-=body; h3-=body
print('제목 스타일 — 장 %s · 절 %s' % (sorted(h2), sorted(h3)))
zout=zipfile.ZipFile('30_proposal.hwpx','w')
for it in zin.infolist():
    d=zin.read(it.filename)
    if it.filename.startswith('Contents/section'):
        s=d.decode('utf-8'); assert len(re.findall(r'<hp:margin[^>]*/>',s))>=1, '여백 태그 미검출'
        s=re.sub(r'<hp:margin[^>]*/>','<hp:margin header="4252" footer="4252" gutter="0" left="8504" right="8504" top="5668" bottom="4252"/>',s)
        d=s.encode('utf-8')
    if it.filename.endswith('header.xml'):
        h=d.decode('utf-8')
        for f in ['함초롬바탕','함초롬돋움','한양신명조','한양중고딕','HY견고딕']: h=h.replace('face="%s"'%f,'face="돋움"')
        for pid,prev,left in [('8','600','0'),('9','0','1100'),('10','0','2200')]:
            def fix(m,prev=prev,left=left):
                s=m.group(0)
                s=re.sub(r'<hc:prev value="\d+"','<hc:prev value="%s"'%prev,s)
                s=re.sub(r'<hc:left value="\d+"','<hc:left value="%s"'%left,s)
                s=re.sub(r'<hc:intent value="-?\d+"','<hc:intent value="-1650"',s)
                return s
            h=re.sub(r'<hh:paraPr id="%s".*?</hh:paraPr>'%pid, fix, h, flags=re.S)
        def norm(m):
            cid,blk=m.group(1),m.group(0)
            if cid in h2 or cid in h3: return blk
            def sz(mm):
                v=int(mm.group(1))
                if 1000<=v<=1250: v=1100
                elif 850<=v<=999: v=900
                return 'height="%d"'%v
            return re.sub(r'height="(\d+)"', sz, blk)
        h=re.sub(r'<hh:charPr id="(\d+)".*?</hh:charPr>', norm, h, flags=re.S)
        def h3fix(m):
            blk=m.group(0)
            if m.group(1) not in h3: return blk
            blk=re.sub(r'height="\d+"','height="1300"',blk)
            return blk if '<hh:bold' in blk else blk.replace('</hh:charPr>','<hh:bold/></hh:charPr>')
        h=re.sub(r'<hh:charPr id="(\d+)".*?</hh:charPr>', h3fix, h, flags=re.S)
        d=h.encode('utf-8')
    zi=zipfile.ZipInfo(it.filename, date_time=it.date_time)
    zi.compress_type=zipfile.ZIP_STORED if it.filename=='mimetype' else zipfile.ZIP_DEFLATED
    zout.writestr(zi,d)
zout.close()
PY

# 4.5) 표 폭을 본문 문단 폭에 맞춘다 — 4단계에서 여백을 양식값으로 바꿨으므로 표도 다시 재단해야 한다.
#      조립 도구는 **자기 프리셋 여백**(좌우 5,669)으로 표를 만들어 놓는다. 이 단계를 빼면
#      본문 폭 42,519 문서에 46,389 짜리 표가 남아 오른쪽 여백을 13.6mm 침범한다(실측).
python3 "$S/hwpx-writing/scripts/fix_table_width.py" --hwpx 30_proposal.hwpx

# 5) 게이트 — 하나가 FAIL 해도 나머지를 다 돌려 전모를 본다
set +e; RC=0
npx -y kordoc@^4 validate 30_proposal.hwpx
EXPECT=""; [ -n "$NTBL" ] && EXPECT="--expect-tables $NTBL"
python3 "$S/hwpx-writing/scripts/gate_hwpx.py"  --hwpx 30_proposal.hwpx --md 30_proposal.md $EXPECT || RC=1
# 게이트 JSON 은 **원고 이름을 접두사로** 남긴다 — 고정 이름이면 다음 판이 직전 판 결과를 덮어써
# 판 간 비교가 불가능해진다(실측으로 겪었다).
BASE="${SRC%.md}"
python3 "$S/hwpx-writing/scripts/gate_form.py"  --hwpx 30_proposal.hwpx --md 30_proposal.md --spec "$SPEC" --json "$WS/${BASE}_gate_form.json"  || RC=1
python3 "$S/hwpx-writing/scripts/gate_pages.py" --hwpx 30_proposal.hwpx --md 30_proposal.md --spec "$SPEC" --json "$WS/${BASE}_gate_pages.json" || RC=1

cp 30_proposal.hwpx "$WS/${SRC%.md}.hwpx"
cp 30_proposal.md   "$WS/${SRC%.md}.build.md"
echo "완료: $WS/${SRC%.md}.hwpx (작업 디렉터리 $W · 게이트 RC=$RC)"
exit $RC
