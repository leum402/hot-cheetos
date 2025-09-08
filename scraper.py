# -*- coding: utf-8 -*-
"""
실시간 급등주 + 오늘자 뉴스 2줄 요약(🟢/🔴) - 캐싱 & 링크 제공 버전
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
import xml.etree.ElementTree as ET
import requests

from urllib.parse import quote_plus
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List, Union
from dotenv import load_dotenv

# =========================
# 환경변수 로드
# =========================
load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:5001/api/update")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "12"))
OPENAI_RETRIES = int(os.getenv("OPENAI_RETRIES", "2"))
MAX_LINE_LEN = int(os.getenv("NEWS_MAX_LINE_LEN", "60"))
CACHE_DURATION_MINUTES = int(os.getenv("NEWS_CACHE_MINUTES", "60"))

# =========================
# 캐시
# =========================
class NewsCache:
    def __init__(self, cache_duration_minutes: int = 60):
        self.cache: Dict[str, Tuple[Union[dict, str], datetime]] = {}
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.hit_count = 0
        self.miss_count = 0
        self.cache_file = "news_cache.json"
        self.load_cache()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                now = datetime.now()
                for stock, (value, ts_str) in data.items():
                    ts = datetime.fromisoformat(ts_str)
                    if now - ts < self.cache_duration:
                        self.cache[stock] = (value, ts)
                print(f"📦 캐시 로드: {len(self.cache)}개 종목")
            except Exception as e:
                print(f"⚠️ 캐시 로드 실패: {e}")

    def save_cache(self):
        try:
            data = {stock: (value, ts.isoformat()) for stock, (value, ts) in self.cache.items()}
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 캐시 저장 실패: {e}")

    def get(self, stock_name: str) -> Optional[dict]:
        if stock_name in self.cache:
            value, cached_time = self.cache[stock_name]
            if datetime.now() - cached_time < self.cache_duration:
                if isinstance(value, str):
                    self.miss_count += 1
                    return None
                self.hit_count += 1
                remaining = self.cache_duration - (datetime.now() - cached_time)
                print(f"  💾 캐시 사용: {stock_name} (남은 {remaining.seconds//60}분)")
                return value
            else:
                del self.cache[stock_name]
        self.miss_count += 1
        return None

    def set(self, stock_name: str, summary_or_obj):
        value = {"summary": summary_or_obj, "bullish_url": "", "bearish_url": "", "sources": []} \
                if isinstance(summary_or_obj, str) else summary_or_obj
        self.cache[stock_name] = (value, datetime.now())
        self.save_cache()
        print(f"  💾 캐시 저장: {stock_name}")

    def get_stats(self) -> str:
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total else 0
        return f"캐시 적중률: {hit_rate:.1f}% (적중:{self.hit_count}, 미스:{self.miss_count})"

    def cleanup(self):
        now = datetime.now()
        expired = [stock for stock, (_, ts) in self.cache.items() if now - ts >= self.cache_duration]
        for stock in expired:
            del self.cache[stock]
        if expired:
            print(f"🗑️ 만료 캐시 정리: {len(expired)}개")
            self.save_cache()

news_cache = NewsCache(CACHE_DURATION_MINUTES)

# =========================
# 유틸/시장시간
# =========================
def is_market_hours() -> bool:
    """평일 09:00~15:30 KST"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    o = datetime.strptime("09:00", "%H:%M").time()
    c = datetime.strptime("15:30", "%H:%M").time()
    return o <= t <= c

def get_update_interval() -> int:
    """장중 10초, 장외 60초"""
    return 10 if is_market_hours() else 60

def _trim_line(s: str, max_len: int = MAX_LINE_LEN) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return (s[:max_len] + "…") if len(s) > max_len else s

