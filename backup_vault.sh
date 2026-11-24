#!/data/data/com.termux/files/usr/bin/bash
set -e

WS_DIR="$HOME/apk-workstation"
LOCAL_BACKUP_DIR="$WS_DIR/backups"
SHARED_BACKUP_DIR="$HOME/storage/shared/Archives/apk-workstation"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_NAME="apk_workstation_vault_${STAMP}.tar.gz"

mkdir -p "$LOCAL_BACKUP_DIR"
cd "$WS_DIR"

TARGETS=()
[ -d "keystores" ] && TARGETS+=("keystores")
[ -d "profiles" ] && TARGETS+=("profiles")
[ -f "libs/android.jar" ] && TARGETS+=("libs/android.jar")

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "[!] Nothing to back up yet (keystores/ and profiles/ are empty)."
  exit 1
fi

tar -czf "$LOCAL_BACKUP_DIR/$ARCHIVE_NAME" "${TARGETS[@]}"
SIZE_KB=$(du -k "$LOCAL_BACKUP_DIR/$ARCHIVE_NAME" | cut -f1)
echo "[+] Local vault snapshot saved: backups/$ARCHIVE_NAME (${SIZE_KB} KB)"

# Keep only the 10 most recent local snapshots
ls -1t "$LOCAL_BACKUP_DIR"/apk_workstation_vault_*.tar.gz 2>/dev/null | tail -n +11 | xargs -r \rm -f

# Mirror to Android shared storage if termux-setup-storage is active
if [ -d "$HOME/storage/shared" ]; then
  mkdir -p "$SHARED_BACKUP_DIR"
  cp "$LOCAL_BACKUP_DIR/$ARCHIVE_NAME" "$SHARED_BACKUP_DIR/$ARCHIVE_NAME"
  ls -1t "$SHARED_BACKUP_DIR"/apk_workstation_vault_*.tar.gz 2>/dev/null | tail -n +11 | xargs -r \rm -f
  echo "[+] Mirrored to Android storage: /sdcard/Archives/apk-workstation/$ARCHIVE_NAME"
else
  echo "[i] Shared storage not mounted (run 'termux-setup-storage' if you want an /sdcard copy)."
fi
