from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from datetime import datetime
import json
import os

app = Flask(__name__)
CORS(app)  # 모든 도메인에서 접근 가능

# 데이터 저장 (실제로는 DB 사용 권장)
stocks_data = []
last_update = None

@app.route('/')
def home():
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
        
        # 로그 출력
        print(f"✅ 데이터 업데이트: {len(stocks_data)}개 종목")
        for stock in stocks_data[:3]:  # 상위 3개만 출력
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
    print("🚀 Flask 서버 시작: http://127.0.0.1:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)