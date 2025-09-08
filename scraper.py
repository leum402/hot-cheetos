# -*- coding: utf-8 -*-
"""
토스 실시간 급등주 + 실제 뉴스 크롤링 및 AI 요약
- Google News RSS로 24시간 이내 뉴스 수집
- OpenAI GPT로 호재/악재 분석
- 1시간 캐싱으로 API 비용 절감
- 실제 뉴스 링크 제공
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
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from urllib.parse import quote_plus
from dotenv import load_dotenv

# =========================
# 환경변수
# =========================
load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8080/api/update")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "12"))
OPENAI_RETRIES = int(os.getenv("OPENAI_RETRIES", "2"))
MAX_LINE_LEN = int(os.getenv("NEWS_MAX_LINE_LEN", "50"))
CACHE_DURATION_MINUTES = int(os.getenv("NEWS_CACHE_MINUTES", "60"))

# =========================
# 뉴스 캐시 시스템
# =========================
class NewsCache:
    """1시간 동안 뉴스 캐싱하여 API 비용 절감"""
    def __init__(self, cache_duration_minutes: int = 60):
        self.cache: Dict[str, Tuple[dict, datetime]] = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.cache_file = "news_cache.json"
        self.load_cache()

    def load_cache(self):
        """저장된 캐시 파일 로드"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                now = datetime.now()
                for stock, (value, ts_str) in data.items():
                    ts = datetime.fromisoformat(ts_str)
                    if now - ts < self.cache_duration:
                        self.cache[stock] = (value, ts)
                print(f"📦 캐시 로드: {len(self.cache)}개 종목", flush=True)
            except Exception as e:
                print(f"⚠️ 캐시 로드 실패: {e}", flush=True)

    def save_cache(self):
        """캐시를 파일로 저장"""
        try:
            data = {}
            for stock, (value, ts) in self.cache.items():
                # 문자열이면 구 형식, dict면 신 형식
                if isinstance(value, str):
                    # 구 형식을 신 형식으로 변환
                    value = {
                        "summary": value,
                        "bullish_url": "",
                        "bearish_url": "",
                        "sources": []
                    }
                data[stock] = (value, ts.isoformat())
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 캐시 저장 실패: {e}", flush=True)

    def get(self, stock_name: str) -> Optional[dict]:
        """캐시에서 데이터 가져오기"""
        if stock_name in self.cache:
            value, cached_time = self.cache[stock_name]
            if datetime.now() - cached_time < self.cache_duration:
                remaining = self.cache_duration - (datetime.now() - cached_time)
                print(f"    💾 캐시 사용: {stock_name} (남은시간: {remaining.seconds//60}분)", flush=True)
                # 문자열이면 구 형식, dict면 신 형식
                if isinstance(value, str):
                    return {
                        "summary": value,
                        "bullish_url": "",
                        "bearish_url": "",
                        "sources": []
                    }
                return value
            else:
                del self.cache[stock_name]
        return None

    def set(self, stock_name: str, value: dict):
        """캐시에 데이터 저장"""
        self.cache[stock_name] = (value, datetime.now())
        self.save_cache()

    def cleanup(self):
        """만료된 캐시 정리"""
        now = datetime.now()
        expired = [stock for stock, (_, ts) in self.cache.items() 
                  if now - ts >= self.cache_duration]
        for stock in expired:
            del self.cache[stock]
        if expired:
            print(f"🗑️ 만료 캐시 정리: {len(expired)}개", flush=True)
            self.save_cache()

# 전역 캐시 인스턴스
news_cache = NewsCache(CACHE_DURATION_MINUTES)

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
# Google News RSS에서 뉴스 수집
# =========================
def fetch_google_news(stock_name: str, max_items: int = 5) -> List[dict]:
    """Google News RSS에서 24시간 이내 뉴스 수집"""
    query = quote_plus(f"{stock_name} when:1d")
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
    except Exception as e:
        print(f"    ⚠️ 뉴스 RSS 실패: {e}", flush=True)
        return []
    
    items = []
    try:
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            
            if title_el is not None and link_el is not None:
                title = title_el.text.strip()
                link = link_el.text.strip()
                published = pub_el.text.strip() if pub_el is not None else ""
                
                # 루머나 추정성 기사 제외
                if any(k in title for k in ["루머", "추정", "소문", "전망만", "예상만"]):
                    continue
                
                items.append({
                    "title": title,
                    "link": link,
                    "published": published
                })
                
                if len(items) >= max_items:
                    break
    except Exception as e:
        print(f"    ⚠️ RSS 파싱 실패: {e}", flush=True)
    
    return items

