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

## 테스트

```bash
pytest
```
