#!/bin/bash
# KOSPI/KODEX 데이터 자동 업데이트 스크립트
# 한국시간 06:30 (현지시간 22:30) 실행용

PROJECT_DIR="/Users/jaeduchan/Documents/jhan/antigravity/KOSPI_KODEX"
cd $PROJECT_DIR

echo "--------------------------------------------------"
echo "📅 실행 일시: $(date)"
echo "🚀 데이터 업데이트 시작..."

# 가상환경이 있다면 활성화 (필요 시)
# source .venv/bin/activate

# collector 실행 (n=0 은 전 종목 의미)
/usr/bin/python3 collector.py --n 0 >> collector.log 2>&1

echo "✅ 업데이트 완료: $(date)"
echo "--------------------------------------------------"
