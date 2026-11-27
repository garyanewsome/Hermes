#!/usr/bin/env bash
# One-time move of a running "hermes" install to the "naradi" names. Run on the
# homelab, from this folder. See docs/renaming-from-hermes.md.
#
#   scripts/migrate-from-hermes.sh              migrate
#   scripts/migrate-from-hermes.sh --rollback   go back to the old names
#
# Nothing old is deleted that holds data: the old data folder, volume, secret
# and image all stay until you remove them yourself.
set -euo pipefail

cd "$(dirname "$0")/.."
DATA_ROOT="${DATA_ROOT:-/mnt/storage}"
HEALTH_URL="${HEALTH_URL:-http://localhost:30080/health}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$DATA_ROOT/naradi-migration-$STAMP"
STEP="starting"

say() { STEP="$1"; printf '\n== %s\n' "$1"; }
die() { printf 'STOPPED: %s\n' "$1" >&2; exit 1; }
exists() { kubectl get "$1" "$2" >/dev/null 2>&1; }
# psql inside the database pod, over its local socket (no password needed).
sql() { kubectl exec -i deploy/planner-postgres -- psql -v ON_ERROR_STOP=1 -U "$1" -d planner -tAc "$2"; }
role_exists() { [ "$(sql "$1" "SELECT count(*) FROM pg_roles WHERE rolname = '$2'" 2>/dev/null || echo 0)" = "1" ]; }

# A role can't rename itself, so a temporary superuser does it.
rename_role() {
  local from="$1" to="$2"
  sql "$from" "DROP ROLE IF EXISTS naradi_migrator"
  sql "$from" "CREATE ROLE naradi_migrator SUPERUSER LOGIN"
  sql naradi_migrator "ALTER ROLE $from RENAME TO $to"
  sql "$to" "DROP ROLE naradi_migrator"
}

wait_for_database() {
  if ! kubectl rollout status deploy/planner-postgres --timeout=180s; then
    # It has stalled in recovery after restarts before; one restart cleared it.
    kubectl rollout restart deploy/planner-postgres
    kubectl rollout status deploy/planner-postgres --timeout=180s
  fi
}

wait_for_health() {
  for _ in $(seq 1 30); do
    curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && return 0
    sleep "${HEALTH_WAIT:-2}"
  done
  return 1
}

no_pods() {
  for _ in $(seq 1 60); do
    [ -z "$(kubectl get pods -l "app=$1" -o name)" ] && return 0
    sleep "${HEALTH_WAIT:-2}"
  done
  return 1
}

suspend_cronjobs() {
  for job in vault-tasks-import planner-postgres-backup; do
    if exists cronjob "$job"; then
      kubectl patch cronjob "$job" --type merge -p "{\"spec\":{\"suspend\":$1}}"
    fi
  done
}

rollback() {
  say "Finding the old manifests in git"
  local renamed old
  renamed="$(git log --format=%H -1 --diff-filter=DR -- k8s/hermes-api.yaml)"
  [ -n "$renamed" ] || die "can't find the commit that renamed k8s/hermes-api.yaml"
  old="$renamed~1"
  read -r -p "Type rollback to go back to the old names: " answer
  [ "$answer" = "rollback" ] || die "nothing changed"
  docker image inspect hermes:latest >/dev/null 2>&1 || echo "Note: no local hermes image; K3s must still have it."

  say "Removing the naradi app (its data folder is kept)"
  suspend_cronjobs true
  kubectl delete ingress naradi-api --ignore-not-found
  kubectl delete service naradi-api naradi-api-nodeport --ignore-not-found
  kubectl delete deployment naradi-api --ignore-not-found
  no_pods naradi-api || die "naradi-api pods are still running"

  say "Database role"
  if role_exists naradi naradi; then rename_role naradi hermes; fi

  say "Restoring the old manifests"
  for file in planner-postgres.yaml planner-postgres-backup-cronjob.yaml hermes-pv.yaml hermes-api.yaml vault-tasks-cronjob.yaml; do
    git show "$old:k8s/$file" | kubectl apply -f -
    [ "$file" = planner-postgres.yaml ] && wait_for_database
  done
  suspend_cronjobs false
  kubectl rollout status deploy/hermes-api --timeout=180s
  wait_for_health || die "the old app isn't answering on $HEALTH_URL"
  if sudo test -e "$DATA_ROOT/naradi-data"; then
    sudo mv "$DATA_ROOT/naradi-data" "$DATA_ROOT/naradi-data.rolled-back-$STAMP"
  fi
  printf '\nBack on the old names. Chats made since the migration are in %s.\n' "$DATA_ROOT/naradi-data.rolled-back-$STAMP"
}

