"""
KOSPI / KOSDAQ 시가총액 상위 500개 종목
거래량 5일, 20일 이동평균 계산

데이터 소스:
  - 종목 리스트 + 시가총액: FinanceDataReader (KRX 기반)
  - OHLCV 히스토리:         pykrx (KRX 공식)

실행 시간: 약 6~10분 (1000 종목 × API 호출)
"""

import FinanceDataReader as fdr
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
import time

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
TOP_N     = 500       # 시가총액 상위 N개
MA_SHORT  = 5         # 단기 이동평균
MA_LONG   = 20        # 장기 이동평균
SLEEP_SEC = 0.3       # API 호출 간격 (초)

# 날짜 설정: 20일 MA를 위해 영업일 기준 30일 여유를 두고 조회
end_date   = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')   # 어제
start_date = (datetime.now() - timedelta(days=45)).strftime('%Y%m%d')  # 45일 전

print(f"기준 기간: {start_date} ~ {end_date}")
print(f"상위 {TOP_N}개 / MA{MA_SHORT} / MA{MA_LONG}")
print("=" * 55)


# ──────────────────────────────────────────────
# 함수: 시가총액 상위 N개 종목 추출 (fdr 사용)
# ──────────────────────────────────────────────
def get_top_tickers(market: str, n: int) -> pd.DataFrame:
    df = fdr.StockListing(market)
    df = df.sort_values('Marcap', ascending=False).head(n).copy()
    df['시가총액(억원)'] = (df['Marcap'] / 1e8).astype(int)
    df = df.rename(columns={'Code': '종목코드', 'Name': '종목명', 'Close': '종가'})
    df = df.set_index('종목코드')[['종목명', '시가총액(억원)', '종가']]
    df.index.name = '종목코드'
    return df


# ──────────────────────────────────────────────
# 함수: 종목별 pykrx OHLCV → 거래량 MA 계산
# ──────────────────────────────────────────────
def calc_volume_ma(tickers: list, start: str, end: str,
                   ma_short: int, ma_long: int) -> pd.DataFrame:
    results = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        try:
            df = stock.get_market_ohlcv(start, end, ticker)
            if df is None or df.empty or len(df) < ma_long:
                results[ticker] = {'거래량_최근': None,
                                   f'MA{ma_short}': None,
                                   f'MA{ma_long}': None}
                continue

            vol = df['거래량']
            results[ticker] = {
                '거래량_최근': int(vol.iloc[-1]),
                f'MA{ma_short}':  round(vol.rolling(ma_short).mean().iloc[-1]),
                f'MA{ma_long}':   round(vol.rolling(ma_long).mean().iloc[-1]),
            }
        except Exception as e:
            results[ticker] = {'거래량_최근': None,
                               f'MA{ma_short}': None,
                               f'MA{ma_long}': None}

        if i % 50 == 0 or i == total:
            pct = i / total * 100
            print(f"  [{i:>3}/{total}] {pct:5.1f}% 완료...")
        time.sleep(SLEEP_SEC)

    return pd.DataFrame(results).T


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
all_results = {}

for market in ['KOSPI', 'KOSDAQ']:
    print(f"\n{'='*55}")
    print(f"[{market}] 시가총액 상위 {TOP_N}개 추출 중...")
    top_df = get_top_tickers(market, TOP_N)
    tickers = top_df.index.tolist()

    print(f"  1위  : {top_df.iloc[0]['종목명']}  {top_df.iloc[0]['시가총액(억원)']:,}억원")
    print(f"  {TOP_N}위 : {top_df.iloc[-1]['종목명']}  {top_df.iloc[-1]['시가총액(억원)']:,}억원")

    print(f"\n[{market}] 거래량 히스토리 수집 + MA 계산 중...")
    t0 = time.time()
    ma_df = calc_volume_ma(tickers, start_date, end_date, MA_SHORT, MA_LONG)
    elapsed = time.time() - t0
    print(f"  소요시간: {elapsed:.0f}초")

    # 합치기
    result = top_df.join(ma_df)
    result.insert(0, '순위', range(1, len(result) + 1))
    result.index.name = '종목코드'

    # MA 비율 (단기/장기) - 1 이상이면 거래량 증가 추세
    denom = pd.to_numeric(result[f'MA{MA_LONG}'], errors='coerce').replace(0, float('nan'))
    numer = pd.to_numeric(result[f'MA{MA_SHORT}'], errors='coerce')
    result['MA비율(단기/장기)'] = (numer / denom).round(3)

    all_results[market] = result

    # CSV 저장
    fname = f'/Users/jaeduchan/Documents/jhan/antigravity/KOSPI_KODEX/{market.lower()}_volume_ma.csv'
    result.to_csv(fname, encoding='utf-8-sig')
    print(f"  저장: {fname}")


# ──────────────────────────────────────────────
# 결과 미리보기
# ──────────────────────────────────────────────
for market in ['KOSPI', 'KOSDAQ']:
    print(f"\n{'='*55}")
    print(f"=== {market} 상위 10개 ===")
    cols = ['순위', '종목명', '시가총액(억원)', '거래량_최근',
            f'MA{MA_SHORT}', f'MA{MA_LONG}', 'MA비율(단기/장기)']
    print(all_results[market].head(10)[cols].to_string(index=True))

print("\n✅ 완료!")
print("  저장파일: kospi_volume_ma.csv / kosdaq_volume_ma.csv")
