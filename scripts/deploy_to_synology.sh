#!/bin/sh
set -eu

NAS_USER="${NAS_USER:-maurice}"
NAS_HOST="${NAS_HOST:-192.168.1.5}"
NAS_PORT="${NAS_PORT:-21967}"
HA_CONFIG="${HA_CONFIG:-/volume1/docker/homeassistant}"

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPONENT="growatt_export_controller"
SOURCE_PARENT="${REPO_ROOT}/custom_components"
SOURCE="${SOURCE_PARENT}/${COMPONENT}"

REMOTE_BASE="${HA_CONFIG}/custom_components"
REMOTE_TARGET="${REMOTE_BASE}/${COMPONENT}"
BACKUP_BASE="${HA_CONFIG}/growatt_export_controller_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REMOTE_BACKUP="${BACKUP_BASE}/${COMPONENT}_backup_${TIMESTAMP}"
REMOTE_STAGE="${HA_CONFIG}/.${COMPONENT}_stage_${TIMESTAMP}"
REMOTE="${NAS_USER}@${NAS_HOST}"

if [ ! -f "${SOURCE}/manifest.json" ]; then
    printf 'Error: manifest.json was not found in %s\n' "$SOURCE" >&2
    exit 1
fi

printf 'Deploying Growatt Export Controller\n'
printf 'Target: %s:%s\n' "$REMOTE" "$REMOTE_TARGET"
printf 'Backups: %s\n\n' "$BACKUP_BASE"

tar \
    --exclude='*/__pycache__' \
    --exclude='*.pyc' \
    -czf - \
    -C "$SOURCE_PARENT" \
    "$COMPONENT" \
| ssh -p "$NAS_PORT" "$REMOTE" "
    set -eu

    mkdir -p '$REMOTE_BASE' '$BACKUP_BASE'

    # Move legacy backups out of custom_components so Home Assistant cannot
    # discover them as duplicate custom integrations.
    for d in '$REMOTE_BASE'/${COMPONENT}_backup_* '$REMOTE_BASE'/${COMPONENT}_failed_*; do
        [ -e \"\$d\" ] || continue
        mv \"\$d\" '$BACKUP_BASE/'
    done

    rm -rf '$REMOTE_STAGE'
    mkdir -p '$REMOTE_STAGE'
    tar -xzf - -C '$REMOTE_STAGE'
    test -f '$REMOTE_STAGE/$COMPONENT/manifest.json'

    if [ -e '$REMOTE_TARGET' ] || [ -L '$REMOTE_TARGET' ]; then
        cp -a '$REMOTE_TARGET' '$REMOTE_BACKUP'
        printf 'Backup created: %s\n' '$REMOTE_BACKUP'
    fi

    rm -rf '$REMOTE_TARGET'
    mv '$REMOTE_STAGE/$COMPONENT' '$REMOTE_TARGET'
    rmdir '$REMOTE_STAGE'

    test -f '$REMOTE_TARGET/manifest.json'
    printf 'Deployment verified: %s\n' '$REMOTE_TARGET/manifest.json'
"

printf '\nDeployment complete.\n'
printf 'Restart Home Assistant in Synology Container Manager.\n'
printf 'Rollback command, if needed: ./scripts/rollback_on_synology.sh\n'
