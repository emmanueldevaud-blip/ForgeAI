#!/bin/bash

set -e

echo "================================"
echo "     DEPLOIEMENT FORGEAI"
echo "================================"

ssh vps-7e13a64a.vps.ovh.net '
    set -e

    cd /var/www/forgeai

    COMPOSE_BACKUP="/tmp/forgeai-production-docker-compose.yml"
    cp docker-compose.yml "$COMPOSE_BACKUP"
    restore_compose() {
        if [ -f "$COMPOSE_BACKUP" ]; then
            cp "$COMPOSE_BACKUP" docker-compose.yml
            rm -f "$COMPOSE_BACKUP"
        fi
    }
    trap restore_compose EXIT

    echo ""
    echo "=== Git pull ==="
    git restore docker-compose.yml
    git pull
    restore_compose
    trap - EXIT

    echo ""
    echo "=== Migrations Alembic ==="
    docker compose run --rm app alembic upgrade head

    echo ""
    echo "=== Docker Compose ==="
    docker compose up -d --build

    echo ""
    echo "=== Etat des conteneurs ==="
    docker compose ps

    echo ""
    echo "=== Derniers logs APP ==="
    docker compose logs --tail=50 app

    echo ""
    echo "=== DEPLOIEMENT TERMINE ==="
'
