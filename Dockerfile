FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install Python dependencies
COPY reqs.txt ./
RUN pip install -r reqs.txt

# Copy application code
COPY bot.py ./
COPY creds.json ./
COPY data ./data

CMD ["python", "-u", "bot.py"]


