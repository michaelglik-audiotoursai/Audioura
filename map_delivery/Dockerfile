FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# [LOCAL-824] COPY . . below bundles serper_meter.py (vendored into this dir, an
# identical copy of the repo-root module, like safe_headers.py / failure_log.py).
# app.py's /geocode (LOCAL-793) imports it for the metered Serper Places door;
# this build context is ./map_delivery, so a repo-root-only module would NOT be in
# the image and /geocode would silently lose its paid path. No new pip dependency:
# serper_meter uses stdlib urllib, and the Nominatim fallback does too.
COPY . .

# Build-time manifest: record checksums of all Python sources + git SHA
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
RUN python build_manifest.py /app /app/.build_manifest.json

EXPOSE 5005

CMD ["python", "app.py"]
