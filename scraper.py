# -*- coding: utf-8 -*-
"""
실시간 급등주 + 오늘자 뉴스 2줄 요약(🟢/🔴) - 캐싱 & 링크 제공 버전
- Google News RSS(24h) 헤드라인 → GPT가 호재/악재와 근거 인덱스 반환 → 링크 매핑
- 동일 종목: 1시간 캐시 (news_cache.json)
- 캐시에 과거 문자열 포맷 있으면 MISS 처리하여 링크 붙게 재생성
- API로 bullish_url/bearish_url/sources 포함
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
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
from typing import Dict, Optional, Tuple, List
from dotenv import load_dotenv

# =========================
# 환경변수 로드
# =========================
load_dotenv()

API_URL = os.getenv("API_URL", "http://127.0.0.1:5001/api/update")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # .env에서 조절 가능
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "12"))
OPENAI_RETRIES = int(os.getenv("OPENAI_RETRIES", "2"))
MAX_LINE_LEN = int(os.getenv("NEWS_MAX_LINE_LEN", "60"))
CACHE_DURATION_MINUTES = int(os.getenv("NEWS_CACHE_MINUTES", "60"))

# =========================
# 캐시
# =========================
class NewsCache:
    """
    value(dict) 스키마:
    {
      "summary": "🟢 ...\n🔴 ...",
      "bullish_url": str,
      "bearish_url": str,
      "sources": [{"title":..., "link":..., "published":...}, ...]
    }
    """
    def __init__(self, cache_duration_minutes: int = 60):
        self.cache: Dict[str, Tuple[dict|str, datetime]] = {}
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
        """문자열 포맷(옛 캐시)은 MISS로 처리 → 링크 붙도록 재요약 유도"""
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
# 토스 페이지 상태 체크
# =========================
def check_page_health(driver) -> bool:
    try:
        result = driver.execute_script("""
            return {
                ready: document.readyState === 'complete',
                hasData: document.querySelectorAll('tr[data-tossinvest-log="RankingListRow"]').length > 0
            }
        """)
        return bool(result.get('ready')) and bool(result.get('hasData'))
    except Exception:
        return False

# =========================
# 뉴스 수집 (Google News RSS)
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
    items: List[dict] = []
    try:
        root = ET.fromstring(resp.content)
        for it in root.findall(".//item"):
            title_el = it.find("title")
            link_el  = it.find("link")
            pub_el   = it.find("{http://purl.org/dc/elements/1.1/}date") or it.find("pubDate")
            title = (title_el.text if title_el is not None else "") or ""
            link  = (link_el.text  if link_el  is not None else "") or ""
            pub   = (pub_el.text   if pub_el   is not None else "") or ""
            title, link, pub = title.strip(), link.strip(), pub.strip()
            if any(k in title for k in ["루머", "추정", "소문", "전망만", "예상만"]):
                continue
            if title:
                items.append({"title": title, "link": link, "published": pub})
            if len(items) >= max_items:
                break
    except Exception:
        return []
    return items

def format_headlines_for_prompt(headlines: List[dict]) -> str:
    if not headlines:
        return "헤드라인 없음"
    return "\n".join(f"{i}. {h.get('title','')} ({h.get('link','')})" for i, h in enumerate(headlines, 1))

# =========================
# 요약(GPT or 규칙) → 링크 매핑
# =========================
def summarize_with_gpt_from_headlines(stock_name: str, rate_text: str, headlines: List[dict]) -> dict:
    """
    반환:
    {
      "summary": "🟢 ...\n🔴 ...",
      "bullish_url": str,
      "bearish_url": str,
      "sources": [ {title,link,published}, ... ]
    }
    """
    def _wrap(summary_text: str, bull_idx: int|None = None, bear_idx: int|None = None) -> dict:
        bull_url = headlines[bull_idx-1]["link"] if headlines and bull_idx and 1 <= bull_idx <= len(headlines) else ""
        bear_url = headlines[bear_idx-1]["link"] if headlines and bear_idx and 1 <= bear_idx <= len(headlines) else ""
        return {
            "summary": _force_two_lines(summary_text),
            "bullish_url": bull_url,
            "bearish_url": bear_url,
            "sources": headlines[:]
        }

    # 규칙기반(키 없으면)
    if not OPENAI_API_KEY:
        base = rule_based_summary(stock_name, rate_text, headlines)
        # 기본값: 호재=1번, 악재=2번(없으면 1번)
        return _wrap(base, bull_idx=1 if len(headlines)>=1 else None,
                          bear_idx=2 if len(headlines)>=2 else (1 if len(headlines)>=1 else None))

    # OpenAI SDK
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        base = rule_based_summary(stock_name, rate_text, headlines)
        return _wrap(base, bull_idx=1 if len(headlines)>=1 else None,
                          bear_idx=2 if len(headlines)>=2 else (1 if len(headlines)>=1 else None))

    system = (
        "너는 한국 주식 뉴스 요약 도우미다. 반드시 '오늘/최근 24시간' 실제 기사 제목만 근거로 한다. "
        "출력은 정확히 두 줄(🟢/🔴), 각 한 문장, 60자 이내."
    )
    user = (
        f"종목: {stock_name}\n등락률: {rate_text}\n"
        f"오늘자 헤드라인(번호 부여됨):\n{format_headlines_for_prompt(headlines)}\n\n"
        "아래 JSON만 출력하라(텍스트 설명 금지):\n"
        "{\n"
        '  "bullish": "호재 한 문장",\n'
        '  "bearish": "악재 한 문장",\n'
        '  "bullish_idx": 1,\n'
        '  "bearish_idx": 2\n'
        "}\n"
        "인덱스는 위 헤드라인 번호(1부터). 근거가 없으면 해당 *_idx는 생략."
    )

    last_err = None
    for attempt in range(OPENAI_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                max_tokens=160,
                timeout=OPENAI_TIMEOUT,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            out = (resp.choices[0].message.content or "").strip()
            # 코드블록 제거
            if out.startswith("```"):
                out = out.strip("`").strip()
                if out.startswith("json"):
                    out = out[4:].strip()
            try:
                data = json.loads(out)
            except Exception:
                # JSON 실패 → 텍스트 2줄 강제 + 기본 인덱스
                return _wrap(out,
                             bull_idx=1 if len(headlines)>=1 else None,
                             bear_idx=2 if len(headlines)>=2 else (1 if len(headlines)>=1 else None))

            green = _trim_line(f"🟢 호재: {data.get('bullish','특별한 뉴스 없음')}")
            red   = _trim_line(f"🔴 악재: {data.get('bearish','특별한 뉴스 없음')}")
            bull_idx = data.get("bullish_idx") or (1 if len(headlines)>=1 else None)
            bear_idx = data.get("bearish_idx") or (2 if len(headlines)>=2 else (bull_idx if bull_idx else None))
            return _wrap(f"{green}\n{red}", bull_idx=bull_idx, bear_idx=bear_idx)

        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))

    base = rule_based_summary(stock_name, rate_text, headlines)
    return _wrap(base, bull_idx=1 if len(headlines)>=1 else None,
                      bear_idx=2 if len(headlines)>=2 else (1 if len(headlines)>=1 else None))

def rule_based_summary(stock_name: str, rate_text: str, headlines: List[dict]) -> str:
    if headlines:
        top = _trim_line(headlines[0]["title"])
        green = f"🟢 호재: {top}"
        red = "🔴 악재: 단기 변동성/차익실현 주의"
    else:
        green = "🟢 호재: 특별한 뉴스 없음"
        red = "🔴 악재: 특별한 뉴스 없음"
    return f"{_trim_line(green)}\n{_trim_line(red)}"

# =========================
# GPT 호출(캐시 사용)
# =========================
def get_gpt_news_with_context_cached(stock_name: str, current_rate: str) -> dict:
    cached = news_cache.get(stock_name)
    if cached:
        return cached
    print(f"  🔄 새로운 뉴스 요청: {stock_name}")
    headlines = fetch_google_news_today(stock_name)
    result = summarize_with_gpt_from_headlines(stock_name, current_rate, headlines)
    news_cache.set(stock_name, result)
    return result

# =========================
# 크롬 드라이버
# =========================
def setup_driver():
    options = Options()
    options.add_argument('--headless')  # ← 주석 해제 필수!
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    # Docker 환경을 위한 추가 옵션
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # ChromeDriver 경로 자동 설정
    try:
        service = Service(ChromeDriverManager().install())
    except:
        # Docker 환경에서 실패 시 직접 경로 지정
        service = Service('/usr/bin/chromedriver')
    
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# =========================
# 토스 파싱
# =========================
def parse_toss_data_with_cache(soup, use_gpt=True):
    stocks = []
    rows = soup.select('tr[data-tossinvest-log="RankingListRow"]')
    if not rows:
        print("⚠️ 데이터를 찾을 수 없습니다.")
        rows = soup.select('tbody tr')[:10]

    print(f"\n📊 {len(rows)}개 종목 발견.")
    print(f"📈 {news_cache.get_stats()}\n")

    for i, row in enumerate(rows[:10], 1):
        try:
            # 종목명
            name = None
            tag = row.select_one('span[class*="60z0ev1"]')
            if tag: name = tag.get_text(strip=True)
            if not name:
                for sp in row.select('span'):
                    tx = sp.get_text(strip=True)
                    if tx and '%' not in tx and '원' not in tx and ',' not in tx and 2 <= len(tx) <= 20:
                        name = tx; break

            # 가격/등락률
            price_spans = row.select('span._1p5yqoh0')
            if not name: name = f"종목{i}"
            price = "가격 확인중"; rate = "+0.00%"
            if len(price_spans) >= 2:
                price = price_spans[0].get_text(strip=True)
                rate  = price_spans[1].get_text(strip=True)
            elif len(price_spans) == 1:
                price = price_spans[0].get_text(strip=True)

            print(f"  {i}. {name} - {price} ({rate})")

            # 뉴스(캐시)
            if use_gpt:
                result = get_gpt_news_with_context_cached(name, rate)
            else:
                cached = news_cache.get(name)
                if cached: result = cached
                else:
                    result = {"summary": get_simple_summary(name), "bullish_url":"", "bearish_url":"", "sources":[]}
                    news_cache.set(name, result)

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
            if result.get("bullish_url"): print(f"      ↗ 호재 링크: {result['bullish_url']}")
            if result.get("bearish_url"): print(f"      ↗ 악재 링크: {result['bearish_url']}")
            print()

        except Exception as e:
            print(f"  ❌ {i}번 종목 오류: {e}")
            stocks.append({
                "rank": i,
                "name": f"종목{i}",
                "price": "확인중",
                "rate": "+0.00%",
                "summary": get_simple_summary(f"종목{i}"),
                "bullish_url": "",
                "bearish_url": "",
                "sources": []
            })

    return stocks

# =========================
# 테스트 데이터
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
    print(f"📈 {news_cache.get_stats()}\n")

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
        for ln in result["summary"].split('\n'):
            print(f"      {ln}")
        if result.get("bullish_url"): print(f"      ↗ 호재 링크: {result['bullish_url']}")
        if result.get("bearish_url"): print(f"      ↗ 악재 링크: {result['bearish_url']}")
        print()

    return stocks

# =========================
# 단순 요약(비상)
# =========================
def get_simple_summary(stock_name):
    samples = [
        f"🟢 호재: {stock_name} 거래량 급증\n🔴 악재: 단기 과열 주의",
        f"🟢 호재: {stock_name} 기관 순매수 유입\n🔴 악재: 차익실현 매물 가능",
        f"🟢 호재: {stock_name} 업종 강세 동조\n🔴 악재: 변동성 확대 주의"
    ]
    return random.choice(samples)

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
# 메인
# =========================
def main():
    print("=" * 50)
    print("🚀 실시간 급등주 + 2줄 뉴스 & 링크 (캐싱)")
    print(f"⏰ 캐시 유지: {CACHE_DURATION_MINUTES}분")
    print("=" * 50)

    if OPENAI_API_KEY:
        print(f"✅ OpenAI API 키 확인됨: {OPENAI_API_KEY[:10]}…  (모델: {OPENAI_MODEL})")
    else:
        print("⚠️ OpenAI API 키 없음 → 규칙기반 요약 사용")

    print("\n모드 선택:")
    print("1. 토스 + GPT(또는 규칙) 뉴스 (캐싱)")
    print("2. 테스트 데이터 + GPT(또는 규칙) 뉴스 (캐싱)")
    print("3. 토스 + 백업/단순 뉴스 (캐싱)")
    print("4. 빠른 테스트 (5개 종목)")

    mode = input("\n선택 (1-4): ").strip() or "2"
    use_toss = mode in ["1", "3"]
    use_gpt  = mode in ["1", "2", "4"]
    quick    = mode == "4"

    driver = None
    if use_toss:
        driver = setup_driver()

    try:
        if quick:
            print("\n🧪 빠른 테스트 (상위 5개)")
            data = generate_test_data_with_cache()[:5]
            print("\n" + "="*50)
            print("📈 테스트 결과:")
            for s in data:
                print(f"\n{s['rank']}. {s['name']} ({s['rate']})")
                for ln in s['summary'].split('\n'):
                    print(f"   {ln}")
                if s.get("bullish_url"): print(f"   ↗ 호재 링크: {s['bullish_url']}")
                if s.get("bearish_url"): print(f"   ↗ 악재 링크: {s['bearish_url']}")
            with open('test_news.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                print("\n💾 test_news.json 저장 완료")
            return

        cycle = 0
        error_count = 0

        if use_toss:
            url = 'https://www.tossinvest.com/?live-chart=heavy_soar'
            print(f"📍 최초 접속: {url}")
            driver.get(url); time.sleep(5)
            print("✅ 페이지 로드 완료\n")

        while True:
            cycle += 1
            print(f"\n⏰ [{cycle}회차] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            if cycle % 60 == 0:
                news_cache.cleanup()

            if use_toss:
                if not check_page_health(driver):
                    error_count += 1
                    print(f"⚠️ 페이지 상태 이상 ({error_count}회)")
                    if error_count >= 3:
                        print("🔄 새로고침"); driver.refresh(); time.sleep(5); error_count = 0
                else:
                    error_count = 0
                    print("📡 실시간 DOM 읽기")

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                if mode == "3":
                    # 강제 백업/단순
                    rows = soup.select('tr[data-tossinvest-log="RankingListRow"]') or soup.select('tbody tr')[:10]
                    data = []
                    for i, row in enumerate(rows[:10], 1):
                        name = None
                        tag = row.select_one('span[class*="60z0ev1"]')
                        if tag: name = tag.get_text(strip=True)
                        if not name:
                            for sp in row.select('span'):
                                tx = sp.get_text(strip=True)
                                if tx and '%' not in tx and '원' not in tx and ',' not in tx and 2 <= len(tx) <= 20:
                                    name = tx; break
                        if not name: name = f"종목{i}"
                        cached = news_cache.get(name)
                        if cached: res = cached
                        else:
                            res = {"summary": get_simple_summary(name), "bullish_url":"", "bearish_url":"", "sources":[]}
                            news_cache.set(name, res)
                        data.append({
                            "rank": i, "name": name, "price": "확인중", "rate": "+0.00%",
                            "summary": res["summary"],
                            "bullish_url": res.get("bullish_url",""),
                            "bearish_url": res.get("bearish_url",""),
                            "sources": res.get("sources", [])
                        })
                else:
                    data = parse_toss_data_with_cache(soup, use_gpt=True)
                if not data:
                    print("⚠️ 데이터 없음 → 테스트로 대체")
                    data = generate_test_data_with_cache()
            else:
                data = generate_test_data_with_cache()

            if data:
                send_to_api(data)
                with open('latest_stocks.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    print("💾 latest_stocks.json 저장 완료")

                print("\n" + "="*50)
                print("📈 TOP 3:")
                for s in data[:3]:
                    print(f"\n{s['rank']}. {s['name']} ({s['rate']})")
                    print(f"   {s['summary'].splitlines()[0]}")
                    if s.get("bullish_url"): print(f"   ↗ 호재 링크: {s['bullish_url']}")

                print(f"\n📊 {news_cache.get_stats()}")
                print(f"📈 시장 상태: {'🔴 장중' if is_market_hours() else '⚫ 장외'}")

            interval = get_update_interval()
            print(f"\n⏳ {interval}초 후 재수집…")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n🛑 종료")
        print(f"📊 최종 {news_cache.get_stats()}")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback; traceback.print_exc()
    finally:
        if driver:
            driver.quit()
        news_cache.save_cache()

# scraper.py의 main() 함수 끝부분 수정
if __name__ == "__main__":
    # Docker/Production 환경에서는 자동으로 모드 선택
    import sys
    
    if len(sys.argv) > 1 or os.environ.get('DOCKER_ENV'):
        # Docker 환경이거나 인자가 있으면 자동 실행
        print("🚀 자동 모드: 토스 크롤링 시도, 실패시 테스트 데이터")
        
        driver = None
        try:
            driver = setup_driver()
            url = 'https://www.tossinvest.com/?live-chart=heavy_soar'
            print(f"📍 토스 접속 시도: {url}")
            driver.get(url)
            time.sleep(5)
            
            # 페이지 체크
            if check_page_health(driver):
                print("✅ 토스 페이지 정상 로드")
                # 실제 크롤링 코드...
            else:
                raise Exception("토스 페이지 로드 실패")
                
        except Exception as e:
            print(f"⚠️ 토스 크롤링 실패: {e}")
            print("📊 테스트 데이터로 대체")
            if driver:
                driver.quit()
            # 테스트 데이터 생성
            data = generate_test_data_with_cache()
            send_to_api(data)
    else:
        # 로컬에서는 기존 메뉴 방식
        main()
