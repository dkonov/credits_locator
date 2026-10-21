FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY locator.py extract_credits.py structure_credits.py credits_v05_import.py .
ENTRYPOINT ["python", "/app/locator.py"]
