# [LOCAL-854] tile_proxy image. Its own small build context (this directory).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install deps first so the layer caches across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py gunicorn.conf.py ./

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# gunicorn serves the module-level `app` in app.py, using gunicorn.conf.py.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
