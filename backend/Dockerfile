FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m dfis && mkdir /data && chown dfis /data
USER dfis
EXPOSE 8000
CMD ["sh", "-c", "python -m scripts.init_db --admin-user ${DFIS_ADMIN_USER:-admin} && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
