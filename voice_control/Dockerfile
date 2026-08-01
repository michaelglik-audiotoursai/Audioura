FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build-time manifest: record checksums of all Python sources + git SHA
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
RUN python build_manifest.py /app /app/.build_manifest.json

EXPOSE 5008

CMD ["python", "app.py"]
