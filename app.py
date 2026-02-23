"""
주식 스크리닝 웹 대시보드 - Flask 서버
실행: python3 app.py
접속: http://localhost:5000
"""

from flask import Flask, render_template, jsonify, request
from fetcher import get_signals, get_investor_data
import threading
import subprocess
import re
import os

app = Flask(__name__)

# 스캐너 상태 전역 변수 (타겟별로 관리)
scan_state = {
    'price_gc': {'is_running': False, 'progress': 0.0, 'message': '대기 중', 'signals_found': 0},
    'vol_gc':   {'is_running': False, 'progress': 0.0, 'message': '대기 중', 'signals_found': 0},
    'pullback': {'is_running': False, 'progress': 0.0, 'message': '대기 중', 'signals_found': 0},
}

def run_scanner_bg(target_type):
    global scan_state
    state = scan_state[target_type]
    state['is_running'] = True
    state['progress'] = 0.0
    state['message'] = '초기화 중...'
    state['signals_found'] = 0
    
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strategy_golden_pullback.py')
    
    try:
        process = subprocess.Popen(
            ['python3', script_path, '--target', target_type],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # 정규식 패턴: [250/500] 50.0% 완료... 신호 4개 발견
        pattern = re.compile(r'\[\s*(\d+)/(\d+)\]\s*([\d.]+)%\s*완료.*?신호\s*(\d+)개')
        current_market = ""

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            if "[KOSPI] 시가총액 상위 500개 추출 중..." in line:
                state['message'] = 'KOSPI 데이터 추출 중...'
            elif "[KOSPI] 전략 스캔 시작..." in line:
                current_market = "KOSPI"
                state['message'] = 'KOSPI 스캔 중...'
            elif "[KOSDAQ] 시가총액 상위 500개 추출 중..." in line:
                state['message'] = 'KOSDAQ 데이터 추출 중...'
            elif "[KOSDAQ] 전략 스캔 시작..." in line:
                current_market = "KOSDAQ"
                state['message'] = 'KOSDAQ 스캔 중...'
                
            match = pattern.search(line)
            if match:
                current_cnt = int(match.group(1))
                total_cnt = int(match.group(2))
                raw_pct = float(match.group(3))
                sigs = int(match.group(4))
                
                # KOSPI 50%, KOSDAQ 50% 분배
                if current_market == "KOSPI":
                    state['progress'] = raw_pct / 2
                elif current_market == "KOSDAQ":
                    state['progress'] = 50.0 + (raw_pct / 2)
                
                state['message'] = f'{current_market} 탐색 중... ({current_cnt}/{total_cnt})'
                state['signals_found'] = sigs
                
        process.wait()
        
        if process.returncode == 0:
            state['progress'] = 100.0
            state['message'] = '데이터 갱신 완료!'
        else:
            state['message'] = '스캔 중 오류 발생'
            
    except Exception as e:
        state['message'] = f'오류: {str(e)}'
        
    finally:
        state['is_running'] = False


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/signals')
def api_signals():
    """골든크로스 + 눌림매수 신호 데이터"""
    try:
        data = get_signals()
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/investor')
def api_investor():
    """기관/외국인/개인 순매수 TOP30"""
    date = request.args.get('date', None)
    try:
        data = get_investor_data(date)
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/scan/start', methods=['POST'])
def api_scan_start():
    data = request.get_json() or {}
    target_type = data.get('target')
    
    if target_type not in scan_state:
        return jsonify({'ok': False, 'message': '잘못된 타겟입니다.'})
        
    if scan_state[target_type]['is_running']:
        return jsonify({'ok': False, 'message': '이미 스캔이 진행 중입니다.'})
    
    thread = threading.Thread(target=run_scanner_bg, args=(target_type,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'ok': True, 'message': f'{target_type} 스캔 시작'})


@app.route('/api/scan/status', methods=['GET'])
def api_scan_status():
    target_type = request.args.get('target')
    if target_type not in scan_state:
        return jsonify({'ok': False, 'message': '잘못된 타겟입니다.'})
        
    return jsonify({
        'ok': True,
        'data': scan_state[target_type]
    })


if __name__ == '__main__':
    print("=" * 50)
    print("📊 주식 스크리닝 대시보드 시작")
    print("   http://localhost:8080")
    print("=" * 50)
    app.run(debug=True, port=8080, host='0.0.0.0')
