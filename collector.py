import FinanceDataReader as fdr
from pykrx import stock
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 설정
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TOP_N = 0  # 0이면 전 종목 관리

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"📁 데이터 폴더 생성됨: {DATA_DIR}")

def get_top_tickers(market, n):
    """시가총액 상위 종목 리스트 가져오기"""
    print(f"🔍 {market} 시가총액 상위 {n}개 추출 중...")
    try:
        df = fdr.StockListing(market)
        df = df.sort_values('Marcap', ascending=False)
        if n > 0:
            df = df.head(n)
        return df['Code'].tolist()
    except Exception as e:
        print(f"❌ {market} 리스트 추출 실패: {e}")
        return []

def collect_ohlcv(ticker, start_date, end_date):
    """특정 종목의 OHLCV 데이터를 가져와서 CSV로 저장 (증분 업데이트 지원)"""
    file_path = os.path.join(DATA_DIR, f"{ticker}.csv")
    
    try:
        # 1. 기존 데이터 확인
        if os.path.exists(file_path):
            existing_df = pd.read_csv(file_path, index_col=0, parse_dates=True)
            if not existing_df.empty:
                last_date = existing_df.index[-1]
                target_end_dt = pd.to_datetime(end_date)
                
                # 이미 최신이면 스킵
                if last_date >= target_end_dt:
                    return True
                
                # 부족한 부분만 가져오기
                fetch_start = (last_date + timedelta(days=1)).strftime('%Y%m%d')
                delta_df = stock.get_market_ohlcv(fetch_start, end_date, ticker)
                
                if delta_df is not None and not delta_df.empty:
                    # 인덱스 이름(날짜) 맞추기
                    delta_df.index.name = existing_df.index.name
                    updated_df = pd.concat([existing_df, delta_df])
                    updated_df.to_csv(file_path, encoding='utf-8-sig')
                    return True
                else:
                    return True # 추가 데이터 없음 (휴장일 등)

        # 2. 데이터가 없으면 통째로 가져오기
        df = stock.get_market_ohlcv(start_date, end_date, ticker)
        if df is None or df.empty:
            return False
        
        df.to_csv(file_path, encoding='utf-8-sig')
        return True
    except Exception as e:
        print(f"   - {ticker} 실패: {e}")
        return False

def run_collection(n=TOP_N):
    ensure_data_dir()
    
    # 기준일 설정 (영업일 400일 이상 확보를 위해 약 700일 전부터 수집)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=700)).strftime("%Y%m%d")
    
    print(f"🚀 데이터 수집 시작 ({start_date} ~ {end_date})")
    
    for market in ['KOSPI', 'KOSDAQ']:
        tickers = get_top_tickers(market, n)
        total = len(tickers)
        
        for i, ticker in enumerate(tickers, 1):
            success = collect_ohlcv(ticker, start_date, end_date)
            status = "✅" if success else "❌"
            print(f"[{market}] {i}/{total} {ticker} {status}", end='\r')
            time.sleep(0.05)  # 서버 부하 방지용 미세 지연
        print(f"\n[{market}] 수집 완료!")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--n', type=int, default=TOP_N, help='시장별 수집 종목 수')
    args = parser.parse_args()
    
    run_collection(args.n)
    print("\n✨ 모든 데이터 수집 작업이 완료되었습니다.")