migrate() {
  say "Checks (nothing is changed yet)"
  for tool in kubectl docker curl git sudo base64; do
    command -v "$tool" >/dev/null || die "$tool isn't installed"
  done
  [ -f k8s/naradi-api.yaml ] || die "run git pull first: k8s/naradi-api.yaml is missing"
  exists deployment hermes-api || die "there is no hermes-api deployment (already migrated?)"
  ! exists deployment naradi-api || die "naradi-api already exists; use --rollback before trying again"
  exists secret hermes-auth-secret || die "secret hermes-auth-secret is missing"
  exists secret planner-postgres-secret || die "secret planner-postgres-secret is missing"
  sudo test -d "$DATA_ROOT/hermes-data" || die "$DATA_ROOT/hermes-data isn't there"
  ! sudo test -e "$DATA_ROOT/naradi-data" || die "$DATA_ROOT/naradi-data already exists; move it aside first"
  role_exists hermes hermes || die "the database has no hermes role"
  # Renaming a role erases an MD5 password; a SCRAM one survives.
  [ "$(sql hermes "SELECT left(rolpassword, 5) FROM pg_authid WHERE rolname = 'hermes'")" = "SCRAM" ] \
    || die "the hermes database password isn't stored as SCRAM, so renaming would erase it"
  local url_data url new_url
  url_data="$(kubectl get secret planner-postgres-secret -o 'jsonpath={.data.hermes-db-url}')"
  url="$(printf %s "$url_data" | base64 -d)"
  new_url="${url/\/\/hermes:/\/\/naradi:}"
  [ -n "$url" ] && [ "$new_url" != "$url" ] || die "hermes-db-url isn't in the expected postgresql://hermes:... form"

  cat <<MSG

This will:
  1. build the naradi image (the app keeps running)
  2. back up the database and data to $BACKUP
  3. stop the app, copy its data, rename the database user
  4. start it under the new names (a few minutes of downtime)
MSG
  read -r -p "Type migrate to continue: " answer
  [ "$answer" = "migrate" ] || die "nothing changed"
  trap 'printf "\nFailed during: %s\nTo go back: scripts/migrate-from-hermes.sh --rollback\nBackup: %s\n" "$STEP" "$BACKUP" >&2' ERR

  say "Building the new image"
  docker build --provenance=false --sbom=false -t naradi:latest .
  docker save naradi:latest -o naradi.tar
  sudo k3s ctr images import naradi.tar
  rm -f naradi.tar

  say "Backing up the database"
  sudo install -d -m 700 -o "$(id -un)" "$BACKUP"
  kubectl exec deploy/planner-postgres -- pg_dump -U hermes -d planner > "$BACKUP/planner.sql"
  grep -q "PostgreSQL database dump complete" "$BACKUP/planner.sql" || die "the database backup is incomplete"

  say "Stopping the app"
  suspend_cronjobs true
  kubectl scale deployment hermes-api --replicas=0
  no_pods hermes-api || die "hermes-api pods are still running"

  say "Copying the data"
  sudo cp -a "$DATA_ROOT/hermes-data" "$BACKUP/hermes-data"
  sudo cp -a "$DATA_ROOT/hermes-data" "$DATA_ROOT/naradi-data"
  for suffix in "" -wal -shm -journal; do
    if sudo test -e "$DATA_ROOT/naradi-data/hermes.db$suffix"; then
      sudo mv "$DATA_ROOT/naradi-data/hermes.db$suffix" "$DATA_ROOT/naradi-data/naradi.db$suffix"
    fi
  done

  say "Copying the secrets (values are never printed)"
  local password session
  password="$(kubectl get secret hermes-auth-secret -o 'jsonpath={.data.auth-password}')"
  session="$(kubectl get secret hermes-auth-secret -o 'jsonpath={.data.session-secret}')"
  [ -n "$password" ] && [ -n "$session" ] || die "hermes-auth-secret is missing a value"
  kubectl apply -f - <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: naradi-auth-secret
type: Opaque
data:
  auth-password: $password
  session-secret: $session
YAML
  # Through stdin, so the database password never appears in the process list.
  printf '{"data":{"naradi-db-url":"%s"}}' "$(printf %s "$new_url" | base64 | tr -d '\n')" \
    | kubectl patch secret planner-postgres-secret --type merge --patch-file /dev/stdin

  say "Renaming the database user"
  rename_role hermes naradi

  say "Applying the new manifests"
  kubectl apply -f k8s/planner-postgres.yaml
  wait_for_database
  # The old services go first: they hold port 30080.
  kubectl delete ingress hermes-api --ignore-not-found
  kubectl delete service hermes-api hermes-api-nodeport --ignore-not-found
  kubectl delete deployment hermes-api
  kubectl apply -f k8s/naradi-pv.yaml
  kubectl apply -f k8s/naradi-api.yaml
  kubectl apply -f k8s/planner-postgres-backup-cronjob.yaml
  kubectl apply -f k8s/vault-tasks-cronjob.yaml
  suspend_cronjobs false

  say "Waiting for Naradi"
  kubectl rollout status deploy/naradi-api --timeout=180s
  wait_for_health || die "Naradi isn't answering on $HEALTH_URL"
  trap - ERR
  cat <<MSG

Naradi is running. Backup: $BACKUP

Check your chats, tasks and pictures. After a few good days, remove the old
pieces with the commands in docs/renaming-from-hermes.md.
MSG
}

case "${1:-}" in
  "") migrate ;;
  --rollback) rollback ;;
  *) die "unknown option $1" ;;
esac
