#!/usr/bin/env bash
set -euo pipefail

# Disposable test services only. Never connects to Supabase or deploys the app.
contract_root="$(cd "$(dirname "$0")/.." && pwd)"
contract_python="${PYTHON:-python}"
contract_prefix="studentcrm-contract-${GITHUB_RUN_ID:-local}-$$"
contract_db="${contract_prefix}-db"
contract_api="${contract_prefix}-api"
cleanup() {
  docker rm -f "$contract_api" "$contract_db" >/dev/null 2>&1 || true
  docker network rm "$contract_prefix" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$contract_prefix" >/dev/null
docker run -d --name "$contract_db" --network "$contract_prefix" \
  -e POSTGRES_PASSWORD=contract-only-password -e POSTGRES_DB=studentcrm_test \
  postgres:17 >/dev/null
contract_ready=false
for _ in {1..30}; do
  if docker exec "$contract_db" pg_isready -h 127.0.0.1 -U postgres -d studentcrm_test >/dev/null 2>&1; then
    contract_ready=true
    break
  fi
  sleep 1
done
[[ "$contract_ready" == true ]]
"$contract_python" "$contract_root/scripts/check_postgrest_contract.py" --seed-sql | \
  docker exec -i "$contract_db" psql -v ON_ERROR_STOP=1 -U postgres -d studentcrm_test >/dev/null
docker run -d --name "$contract_api" --network "$contract_prefix" -p 127.0.0.1::3000 \
  -e "PGRST_DB_URI=postgres://postgres:contract-only-password@${contract_db}:5432/studentcrm_test" \
  -e PGRST_DB_SCHEMAS=public -e PGRST_DB_ANON_ROLE=contract_reader \
  -e PGRST_JWT_SECRET=studentcrm-disposable-contract-secret-only -e PGRST_DB_MAX_ROWS=1 \
  postgrest/postgrest:v14.0 >/dev/null
contract_address="$(docker port "$contract_api" 3000/tcp)"
export STUDENTCRM_CONTRACT_POSTGREST_URL="http://${contract_address}"
contract_ready=false
for _ in {1..30}; do
  if curl --fail --silent "$STUDENTCRM_CONTRACT_POSTGREST_URL/" >/dev/null; then
    contract_ready=true
    break
  fi
  sleep 1
done
if [[ "$contract_ready" != true ]]; then
  docker logs "$contract_api"
  exit 1
fi
"$contract_python" "$contract_root/scripts/check_postgrest_contract.py"
