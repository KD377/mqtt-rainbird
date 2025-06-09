FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       git \
    && pip install --no-cache-dir --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir \
    git+https://github.com/allenporter/pyrainbird.git@main#egg=pyrainbird

COPY ./mqtt_client.py ./main.py

CMD ["python", "main.py"]