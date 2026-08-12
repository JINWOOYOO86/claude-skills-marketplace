# 기여 규칙 (jinwoo-skills 마켓플레이스)

이 저장소는 **편집 원본이자 배포 원본**이다. main에 머지되는 순간 각 PC가 `plugin marketplace update` 로 끌어가는 배포본이 바뀐다. 그래서 규칙이 필요하다.

## 0. 3줄 요약

1. **main 직접 push 금지.** 모든 변경은 브랜치 → PR → 리뷰 승인 → squash 머지.
2. **편집은 개발용 클론에서만.** `~/.claude/plugins/marketplaces/jinwoo-skills` 는 읽기 전용이다.
3. **파일을 바꿨으면 `plugin.json` 의 version을 반드시 올린다.** 안 올리면 상대 PC에 옛 스냅샷이 남는다.

## 1. 클론 두 개를 구분한다

| | 경로 | 용도 |
|---|---|---|
| 개발용 | `~/dev/claude-skills-marketplace` (경로는 각자 자유) | 편집·브랜치·커밋·PR **전용** |
| 소비자 | `~/.claude/plugins/marketplaces/jinwoo-skills` | Claude Code가 자동으로 `git pull` 하는 설치 경로. **여기서 편집·커밋 금지** |

소비자 클론에서 편집하면 다음 `marketplace update` 때 충돌하거나 조용히 덮어써진다.

```bash
gh repo clone JINWOOYOO86/claude-skills-marketplace ~/dev/claude-skills-marketplace
```

## 2. 작업 착수 전

1. 무엇을 잡을지 **먼저 선언한다** (이슈 또는 채팅). 예: "나 `plugins/rfp-proposal-harness/skills/patent-research/` 잡는다."
   - 스킬·에이전트는 긴 마크다운이라 같은 파일을 둘이 만지면 머지 충돌 해결이 사실상 재작성이 된다. **파일 단위로 겹치지 않게 자르는 것이 유일한 예방책이다.**
2. 항상 최신 main에서 시작한다.

```bash
cd ~/dev/claude-skills-marketplace
git switch main && git pull
git switch -c feat/rfp-proposal-harness-<무엇>
```

## 3. 브랜치·커밋 규칙

- 브랜치명: `feat/<플러그인>-<내용>`, `fix/<플러그인>-<내용>`, `docs/<내용>`
- **1 PR = 1 플러그인.** "하네스 전반 개선" 같은 PR은 리뷰가 불가능하니 쪼갠다.
- `git add -A` **금지**. 반드시 경로를 명시한다.
  ```bash
  git add plugins/rfp-proposal-harness   # ← 이렇게
  ```
  (과거에 `add -A` 로 다른 세션의 미커밋 변경을 남의 커밋에 통째로 흡수한 사고가 있었다.)
- 같은 클론에서 Claude Code 세션 2개를 동시에 돌리지 않는다.

## 4. 충돌 다발 지점 두 곳

| 파일 | 규칙 |
|---|---|
| `.claude-plugin/marketplace.json` | 플러그인 **추가/설명 변경 시에만** 건드린다. 둘이 동시에 고치지 않게 미리 말한다. |
| `plugins/<이름>/.claude-plugin/plugin.json` 의 `version` | PR에서 올린다. 충돌하면 **나중에 머지하는 쪽이 상대 값 기준으로 다시 +1** 하고 rebase 한다. 절대 상대 값을 되돌리지 않는다. |

### 버전 올리는 기준
- patch(0.8.0 → 0.8.1): 문구 수정, 버그 픽스
- minor(0.8.0 → 0.9.0): 스킬·에이전트 추가/삭제, 절차 변경, 파일 구성 변경
- ⚠️ **파일 구성을 바꿨는데 version을 그대로 두면 안 된다.** 플러그인 캐시는 버전 디렉터리 단위라, 상대 PC는 계속 옛 버전 디렉터리를 읽는다.

## 5. PR 열기

```bash
git push -u origin HEAD
gh pr create --base main --fill
```

