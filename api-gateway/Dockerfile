FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask requests pyyaml
COPY main.py gateway_routes.yaml gateway_routes.subscribed.yaml /app/
EXPOSE 8080
CMD ["python", "main.py"]
