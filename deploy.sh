#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

git pull

# An install from before the rename has to be moved over once first.
if kubectl get deployment hermes-api >/dev/null 2>&1; then
  echo "This install still uses the old names. Run scripts/migrate-from-hermes.sh once (docs/renaming-from-hermes.md)." >&2
  exit 1
fi

# --provenance=false --sbom=false avoids a BuildKit gotcha: without them,
# attestation metadata turns the image into a multi-manifest index that
# doesn't cleanly retag on a repeat `ctr images import` of the same tag.
docker build --provenance=false --sbom=false -t naradi:latest .
docker save naradi:latest -o naradi.tar

# Explicitly removing the old image first guards against that same stale-
# digest issue if one ever slips through anyway.
sudo k3s ctr images rm docker.io/library/naradi:latest || true
sudo k3s ctr images import naradi.tar
rm -f naradi.tar

kubectl rollout restart deployment naradi-api
kubectl rollout status deployment naradi-api
