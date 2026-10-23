#!/bin/bash
set -euo pipefail

# Configuration
VPS_HOST="forgeai-vps"
VPS_DB="forgeai"
VPS_ROOT_PWD="root_password_change_me"
LOCAL_DB="forgeai"
LOCAL_ROOT_PWD="root_password_change_me"
LOCAL_CONTAINER="forgeai-mysql"
LOG_FILE="/home/edevaud/forgeai/data/sync-vps-to-local.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Début sync VPS → Local ==="

# 1. Dump VPS (stream via SSH)
log "Dump VPS en cours..."
ssh "$VPS_HOST" "docker exec forgeai-mysql mysqldump \
  -uroot -p$VPS_ROOT_PWD \
  --single-transaction --routines --triggers --events \
  --set-gtid-purged=OFF $VPS_DB" 2>/tmp/vps_dump_err.log \
  | gzip > /tmp/vps_dump_latest.sql.gz

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERREUR dump VPS:"
    cat /tmp/vps_dump_err.log | tee -a "$LOG_FILE"
    exit 1
fi

DUMP_SIZE=$(du -h /tmp/vps_dump_latest.sql.gz | cut -f1)
log "Dump reçu: $DUMP_SIZE"

# 2. Import local (drop + recreate DB pour éviter conflits)
log "Import local en cours..."
docker exec -i "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" -e "
  DROP DATABASE IF EXISTS $LOCAL_DB;
  CREATE DATABASE $LOCAL_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
" 2>&1 | grep -v Warning | tee -a "$LOG_FILE"

gunzip -c /tmp/vps_dump_latest.sql.gz | docker exec -i "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" "$LOCAL_DB" 2>&1 | grep -v Warning | tee -a "$LOG_FILE"

if [ ${PIPESTATUS[1]} -ne 0 ]; then
    log "ERREUR import local"
    exit 1
fi

# 3. Vérification rapide
COUNT=$(docker exec "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" "$LOCAL_DB" -N -e "SELECT COUNT(*) FROM intendance_expenses;" 2>/dev/null | grep -v Warning)
log "Vérification: intendance_expenses = $COUNT lignes"

# 4. Nettoyage
rm -f /tmp/vps_dump_latest.sql.gz /tmp/vps_dump_err.log

log "=== Sync terminée avec succès ==="