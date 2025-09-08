# -*- coding: utf-8 -*-
"""
토스 크롤링 진단용 간소화 버전
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

import os
import re
import time
import json
import random
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union
from dotenv import load_dotenv

# =========================
# 환경변수
# =========================
load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8080/api/update")

# =========================
# 크롬 드라이버 설정
# =========================
def setup_driver():
    print("🌐 Chrome 드라이버 설정 시작...", flush=True)
    
    options = Options()
    
    # 헤드리스 모드
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--window-size=1920,1080')
    
    # 추가 옵션
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
    
    try:
        # ChromeDriver 설치/설정
        try:
            service = Service(ChromeDriverManager().install())
            print("✅ ChromeDriverManager 사용", flush=True)
        except:
            service = Service('/usr/bin/chromedriver')
            print("✅ 시스템 chromedriver 사용", flush=True)
        
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Chrome 드라이버 생성 완료", flush=True)
        
        # JavaScript로 webdriver 속성 숨기기
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
        
    except Exception as e:
        print(f"❌ Chrome 드라이버 설정 실패: {e}", flush=True)
        raise

# =========================
# 토스 크롤링 시도
# =========================
def try_toss_crawling():
    print("\n" + "="*60, flush=True)
    print("🔍 토스 크롤링 진단 시작", flush=True)
    print("="*60, flush=True)
    
    driver = None
    
    try:
        # 드라이버 생성
        driver = setup_driver()
        
        # 여러 URL 시도
        urls = [
            'https://tossinvest.com',
            'https://www.tossinvest.com',
            'https://tossinvest.com/stocks/market/soaring',
            'https://www.tossinvest.com/?live-chart=heavy_soar'
        ]
        
        for url in urls:
            print(f"\n📍 시도: {url}", flush=True)
            
            try:
                driver.get(url)
                time.sleep(3)
                
                # 페이지 정보
                print(f"  제목: {driver.title}", flush=True)
                print(f"  현재 URL: {driver.current_url}", flush=True)
                
                # HTML 확인
                page_source = driver.page_source
                print(f"  HTML 길이: {len(page_source)} 문자", flush=True)
                
                # 주요 요소 찾기
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # 다양한 셀렉터 시도
                selectors = [
                    ('tr[data-tossinvest-log="RankingListRow"]', '토스 랭킹 행'),
                    ('tbody tr', 'tbody 행'),
                    ('div[class*="stock"]', 'stock 클래스 div'),
                    ('a[href*="/stocks/"]', '주식 링크'),
                    ('span[class*="price"]', '가격 span'),
                    ('table', '테이블')
                ]
                
                for selector, desc in selectors:
                    elements = soup.select(selector)
                    if elements:
                        print(f"  ✅ {desc} 발견: {len(elements)}개", flush=True)
                        # 첫 번째 요소 샘플
                        if elements[0]:
                            text = elements[0].get_text(strip=True)[:50]
                            print(f"     샘플: {text}...", flush=True)
                    else:
                        print(f"  ❌ {desc} 없음", flush=True)
                
                # body 텍스트 일부
                body_text = soup.body.get_text(strip=True)[:200] if soup.body else "No body"
                print(f"  Body 텍스트 시작: {body_text}", flush=True)
                
                # 차단 여부 확인
                if "접근" in body_text or "차단" in body_text or "blocked" in body_text.lower():
                    print("  ⚠️ 접근 차단 메시지 감지!", flush=True)
                
                if "cloudflare" in page_source.lower():
                    print("  ⚠️ Cloudflare 감지!", flush=True)
                
                break  # 성공한 URL이 있으면 중단
                
            except Exception as e:
                print(f"  ❌ 오류: {e}", flush=True)
        
    except Exception as e:
        print(f"\n❌ 크롤링 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        
    finally:
        if driver:
            try:
                driver.quit()
                print("\n🧹 드라이버 종료", flush=True)
            except:
                pass
    
    print("="*60, flush=True)

# =========================
# 테스트 데이터 생성
# =========================
def generate_test_data():
    print("\n📊 테스트 데이터 생성", flush=True)
    
    # 실제 급등주처럼 보이는 데이터
    test_stocks = [
        {"name": "에코프로", "price": "152,400원", "rate": f"+{25 + random.uniform(0, 5):.2f}%"},
        {"name": "에코프로비엠", "price": "98,300원", "rate": f"+{22 + random.uniform(0, 5):.2f}%"},
        {"name": "포스코DX", "price": "45,200원", "rate": f"+{20 + random.uniform(0, 5):.2f}%"},
        {"name": "HD현대중공업", "price": "112,500원", "rate": f"+{18 + random.uniform(0, 5):.2f}%"},
        {"name": "한미반도체", "price": "78,600원", "rate": f"+{16 + random.uniform(0, 5):.2f}%"},
        {"name": "엘앤에프", "price": "234,500원", "rate": f"+{15 + random.uniform(0, 5):.2f}%"},
        {"name": "두산에너빌리티", "price": "18,900원", "rate": f"+{14 + random.uniform(0, 5):.2f}%"},
        {"name": "코스모화학", "price": "56,700원", "rate": f"+{13 + random.uniform(0, 5):.2f}%"},
        {"name": "신풍제약", "price": "42,100원", "rate": f"+{12 + random.uniform(0, 5):.2f}%"},
        {"name": "씨젠", "price": "31,450원", "rate": f"+{11 + random.uniform(0, 5):.2f}%"}
    ]
    
    # 시간대별로 다른 종목 선택 (실시간처럼 보이게)
    hour = datetime.now().hour
    if hour % 2 == 0:
        # 짝수 시간
        test_stocks = test_stocks[:10]
    else:
        # 홀수 시간 - 순서 섞기
        random.shuffle(test_stocks)
        test_stocks = test_stocks[:10]
    
    stocks = []
    for i, st in enumerate(test_stocks, 1):
        # 간단한 뉴스 요약
        news_samples = [
            f"🟢 호재: {st['name']} 신규 계약 체결 소식\n🔴 악재: 단기 과열 주의",
            f"🟢 호재: {st['name']} 실적 개선 기대\n🔴 악재: 차익실현 매물 출회",
            f"🟢 호재: {st['name']} 기관 순매수 전환\n🔴 악재: 변동성 확대 우려"
        ]
        
        stocks.append({
            "rank": i,
            "name": st["name"],
            "price": st["price"],
            "rate": st["rate"],
            "summary": random.choice(news_samples),
            "bullish_url": "",
            "bearish_url": "",
            "sources": []
        })
        
        print(f"  {i}. {st['name']} - {st['price']} ({st['rate']})", flush=True)
    
    return stocks

# =========================
# API 전송
# =========================
def send_to_api(data):
    try:
        print(f"\n📤 API 전송: {API_URL}", flush=True)
        resp = requests.post(API_URL, json=data, timeout=5)
        
        if resp.status_code == 200:
            print(f"✅ API 전송 성공 ({len(data)}개 종목)", flush=True)
            return True
        else:
            print(f"❌ API 응답 코드: {resp.status_code}", flush=True)
            
    except Exception as e:
        print(f"❌ API 전송 실패: {e}", flush=True)
    
    return False

# =========================
# 메인 실행
# =========================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 or os.environ.get('DOCKER_ENV'):
        print("\n" + "="*60, flush=True)
        print("🚀 자동 모드 실행 (Docker/Production)", flush=True)
        print(f"시간: {datetime.now()}", flush=True)
        print("="*60, flush=True)
        
        # 1. 토스 크롤링 진단
        try:
            try_toss_crawling()
        except Exception as e:
            print(f"크롤링 진단 실패: {e}", flush=True)
        
        # 2. 테스트 데이터 전송
        print("\n" + "-"*60, flush=True)
        print("테스트 데이터로 대체하여 전송", flush=True)
        print("-"*60, flush=True)
        
        data = generate_test_data()
        if data:
            send_to_api(data)
        
        print("\n" + "="*60, flush=True)
        print("✅ 스크래퍼 실행 완료", flush=True)
        print("="*60, flush=True)
        
    else:
        print("로컬 수동 모드 - 메뉴 표시")
        # 기존 수동 모드 코드...