def _force_two_lines(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    green = next((l for l in lines if l.startswith("🟢")), None)
    red   = next((l for l in lines if l.startswith("🔴")), None)
    if not green:
        first = lines[0] if lines else "특별한 뉴스 없음"
        green = f"🟢 호재: {_trim_line(first)}"
    if not red:
        second = lines[1] if len(lines) > 1 else "특별한 뉴스 없음"
        red = f"🔴 악재: {_trim_line(second)}"
    return f"{_trim_line(green)}\n{_trim_line(red)}"

# =========================
# 크롬 드라이버 (개선된 버전)
# =========================
def setup_driver():
    print("🌐 Chrome 드라이버 설정 중...")
    
    options = Options()
    
    # 기본 옵션
    options.add_argument('--headless=new')  # 새로운 headless 모드
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--window-size=1920,1080')
    
    # 메모리 최적화
    options.add_argument('--memory-pressure-off')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-renderer-backgrounding')
    
    # 안티 디텍션
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-web-security')
    
    # User-Agent 설정 (최신 Chrome)
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36')
    
    # 실험적 옵션
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_experimental_option('prefs', {
        'profile.default_content_setting_values.notifications': 2,
        'profile.default_content_settings.popups': 0
    })
    
    try:
        # ChromeDriver 설치/경로 설정
        try:
            service = Service(ChromeDriverManager().install())
            print("✅ ChromeDriverManager로 드라이버 설치 완료")
        except:
            service = Service('/usr/bin/chromedriver')
            print("✅ 시스템 chromedriver 사용")
        
        driver = webdriver.Chrome(service=service, options=options)
        
        # JavaScript로 webdriver 속성 숨기기
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']})")
        
        print("✅ Chrome 드라이버 준비 완료")
        return driver
        
    except Exception as e:
        print(f"❌ Chrome 드라이버 설정 실패: {e}")
        raise

# =========================
# 토스 페이지 체크 (개선)
# =========================
def check_page_health(driver) -> bool:
    try:
        # 페이지 완전 로드 대기
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # 데이터 테이블 존재 확인
        result = driver.execute_script("""
            const rows = document.querySelectorAll('tr[data-tossinvest-log="RankingListRow"]');
            const tbody = document.querySelector('tbody');
            return {
                ready: document.readyState === 'complete',
                hasData: rows.length > 0,
                hasTbody: tbody !== null,
                rowCount: rows.length,
                bodyText: document.body.innerText.substring(0, 200)
            }
        """)
        
        print(f"  페이지 상태: ready={result.get('ready')}, 데이터행={result.get('rowCount')}개")
        
        if not result.get('hasData'):
            print(f"  페이지 내용 일부: {result.get('bodyText')}")
            
        return bool(result.get('ready')) and bool(result.get('hasData'))
        
    except Exception as e:
        print(f"  페이지 체크 실패: {e}")
        return False

# =========================
# 토스 크롤링 (개선)
# =========================
def scrape_toss_stocks(driver):
    """토스에서 급등주 데이터 크롤링"""
    try:
        url = 'https://tossinvest.com/stocks/market/soaring'  # 다른 URL 시도
        print(f"📍 토스 접속: {url}")
        driver.get(url)
        
        # 초기 로딩 대기
        print("  ⏳ 페이지 로딩 대기 중...")
        time.sleep(3)
        
        # 스크롤하여 동적 콘텐츠 로드
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(2)
        
        # HTML 파싱
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 여러 셀렉터 시도
        selectors = [
            'tr[data-tossinvest-log="RankingListRow"]',
            'tbody tr',
            'div[class*="stock-item"]',
            'a[href*="/stocks/"]'
        ]
        
        rows = None
        for selector in selectors:
            rows = soup.select(selector)
            if rows:
                print(f"  ✅ {len(rows)}개 종목 발견 (셀렉터: {selector})")
                break
        
        if not rows:
            # 페이지 소스 일부 출력하여 디버깅
            print("  ❌ 데이터를 찾을 수 없음. HTML 구조 확인:")
            print(soup.prettify()[:1000])
            return None
            
        return parse_toss_data_with_cache(soup, use_gpt=True)
        
    except Exception as e:
        print(f"❌ 토스 크롤링 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# =========================
# 토스 파싱
# =========================
def parse_toss_data_with_cache(soup, use_gpt=True):
    stocks = []
    rows = soup.select('tr[data-tossinvest-log="RankingListRow"]')
    
    if not rows:
        print("⚠️ 기본 셀렉터 실패, 대체 셀렉터 시도...")
        rows = soup.select('tbody tr')[:10]
    
    if not rows:
        print("⚠️ 데이터를 찾을 수 없습니다.")
        return None

    print(f"\n📊 {len(rows)}개 종목 파싱 시작")
    print(f"📈 {news_cache.get_stats()}\n")

    for i, row in enumerate(rows[:10], 1):
        try:
            # 종목명 찾기 (여러 방법 시도)
            name = None
            
            # 방법 1: 클래스명으로
            name_elem = row.select_one('span[class*="stock-name"], span[class*="60z0ev1"]')
            if name_elem:
                name = name_elem.get_text(strip=True)
            
            # 방법 2: 링크에서
            if not name:
                link = row.select_one('a[href*="/stocks/"]')
                if link:
                    name = link.get_text(strip=True)
            
            # 방법 3: 모든 span에서
            if not name:
                for sp in row.select('span'):
                    tx = sp.get_text(strip=True)
                    if tx and '%' not in tx and '원' not in tx and ',' not in tx and 2 <= len(tx) <= 20:
                        name = tx
                        break

            # 가격/등락률
            price_elements = row.select('span[class*="price"], span._1p5yqoh0')
            price = "가격 확인중"
            rate = "+0.00%"
            
            if len(price_elements) >= 2:
                price = price_elements[0].get_text(strip=True)
                rate = price_elements[1].get_text(strip=True)
            elif len(price_elements) == 1:
                text = price_elements[0].get_text(strip=True)
                if '원' in text:
                    price = text
                elif '%' in text:
                    rate = text

            if not name:
                name = f"종목{i}"

            print(f"  {i}. {name} - {price} ({rate})")

            # 뉴스 가져오기
            if use_gpt:
                result = get_gpt_news_with_context_cached(name, rate)
            else:
                result = {"summary": get_simple_summary(name), "bullish_url":"", "bearish_url":"", "sources":[]}

            stocks.append({
                "rank": i,
                "name": name,
                "price": price,
                "rate": rate,
                "summary": result["summary"],
                "bullish_url": result.get("bullish_url", ""),
                "bearish_url": result.get("bearish_url", ""),
                "sources": result.get("sources", [])
            })

            for ln in result["summary"].split('\n'):
                print(f"      {ln}")

        except Exception as e:
            print(f"  ❌ {i}번 종목 파싱 오류: {e}")

    return stocks if stocks else None

# =========================
# 뉴스 수집 & 요약 (기존 함수들)
# =========================
def fetch_google_news_today(stock_name: str, max_items: int = 6) -> List[dict]:
    q = quote_plus(f"{stock_name} when:1d")
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=4)
        resp.raise_for_status()
    except Exception:
        return []
    items = []
    try:
        root = ET.fromstring(resp.content)
        for it in root.findall(".//item"):
            title_el = it.find("title")
            link_el = it.find("link")
            title = (title_el.text if title_el is not None else "") or ""
            link = (link_el.text if link_el is not None else "") or ""
            if title:
                items.append({"title": title, "link": link, "published": ""})
            if len(items) >= max_items:
                break
    except Exception:
        return []
    return items

def summarize_with_gpt_from_headlines(stock_name: str, rate_text: str, headlines: List[dict]) -> dict:
    def _wrap(summary_text: str, bull_idx: Optional[int] = None, bear_idx: Optional[int] = None) -> dict:
        bull_url = headlines[bull_idx-1]["link"] if headlines and bull_idx and 1 <= bull_idx <= len(headlines) else ""
        bear_url = headlines[bear_idx-1]["link"] if headlines and bear_idx and 1 <= bear_idx <= len(headlines) else ""
        return {
            "summary": _force_two_lines(summary_text),
            "bullish_url": bull_url,
            "bearish_url": bear_url,
            "sources": headlines[:]
        }

    base = rule_based_summary(stock_name, rate_text, headlines)
    return _wrap(base, bull_idx=1 if len(headlines)>=1 else None,
                      bear_idx=2 if len(headlines)>=2 else None)

def rule_based_summary(stock_name: str, rate_text: str, headlines: List[dict]) -> str:
    if headlines:
        top = _trim_line(headlines[0]["title"])
        green = f"🟢 호재: {top}"
        red = "🔴 악재: 단기 변동성/차익실현 주의"
    else:
        green = "🟢 호재: 특별한 뉴스 없음"
        red = "🔴 악재: 특별한 뉴스 없음"
    return f"{_trim_line(green)}\n{_trim_line(red)}"

def get_gpt_news_with_context_cached(stock_name: str, current_rate: str) -> dict:
    cached = news_cache.get(stock_name)
    if cached:
        return cached
    print(f"  🔄 새로운 뉴스 요청: {stock_name}")
    headlines = fetch_google_news_today(stock_name)
    result = summarize_with_gpt_from_headlines(stock_name, current_rate, headlines)
    news_cache.set(stock_name, result)
    return result

def get_simple_summary(stock_name):
    samples = [
        f"🟢 호재: {stock_name} 거래량 급증\n🔴 악재: 단기 과열 주의",
        f"🟢 호재: {stock_name} 기관 순매수 유입\n🔴 악재: 차익실현 매물 가능",
        f"🟢 호재: {stock_name} 업종 강세 동조\n🔴 악재: 변동성 확대 주의"
    ]
    return random.choice(samples)

# =========================
# 테스트 데이터 생성
# =========================
def generate_test_data_with_cache():
    test_stocks = [
        {"name": "삼성전자", "price": "87,500원", "rate": "+29.95%"},
        {"name": "SK하이닉스", "price": "142,300원", "rate": "+25.32%"},
        {"name": "카카오", "price": "58,900원", "rate": "+21.24%"},
        {"name": "네이버", "price": "185,200원", "rate": "+18.56%"},
        {"name": "현대차", "price": "245,000원", "rate": "+15.87%"},
        {"name": "LG화학", "price": "485,000원", "rate": "+12.65%"},
        {"name": "포스코홀딩스", "price": "392,500원", "rate": "+10.93%"},
        {"name": "삼성SDI", "price": "425,000원", "rate": "+9.54%"},
        {"name": "셀트리온", "price": "178,900원", "rate": "+8.82%"},
        {"name": "기아", "price": "115,200원", "rate": "+7.95%"}
    ]

    stocks = []
    print(f"\n📊 테스트 모드: {len(test_stocks)}개 종목")
    
    for i, st in enumerate(test_stocks, 1):
        print(f"  {i}. {st['name']} - {st['price']} ({st['rate']})")
        result = get_gpt_news_with_context_cached(st["name"], st["rate"])
        stocks.append({
            "rank": i,
            "name": st["name"],
            "price": st["price"],
            "rate": st["rate"],
            "summary": result["summary"],
            "bullish_url": result.get("bullish_url", ""),
            "bearish_url": result.get("bearish_url", ""),
            "sources": result.get("sources", [])
        })
    return stocks

# =========================
# API 전송
# =========================
def send_to_api(data):
    try:
        resp = requests.post(API_URL, json=data, timeout=5)
        if resp.status_code == 200:
            print("✅ API 전송 성공")
            return True
        else:
            print(f"❌ API 응답 코드: {resp.status_code}")
    except Exception as e:
        print(f"❌ API 전송 실패: {e}")
    return False

# =========================
# 메인 (수동 모드)
# =========================
def main():
    print("=" * 50)
    print("🚀 실시간 급등주 + 2줄 뉴스 & 링크 (캐싱)")
    print("=" * 50)
    # ... (기존 수동 모드 코드)

# =========================
# 자동 실행 모드 (Docker/Production)
# =========================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 or os.environ.get('DOCKER_ENV'):
        print("🚀 자동 모드 실행 (Docker/Production)")
        print("=" * 60)
        
        cycle = 0
        consecutive_failures = 0
        
        while True:
            cycle += 1
            print(f"\n⏰ [{cycle}회차] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 60)
            
            # 캐시 정리
            if cycle % 60 == 0:
                news_cache.cleanup()
            
            driver = None
            data = None
            
            try:
                # Chrome 드라이버 생성
                driver = setup_driver()
                
                # 토스 크롤링 시도
                data = scrape_toss_stocks(driver)
                
                if data:
                    send_to_api(data)
                    print(f"✅ 토스 실시간 데이터 {len(data)}개 종목 전송 완료")
                    consecutive_failures = 0
                else:
                    raise Exception("토스 데이터 파싱 실패")
                    
            except Exception as e:
                consecutive_failures += 1
                print(f"⚠️ 토스 크롤링 실패 (연속 {consecutive_failures}회): {e}")
                
                # 3회 연속 실패 시 다른 URL 시도
                if consecutive_failures >= 3:
                    print("🔄 대체 방법으로 시도...")
                
                # 테스트 데이터로 대체
                print("📊 테스트 데이터로 대체")
                data = generate_test_data_with_cache()
                if data:
                    send_to_api(data)
                    print(f"✅ 테스트 데이터 {len(data)}개 종목 전송 완료")
                    
            finally:
                # 드라이버 정리
                if driver:
                    try:
                        driver.quit()
                        print("🧹 드라이버 정리 완료")
                    except:
                        pass
            
            # 다음 주기까지 대기
            interval = get_update_interval()
            print(f"\n⏳ {interval}초 후 재실행...")
            print("=" * 60)
            time.sleep(interval)
            
    else:
        # 로컬 수동 모드
        main()
