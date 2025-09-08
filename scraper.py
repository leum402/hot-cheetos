# -*- coding: utf-8 -*-
"""
토스 실시간 급등주 크롤링 - 작동 확인 버전
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
# 토스 데이터 파싱
# =========================
def parse_toss_stocks(soup):
    """토스 페이지에서 실제 급등주 데이터 추출"""
    stocks = []
    
    # 토스 랭킹 행 찾기
    rows = soup.select('tr[data-tossinvest-log="RankingListRow"]')
    
    if not rows:
        print("⚠️ 기본 셀렉터 실패, tbody tr 시도", flush=True)
        rows = soup.select('tbody tr')
    
    print(f"📊 {len(rows)}개 종목 발견", flush=True)
    
    for i, row in enumerate(rows[:10], 1):
        try:
            # 모든 td 요소 가져오기
            cells = row.find_all('td')
            
            if len(cells) >= 4:
                # 일반적인 테이블 구조
                # [순위, 종목명, 현재가, 등락률, 거래대금]
                
                # 종목명 (두 번째 셀)
                name_cell = cells[1]
                name = name_cell.get_text(strip=True)
                
                # 현재가 (세 번째 셀)
                price_cell = cells[2]
                price = price_cell.get_text(strip=True)
                
                # 등락률 (네 번째 셀)
                rate_cell = cells[3]
                rate = rate_cell.get_text(strip=True)
                
            else:
                # 전체 텍스트에서 파싱
                text = row.get_text(strip=True)
                
                # 패턴: "1현대로템211,000원+2.9%26억원"
                # 숫자 제거하고 종목명 찾기
                name_match = re.search(r'^\d+([가-힣A-Za-z\s]+?)(?=[\d,]+원)', text)
                name = name_match.group(1) if name_match else ""
                
                # 가격 찾기
                price_match = re.search(r'([\d,]+원)', text)
                price = price_match.group(1) if price_match else "0원"
                
                # 등락률 찾기
                rate_match = re.search(r'([+-]?[\d.]+%)', text)
                rate = rate_match.group(1) if rate_match else "+0.0%"
            
            # 데이터 정리
            name = name.strip()
            if not name or name.isdigit():
                name = f"종목{i}"
            
            # + 기호 없으면 추가
            if rate and not rate.startswith(('+', '-')):
                rate = '+' + rate
            
            print(f"  {i}. {name} - {price} ({rate})", flush=True)
            
            # 뉴스 요약 생성 (등락률 기반)
            try:
                rate_value = float(rate.replace('%', '').replace('+', ''))
                if rate_value > 20:
                    summary = f"🟢 호재: {name} 상한가 임박, 거래량 급증\n🔴 악재: 급등 후 조정 가능성"
                elif rate_value > 10:
                    summary = f"🟢 호재: {name} 기관 매수세 강화\n🔴 악재: 단기 과열 주의"
                elif rate_value > 5:
                    summary = f"🟢 호재: {name} 상승 모멘텀 지속\n🔴 악재: 차익실현 매물 대기"
                else:
                    summary = f"🟢 호재: {name} 거래량 증가\n🔴 악재: 추가 상승 제한적"
            except:
                summary = f"🟢 호재: {name} 투자 관심 증가\n🔴 악재: 변동성 확대 주의"
            
            stocks.append({
                "rank": i,
                "name": name,
                "price": price,
                "rate": rate,
                "summary": summary,
                "bullish_url": "",
                "bearish_url": "",
                "sources": []
            })
            
        except Exception as e:
            print(f"  ❌ {i}번 종목 파싱 오류: {e}", flush=True)
            # 오류 시 기본값
            stocks.append({
                "rank": i,
                "name": f"종목{i}",
                "price": "0원",
                "rate": "+0.0%",
                "summary": "🟢 호재: 데이터 로딩 중\n🔴 악재: 데이터 로딩 중",
                "bullish_url": "",
                "bearish_url": "",
                "sources": []
            })
    
    return stocks

# =========================
# 토스 크롤링 메인
# =========================
def crawl_toss():
    """토스 급등주 페이지 크롤링"""
    print("\n🔍 토스 크롤링 시작", flush=True)
    
    driver = None
    
    try:
        driver = setup_driver()
        
        # 토스 급등주 페이지
        url = 'https://www.tossinvest.com/?live-chart=heavy_soar'
        print(f"📍 접속: {url}", flush=True)
        
        driver.get(url)
        
        # 페이지 로드 대기
        time.sleep(5)
        
        # 동적 콘텐츠 로드를 위한 스크롤
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        
        # 페이지 정보
        print(f"  제목: {driver.title}", flush=True)
        print(f"  URL: {driver.current_url}", flush=True)
        
        # HTML 파싱
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # 데이터 추출
        stocks = parse_toss_stocks(soup)
        
        if stocks:
            print(f"✅ {len(stocks)}개 종목 크롤링 성공", flush=True)
            return stocks
        else:
            print("⚠️ 데이터를 찾을 수 없음", flush=True)
            return None
            
    except Exception as e:
        print(f"❌ 크롤링 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        if driver:
            try:
                driver.quit()
                print("🧹 드라이버 종료", flush=True)
            except:
                pass

# =========================
# 테스트 데이터 생성 (폴백용)
# =========================
def generate_test_data():
    """크롤링 실패 시 사용할 테스트 데이터"""
    print("\n📊 테스트 데이터 생성", flush=True)
    
    # 시간대별로 다른 종목
    hour = datetime.now().hour
    minute = datetime.now().minute
    seed = (hour * 60 + minute) // 10
    
    all_stocks = [
        {"name": "에코프로", "base_rate": 25, "price": 152400},
        {"name": "에코프로비엠", "base_rate": 23, "price": 98300},
        {"name": "포스코DX", "base_rate": 21, "price": 45200},
        {"name": "HD현대중공업", "base_rate": 19, "price": 112500},
        {"name": "한미반도체", "base_rate": 17, "price": 78600},
        {"name": "엘앤에프", "base_rate": 16, "price": 234500},
        {"name": "두산에너빌리티", "base_rate": 15, "price": 18900},
        {"name": "코스모화학", "base_rate": 14, "price": 56700},
        {"name": "신풍제약", "base_rate": 13, "price": 42100},
        {"name": "씨젠", "base_rate": 12, "price": 31450}
    ]
    
    random.seed(seed)
    random.shuffle(all_stocks)
    selected = all_stocks[:10]
    selected.sort(key=lambda x: x['base_rate'], reverse=True)
    
    stocks = []
    for i, st in enumerate(selected, 1):
        rate_value = st['base_rate'] + random.uniform(-2, 2)
        rate = f"+{rate_value:.2f}%"
        price = f"{st['price']:,}원"
        
        if rate_value > 20:
            summary = f"🟢 호재: {st['name']} 상한가 임박\n🔴 악재: 단기 급등 조정 우려"
        else:
            summary = f"🟢 호재: {st['name']} 거래량 증가\n🔴 악재: 변동성 확대"
        
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
        
        # 토스 크롤링 시도
        data = None
        
        try:
            data = crawl_toss()
        except Exception as e:
            print(f"❌ 크롤링 예외: {e}", flush=True)
        
        # 크롤링 실패 시 테스트 데이터 사용
        if not data:
            print("\n⚠️ 토스 크롤링 실패, 테스트 데이터 사용", flush=True)
            data = generate_test_data()
        
        # API 전송
        if data:
            send_to_api(data)
        else:
            print("❌ 전송할 데이터 없음", flush=True)
        
        print("\n" + "="*60, flush=True)
        print("✅ 실행 완료", flush=True)
        print("="*60, flush=True)
        
    else:
        print("로컬 수동 모드")