PR 본문에는 아래 3개 항목을 반드시 채운다(템플릿 자동 삽입됨). 스킬은 문서라서 **diff만 봐서는 동작을 알 수 없다.** 실제로 돌려본 결과가 없으면 리뷰할 수 없다.

- **무엇을** / **왜** / **검증**(실행한 요청 문구 + 산출물 경로 + 확인한 것)

## 6. 리뷰

리뷰어는 브랜치를 받아 **실물로 돌려본다.**

```bash
gh pr checkout <번호>
claude plugin marketplace add ~/dev/claude-skills-marketplace   # 로컬 경로를 임시 마켓으로 등록
# ... 해당 스킬을 실제로 실행해 확인 ...
claude plugin marketplace remove <임시마켓명>
```

코드 리뷰 보조: `/code-review <PR번호>`

체크리스트
- [ ] 다른 스킬의 트리거 문구와 충돌하지 않는가 (역할 경계가 description에 명시되었는가)
- [ ] `plugin.json` version이 올라갔는가
- [ ] 스킬 본문이 서로를 **접두사 없는 이름**으로 부르는가 (`pdf-extract` 스킬, `subagent_type:"paper-analyst"`)
- [ ] 개인정보·소속기관·타인 실명·개별 과제명·로컬 경로가 들어가지 않았는가 (**공개 저장소다**)
- [ ] 생성 산출물의 기본값(표지·footer·샘플 데이터)에 실데이터가 박혀 있지 않은가

## 7. 머지

**Squash merge** 만 사용한다(선형 이력 유지). 머지 후 브랜치는 자동 삭제된다.

## 8. 머지 후 — 두 사람 모두 반영해야 한다

머지됐다고 각자 PC에 반영되지 않는다. **4단계 전부** 필요하다.

```bash
git -C ~/dev/claude-skills-marketplace switch main && git -C ~/dev/claude-skills-marketplace pull
claude plugin marketplace update jinwoo-skills
claude plugin update <플러그인>@jinwoo-skills     # ← 이걸 빠뜨리면 설치본은 그대로다
# Claude Code 재시작
```

`marketplace update` 만으로는 설치본이 올라가지 않는다(캐시에 새 버전 디렉터리가 생기지 않음). 검증:

```bash
ls ~/.claude/plugins/cache/jinwoo-skills/<플러그인>/<신버전>
diff -rq ~/.claude/plugins/marketplaces/jinwoo-skills/plugins/<플러그인> \
         ~/.claude/plugins/cache/jinwoo-skills/<플러그인>/<신버전>   # .in_use 외 차이 0
```

## 9. 새 플러그인(하네스)을 추가할 때

1. `plugins/<이름>/` 한 레벨에 만든다. 도메인 접두사를 붙인다(`paper-`/`patent-`/`rfp-`, 범용 도구는 생략).
2. **단일 스킬 = 플러그인명 = 스킬명** (참조가 `pdf-extract:pdf-extract` 꼴). 여러 에이전트가 협업하는 것만 하네스로 묶는다.
3. `.claude-plugin/plugin.json` 에 name/version/description.
4. 루트 `.claude-plugin/marketplace.json` 의 `plugins` 배열에 등록.
5. **같은 스킬을 공개/비공개 양쪽에 두지 않는다** — 목록 중복과 drift가 생긴다. 스킬 1개는 반드시 한쪽에만.
6. 로컬 `~/.claude/skills/` 에 같은 스킬을 두지 않는다(단일 소스 원칙).

## 10. 공개 저장소라서 지켜야 할 것

- 소속기관명·타인 실명·개별 과제명·기업 실명·특허번호·개인 폴더 경로 금지.
- 저장소에는 **형식과 절차만**, 실제 조사 내용·예시 데이터는 각자 로컬(`~/.claude/local/`)에 둔다.
- 기능과 얽혀 삭제할 수 없는 것은 지우지 말고 **중립화**한다(기관 CI → "브랜드 컬러(교체 가능)").
