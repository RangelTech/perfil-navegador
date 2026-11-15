# Chromium e dependências já vêm na imagem oficial do Playwright (mesma versão do pacote Python).
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
RUN useradd --system --uid 10001 --create-home app && mkdir /data && chown 10001:10001 /data
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ARG GIT_COMMIT=dev
ENV GIT_COMMIT=${GIT_COMMIT} PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PN_DADOS=/data PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
