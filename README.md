# KOSPI_KODEX 주식 분석 프로젝트

KRX 공식 데이터 기반 한국 증시(KOSPI/KOSDAQ) 종목 분석 스크립트 모음

## 데이터 소스
- **종목 리스트 + 시가총액**: FinanceDataReader (KRX 기반)
- **OHLCV 히스토리**: pykrx (KRX 공식)

## 스크립트

### `strategy_golden_pullback.py` ⭐ 메인 전략
> 전략: 골든크로스 이후 눌림 매수

```
1단계: 가격 MA20 > MA200 골든크로스 발생 + 거래량 MA20 > MA200
2단계: 골든크로스 후 3~10 영업일 이내 주가가 MA20까지 눌림
3단계: MA20 터치 후 양봉 전환 + 전일 고가 돌파 → 매수 신호
```

### `golden_cross.py`
KOSPI/KOSDAQ 시가총액 상위 500개 종목에서 MA20 vs MA200 골든크로스 탐색

### `volume_ma.py`
KOSPI/KOSDAQ 시가총액 상위 500개 종목 거래량 MA5 / MA20 계산

## 결과 파일 (2026-02-20 기준)

| 파일 | 설명 |
|------|------|
| `kospi_top500.csv` | KOSPI 시가총액 상위 500개 |
| `kosdaq_top500.csv` | KOSDAQ 시가총액 상위 500개 |
| `kospi_golden_cross.csv` | KOSPI 골든크로스 종목 (33개) |
| `kosdaq_golden_cross.csv` | KOSDAQ 골든크로스 종목 (13개) |
| `kospi_gc_pullback_signal.csv` | KOSPI 골든크로스 눌림 매수 신호 (10개) |
| `kosdaq_gc_pullback_signal.csv` | KOSDAQ 골든크로스 눌림 매수 신호 (13개) |

## 설치

```bash
pip install finance-datareader pykrx pandas
```

## 실행

```bash
# 전략 스캔 (약 20분 소요)
python strategy_golden_pullback.py

# 골든크로스 탐색 (약 20분 소요)
python golden_cross.py

# 거래량 이동평균
python volume_ma.py
```
