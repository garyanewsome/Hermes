#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

git pull

# --provenance=false --sbom=false avoids a BuildKit gotcha: without them,
# attestation metadata turns the image into a multi-manifest index that
# doesn't cleanly retag on a repeat `ctr images import` of the same tag.
docker build --provenance=false --sbom=false -t hermes:latest .
docker save hermes:latest -o hermes.tar

# Explicitly removing the old image first guards against that same stale-
# digest issue if one ever slips through anyway.
sudo k3s ctr images rm docker.io/library/hermes:latest || true
sudo k3s ctr images import hermes.tar
rm -f hermes.tar

kubectl rollout restart deployment hermes-api
kubectl rollout status deployment hermes-api
