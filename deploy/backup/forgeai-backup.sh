#!/bin/bash
set -euo pipefail

BACKUP_DIR="/var/www/forgeai/data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/forgeai_backup_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

docker exec forgeai-mysql mysqldump \
  -uroot -proot_password_change_me \
  --single-transaction --routines --triggers --events \
  --set-gtid-purged=OFF forgeai \
  | gzip > "$FILE"

ls -1t "${BACKUP_DIR}"/forgeai_backup_*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm -f

echo "Backup créé: $FILE ($(du -h "$FILE" | cut -f1))"