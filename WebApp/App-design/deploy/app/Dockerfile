FROM python:3.10-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
# Mã nguồn trợ lý pháp luật (builder/, solver/, schema/ ...) đặt cạnh Dockerfile này
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
HEALTHCHECK CMD curl -fs http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
