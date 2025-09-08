FROM python:3.9-slim

# Chrome 및 필요 패키지 설치
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements 먼저 복사 (캐싱 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 나머지 파일 복사
COPY . .

# 환경변수 설정
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/lib/chromium/

# PORT는 DigitalOcean이 자동으로 설정함
EXPOSE 8080

CMD ["python", "run.py"]
