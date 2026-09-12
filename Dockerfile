FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -m playwright install --with-deps chromium
COPY . .
RUN useradd --uid 10001 --create-home monitor && mkdir -p data && chown -R monitor:monitor /app
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN PLAYWRIGHT_BROWSERS_PATH=/opt/browsers python -m playwright install chromium && chmod -R a+rX /opt/browsers
USER monitor
CMD ["python", "main.py"]
