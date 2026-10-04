# real_estate

관심 아파트 단지 실거래·전월세·매물 동향 추적 (1단계: 실거래 백필 + 대시보드).

## 설치

```bash
pip install -r requirements.txt
pip install -e .
cp .env.example .env   # DATA_GO_KR_KEY=<공공데이터포털 Decoding 키>
```

키는 `.env`(gitignore) 또는 환경변수로만 제공한다. 절대 커밋하지 않는다.
공공데이터포털에서 **API마다 따로 활용신청**이 필요하다:
- 국토교통부_아파트 매매 실거래가 상세 자료 (`RTMSDataSvcAptTradeDev`)
- 국토교통부_아파트 전월세 실거래가 자료 (`RTMSDataSvcAptRent`)

## 수집

```bash
python -m realestate.ingest                  # backfill_start ~ 현재월, 매매+전월세
python -m realestate.ingest --api trade      # 매매만
python -m realestate.ingest --start 202501 --end 202503 --force
python -m realestate.ingest --dry-run        # 호출 대상만 출력
```

- 시군구 전체 거래를 `data/realestate.db`에 저장 (타깃 단지만 X → 매칭 규칙 바꿔도 재수집 불필요).
- 완료된 월은 건너뛰고, 현재월 포함 최근 `refetch_recent_months`(기본 3)개월은 매번 재수집해 지연 신고·해제를 반영.
- 원문 XML은 `raw_response`에 zlib 압축 저장. 직전과 같은 원문이면 이력만 남기고 본문은 생략.
- 키 미등록·한도 초과 같은 치명적 오류가 나면 해당 API의 남은 월은 건너뛴다.

## 설정

- `config/settings.yaml`: 시군구 코드, 호출 간격·재시도, 매수 상한, 평형 구간
- `config/complexes.yaml`: 관심 단지 매칭 (aptSeq 우선, 보조로 법정동+지번+단지명)
  - 보조 키에서 `apt_nm` 을 빼면 법정동+지번만으로 매칭 (새 단지의 실거래 단지명 표기를 모를 때 임시로)
  - 평형 구간: 59 · 74 · 84 · 93 · 101 · 118 (84형 위 대형은 2026-09-29 추가, 단지별 `bands` 에 있는 것만 화면에 나옴)

## 보조 스크립트

```bash
python scripts/list_complex_names.py --umd 상일동 여수동
python scripts/list_complex_names.py --sgg 41450 --like 더샵
```

## 검증

```bash
python -m realestate.validate               # 단지·평형·월별 건수, 이상치, 공개시스템 대조 샘플
python scripts/area_distribution.py         # 관심 단지 전용면적 분포
```

## 대시보드

```bash
streamlit run dashboard/app.py          # http://localhost:8501  (?band=74 처럼 평형 지정 가능)
```

- 필터: 평형, 단지, 기간 / 직거래 중앙값 포함 토글(기본 제외), 해제 건 표시 토글
- ① 매매 산점도(중개·직거래·해제 구분) + 3개월 이동중앙값 ② 월별 거래량(직거래·해제 별도 색)
  ③ 매매 vs 전세 같은 축 ④ 전세가율 ⑤ 전세 공급 지표(신규·갱신 전세·월세 건수, 갱신 비율, 월세 비중)
  ⑥ 같은 평형 단지 간 비교 + 요약표
- 매매 중앙값은 해제·직거래 제외, 전세 중앙값은 갱신 계약 제외 (각각 토글로 포함 가능)
- 전세가율 기본 창은 3개월 (같은 월 선택 가능), 표본 수(n) 표시, 매수 상한선(settings.yaml `buy_cap_manwon`)
- 3개월 이동중앙값 = 해당 월 포함 직전 3개월 개별 거래를 모아 계산 (월 중앙값의 중앙값 아님)

## 네이버 매물 (북마클릿, 국내 PC)

네이버페이 부동산은 자동화 브라우저·서버 요청을 거절하므로, **사용자의 크롬에서 즐겨찾기 버튼 한 번**으로
페이지가 쓰는 같은 출처 API를 호출해 파일로 내려받고, 그 파일을 저장소에 쌓는다.

