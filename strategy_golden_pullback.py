"""
전략: 골든크로스 이후 눌림 매수 (Golden Cross Pullback Buy)
기준일: 2025-01-01 ~ 현재 (2/20 종가 기준)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[1단계] 골든크로스 발생
  - 가격 MA20 > 가격 MA200 (상향 돌파)
  - 거래량 MA20 > 거래량 MA200 (거래량도 증가 추세)

[2단계] 크로스 후 3~10일 이내 MA20 눌림
  - 골든크로스 후 3~10 영업일 내에
  - 저가(low) 또는 종가(close)가 MA20 이하 또는 근접 (±2%)

[3단계] 매수 신호 (양봉 전환 + 전일 고가 돌파)
  - 2단계 눌림 이후
  - 당일 양봉 (close > open)
  - 당일 고가(또는 종가) > 전일 고가 → 매수 신호
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

데이터:
  - 종목 리스트 + 시가총액: FinanceDataReader
  - OHLCV 히스토리:         pykrx
"""

from __future__ import annotations
import FinanceDataReader as fdr
from pykrx import stock
import pandas as pd
import numpy as np
import time
from typing import Optional

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
TOP_N         = 500
BASE_DATE     = '20260220'   # 기준일 (2/20)
START_DATE    = '20250101'   # 200일 MA 충분히 확보
GC_LOOKBACK   = 30           # 골든크로스 탐색 범위: 최근 몇 날 이내
PULLBACK_MIN  = 3            # GC 이후 최소 눌림 대기일
PULLBACK_MAX  = 10           # GC 이후 최대 눌림 대기일
TOUCH_MARGIN  = 0.02         # MA20 터치 허용 오차 (2%)
SLEEP_SEC     = 0.3
SIGNAL_LOOKBACK = 3          # 매수 신호 탐색: 눌림 이후 최근 N일


# ──────────────────────────────────────────────
# 함수: 시가총액 상위 N개 추출 (fdr)
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
# 함수: 전략 스캔 (종목별)
# ──────────────────────────────────────────────
def scan_strategy(df: pd.DataFrame) -> dict | None:
    """
    OHLCV DataFrame을 받아 3단계 전략 조건 분석.
    조건 충족 시 결과 dict 반환, 미충족 시 None.
    """
    if df is None or len(df) < 201:
        return None

    close  = df['종가']
    high   = df['고가']
    low    = df['저가']
    open_  = df['시가']
    volume = df['거래량']

    # MA 계산
    price_ma20  = close.rolling(20).mean()
    price_ma200 = close.rolling(200).mean()
    vol_ma20    = volume.rolling(20).mean()
    vol_ma200   = volume.rolling(200).mean()

    n = len(df)

    # ── 1단계: 최근 GC_LOOKBACK 영업일 이내 골든크로스 탐색 ──
    gc_idx = None
    gc_date = None
    search_start = max(201, n - GC_LOOKBACK - 1)

    for i in range(search_start, n):
        prev_p20  = price_ma20.iloc[i-1]
        curr_p20  = price_ma20.iloc[i]
        prev_p200 = price_ma200.iloc[i-1]
        curr_p200 = price_ma200.iloc[i]
        curr_v20  = vol_ma20.iloc[i]
        curr_v200 = vol_ma200.iloc[i]

        if any(pd.isna([prev_p20, curr_p20, prev_p200, curr_p200, curr_v20, curr_v200])):
            continue

        # 가격 골든크로스
        price_gc = (prev_p20 <= prev_p200) and (curr_p20 > curr_p200)
        # 거래량 조건: GC 발생 시점에 거래량 MA20 > MA200
        vol_ok   = curr_v20 > curr_v200

        if price_gc and vol_ok:
            # 가장 최근 골든크로스를 사용 (여러 개면 마지막 것)
            gc_idx  = i
            gc_date = df.index[i]

    if gc_idx is None:
        return None

    # ── 2단계: GC 이후 3~10 영업일 이내 MA20 눌림 탐색 ──
    pullback_idx  = None
    pullback_date = None
    pullback_low  = None

    end_search = min(gc_idx + PULLBACK_MAX + 1, n)
    for i in range(gc_idx + PULLBACK_MIN, end_search):
        if i >= n:
            break
        curr_low   = low.iloc[i]
        curr_close = close.iloc[i]
        curr_ma20  = price_ma20.iloc[i]

        if pd.isna(curr_ma20):
            continue

        # 눌림 조건: 저가 또는 종가가 MA20 기준 ±TOUCH_MARGIN 이내
        touch_low   = curr_low   <= curr_ma20 * (1 + TOUCH_MARGIN)
        touch_close = curr_close <= curr_ma20 * (1 + TOUCH_MARGIN)

        if touch_low or touch_close:
            pullback_idx  = i
            pullback_date = df.index[i].strftime('%Y-%m-%d')
            pullback_low  = round(curr_low)
            break

    if pullback_idx is None:
        return None

    # ── 3단계: 눌림 이후 매수 신호 탐색 (양봉 + 전일 고가 돌파) ──
    signal_idx  = None
    signal_date = None
    signal_type = None

    end_signal = min(pullback_idx + SIGNAL_LOOKBACK + 1, n)
    for i in range(pullback_idx + 1, end_signal):
        if i >= n:
            break
        curr_open  = open_.iloc[i]
        curr_close = close.iloc[i]
        curr_high  = high.iloc[i]
        prev_high  = high.iloc[i-1]
        curr_ma20  = price_ma20.iloc[i]

        if any(pd.isna([curr_open, curr_close, curr_high, prev_high])):
            continue

        # 양봉 여부
        is_bullish = curr_close > curr_open
        # 전일 고가 돌파
        breaks_prev_high = curr_close > prev_high or curr_high > prev_high

        if is_bullish and breaks_prev_high:
            signal_idx  = i
            signal_date = df.index[i].strftime('%Y-%m-%d')
            # 매수 시점이 오늘(마지막 날)이면 "오늘 신호", 이전이면 "발생"
            if i == n - 1:
                signal_type = '🔔 오늘 신호'
            else:
                signal_type = f'발생({df.index[i].strftime("%m/%d")})'
            break

    if signal_idx is None:
        return None

    # 최종 결과
    last_close  = close.iloc[-1]
    last_ma20   = price_ma20.iloc[-1]
    last_ma200  = price_ma200.iloc[-1]

    return {
        'GC발생일':       gc_date.strftime('%Y-%m-%d') if gc_idx is not None else '-',
        '눌림일':         pullback_date,
        '눌림저가':       pullback_low,
        '매수신호일':     signal_date,
        '신호유형':       signal_type,
        '종가':           int(last_close),
        'MA20':           round(last_ma20),
        'MA200':          round(last_ma200),
        'MA20_MA200갭(%)': round((last_ma20 / last_ma200 - 1) * 100, 2) if last_ma200 else None,
    }


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
print("=" * 60)
print("전략: 골든크로스 이후 눌림 매수")
print(f"기준일: {BASE_DATE}  |  데이터 시작: {START_DATE}")
print(f"GC 탐색 범위: 최근 {GC_LOOKBACK}일 / 눌림 허용: {PULLBACK_MIN}~{PULLBACK_MAX}일")
print(f"MA20 터치 마진: ±{TOUCH_MARGIN*100:.0f}%")
print("=" * 60)

