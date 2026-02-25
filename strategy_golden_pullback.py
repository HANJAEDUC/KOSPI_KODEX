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
import sys
from typing import Optional
from fetcher import get_ohlcv  # 로컬 데이터 연동

# stdout/stderr 강제 UTF-8 모드 및 실시간 출력(버퍼링 제거) 방침
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True, write_through=True)
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True, write_through=True)

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
GC_LOOKBACK   = 30           # 골든크로스 탐색 범위: 최근 몇 날 이내
PULLBACK_MIN  = 3            # GC 이후 최소 눌림 대기일
PULLBACK_MAX  = 10           # GC 이후 최대 눌림 대기일
TOUCH_MARGIN  = 0.02         # MA20 터치 허용 오차 (2%)
SLEEP_SEC     = 0.02         # (변경) 기존 0.3s -> 0.02s 로 대폭 축소하여 초고속 스캔 (pykrx 밴 조심)
SIGNAL_LOOKBACK = 3          # 매수 신호 탐색: 눌림 이후 최근 N일


# ──────────────────────────────────────────────
# 함수: 시가총액 상위 N개 추출 (fdr)
# ──────────────────────────────────────────────
def get_top_tickers(market: str, n: int) -> pd.DataFrame:
    df = fdr.StockListing(market)
    df = df.sort_values('Marcap', ascending=False)
    if n > 0:
        df = df.head(n)
    df = df.copy()
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

        # 눌림 조건: 저가 또는 종가가 MA20 기준 ±TOUCH_MARGIN (±2%) 이내로 진입했는지 확인
        touch_low   = (curr_ma20 * (1 - TOUCH_MARGIN) <= curr_low   <= curr_ma20 * (1 + TOUCH_MARGIN))
        touch_close = (curr_ma20 * (1 - TOUCH_MARGIN) <= curr_close <= curr_ma20 * (1 + TOUCH_MARGIN))

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
                signal_type = f'발생({df.index[i].strftime("%Y.%m.%d")})'
            break

    if signal_idx is None:
        return None

    # ── 4단계: 거래량 골든크로스 (추가 요청) ──
    v_ma5 = volume.rolling(5).mean()
    curr_v5 = v_ma5.iloc[-1]
    curr_v20 = vol_ma20.iloc[-1]
    
    vol_gc_ratio = 0
    if not any(pd.isna([curr_v5, curr_v20])) and curr_v20 > 0 and curr_v5 > curr_v20:
        vol_gc_ratio = round(curr_v5 / curr_v20, 2)

    # 최종 결과 (가격 GC & Pullback 신호 + 볼륨 GC 신호 분리 반환용)
    last_close  = close.iloc[-1]
    last_ma20   = price_ma20.iloc[-1]
    last_ma200  = price_ma200.iloc[-1]
    
    gap_pct = round((last_ma20 / last_ma200 - 1) * 100, 2) if (not pd.isna(last_ma200) and last_ma200 > 0) else None

    # 가격 GC 정보
    price_gc_info = None
    if curr_p20 > curr_p200 and not pd.isna(curr_p200):
        # 방금 막 GC 된 경우만 잡을지, 단순히 역배열->정배열 상태만 잡을지는 현재 상태(>0)로 판단
        price_gc_info = {
            'MA20': round(last_ma20),
            'MA200': round(last_ma200),
            'MA20_MA200갭(%)': gap_pct,
            '골든크로스일': gc_date.strftime('%Y-%m-%d') if gc_date else '진행중'
        }

    pullback_info = None
    if signal_idx is not None:
        pullback_info = {
            'GC발생일':       gc_date.strftime('%Y-%m-%d') if gc_idx is not None else '-',
            '눌림일':         pullback_date,
            '눌림저가':       pullback_low,
            '매수신호일':     signal_date,
            '신호유형':       signal_type,
        }

    vol_info = None
    if vol_gc_ratio > 0:
        vol_info = {
            'V_MA5': round(curr_v5),
            'V_MA20': round(curr_v20),
            'Volume_Ratio(배)': vol_gc_ratio
        }

    if price_gc_info is None and pullback_info is None and vol_info is None:
        return None

    return {
        '종가': int(last_close),
        'price_gc': price_gc_info,
        'pullback': pullback_info,
        'vol_gc': vol_info
    }


