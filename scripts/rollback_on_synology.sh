#!/bin/sh
set -eu

NAS_USER="${NAS_USER:-maurice}"
NAS_HOST="${NAS_HOST:-192.168.1.5}"
NAS_PORT="${NAS_PORT:-21967}"
HA_CONFIG="${HA_CONFIG:-/volume1/docker/homeassistant}"

COMPONENT="growatt_export_controller"
REMOTE_BASE="${HA_CONFIG}/custom_components"
REMOTE_TARGET="${REMOTE_BASE}/${COMPONENT}"
BACKUP_BASE="${HA_CONFIG}/growatt_export_controller_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REMOTE_FAILED="${BACKUP_BASE}/${COMPONENT}_failed_${TIMESTAMP}"
REMOTE="${NAS_USER}@${NAS_HOST}"

LATEST_BACKUP=$(ssh -p "$NAS_PORT" "$REMOTE" \
    "find '$BACKUP_BASE' -maxdepth 1 -type d -name '${COMPONENT}_backup_*' 2>/dev/null | sort | tail -n 1")

if [ -z "$LATEST_BACKUP" ]; then
    printf 'No Growatt backup was found in %s.\n' "$BACKUP_BASE" >&2
    exit 1
fi

printf 'Restoring %s\n' "$LATEST_BACKUP"
ssh -p "$NAS_PORT" "$REMOTE" "
    set -eu
    mkdir -p '$BACKUP_BASE' '$REMOTE_BASE'
    if [ -e '$REMOTE_TARGET' ] || [ -L '$REMOTE_TARGET' ]; then
        mv '$REMOTE_TARGET' '$REMOTE_FAILED'
        printf 'Current copy saved as: %s\n' '$REMOTE_FAILED'
    fi
    cp -a '$LATEST_BACKUP' '$REMOTE_TARGET'
    test -f '$REMOTE_TARGET/manifest.json'
    printf 'Rollback verified.\n'
"

printf 'Rollback complete. Restart Home Assistant in Synology Container Manager.\n'
