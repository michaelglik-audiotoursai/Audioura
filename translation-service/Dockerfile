FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
# [LOCAL-578] cost_meter.py added so the translation service can write cost_ledger
# rows (translation_generate + per-stop tts_generate). The COPY list is explicit —
# a module missing from it is absent in the image and import fails at runtime
# (this trap bit twice this week), so new runtime deps MUST be added here.
COPY translation_service.py blobstorage.py build_manifest.py cost_rates.py cost_meter.py ./

# Build-time manifest: record checksums of all Python sources + git SHA
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
RUN python build_manifest.py /app /app/.build_manifest.json

EXPOSE 5030

CMD ["python", "translation_service.py"]
