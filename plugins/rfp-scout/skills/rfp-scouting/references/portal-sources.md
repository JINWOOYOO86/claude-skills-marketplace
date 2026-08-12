# 공고 포털 소스 목록

`rfp-scouting` 스킬의 수집 대상 포털과 접근 방법.

> **검증 상태 표기**: `검증됨(YYYY-MM-DD)` = 실제 접속해 목록 추출까지 확인 / `미검증` = URL만 기재, 실행 시 확인 필요.
> 접속에 성공하거나 경로가 바뀐 것을 발견하면 **이 파일을 갱신**한다. 다음 실행이 같은 시행착오를
> 반복하지 않게 하는 것이 이 파일의 존재 이유다.

## 목차
1. 통합 포털 (최우선)
2. IRIS HTTP 경로 — 실측
3. 부처·전문기관
4. 첨부 텍스트 추출
5. 알려진 함정

---

## 1. 통합 포털 (최우선)

여기서 대부분의 국가 R&D 공고가 잡힌다. 부처 홈페이지는 보완용이다.

| 포털 | URL | 성격 | 검증 상태 |
|------|-----|------|----------|
| **IRIS** (범부처통합연구지원시스템) | https://www.iris.go.kr | 국가 R&D 사업 공고·접수 통합 창구. 사실상 1순위 | **검증됨(2026-08-12)** |
| **NTIS** (국가과학기술지식정보서비스) | https://www.ntis.go.kr | 사업공고 + 기존 과제 DB(중복성 검토에 유용) | 미검증 |
| **나라장터** | https://www.g2b.go.kr | 용역·구매 성격 과제(연구용역 포함) | 미검증 |

---

## 2. IRIS HTTP 경로 — 실측

**목록·상세·첨부 전 구간이 브라우저 자동화 없이 받아진다. 로그인·쿠키·세션 전부 불필요하다.**
(2026-08-04 최초 실측 → 2026-08-12 재확인: 목록 POST 200 / 상세 POST 200 / 첨부 GET 200)

동봉 스크립트 `scripts/iris_fetch.py`가 아래를 그대로 구현하고 있다. 직접 호출할 일이 있을 때를 위해 남긴다.

```
① 목록 (JSON)
POST https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituList.do
  Content-Type: application/x-www-form-urlencoded; charset=UTF-8
  X-Requested-With: XMLHttpRequest
  Referer: https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do
  body: ancmPrg=ancmIng&pageIndex=1      # ancmPre=접수예정 / ancmEnd=마감
→ { paginationInfo:{totalRecordCount,totalPageCount,...},
    listBsnsAncmBtinSitu:[{ancmId,ancmTl,ancmNo,rcveStrDe,rcveEndDe,dDay,
                           sorgnNm,blngGovdSeNm,pbofrTpSeNmLst,rcveStt},...] }
  페이지당 10건. ListView.do 를 GET 해도 1페이지 10건은 서버렌더로 들어 있다.
  ※ ancmPre(접수예정)는 과거분을 포함한 전체 아카이브(수천 건)다. 증분 탐색에 쓰지 말 것.

② 상세 (HTML)
POST https://www.iris.go.kr/contents/retrieveBsnsAncmView.do
  body: ancmId={ancmId}&ancmPrg=ancmIng
  ※ 목록의 f_bsnsAncmBtinSituListForm_view(id,prg) 는 hidden input 2개를 채우고 폼 action 을
    이 URL 로 바꿔 submit 하는 것이 전부다(JS 실행 불필요).
    소스: /resources/js/contents/bsnsancm/bsnsAncmBtinSituList.js  L203-221

③ 첨부 (파일)
GET  https://www.iris.go.kr/comm/file/fileDownload.do
       ?atchDocId={urlencode}&atchFileId={urlencode}
  ※ 두 ID 는 상세 HTML 의
    f_bsnsAncm_downloadAtchFile('{atchDocId}','{atchFileId}','{파일명}','{크기}') 인자에 그대로 있다.
    ID 는 base64 형태라 +, /, = 를 포함한다 → 반드시 percent-encoding 할 것.
    정규식 첫 매치는 함수 정의부(인자가 'atchDocId')이므로 건너뛴다.
    선행 호출 retrieveCheckFileDownload.do 는 불필요하며, 오히려 응답이 지연된다.
```

**사람이 열어볼 링크 (리포트·메일·캘린더에 붙인다)** — 둘 다 GET 200으로 열린다.

```
사업공고  https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancmId}
공모예고  https://www.iris.go.kr/contents/retrieveAncmPrntcView.do?bsnsPrntcNo={번호}
```

수집에 쓰는 POST 경로와 별개다. **공고번호를 언급하는 모든 자리에 링크를 건다** — 히트뿐 아니라
탈락·감시대상까지. 번호만 적어 두면 확인할 때마다 포털에서 다시 검색해야 한다.

**목록에 없는 것들** — 접수기간·지원규모·주관자격·첨부는 목록 JSON에 없다. **상세 진입이 필수**다.
목록만 보고 판정하지 말 것.

---

## 3. 부처·전문기관

IRIS가 1순위이고, 아래는 누락 보완·온디맨드 탐색용이다. 프로파일 분야에 따라 가감한다.

