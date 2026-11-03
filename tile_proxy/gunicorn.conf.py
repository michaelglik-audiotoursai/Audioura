# [LOCAL-854] gunicorn config for the tile proxy.
#
# Cloud Run gives one container 256Mi and routes concurrent requests to a single
# instance, so we use a SMALL number of worker PROCESSES with several THREADS
# each. Threads suit this workload: each request is I/O-bound (a GCS read and,
# on a miss, an origin HTTP GET). The per-instance origin-fetch concurrency cap
# (TILE_MAX_CONCURRENT_ORIGIN, default 4) is enforced in app.py with a
# process-local semaphore, so keep workers low to keep that cap meaningful.
import os

bind = "0.0.0.0:{}".format(os.environ.get("PORT", "8080"))
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("WEB_THREADS", "8"))
worker_class = "gthread"
timeout = int(os.environ.get("WEB_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5
accesslog = "-"   # stdout, so Cloud Run captures it
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
