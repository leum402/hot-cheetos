FROM python:3.10-slim

# Chrome 및 ChromeDriver 설치
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F'.' '{print $1}') \
    && wget -q https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION} -O /tmp/chromedriver_version \
    && DRIVER_VERSION=$(cat /tmp/chromedriver_version) \
    && wget -q https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip -O /tmp/chromedriver.zip \
    && unzip -q /tmp/chromedriver.zip -d /usr/bin/ \
    && chmod +x /usr/bin/chromedriver \
    && rm /tmp/chromedriver.zip /tmp/chromedriver_version \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/lib/chromium/
EXPOSE 8080
CMD ["python", "app.py"]