| 기관 | URL | 주력 분야 | 검증 상태 |
|------|-----|----------|----------|
| KEIT (한국산업기술기획평가원) | https://srome.keit.re.kr | 산업부 R&D 전반(기계·소재·에너지) | 미검증 |
| KETEP (한국에너지기술평가원) | https://www.ketep.re.kr | 에너지 R&D | 미검증 |
| KIAT (한국산업기술진흥원) | https://www.kiat.or.kr | 국제공동·기반조성·인력양성 | 미검증 |
| 에너지공단 | https://www.energy.or.kr | 보급·실증사업 | 미검증 |
| IITP / NRF | https://www.iitp.kr , https://www.nrf.re.kr | ICT, 기초·원천 | 미검증 |
| 중기부 / TIPA | https://www.smtech.go.kr | 중소기업 협업과제(기업 주관) | 미검증 |
| 지자체·지역혁신 | 각 지역 R&D 지원기관 | 프로파일에 지역 조건이 있을 때만 | 미검증 |
| 국제공동(Horizon Europe 등) | https://ec.europa.eu/info/funding-tenders | 국제공동 기획과 연계될 때 | 미검증 |
| 소속기관 내부 공고(원내 게시판·메일) | 사용자 제공 | 자동 수집 불가 → 모드 D(파일 투입) | — |

부처 홈페이지는 **공지 게시판이 정적 HTML인 경우가 많아 `WebFetch`로 바로 긁히는 편**이다.

---

## 4. 첨부 텍스트 추출

동봉 `scripts/extract_attachment.py`가 PDF·HWPX·HWP·ZIP을 처리한다. 형식별 요점:

| 형식 | 방법 | 주의 |
|------|------|------|
| PDF | `pypdf` → 없으면 `pymupdf` | 스캔본은 텍스트가 0자로 나온다 → 그 사실을 리포트에 적는다 |
| HWPX | zip + `Contents/section*.xml` 태그 제거 | 섹션 번호 순서로 이어붙여야 본문이 뒤섞이지 않는다 |
| HWP 5.x | OLE(`olefile`) → 섹션 raw deflate(`zlib.decompress(data,-15)`) → 레코드 파싱 | 레코드 헤더 UINT32 = tag(10b)\|level(10b)\|size(12b), size==0xFFF 이면 다음 UINT32 가 실제 크기 |
| ZIP | 내부 파일 재귀 추출 | **내부 파일명이 CP949**인 경우가 많다(UTF-8 플래그 미설정) → `cp437` 디코딩 후 `cp949` 재해석 |

> ⚠️ **HWP 본문의 컨트롤 문자를 "코드 32 미만"으로만 걸러내면 안 된다.** 확장·인라인 컨트롤은
> 8 WCHAR를 차지하고 그 안에 4바이트 ASCII ID를 물고 있어서, 단순 필터링만 하면 본문에
> `捤獥汤捯湰灧` 같은 쓰레기 문자열이 박힌다. 컨트롤 코드(1~9,11,12,14~23)를 만나면 8 WCHAR를
> 통째로 건너뛴다. 동봉 스크립트는 이렇게 처리하고, 탭·묶음빈칸은 글자로 되살린다.

라이브러리 설치가 불가능한 환경에서는 Node로 우회할 수 있다:
```
PDF   npm i pdf-parse  →  const {PDFParse}=require('pdf-parse')
                          await new PDFParse({data:new Uint8Array(buf)}).getText()
                          ※ 구버전 API(pdf(buf))는 더 이상 동작하지 않는다
HWP5  npm i cfb        →  CFB.read(buf) 로 컨테이너를 열고 BodyText/Section* 을
                          zlib.inflateRawSync 후 위와 같은 레코드 파싱
```

---

## 5. 알려진 함정

| 함정 | 증상 | 대응 |
|------|------|------|
| **"JS 렌더링이라 브라우저가 필요하다"는 오해** | 브라우저 자동화 도구가 없다고 모니터링을 포기 | IRIS는 전 구간 HTTP다(§2). 클라우드·헤드리스에서도 돈다 |
| **상세 URL 직접 접근** | `retrieveBsnsAncmView.do`를 POST 없이 열면 목록으로 리다이렉트되던 시기가 있었다 | 수집은 POST로, 사람이 볼 링크는 `?ancmId=` GET으로 — 둘을 구분한다 |
| **게시일 ≠ 마감일** | 검색 스니펫 날짜를 마감일로 오인 | 원문 진입 전에는 `확인필요`로 강등 |
| **동일 공고 중복 게시** | IRIS·부처 홈페이지·보도자료에 같은 사업 | (공고명 정규화 + 마감일) 키로 중복 제거, 별칭URL 병기 |
| **사업명 검색의 한계** | 기술 키워드로 검색하면 0건인데 실제로는 존재 | 접수중 전수 훑기(20~30건)가 키워드 검색보다 안전 |
| **롤링 재공고** | 상태가 `공고마감,공고접수중`으로 동시에 표기 | RFP별 미응모분 재공고다. 마감으로 오판하지 말 것 |
| **접수기간이 사전공고/본공고로 나뉨** | D-day 착시 | 사전공고는 별도 표기, D-day는 본공고 기준 |
| **선정 완료된 협약 건이 목록에 남음** | 공모 대상이 아닌데 신규로 잡힘 | 상세에서 공모유형·접수상태를 확인해 탈락 처리 |
| **첨부 다운로드 차단(다른 포털)** | 상세는 보이나 파일이 안 받아짐 | 첨부명·크기만 기록하고 사용자 수동 다운로드 요청 |