all_signals = {}

for market in ['KOSPI', 'KOSDAQ']:
    print(f"\n[{market}] 시가총액 상위 {TOP_N}개 추출 중...")
    top_df  = get_top_tickers(market, TOP_N)
    tickers = top_df.index.tolist()
    print(f"  1위: {top_df.iloc[0]['종목명']}  {top_df.iloc[0]['시가총액(억원)']:,}억원")
    print(f"  {TOP_N}위: {top_df.iloc[-1]['종목명']}  {top_df.iloc[-1]['시가총액(억원)']:,}억원")

    print(f"\n[{market}] 전략 스캔 시작...")
    t0 = time.time()
    signals = []

    for i, ticker in enumerate(tickers, 1):
        try:
            df = stock.get_market_ohlcv(START_DATE, BASE_DATE, ticker)
            result = scan_strategy(df)
            if result:
                result['종목명']       = top_df.loc[ticker, '종목명']
                result['시가총액(억원)'] = top_df.loc[ticker, '시가총액(억원)']
                signals.append((ticker, result))
        except Exception:
            pass

        if i % 50 == 0 or i == TOP_N:
            elapsed = time.time() - t0
            print(f"  [{i:>3}/{TOP_N}] {i/TOP_N*100:5.1f}% 완료...  신호 {len(signals)}개 발견  ({elapsed:.0f}s)")
        time.sleep(SLEEP_SEC)

    # 결과 정리
    if signals:
        result_df = pd.DataFrame(
            [r for _, r in signals],
            index=[t for t, _ in signals]
        )
        result_df.index.name = '종목코드'
        result_df = result_df.sort_values('시가총액(억원)', ascending=False)
        result_df.insert(0, '순위(시총)', range(1, len(result_df)+1))

        cols = ['순위(시총)', '종목명', '시가총액(억원)', '종가',
                'MA20', 'MA200', 'MA20_MA200갭(%)',
                'GC발생일', '눌림일', '눌림저가', '매수신호일', '신호유형']
        result_df = result_df[cols]
        all_signals[market] = result_df

        fname = f'/Users/jaeduchan/Documents/jhan/antigravity/KOSPI_KODEX/{market.lower()}_gc_pullback_signal.csv'
        result_df.to_csv(fname, encoding='utf-8-sig')
        print(f"\n  ✅ {len(result_df)}개 신호 저장: {fname}")
    else:
        all_signals[market] = pd.DataFrame()
        print(f"\n  ⚠ 신호 없음")

# ──────────────────────────────────────────────
# 결과 출력
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
for market in ['KOSPI', 'KOSDAQ']:
    df = all_signals.get(market, pd.DataFrame())
    print(f"\n=== {market} 골든크로스 눌림 매수 신호 (총 {len(df)}개) ===")
    if not df.empty:
        print(df.to_string(index=True))
    else:
        print("  없음")

print("\n✅ 완료!")
print("  kospi_gc_pullback_signal.csv")
print("  kosdaq_gc_pullback_signal.csv")