설치 (한 번): `tools/bookmarklet.html` 을 크롬으로 열고 파란 버튼을 즐겨찾기 막대로 드래그.

매일:
1. 크롬에서 https://fin.land.naver.com/ 을 연다.
2. 즐겨찾기의 **📥 네이버 매물 덤프** 클릭 → `~/Downloads/naver_listings_YYYYMMDD_HHMM.json`
3. `cd ~/real_estate && python3 scripts/save_listings.py` → `data/listings/raw/` 에 저장, 커밋, push

대시보드 ⑦이 `data/listings/raw/*.json` 을 자동 적재한다 (`listing_raw` 원문 + `listing_metric` 숫자 값 전부).
어떤 JSON 경로가 매물 수·최저 호가인지는 `config/settings.yaml` 의 `listing_metrics` 정규식으로 정한다 —
첫 실제 덤프를 보고 확정하며, 규칙만 고치면 이미 쌓인 덤프에 소급 적용된다.
단지 목록(`config/complexes.yaml` 의 `naver_id`)이 바뀌면 `python3 tools/build_bookmarklet.py` 로 다시 빌드.

## 아실 일별 매물 수 (자동, 매일)

아실(asil.kr) '매물증감 → 일별 매물현황'의 단지별 매매·전세·월세 매물 수를
`data/listings/asil/asil_offer_counts.csv` (`date, complex_id, naver_id, sale, jeonse, wolse, total`)에 쌓는다.

- GitHub Actions `데이터 갱신`(매일 06:30 KST)이 `python scripts/asil_collect.py` 로 최근 3개월을 다시 받아 병합·커밋한다.
  단지당 하루 1회 요청. 하루 이틀 실패해도 다음 실행에서 빈 날이 채워진다.
- 백필: `python scripts/asil_collect.py --start 2023-09` (아실은 약 3년치 제공, 2023-09-01부터 저장돼 있음).
- 아실 단지 번호 = `config/complexes.yaml` 의 `naver_id`. 단지를 추가하면 다음 실행부터 함께 수집된다.
- 아실 집계는 같은 물건을 여러 중개사가 올려도 1건으로 센다 (네이버 단지 매물 수와 같은 값).
  아실 쪽에 기록이 없는 날은 행이 없다.
- 공개 API가 아니라 화면 내부 주소다. 응답이 비거나 형식이 바뀌면 워크플로가 실패로 표시된다 — 우회하지 말고 확인할 것.

### Mac 매일 작업 (실거래 + 아실 매물 목록)

**공공데이터포털(실거래)과 아실 매물 서버는 해외 접속을 막아서** GitHub Actions 에서는 받을 수 없다
(2026-09-29 확인: Actions 에서 공공데이터포털 호출이 전부 ConnectTimeout). 그래서 국내 Mac 이 매일 07:13 에
`scripts/mac_daily.py` 로 ① 실거래 수집(최근 3개월 + 빠진 달·새 시군구 백필) ② 아실 매물 목록 ③ 웹앱 데이터 생성을 하고
커밋·push 한다. DB(45MB)는 매월 1일·대량 백필 날만 커밋하고, 평소엔 `web/data/app.json` 만 올린다.
Actions 가 저장소의 오래된 DB로 웹앱 데이터를 다시 만들어도, 실거래 부분은 `trades_fetched_at` 이 더 새 app.json 쪽을 유지한다.

```bash
pip3 install -r requirements.txt                  # launchd 가 쓰는 같은 python3 으로 (requests·PyYAML·pandas)
python3 scripts/install_asil_offers.py            # 매일 07:13 실행 등록 (--status, --run-now, --uninstall)
python3 scripts/mac_daily.py --no-push            # 수동 실행 (커밋·push 없이)
```

- 실거래 키: 저장소의 `.env` (`DATA_GO_KR_KEY`). 서버에 연결이 안 되면 남은 호출을 모두 건너뛴다(오래 매달리지 않음).
- 예전에 등록한 `asil_offers.py --commit` 작업도 이제 `mac_daily.py` 로 넘어간다.

