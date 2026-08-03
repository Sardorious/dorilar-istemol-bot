FROM python:3.12-slim

WORKDIR /app

# Konteyner vaqt zonasi — APScheduler bilan mos bo'lishi shart
ENV TZ=Asia/Tashkent
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc tzdata && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "app.main"]
