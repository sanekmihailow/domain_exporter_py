FROM python:3.12-alpine

# Don't buffer stdout/stderr (logs show up immediately) and don't write .pyc.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY *.py ./

# Run as a non-root user.
RUN adduser -D -u 10001 appuser
USER appuser

EXPOSE 9223

CMD ["python", "main.py"]
