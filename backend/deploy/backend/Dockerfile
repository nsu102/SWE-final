FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HOME=/app/cache
WORKDIR /app
COPY requirements-backend.txt requirements-ml.txt requirements-aws.txt ./
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements-backend.txt -r requirements-ml.txt -r requirements-aws.txt
COPY src/backend src/backend
COPY src/common src/common
COPY src/jobs src/jobs
RUN useradd --uid 10001 --create-home api && mkdir -p /app/cache /app/storage && chown -R api:api /app/cache /app/storage
USER api
CMD ["uvicorn", "src.backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--forwarded-allow-ips", "*", "--limit-concurrency", "8"]