import argparse

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from datetime import datetime, timedelta
    parser = argparse.ArgumentParser(description="주식 스크리닝 (GC, 눌림매수, 거래량GC 분리 실행)")
    parser.add_argument('--target', type=str, required=True, choices=['price_gc', 'vol_gc', 'pullback'],
                        help="스캔할 대상을 지정합니다: price_gc, vol_gc, pullback")
    parser.add_argument('--target_date', type=str, default=None, help="기준일 (예: 2026-02-23)")
    parser.add_argument('--top_n', type=int, default=500, help="조회할 시가총액 상위 종목 수 (0이면 전체)")
    args = parser.parse_args()

    if args.target_date:
        base_date_dt = datetime.strptime(args.target_date, "%Y-%m-%d")
    else:
        base_date_dt = datetime.now()
    BASE_DATE = base_date_dt.strftime("%Y%m%d")
    START_DATE = (base_date_dt - timedelta(days=400)).strftime("%Y%m%d")

    print("=" * 60)
    print(f"전략: 단일 스크리너 실행 (타겟: {args.target})")
    print(f"기준일: {BASE_DATE}  |  데이터 시작: {START_DATE}")
    print("=" * 60)

    all_pullback_signals = {}
    all_price_gcs = {}
    all_vol_gcs = {}

    # 누적 발견 신호 수 (UI 표시용)
    total_found_cnt = 0

    for market in ['KOSPI', 'KOSDAQ']:
        print(f"\n[{market}] 시가총액 상위 {args.top_n if args.top_n > 0 else '전체'}개 추출 중...", flush=True)
        top_df  = get_top_tickers(market, args.top_n)
        tickers = top_df.index.tolist()
        total_tickers = len(tickers)

        print(f"\n[{market}] 전략 스캔 시작 (총 {total_tickers}개 종목)...", flush=True)
        t0 = time.time()
        
        pb_signals = []
        pgc_signals = []
        vgc_signals = []

        for i, ticker in enumerate(tickers, 1):
            try:
                # fetcher를 통해 로컬 우선 데이터 로드 (매우 빠름)
                df = get_ohlcv(ticker, START_DATE, BASE_DATE)
                result = scan_strategy(df)
                if result:
                    base_info = {
                        '종목명': top_df.loc[ticker, '종목명'],
                        '종목코드': ticker,
                        '시가총액(억원)': top_df.loc[ticker, '시가총액(억원)'],
                        '종가': result['종가']
                    }
                    
                    found_item = None
                    if args.target == 'pullback' and result['pullback']:
                        found_item = {**base_info, **result['pullback']}
                        pb_signals.append((ticker, found_item))
                        total_found_cnt += 1
                    elif args.target == 'price_gc' and result['price_gc']:
                        found_item = {**base_info, **result['price_gc']}
                        pgc_signals.append((ticker, found_item))
                        total_found_cnt += 1
                    elif args.target == 'vol_gc' and result['vol_gc']:
                        found_item = {**base_info, **result['vol_gc']}
                        vgc_signals.append((ticker, found_item))
                        total_found_cnt += 1
                        
                    if found_item:
                        import json
                        import numpy as np
                        def _cvt(v):
                            if isinstance(v, (np.integer, np.int64)): return int(v)
                            elif isinstance(v, (np.floating, np.float64)): return float(v)
                            elif pd.isna(v): return None
                            return v
                        clean_item = {k: _cvt(v) for k, v in found_item.items()}
                        print(f"!!!FOUND_JSON!!! {json.dumps({'market': market, 'item': clean_item}, ensure_ascii=False)}", flush=True)
            except Exception:
                pass

            if True: # 모든 종목(매 루프)마다 실시간 출력 (리얼타임 퍼센트 적용)
                elapsed = time.time() - t0
                # [시장명][현재/전체] 신호 N개 발견 형식으로 출력하여 app.py에서 인식하기 쉽게 함
                print(f"  [{market}][{i:>3}/{total_tickers}] 신호 {total_found_cnt}개 발견  ({elapsed:.0f}s)", flush=True)
            time.sleep(SLEEP_SEC)

        # DataFrame 변환 및 저장 헬퍼 함수
        def save_results(signals_list, market_name, prefix, sort_col, asc=False):
            if not signals_list:
                print(f"  ⚠ {prefix} 신호 없음")
                return pd.DataFrame()
                
            res_df = pd.DataFrame([r for _, r in signals_list])
            
            if sort_col in res_df.columns:
                res_df = res_df.sort_values(sort_col, ascending=asc)
            
            # 순위 추가
            res_df.insert(0, '순위', range(1, len(res_df)+1))
            
            import os
            fname = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'{market_name.lower()}_{prefix}.csv')
            res_df.to_csv(fname, encoding='utf-8-sig', index=False)
            return res_df

        # 타겟에 따라 지정된 CSV 1개만 저장
        if args.target == 'pullback':
            all_pullback_signals[market] = save_results(pb_signals, market, 'gc_pullback_signal', '시가총액(억원)')
        elif args.target == 'price_gc':
            all_price_gcs[market] = save_results(pgc_signals, market, 'golden_cross', '시가총액(억원)')
        elif args.target == 'vol_gc':
            all_vol_gcs[market] = save_results(vgc_signals, market, 'volume_ma', 'Volume_Ratio(배)')

# ──────────────────────────────────────────────
# 결과 출력
# ──────────────────────────────────────────────
print("\n" + "=" * 60)
for market in ['KOSPI', 'KOSDAQ']:
    if args.target == 'pullback':
        df = all_pullback_signals.get(market, pd.DataFrame())
    elif args.target == 'price_gc':
        df = all_price_gcs.get(market, pd.DataFrame())
    else:
        df = all_vol_gcs.get(market, pd.DataFrame())
        
    print(f"\n=== {market} {args.target} 신호 (총 {len(df)}개) ===")
    if not df.empty:
        print(df.to_string(index=True))
    else:
        print("  없음")

print("\n✅ 완료!")
print("  저장 완료되었습니다.")
