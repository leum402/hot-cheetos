from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from datetime import datetime
import json
import os

app = Flask(__name__)
CORS(app)

# 데이터 저장
stocks_data = []
last_update = None

@app.route('/')
def home():
    """static 폴더의 index.html 파일 서빙"""
    if os.path.exists('static/index.html'):
        return send_file('static/index.html')
    else:
        # index.html이 없을 때 API 정보 표시
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
    print(f"🚀 Flask 서버 시작: http://0.0.0.0:{port}")
    app.run(debug=False, host='0.0.0.0', port=port)
