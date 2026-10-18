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
# [LOCAL-708B / D670] Per-plan article length + the plan-aware truncation notice
# (names the plans, page lengths, "See plans") for TRANSLATED articles. These two
# modules live at the repo root; a copy is kept here (same convention as
# cost_meter.py) because this service's build context is ./translation-service.
COPY article_truncation.py subscription_levels.py ./
# [LOCAL-711 / D673] The translation path translates a source tour's short_title
# the same way it translates tour_name. Self-contained (no llm_models import); a
# copy lives in ./translation-service because this service's build context is
# ./translation-service (same convention as cost_meter.py above).
COPY tour_short_title.py ./

# Build-time manifest: record checksums of all Python sources + git SHA
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
RUN python build_manifest.py /app /app/.build_manifest.json

EXPOSE 5030

CMD ["python", "translation_service.py"]
