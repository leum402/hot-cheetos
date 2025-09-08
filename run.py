import subprocess
import threading
import time
import os
import sys

def run_flask():
    """Flask 서버 실행"""
    print("🚀 Flask 서버 시작중...")
    subprocess.run([sys.executable, 'app.py'])

def run_scraper():
    """스크래퍼 실행 (30초 대기 후)"""
    print("⏳ 30초 후 스크래퍼 시작...")
    time.sleep(30)
    
    while True:
        try:
            print("🔄 스크래퍼 실행 시작...")
            env = os.environ.copy()
            env['API_URL'] = 'http://localhost:8080/api/update'
            
            # 테스트 모드(2)로 먼저 시작
            result = subprocess.run(
                [sys.executable, 'scraper.py'], 
                env=env, 
                input='2\n',  # 테스트 모드로 시작
                text=True,
                capture_output=True
            )
            
            print(f"스크래퍼 stdout: {result.stdout[:500]}")
            if result.stderr:
                print(f"스크래퍼 stderr: {result.stderr[:500]}")
                
            time.sleep(60)
        except Exception as e:
            print(f"❌ 스크래퍼 오류: {e}")
            time.sleep(60)

if __name__ == '__main__':  # ← 여기 수정!
    print("🎬 run.py 시작됨")
    
    # Flask 스레드 시작
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 스크래퍼 스레드 시작
    scraper_thread = threading.Thread(target=run_scraper, daemon=True)
    scraper_thread.start()
    
    # 메인 스레드 유지
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n종료됨")
        sys.exit(0)
