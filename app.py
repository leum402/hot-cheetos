from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from datetime import datetime
import json
import os
import time  # ← 이거 추가!
import subprocess
import sys
import threading


app = Flask(__name__)
CORS(app)

# 초기 테스트 데이터 추가
stocks_data = [
    {
        "rank": 1,
        "name": "삼성전자",
        "price": "87,500원",
        "rate": "+29.95%",
        "summary": "🟢 호재: AI 반도체 대규모 수주 기대\n🔴 악재: 글로벌 규제 리스크"
    },
    {
        "rank": 2,
        "name": "SK하이닉스",
        "price": "142,300원",
        "rate": "+25.32%",
        "summary": "🟢 호재: HBM4 양산 돌입 발표\n🔴 악재: 메모리 가격 조정 압력"
    },
    {
        "rank": 3,
        "name": "카카오",
        "price": "58,900원",
        "rate": "+21.24%",
        "summary": "🟢 호재: 신규 AI 서비스 공개\n🔴 악재: 플랫폼 규제 리스크"
    },
    {
        "rank": 4,
        "name": "네이버",
        "price": "185,200원",
        "rate": "+18.56%",
        "summary": "🟢 호재: 일본 계열 실적 호조\n🔴 악재: 광고 성장 둔화"
    },
    {
        "rank": 5,
        "name": "현대차",
        "price": "245,000원",
        "rate": "+15.87%",
        "summary": "🟢 호재: EV 판매 1위 기대\n🔴 악재: 원자재 비용 부담"
    }
]

last_update = datetime.now().isoformat()

@app.route('/')
def home():
    """static 폴더의 index.html 파일 서빙"""
    if os.path.exists('static/index.html'):
        return send_file('static/index.html')
    else:
        return """
        <h1>📊 Stock Monitor API</h1>
        <p>Endpoints:</p>
        <ul>
            <li>GET /api/stocks - 현재 주식 데이터</li>
            <li>POST /api/update - 데이터 업데이트</li>
            <li>GET /api/status - 서버 상태</li>
        </ul>
        """

@app.route('/api/stocks', methods=['GET'])
def get_stocks():
    """현재 저장된 주식 데이터 반환"""
    return jsonify({
        'stocks': stocks_data,
        'last_update': last_update,
        'count': len(stocks_data)
    })

@app.route('/api/update', methods=['POST'])
def update_stocks():
    """스크래퍼에서 보낸 데이터 저장"""
    global stocks_data, last_update
    
    try:
        stocks_data = request.json
        last_update = datetime.now().isoformat()
        
        print(f"✅ 데이터 업데이트: {len(stocks_data)}개 종목")
        for stock in stocks_data[:3]:
            print(f"  - {stock['rank']}위: {stock['name']} ({stock['rate']})")
        
        return jsonify({
            'status': 'success',
            'message': f'{len(stocks_data)}개 종목 업데이트 완료',
            'timestamp': last_update
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400

@app.route('/api/status', methods=['GET'])
def status():
    """서버 상태 확인"""
    return jsonify({
        'status': 'running',
        'stocks_count': len(stocks_data),
        'last_update': last_update,
        'server_time': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    # 백그라운드에서 스크래퍼 실행
    import threading
    import subprocess
    import sys
    
    def run_scraper_loop():
        time.sleep(30)
        print("🔄 스크래퍼 백그라운드 시작")
        
        while True:
            try:
                print("📊 테스트 데이터 생성 중...")
                # 테스트 모드로 실행 (토스 크롤링은 Docker에서 어려울 수 있음)
                subprocess.run([sys.executable, 'scraper.py'], input='2\n', text=True, timeout=120)
            except Exception as e:
                print(f"스크래퍼 오류: {e}")
            time.sleep(60)
    
    scraper_thread = threading.Thread(target=run_scraper_loop, daemon=True)
    scraper_thread.start()
    
    print(f"🚀 Flask 서버 시작: http://0.0.0.0:{port}")
    app.run(debug=False, host='0.0.0.0', port=port)
