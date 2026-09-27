# 모바일 웹앱 배포 (Cloudflare Pages + 이메일 로그인)

앱 파일은 `web/` 폴더(정적 파일)이고, 데이터는 `web/data/app.json` 하나다.
GitHub Actions(`.github/workflows/update.yml`)가 매일 06:30 KST에 실거래를 수집하고 `app.json` 을 갱신해 커밋하면,
Cloudflare Pages가 그 커밋을 감지해 자동으로 다시 배포한다. 네이버 매물 덤프를 push 할 때도 같은 흐름.

처음 한 번만 아래 3단계를 하면 된다.

## 1. GitHub: 공공데이터 키 등록 (매일 자동 수집용)
1. https://github.com/GTigerPapa/real_estate/settings/secrets/actions 열기
2. **New repository secret**
   - Name: `DATA_GO_KR_KEY`
   - Secret: 공공데이터포털 **일반 인증키(Decoding)** — 로컬 `.env` 에 넣은 것과 같은 값
3. 저장 후 확인: 저장소 **Actions** 탭 → 왼쪽 **데이터 갱신** → **Run workflow** → 초록 체크가 뜨면 성공
   - 실패하고 로그에 `push` 권한 오류가 보이면: **Settings → Actions → General → Workflow permissions → Read and write permissions** 선택 후 다시 실행

## 2. Cloudflare Pages: 사이트 만들기
1. https://dash.cloudflare.com 가입(무료) · 로그인
2. 왼쪽 **Workers & Pages** → **Create** → **Pages** 탭 → **Connect to Git**
3. **GitHub** 선택 → Cloudflare GitHub 앱 설치 화면에서 **Only select repositories → `real_estate`** 만 허용
4. 저장소 선택 후 **Set up builds and deployments**:
   | 항목 | 값 |
   |---|---|
   | Project name | 원하는 이름 (예: `chan-realestate`) → 주소가 `chan-realestate.pages.dev` 가 됨 |
   | Production branch | `main` |
   | Framework preset | `None` |
   | Build command | (비워 둠) |
   | Build output directory | `web` |
5. **Save and Deploy** → 1분 안에 `https://<프로젝트이름>.pages.dev` 생성

> 이 단계가 끝난 직후부터 3단계를 마칠 때까지는 주소를 아는 사람이 볼 수 있다. 3단계를 바로 이어서 한다.

## 3. Cloudflare Access: 내 이메일로만 열리게 잠그기
1. Pages 프로젝트 → **Settings** → **General** → **Access policy** → **Enable access policy**
   - 이것만으로는 미리보기 주소만 잠긴다(Cloudflare 제약). 아래 4번이 운영 주소를 잠그는 단계.
2. (처음이면) Zero Trust 설정 화면이 뜬다: 팀 이름 아무거나 입력, **Free** 플랜 선택
3. **Zero Trust → Access → Applications** 에서 방금 생긴 `<프로젝트이름>` 애플리케이션 → **Edit**(Configure)
4. **Application domain** 의 Subdomain 칸에 있는 `*` 를 지우고 저장 → `<프로젝트이름>.pages.dev` 전체가 보호됨
5. **Policies** 에서 허용 규칙 확인/수정:
   - Action: **Allow**
   - Include: **Emails** = `sc1001.lee@gmail.com` (필요하면 가족 이메일 추가)
6. **Authentication / Login methods**: **One-time PIN** 사용(기본값) → 접속 시 이메일로 6자리 코드가 온다

확인: 휴대폰 시크릿 창에서 `https://<프로젝트이름>.pages.dev` → 이메일 입력 → 받은 코드 입력 → 앱이 뜨면 완료.
다른 이메일로 시도하면 막혀야 정상.

## 4. 휴대폰 홈 화면에 추가
- 아이폰(Safari): 공유 버튼 → **홈 화면에 추가**
- 안드로이드(Chrome): 메뉴 ⋮ → **앱 설치** (또는 홈 화면에 추가)

아이콘을 누르면 주소창 없이 앱처럼 전체 화면으로 열리고, 마지막으로 본 데이터는 오프라인에서도 보인다.
로그인은 기본 24시간 유지된다(Access 애플리케이션 설정의 Session Duration 에서 변경 가능, 예: 1 month).

## 운영 메모
- 데이터 갱신 주기: 실거래 매일 06:30 KST / 네이버 매물은 Cowork·북마클릿으로 덤프를 올린 날
- 수동 갱신: Actions → 데이터 갱신 → Run workflow
- DB 파일(`data/realestate.db`)은 매월 1일에만 커밋(저장소 용량 관리). 매 실행이 최근 3개월을 다시 받으므로 누락 없음
- 앱 화면 코드: `web/app.js`, `web/app.css` · 데이터 생성: `src/realestate/webexport.py`
- 로컬 미리보기: `python3 scripts/export_web.py && python3 -m http.server -d web 8000` → http://localhost:8000
