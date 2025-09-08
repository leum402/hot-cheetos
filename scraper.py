# -*- coding: utf-8 -*-
"""
토스 크롤링 - ChromeDriver 진단 버전
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

import os
import re
import time
import json
import random
import requests
import shutil
import subprocess
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
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--window-size=1920,1080')
    
    # 추가 옵션
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        # chromedriver 경로 찾기
        chromedriver_path = shutil.which('chromedriver')
        if chromedriver_path:
            print(f"✅ 시스템 chromedriver 발견: {chromedriver_path}", flush=True)
            service = Service(chromedriver_path)
        else:
            # 일반적인 경로들 시도
            possible_paths = [
                '/usr/bin/chromedriver',
                '/usr/local/bin/chromedriver',
                '/opt/chromedriver/chromedriver'
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    print(f"✅ chromedriver 발견: {path}", flush=True)
                    service = Service(path)
                    break
            else:
                raise Exception("chromedriver를 찾을 수 없습니다")
        
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Chrome 드라이버 생성 완료", flush=True)
        
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
# 테스트 데이터 생성 (개선된 버전)
# =========================
def generate_test_data():
    print("\n📊 테스트 데이터 생성", flush=True)
    
    # 시간대별로 다른 종목 풀
    hour = datetime.now().hour
    minute = datetime.now().minute
    
    # 종목 풀 (더 많은 종목)
    all_stocks = [
        {"name": "에코프로", "base_rate": 25},
        {"name": "에코프로비엠", "base_rate": 23},
        {"name": "포스코DX", "base_rate": 21},
        {"name": "HD현대중공업", "base_rate": 19},
        {"name": "한미반도체", "base_rate": 17},
        {"name": "엘앤에프", "base_rate": 16},
        {"name": "두산에너빌리티", "base_rate": 15},
        {"name": "코스모화학", "base_rate": 14},
        {"name": "신풍제약", "base_rate": 13},
        {"name": "씨젠", "base_rate": 12},
        {"name": "펄어비스", "base_rate": 11},
        {"name": "카카오게임즈", "base_rate": 10},
        {"name": "넷마블", "base_rate": 9},
        {"name": "위메이드", "base_rate": 8},
        {"name": "컴투스", "base_rate": 7}
    ]
    
    # 10분마다 다른 조합
    seed = (hour * 60 + minute) // 10
    random.seed(seed)
    random.shuffle(all_stocks)
    selected = all_stocks[:10]
    
    # 정렬 (등락률 기준)
    selected.sort(key=lambda x: x['base_rate'], reverse=True)
    
    stocks = []
    for i, st in enumerate(selected, 1):
        # 등락률 변동
        rate_value = st['base_rate'] + random.uniform(-2, 2)
        rate = f"+{rate_value:.2f}%"
        
        # 가격 생성
        base_prices = {
            "에코프로": 152400, "에코프로비엠": 98300, "포스코DX": 45200,
            "HD현대중공업": 112500, "한미반도체": 78600, "엘앤에프": 234500,
            "두산에너빌리티": 18900, "코스모화학": 56700, "신풍제약": 42100,
            "씨젠": 31450, "펄어비스": 28900, "카카오게임즈": 45600,
            "넷마블": 67800, "위메이드": 34200, "컴투스": 89300
        }
        
        price = f"{base_prices.get(st['name'], random.randint(20000, 200000)):,}원"
        
        # 뉴스 요약 (등락률에 따라 다르게)
        if rate_value > 20:
            summary = f"🟢 호재: {st['name']} 상한가 임박, 거래량 폭증\n🔴 악재: 단기 급등 후 조정 우려"
        elif rate_value > 15:
            summary = f"🟢 호재: {st['name']} 기관 대량 매수 유입\n🔴 악재: 차익실현 매물 대기"
        elif rate_value > 10:
            summary = f"🟢 호재: {st['name']} 실적 개선 기대감 상승\n🔴 악재: 변동성 확대 주의"
        else:
            summary = f"🟢 호재: {st['name']} 저가 매수세 유입\n🔴 악재: 추가 상승 모멘텀 부족"
        
        stocks.append({
            "rank": i,
            "name": st["name"],
            "price": price,
            "rate": rate,
            "summary": summary,
            "bullish_url": "",
            "bearish_url": "",
            "sources": []
        })
        
        print(f"  {i}. {st['name']} - {price} ({rate})", flush=True)
    
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
        
        # ChromeDriver 진단
        print("\n🔍 시스템 진단:", flush=True)
        print("-"*40, flush=True)
        
        try:
            # Chrome 버전 확인
            result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ Chrome: {result.stdout.strip()}", flush=True)
            else:
                print(f"❌ Chrome 실행 실패: {result.stderr}", flush=True)
        except FileNotFoundError:
            print("❌ Chrome이 설치되지 않음", flush=True)
        except Exception as e:
            print(f"❌ Chrome 확인 실패: {e}", flush=True)
        
        try:
            # ChromeDriver 버전 확인
            result = subprocess.run(['chromedriver', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ ChromeDriver: {result.stdout.strip()}", flush=True)
            else:
                print(f"❌ ChromeDriver 실행 실패", flush=True)
        except FileNotFoundError:
            print("❌ ChromeDriver가 설치되지 않음", flush=True)
        except Exception as e:
            print(f"❌ ChromeDriver 확인 실패: {e}", flush=True)
        
        # 파일 존재 확인
        paths_to_check = [
            '/usr/bin/google-chrome',
            '/usr/bin/chromedriver',
            '/usr/local/bin/chromedriver'
        ]
        
        print("\n📁 파일 시스템:", flush=True)
        for path in paths_to_check:
            if os.path.exists(path):
                stats = os.stat(path)
                print(f"  ✅ {path} (크기: {stats.st_size} bytes)", flush=True)
            else:
                print(f"  ❌ {path} 없음", flush=True)
        
        print("-"*40, flush=True)
        
        # 토스 크롤링 시도 (옵션)
        try_crawling = False  # 일단 비활성화
        
        if try_crawling:
            try:
                try_toss_crawling()
            except Exception as e:
                print(f"크롤링 진단 실패: {e}", flush=True)
        else:
            print("\n⏭️ 토스 크롤링 스킵 (테스트 모드)", flush=True)
        
        # 테스트 데이터 전송
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
        print("로컬 수동 모드")
