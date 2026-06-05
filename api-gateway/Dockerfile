FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask requests
COPY main.py /app/
EXPOSE 8080
CMD ["python", "main.py"]
