FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Build-time manifest: record checksums of all Python sources + git SHA
ARG GIT_SHA=unknown
RUN echo "${GIT_SHA}" > /app/.git_sha
RUN python build_manifest.py /app /app/.build_manifest.json

EXPOSE 5001

CMD ["python", "app.py"]