# =========================
# OpenAI GPT로 뉴스 요약
# =========================
def summarize_news_with_gpt(stock_name: str, rate: str, headlines: List[dict]) -> dict:
    """GPT로 호재/악재 분석 및 링크 매핑"""
    
    # API 키 없으면 규칙 기반 요약
    if not OPENAI_API_KEY:
        return rule_based_summary(stock_name, rate, headlines)
    
    # OpenAI SDK 임포트
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        print("    ⚠️ OpenAI 라이브러리 없음", flush=True)
        return rule_based_summary(stock_name, rate, headlines)
    except Exception as e:
        print(f"    ⚠️ OpenAI 초기화 실패: {e}", flush=True)
        return rule_based_summary(stock_name, rate, headlines)
    
    # 헤드라인 포맷팅
    headlines_text = "\n".join([
        f"{i}. {h['title']}" 
        for i, h in enumerate(headlines, 1)
    ]) if headlines else "뉴스 없음"
    
    # GPT 프롬프트
    system_prompt = (
        "너는 한국 주식 뉴스 분석 전문가다. "
        "실제 뉴스 헤드라인을 기반으로 호재와 악재를 각각 한 줄로 요약한다. "
        "각 줄은 50자 이내로 작성한다."
    )
    
    user_prompt = f"""
종목: {stock_name}
등락률: {rate}
오늘 뉴스 헤드라인:
{headlines_text}

아래 JSON 형식으로만 출력하라:
{{
  "bullish": "호재 내용 한 줄",
  "bearish": "악재 내용 한 줄",
  "bullish_idx": 1,
  "bearish_idx": 2
}}

bullish_idx는 호재 근거가 되는 헤드라인 번호 (1부터 시작)
bearish_idx는 악재 근거가 되는 헤드라인 번호
근거가 없으면 해당 idx는 null로 설정
"""
    
    # GPT 호출 (재시도 포함)
    for attempt in range(OPENAI_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.3,
                max_tokens=200,
                timeout=OPENAI_TIMEOUT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            content = response.choices[0].message.content.strip()
            
            # JSON 파싱
            if content.startswith("```"):
                content = content.strip("`").strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            
            data = json.loads(content)
            
            # 결과 포맷팅
            bullish = data.get('bullish', '특별한 호재 없음')
            bearish = data.get('bearish', '특별한 악재 없음')
            bull_idx = data.get('bullish_idx')
            bear_idx = data.get('bearish_idx')
            
            # 링크 매핑
            bull_url = ""
            bear_url = ""
            if bull_idx and headlines and 1 <= bull_idx <= len(headlines):
                bull_url = headlines[bull_idx - 1]['link']
            if bear_idx and headlines and 1 <= bear_idx <= len(headlines):
                bear_url = headlines[bear_idx - 1]['link']
            
            # 길이 제한
            if len(bullish) > MAX_LINE_LEN:
                bullish = bullish[:MAX_LINE_LEN-1] + "…"
            if len(bearish) > MAX_LINE_LEN:
                bearish = bearish[:MAX_LINE_LEN-1] + "…"
            
            return {
                "summary": f"🟢 호재: {bullish}\n🔴 악재: {bearish}",
                "bullish_url": bull_url,
                "bearish_url": bear_url,
                "sources": headlines
            }
            
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 텍스트 그대로 사용
            return rule_based_summary(stock_name, rate, headlines)
        except Exception as e:
            if attempt < OPENAI_RETRIES:
                print(f"    ⚠️ GPT 재시도 {attempt+1}/{OPENAI_RETRIES}", flush=True)
                time.sleep(1)
            else:
                print(f"    ⚠️ GPT 최종 실패: {e}", flush=True)
                return rule_based_summary(stock_name, rate, headlines)
    
    return rule_based_summary(stock_name, rate, headlines)

# =========================
# 규칙 기반 요약 (폴백)
# =========================
def rule_based_summary(stock_name: str, rate: str, headlines: List[dict]) -> dict:
    """GPT 사용 불가 시 규칙 기반 요약"""
    if headlines and len(headlines) > 0:
        # 첫 번째 뉴스를 호재로
        bullish = headlines[0]['title'][:MAX_LINE_LEN-8]
        bull_url = headlines[0]['link']
        
        # 두 번째 뉴스를 악재로 (없으면 일반 메시지)
        if len(headlines) > 1:
            bearish = headlines[1]['title'][:MAX_LINE_LEN-8]
            bear_url = headlines[1]['link']
        else:
            bearish = "단기 변동성 주의"
            bear_url = ""
    else:
        # 뉴스가 없을 때
        try:
            rate_value = float(rate.replace('%', '').replace('+', ''))
            if rate_value > 20:
                bullish = f"{stock_name} 상한가 임박"
                bearish = "급등 후 조정 가능성"
            elif rate_value > 10:
                bullish = f"{stock_name} 강세 지속"
                bearish = "차익실현 매물 대기"
            else:
                bullish = f"{stock_name} 상승세"
                bearish = "추가 상승 제한적"
        except:
            bullish = f"{stock_name} 거래량 증가"
            bearish = "변동성 확대 주의"
        
        bull_url = ""
        bear_url = ""
    
    return {
        "summary": f"🟢 호재: {bullish}\n🔴 악재: {bearish}",
        "bullish_url": bull_url,
        "bearish_url": bear_url,
        "sources": headlines
    }

# =========================
# 뉴스 수집 및 요약 (캐시 포함)
# =========================
def get_news_summary_cached(stock_name: str, rate: str) -> dict:
    """캐시를 활용한 뉴스 요약"""
    # 캐시 확인
    cached = news_cache.get(stock_name)
    if cached:
        return cached
    
    print(f"    🔍 새로운 뉴스 검색: {stock_name}", flush=True)
    
    # Google News에서 뉴스 수집
    headlines = fetch_google_news(stock_name)
    if headlines:
        print(f"    📰 {len(headlines)}개 뉴스 발견", flush=True)
    
    # GPT로 요약 또는 규칙 기반 요약
    result = summarize_news_with_gpt(stock_name, rate, headlines)
    
    # 캐시 저장
    news_cache.set(stock_name, result)
    
    return result

# =========================
# 토스 데이터 파싱
# =========================
def parse_toss_stocks(soup):
    """토스 페이지에서 급등주 데이터 추출"""
    stocks = []
    
    # 토스 랭킹 행 찾기
    rows = soup.select('tr[data-tossinvest-log="RankingListRow"]')
    
    if not rows:
        print("⚠️ 기본 셀렉터 실패, tbody tr 시도", flush=True)
        rows = soup.select('tbody tr')
    
    print(f"📊 {len(rows)}개 종목 발견", flush=True)
    
    for i, row in enumerate(rows[:10], 1):
        try:
            # 종목명 추출
            name = ""
            
            # 여러 셀렉터 시도
            name_selectors = [
                'span[class*="60z0ev1"]',
                'a[href*="/stocks/"]',
                'span[class*="stock-name"]',
                'td:nth-child(2) span'
            ]
            
            for selector in name_selectors:
                elem = row.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    # 숫자만 있거나 특수문자만 있는 경우 제외
                    if text and not text.isdigit() and not all(c in ',.%+-' for c in text):
                        name = text
                        break
            
            # 여전히 못 찾았으면 모든 span 검색
            if not name:
                for span in row.select('span'):
                    text = span.get_text(strip=True)
                    # 가격이나 퍼센트가 아닌 텍스트 찾기
                    if text and not any(x in text for x in ['%', '원', ',']) and len(text) > 1:
                        name = text
                        break
            
            # 가격과 등락률 추출
            price = "0원"
            rate = "+0.0%"
            
            # 숫자가 포함된 span들 찾기
            price_spans = row.select('span')
            for span in price_spans:
                text = span.get_text(strip=True)
                if '원' in text and price == "0원":
                    price = text
                elif '%' in text and rate == "+0.0%":
                    rate = text
            
            # 이름이 없으면 기본값
            if not name or len(name) < 2:
                name = f"종목{i}"
            
            # + 기호 없으면 추가
            if rate and not rate.startswith(('+', '-')):
                rate = '+' + rate
            
            print(f"  {i}. {name} - {price} ({rate})", flush=True)
            
            # 실제 뉴스 요약 가져오기 (캐시 활용)
            news_result = get_news_summary_cached(name, rate)
            
            stocks.append({
                "rank": i,
                "name": name,
                "price": price,
                "rate": rate,
                "summary": news_result["summary"],
                "bullish_url": news_result.get("bullish_url", ""),
                "bearish_url": news_result.get("bearish_url", ""),
                "sources": news_result.get("sources", [])
            })
            
            # 요약 출력
            for line in news_result["summary"].split('\n'):
                print(f"    {line}", flush=True)
            
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
            
            # JSON 파일로 저장
            with open('latest_stocks.json', 'w', encoding='utf-8') as f:
                json.dump(stocks, f, ensure_ascii=False, indent=2)
                print("💾 latest_stocks.json 저장 완료", flush=True)
            
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
# 테스트 데이터 생성
# =========================
def generate_test_data():
    """크롤링 실패 시 사용할 테스트 데이터"""
    print("\n📊 테스트 데이터 생성", flush=True)
    
    test_stocks = [
        {"name": "삼성전자", "base_rate": 25, "price": 87500},
        {"name": "SK하이닉스", "base_rate": 23, "price": 142300},
        {"name": "LG에너지솔루션", "base_rate": 21, "price": 425000},
        {"name": "삼성바이오로직스", "base_rate": 19, "price": 895000},
        {"name": "현대차", "base_rate": 17, "price": 245000},
        {"name": "POSCO홀딩스", "base_rate": 16, "price": 392500},
        {"name": "셀트리온", "base_rate": 15, "price": 178900},
        {"name": "카카오", "base_rate": 14, "price": 58900},
        {"name": "NAVER", "base_rate": 13, "price": 185200},
        {"name": "기아", "base_rate": 12, "price": 115200}
    ]
    
    # 시간대별로 다른 종목 선택
    hour = datetime.now().hour
    minute = datetime.now().minute
    seed = (hour * 60 + minute) // 10
    
    random.seed(seed)
    random.shuffle(test_stocks)
    selected = test_stocks[:10]
    selected.sort(key=lambda x: x['base_rate'], reverse=True)
    
    stocks = []
    for i, st in enumerate(selected, 1):
        rate_value = st['base_rate'] + random.uniform(-2, 2)
        rate = f"+{rate_value:.2f}%"
        price = f"{st['price']:,}원"
        
        print(f"  {i}. {st['name']} - {price} ({rate})", flush=True)
        
        # 실제 뉴스 요약 가져오기
        news_result = get_news_summary_cached(st["name"], rate)
        
        stocks.append({
            "rank": i,
            "name": st["name"],
            "price": price,
            "rate": rate,
            "summary": news_result["summary"],
            "bullish_url": news_result.get("bullish_url", ""),
            "bearish_url": news_result.get("bearish_url", ""),
            "sources": news_result.get("sources", [])
        })
        
        # 요약 출력
        for line in news_result["summary"].split('\n'):
            print(f"    {line}", flush=True)
    
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
    
    # Docker/Production 환경에서 자동 실행
    if len(sys.argv) > 1 or os.environ.get('DOCKER_ENV'):
        print("\n" + "="*60, flush=True)
        print("🚀 자동 모드 실행 (Docker/Production)", flush=True)
        print(f"시간: {datetime.now()}", flush=True)
        print("="*60, flush=True)
        
        # OpenAI API 키 확인
        if OPENAI_API_KEY:
            print(f"✅ OpenAI API 활성화 (모델: {OPENAI_MODEL})", flush=True)
        else:
            print("⚠️ OpenAI API 키 없음 - 규칙 기반 요약 사용", flush=True)
        
        # 캐시 정리
        news_cache.cleanup()
        
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
            
            # 결과 요약 출력
            print("\n" + "="*60, flush=True)
            print("📈 TOP 3 급등주:", flush=True)
            for stock in data[:3]:
                print(f"\n{stock['rank']}위: {stock['name']} ({stock['rate']})", flush=True)
                summary_lines = stock['summary'].split('\n')
                for line in summary_lines:
                    print(f"  {line}", flush=True)
                if stock.get('bullish_url'):
                    print(f"  ↗ 호재 링크: {stock['bullish_url'][:50]}...", flush=True)
                if stock.get('bearish_url'):
                    print(f"  ↗ 악재 링크: {stock['bearish_url'][:50]}...", flush=True)
        else:
            print("❌ 전송할 데이터 없음", flush=True)
        
        print("\n" + "="*60, flush=True)
        print("✅ 실행 완료", flush=True)
        print("="*60, flush=True)
        
    else:
        # 로컬 테스트 모드
        print("\n" + "="*60)
        print("📊 로컬 테스트 모드")
        print("="*60)
        
        print("\n1. 토스 크롤링 + 실제 뉴스")
        print("2. 테스트 데이터 + 실제 뉴스")
        print("3. 캐시 상태 확인")
        
        choice = input("\n선택 (1-3): ").strip() or "2"
        
        if choice == "1":
            data = crawl_toss()
            if data:
                print("\n✅ 크롤링 성공")
                send_to_api(data)
        elif choice == "2":
            data = generate_test_data()
            if data:
                print("\n✅ 테스트 데이터 생성")
                send_to_api(data)
        elif choice == "3":
            print(f"\n📦 캐시 상태: {len(news_cache.cache)}개 종목")
            for stock, (value, ts) in list(news_cache.cache.items())[:5]:
                age = datetime.now() - ts
                print(f"  - {stock}: {age.seconds//60}분 전 캐시됨")
        
        # 캐시 저장
        news_cache.save_cache()
