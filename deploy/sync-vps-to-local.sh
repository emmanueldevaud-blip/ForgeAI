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
LOCK_FILE="/tmp/forgeai-sync-vps-to-local.lock"
DUMP_FILE="/tmp/vps_dump_latest.sql.gz"
STAMP="$(date +%Y%m%d_%H%M%S)"
STAGING_DB="${LOCAL_DB}_sync_${STAMP}"
IMPORT_LOG="/home/edevaud/forgeai/data/${STAGING_DB}.import.log"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Synchronisation déjà en cours, abandon." >&2
    exit 0
fi

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cleanup_on_exit() {
    status=$?
    rm -f "$DUMP_FILE" /tmp/vps_dump_err.log
    if [ "$status" -eq 0 ]; then
        rm -f "$IMPORT_LOG"
    else
        log "Échec de synchronisation (code $status). Base temporaire conservée: $STAGING_DB"
        log "Journal d'import conservé: $IMPORT_LOG"
    fi
    exit "$status"
}
trap cleanup_on_exit EXIT

log "=== Début sync VPS → Local ==="

if ! docker exec "$LOCAL_CONTAINER" mysqladmin --protocol=socket -uroot -p"$LOCAL_ROOT_PWD" ping --silent >/dev/null 2>&1; then
    log "ERREUR: MySQL local n'est pas prêt"
    exit 1
fi

# 1. Dump VPS (stream via SSH)
log "Dump VPS en cours..."
ssh "$VPS_HOST" "docker exec forgeai-mysql mysqldump \
  -uroot -p$VPS_ROOT_PWD \
  --single-transaction --routines --triggers --events \
  --set-gtid-purged=OFF $VPS_DB" 2>/tmp/vps_dump_err.log \
  | gzip > "$DUMP_FILE"

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    log "ERREUR dump VPS:"
    cat /tmp/vps_dump_err.log | tee -a "$LOG_FILE"
    exit 1
fi

if ! gzip -t "$DUMP_FILE"; then
    log "ERREUR: dump gzip invalide"
    exit 1
fi
DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
log "Dump reçu: $DUMP_SIZE"

# 2. Import dans une base temporaire. La base locale active n'est jamais
#    supprimée avant validation complète du dump.
log "Import de validation dans $STAGING_DB..."
docker exec -i "$LOCAL_CONTAINER" mysql --protocol=socket -uroot -p"$LOCAL_ROOT_PWD" -e "
  CREATE DATABASE \`$STAGING_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
" 2>&1 | sed '/Warning/d' | tee -a "$LOG_FILE"

set +e
gunzip -c "$DUMP_FILE" | docker exec -i "$LOCAL_CONTAINER" mysql --protocol=socket -uroot -p"$LOCAL_ROOT_PWD" "$STAGING_DB" 2>&1 | tee "$IMPORT_LOG" | tee -a "$LOG_FILE"
IMPORT_STATUS=${PIPESTATUS[1]}
set -e

if [ "$IMPORT_STATUS" -ne 0 ]; then
    log "ERREUR import local dans $STAGING_DB (code $IMPORT_STATUS)"
    log "La base active $LOCAL_DB n'a pas été modifiée. Base temporaire conservée pour diagnostic."
    rm -f "$DUMP_FILE"
    exit 1
fi

# 3. Vérifications minimales avant remplacement
TABLE_COUNT=$(docker exec "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" "$STAGING_DB" -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$STAGING_DB';" 2>/dev/null | grep -v Warning)
USER_COUNT=$(docker exec "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" "$STAGING_DB" -N -e "SELECT COUNT(*) FROM users;" 2>/dev/null | grep -v Warning)
if [ "${TABLE_COUNT:-0}" -lt 1 ] || [ -z "${USER_COUNT:-}" ]; then
    log "ERREUR: dump importé incomplet (tables=$TABLE_COUNT, users=${USER_COUNT:-absent})"
    exit 1
fi
log "Validation staging: $TABLE_COUNT tables, $USER_COUNT utilisateurs"

# 4. Remplacement uniquement après validation. La staging reste disponible
#    si la copie finale doit être reprise manuellement.
log "Remplacement de la base locale active..."
docker exec -i "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" -e "DROP DATABASE IF EXISTS \`$LOCAL_DB\`; CREATE DATABASE \`$LOCAL_DB\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>&1 | sed '/Warning/d' | tee -a "$LOG_FILE"
set +e
docker exec "$LOCAL_CONTAINER" mysqldump -uroot -p"$LOCAL_ROOT_PWD" "$STAGING_DB" | docker exec -i "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" "$LOCAL_DB" 2>&1 | sed '/Warning/d' | tee -a "$LOG_FILE"
FINAL_STATUS=${PIPESTATUS[1]}
set -e
if [ "$FINAL_STATUS" -ne 0 ]; then
    log "ERREUR copie finale (code $FINAL_STATUS). Staging conservée: $STAGING_DB"
    exit 1
fi
docker exec "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" -e "DROP DATABASE \`$STAGING_DB\`;" 2>&1 | sed '/Warning/d' | tee -a "$LOG_FILE"

COUNT=$(docker exec "$LOCAL_CONTAINER" mysql -uroot -p"$LOCAL_ROOT_PWD" "$LOCAL_DB" -N -e "SELECT COUNT(*) FROM intendance_expenses;" 2>/dev/null | grep -v Warning)
log "Vérification finale: intendance_expenses = $COUNT lignes"

# 4. Nettoyage
rm -f "$DUMP_FILE" /tmp/vps_dump_err.log "$IMPORT_LOG"

log "=== Sync terminée avec succès ==="
