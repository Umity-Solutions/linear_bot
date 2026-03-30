FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PORT=8000
CMD gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --timeout 120
