import subprocess
import threading
import time
import os

def run_flask():
    """Flask 서버 실행"""
    port = int(os.environ.get('PORT', 8080))
    subprocess.run(['python', 'app.py'])

def run_scraper():
    """스크래퍼 실행 (30초 대기 후)"""
    time.sleep(30)  # Flask 서버가 시작되길 기다림
    # 테스트 모드로 자동 실행
    env = os.environ.copy()
    env['API_URL'] = 'http://localhost:8080/api/update'
    subprocess.run(['python', 'scraper.py'], env=env, input='2\n', text=True)

if __name__ == '__main__':
    # Flask 스레드 시작
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # 스크래퍼 스레드 시작
    scraper_thread = threading.Thread(target=run_scraper)
    scraper_thread.start()
    
    # 메인 스레드는 계속 실행
    flask_thread.join()
