# Claude Cowork(Mac)용 프롬프트 — 네이버 매물 덤프 1회 수집

아래 블록을 그대로 Cowork에 붙여 넣는다. (매일 반복 실행용으로도 그대로 쓸 수 있음)

---

내 Mac에서 부동산 매물 스냅샷을 한 번 수집해 줘. 저장소는 `~/real_estate` (GitHub GTigerPapa/real_estate, 이미 clone·인증 완료). 순서대로:

1. 터미널에서 `cd ~/real_estate && git pull` 로 최신 코드를 받는다.
2. **크롬**으로 `https://fin.land.naver.com/` 을 연다 (내가 평소 쓰는 크롬 프로필 그대로. 로그인 필요 없음). 페이지가 다 뜰 때까지 기다린다.
3. 그 탭에서 개발자 도구 콘솔을 연다 (`⌥⌘J`). `~/real_estate/tools/console_snippet.js` 파일 내용 **전체**를 콘솔에 붙여 넣고 Enter. 크롬이 `allow pasting` 을 입력하라고 하면 그대로 입력한 뒤 다시 붙여 넣는다.
   - 페이지 오른쪽 위에 "매물 수집 중 1/4 …" 상자가 뜨고 30초쯤 뒤 알림창이 뜬다. 알림창의 **"성공 N / 실패 N" 숫자를 그대로 기록**하고 확인을 누른다.
   - 다운로드 폴더에 `naver_listings_YYYYMMDD_HHMM.json` 이 생긴다.
   - 알림창이 안 뜨거나 "네이버 매물 덤프 오류: …" 가 뜨면 콘솔에 출력된 빨간 오류 메시지를 그대로 복사해 둔다.
4. 터미널에서 `cd ~/real_estate && python3 scripts/save_listings.py` 를 실행한다. 출력 전체를 기록한다. (파일을 `data/listings/raw/` 로 옮기고 커밋·push까지 한다.)
5. (한 번만) 개별 매물 목록 요청의 형식을 알아낸다: 같은 크롬 탭에서 개발자 도구 **Network** 탭을 열고 필터에 `article` 을 입력한 뒤, 지도에서 **고덕자이**를 검색해 단지 패널을 열고 **매물** 탭을 누른다. Network에 `article/list` 요청이 나타나면 그 요청을 클릭해 **Payload(요청 본문) 전체**와 **Response(응답)의 첫 1,000자**를 복사해 둔다. (없으면 `article` 이 들어간 다른 요청 이름들만 적어 둔다.)
6. 마지막으로 나에게 보고: (a) 알림창의 성공/실패 숫자, (b) 4번 터미널 출력 전체, (c) 5번에서 복사한 Payload와 Response 앞부분, (d) 오류가 있었다면 콘솔의 오류 메시지. 덤프 파일 내용은 붙이지 않아도 된다.

주의: 네이버에 이 이상의 요청을 보내거나, 차단·오류를 우회하려고 다른 방법을 시도하지 말 것. 실패하면 그대로 보고만 하면 된다.

---

## 보고를 받은 뒤 (클라우드 세션에서 할 일)
`git pull` 후 `data/listings/raw/` 의 덤프를 열어 실제 JSON 경로를 확인하고 `config/settings.yaml` 의 `listing_metrics` 규칙을 확정한다.