- 단지 번호: `config/complexes.yaml` 의 `asil_id` (네이버·일별 매물 수용 번호와 다름).
- 게시일(`posted`)은 중개사가 광고를 다시 올리면 바뀐다. 그래서 `first_seen`(처음 본 날)·`price_changed`/`prev_price`(가격 변경)·
  `last_seen`+`active=0`(내려감)은 매일 비교해서 직접 기록한다. 추적 시작 2026-09-29.
- 웹앱 '최근 매물' 표는 같은 물건(단지·유형·동·층·전용·가격)을 여러 중개사가 올린 것을 1줄(N곳)로 묶는다.
- 중개사 전화번호는 저장하지 않는다. 내려간 매물은 120일 뒤 파일에서 정리.

## 모바일 웹앱 (휴대폰 홈 화면용)

`web/` 은 설치형 웹앱(PWA): 단지 카드(3개월 중앙값·1년 대비·상한 대비·전세가율·네이버 매물),
단지 상세 차트, 단지 비교, 오프라인 보기, 라이트/다크.
`시장` 탭은 [거시 지표 | 심리] 두 화면이다. 심리 화면: 요약 카드(탐욕/공포·CSI·급매 검색·유튜브 새 영상), 주요 글(뉴스·카페·유튜브
제목·링크·미리보기 문구), 심리와 가격 겹쳐 보기, 네이버 검색량(데이터랩 2016년~), 선행 관계, 카페·뉴스 하루 새 글 수, 유튜브 새 영상 수.
수집: `python scripts/sentiment_collect.py` (NAVER API HUB 키 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`, `YOUTUBE_API_KEY`,
GitHub Actions 가 매일 실행) → `data/sentiment/`. 키워드·주제는 settings.yaml `sentiment`. 키 점검: '키 점검' 워크플로.
거시 지표 화면은 한국은행 ECOS 월별 지표(기준금리·주담대 금리·국고채 3년, 주택가격전망·금리수준전망 CSI, KB 서울 아파트
매매·전세지수, 주택관련대출 순증, 수도권 미분양, 서울·경기 인허가 12개월 합)를 2013년부터 보여 주고, 지표 3개월 변화와 k개월 뒤
KB 서울 아파트 매매지수 변화의 상관(선행 관계)을 계산한다. 수집: `python scripts/ecos_collect.py` (키 = `ECOS_KEY`,
GitHub Actions 가 매일 실행) → `data/macro/ecos_monthly.csv`. 지표 목록은 settings.yaml `ecos.series`.
'매물×가격' 탭은 지역(강동구·분당구·중원구·하남시와 상일동·야탑동·여수동·풍산동, settings.yaml `regions`)과 단지별로
매물 수와 가격을 같은 시간축에 두고(겹쳐 보기는 시작=100 지수, 축 두 개를 겹치지 않음), 매물 3개월 변화 뒤 k개월 가격 변화의
상관(선행 관계)을 보여 준다. 지역 매물은 아실 지역 일별 매물 수(`data/listings/asil/asil_region_counts.csv`, Actions 매일 수집),
지역 가격은 그 지역 전체 아파트 매매의 84㎡ 환산가(㎡당 가격 × 84) 3개월 중앙값 (`src/realestate/overlap.py`).
단지 비교의 '매물 수 추이'는 아실 매물 수를 단지 색으로, 매매는 실선·전월세(전세+월세)는 점선으로 그린다.
기본은 단지 전체 3년(7일 평균, 아실이 평형별 과거 값을 주지 않음)이고, '○○형만' 보기는 매물 목록 추적분(2026-09-29~)이다.
데이터 `web/data/app.json` 은 `scripts/export_web.py` 가 만들고, GitHub Actions `데이터 갱신`이 매일 06:30 KST에
실거래 수집 → 데이터 갱신 → 커밋한다(네이버 덤프 push 때도 실행). Cloudflare Pages가 커밋마다 배포하고,
Cloudflare Access로 본인 이메일만 열리게 잠근다. 설정 방법: **[docs/DEPLOY.md](docs/DEPLOY.md)**

```bash
python3 scripts/export_web.py && python3 -m http.server -d web 8000   # 로컬 미리보기
```

## 테스트

```bash
pytest
```
