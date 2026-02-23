"""
주식 스크리닝 데이터 페처
- 신호 데이터: 사전 계산 CSV 로드
- 투자자 순매수: KRX 데이터포털 직접 요청
"""

import pandas as pd
import requests
import json
from datetime import datetime, timedelta
from pykrx import stock as krx
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────
def get_last_bday() -> str:
    """가장 최근 영업일 날짜 반환 (YYYYMMDD)"""
    d = datetime.now()
    # 토/일이면 전 금요일로
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    # 오전 9시 이전이면 하루 더 뒤로
    if datetime.now().hour < 9:
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d.strftime('%Y%m%d')


def ticker_name(code: str) -> str:
    try:
        return krx.get_market_ticker_name(code)
    except:
        return code


# ──────────────────────────────────────────────
# 1~3: 신호 데이터 (CSV 로드)
# ──────────────────────────────────────────────
def load_csv(filename: str) -> list[dict]:
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
        df = df.fillna('-')
        # 숫자 컬럼 콤마 포맷
        for col in df.select_dtypes(include='number').columns:
            df[col] = df[col].apply(lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x)
        return df.to_dict(orient='records')
    except:
        return []


def get_signals() -> dict:
    return {
        'price_gc_kospi':    load_csv('kospi_golden_cross.csv'),
        'price_gc_kosdaq':   load_csv('kosdaq_golden_cross.csv'),
        'vol_gc_kospi':      load_csv('kospi_volume_ma.csv'),
        'vol_gc_kosdaq':     load_csv('kospi_volume_ma.csv'), # kodaq volume ma csv가 아직 없으면 kospi 임시 바인딩(후속작업필요)
        'pullback_kospi':    load_csv('kospi_gc_pullback_signal.csv'),
        'pullback_kosdaq':   load_csv('kosdaq_gc_pullback_signal.csv'),
        'last_updated':      get_last_bday(),
    }


# ──────────────────────────────────────────────
# 4~6: 투자자 순매수 (KRX 직접 요청)
# ──────────────────────────────────────────────
KRX_URL = 'http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
KRX_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Referer': 'http://data.krx.co.kr/',
    'Content-Type': 'application/x-www-form-urlencoded',
}

INVESTOR_CODES = {
    '기관': '2000',
    '외국인': '4000',
    '개인': '1000',
}

MKT_CODES = {
    'KOSPI': 'STK',
    'KOSDAQ': 'KSQ',
}


def fetch_investor_data(date: str, market: str, investor: str, top_n: int = 30) -> list[dict]:
    """KRX에서 투자자별 순매수 상위 종목 조회"""
    mkt_code = MKT_CODES.get(market, 'STK')
    inv_code = INVESTOR_CODES.get(investor, '2000')

    params = {
        'bld': 'dbms/MDC/STAT/standard/MDCSTAT02402',
        'locale': 'ko_KR',
        'mktId': mkt_code,
        'invstTpCd': inv_code,
        'trdDd': date,
        'share': '1',
        'money': '1',
        'csvxls_isNo': 'false',
    }

    try:
        resp = requests.post(KRX_URL, data=params, headers=KRX_HEADERS, timeout=10)
        data = resp.json()
        items = data.get('output', [])
        if not items:
            return []

        # 순매수거래량 기준 상위 N개
        df = pd.DataFrame(items)
        # 컬럼명 정규화
        col_map = {}
        for col in df.columns:
            if '종목' in col and '코드' in col: col_map[col] = '종목코드'
            elif '종목' in col and ('명' in col or '이름' in col): col_map[col] = '종목명'
            elif '순매수' in col and '거래량' in col: col_map[col] = '순매수거래량'
            elif '순매수' in col and '거래대금' in col: col_map[col] = '순매수거래대금'
        df = df.rename(columns=col_map)

        # 순매수거래량 숫자 변환
        if '순매수거래량' in df.columns:
            df['순매수거래량'] = pd.to_numeric(
                df['순매수거래량'].astype(str).str.replace(',', ''), errors='coerce'
            )
            df = df.sort_values('순매수거래량', ascending=False).head(top_n)
            df['순매수거래량'] = df['순매수거래량'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else '-')

        return df.fillna('-').to_dict(orient='records')
    except Exception as e:
        print(f"[KRX 오류] {investor} {market}: {e}")
        return []


def get_investor_data(date: str = None) -> dict:
    if not date:
        date = get_last_bday()

    result = {'date': date, 'data': {}}
    for market in ['KOSPI', 'KOSDAQ']:
        result['data'][market] = {}
        for inv in ['기관', '외국인', '개인']:
            result['data'][market][inv] = fetch_investor_data(date, market, inv)

    return result
