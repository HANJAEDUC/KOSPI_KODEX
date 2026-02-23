"""
골든크로스 탐색: 2/20 종가 기준
KOSPI 시가총액 상위 500개 + KOSDAQ 시가총액 상위 500개

골든크로스 정의:
  - 2/20 기준: MA20 > MA200  (현재 골든크로스 상태)
  - 2/19 기준: MA20 ≤ MA200  (이전에는 데드크로스 상태)
  → 즉, 2/20 당일 또는 최근 5 영업일 이내 MA20이 MA200을 상향 돌파

데이터:
  - 종목 리스트+시가총액: FinanceDataReader (KRX 기반)
  - OHLCV 히스토리     : pykrx (KRX 공식)
  - 200일 MA 산출을 위해 약 300 캘린더일(2025-03-01~2026-02-20) 수집
"""

import FinanceDataReader as fdr
from pykrx import stock
import pandas as pd
import time

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
TOP_N       = 500
BASE_DATE   = '20260220'   # 기준일 (2/20 종가)
START_DATE  = '20250101'   # 200일 MA를 충분히 계산하기 위한 시작일
GC_WINDOW   = 5            # 최근 N 영업일 이내 골든크로스 탐지
SLEEP_SEC   = 0.3

# ──────────────────────────────────────────────
# 함수: 시가총액 상위 N개 종목 추출 (fdr)
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
# 함수: 골든크로스 탐지
# ──────────────────────────────────────────────
def find_golden_cross(tickers: list, top_df: pd.DataFrame,
                      start: str, end: str, gc_window: int) -> pd.DataFrame:
    golden_list = []
    dead_list   = []   # 현재 MA20 > MA200이지만 최근 크로스 아닌 것
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        try:
            df = stock.get_market_ohlcv(start, end, ticker)
            if df is None or df.empty or len(df) < 200:
                if (i % 50 == 0 or i == total):
                    print(f"  [{i:>3}/{total}] {i/total*100:5.1f}% 완료...")
                time.sleep(SLEEP_SEC)
                continue

            close = df['종가']
            ma20  = close.rolling(20).mean()
            ma200 = close.rolling(200).mean()

            # 최근 유효 데이터 (마지막 gc_window+1일)
            recent_ma20  = ma20.iloc[-(gc_window+1):]
            recent_ma200 = ma200.iloc[-(gc_window+1):]

            # 골든크로스: 최근 gc_window일 중 MA20이 MA200을 상향 돌파한 시점 존재?
            cross_occurred = False
            cross_date = None
            for j in range(1, len(recent_ma20)):
                prev20, curr20 = recent_ma20.iloc[j-1], recent_ma20.iloc[j]
                prev200, curr200 = recent_ma200.iloc[j-1], recent_ma200.iloc[j]
                if pd.isna(prev20) or pd.isna(curr20) or pd.isna(prev200) or pd.isna(curr200):
                    continue
                if prev20 <= prev200 and curr20 > curr200:
                    cross_occurred = True
                    cross_date = recent_ma20.index[j].strftime('%Y-%m-%d')
                    break

            last_ma20  = ma20.iloc[-1]
            last_ma200 = ma200.iloc[-1]
            last_close = close.iloc[-1]

            if pd.isna(last_ma20) or pd.isna(last_ma200):
                if (i % 50 == 0 or i == total):
                    print(f"  [{i:>3}/{total}] {i/total*100:5.1f}% 완료...")
                time.sleep(SLEEP_SEC)
                continue

            row = {
                '종목명':      top_df.loc[ticker, '종목명'],
                '시가총액(억원)': top_df.loc[ticker, '시가총액(억원)'],
                '종가':        int(last_close),
                'MA20':        round(last_ma20),
                'MA200':       round(last_ma200),
                'MA20_MA200갭(%)': round((last_ma20/last_ma200 - 1)*100, 2),
                '골든크로스일': cross_date if cross_occurred else '-',
            }

            if cross_occurred:
                golden_list.append((ticker, row))

        except Exception as e:
            pass

        if i % 50 == 0 or i == total:
            print(f"  [{i:>3}/{total}] {i/total*100:5.1f}% 완료... (골든크로스 {len(golden_list)}개 발견)")
        time.sleep(SLEEP_SEC)

    if not golden_list:
        return pd.DataFrame()

    result = pd.DataFrame(
        {t: r for t, r in golden_list}.values(),
        index=[t for t, _ in golden_list]
    )
    result.index.name = '종목코드'

    # 시가총액 기준 정렬
    result = result.sort_values('시가총액(억원)', ascending=False)
    result.insert(0, '순위(시총)', range(1, len(result)+1))
    return result


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
print(f"기준일: {BASE_DATE}  |  수집 시작: {START_DATE}")
print(f"골든크로스 탐지 범위: 최근 {GC_WINDOW} 영업일 이내")
print("=" * 60)

all_golden = {}

for market in ['KOSPI', 'KOSDAQ']:
    print(f"\n[{market}] 시가총액 상위 {TOP_N}개 추출 중...")
    top_df  = get_top_tickers(market, TOP_N)
    tickers = top_df.index.tolist()
    print(f"  1위: {top_df.iloc[0]['종목명']}  {top_df.iloc[0]['시가총액(억원)']:,}억원")
    print(f"  {TOP_N}위: {top_df.iloc[-1]['종목명']}  {top_df.iloc[-1]['시가총액(억원)']:,}억원")

    print(f"\n[{market}] OHLCV 수집 + 골든크로스 탐색 중...")
    t0 = time.time()
    gc_df = find_golden_cross(tickers, top_df, START_DATE, BASE_DATE, GC_WINDOW)
    elapsed = time.time() - t0

    print(f"\n  소요시간: {elapsed:.0f}초")
    print(f"  골든크로스 종목 수: {len(gc_df)}개")

    if not gc_df.empty:
        fname = f'/Users/jaeduchan/Documents/jhan/antigravity/KOSPI_KODEX/{market.lower()}_golden_cross.csv'
        gc_df.to_csv(fname, encoding='utf-8-sig')
        print(f"  저장: {fname}")
        all_golden[market] = gc_df
    else:
        print(f"  ⚠ 골든크로스 종목 없음")
        all_golden[market] = pd.DataFrame()

# ──────────────────────────────────────────────
# 결과 출력
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
for market in ['KOSPI', 'KOSDAQ']:
    gc = all_golden[market]
    print(f"\n=== {market} 골든크로스 종목 (총 {len(gc)}개) ===")
    if not gc.empty:
        cols = ['순위(시총)', '종목명', '시가총액(억원)', '종가',
                'MA20', 'MA200', 'MA20_MA200갭(%)', '골든크로스일']
        print(gc[cols].to_string(index=True))
    else:
        print("  없음")

print("\n✅ 완료! 저장파일:")
print("  kospi_golden_cross.csv")
print("  kosdaq_golden_cross.csv")
