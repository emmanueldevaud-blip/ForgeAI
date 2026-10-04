FROM python:3.11-slim

# Entrée passwd pour l'UID exécutant l'app (docker-compose `user:`) :
# ssh refuse de démarrer sans utilisateur correspondant à l'UID courant.
RUN useradd --uid 1000 --create-home --shell /bin/bash edevaud

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    git \
    openssh-client \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--lifespan", "on"]