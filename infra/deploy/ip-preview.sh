#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DEPLOY_ROOT=${ORBIT_DEPLOY_ROOT:-/opt/orbit-wars}
DATA_ROOT=${ORBIT_DATA_ROOT:-${DEPLOY_ROOT}/data}
ENV_FILE=${ORBIT_ENV_FILE:-${DEPLOY_ROOT}/preview.env}
PUBLIC_PORT=${ORBIT_PUBLIC_PORT:-4000}
RELEASE=${ORBIT_RELEASE:-$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}
NETWORK=orbit-wars
PLATFORM_IMAGE=localhost/orbit-wars-platform:${RELEASE}
WEB_IMAGE=localhost/orbit-wars-web:${RELEASE}
SANDBOX_IMAGE=orbit-agent-sandbox:py311-stdlib-v1

log() {
  printf '[orbit-deploy] %s\n' "$*"
}

wait_for() {
  local description=$1
  shift
  for _attempt in $(seq 1 60); do
    if "$@" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  log "timed out waiting for ${description}"
  return 1
}

replace_container() {
  local name=$1
  docker rm --force "${name}" >/dev/null 2>&1 || true
}

common_app_env() {
  printf '%s\n' \
    --env APP_ENV=preview \
    --env ORBIT_DEV_AUTH=true \
    --env DATABASE_URL="postgresql://orbit_wars:${POSTGRES_PASSWORD}@orbit-postgres:5432/orbit_wars" \
    --env REDIS_URL=redis://orbit-redis:6379/0 \
    --env S3_ENDPOINT_URL=http://orbit-minio:9000 \
    --env S3_ACCESS_KEY="${S3_ACCESS_KEY}" \
    --env S3_SECRET_KEY="${S3_SECRET_KEY}" \
    --env S3_REGION=us-east-1 \
    --env S3_BUCKET=orbit-wars-preview \
    --env MATCH_TICKET_SECRET="${MATCH_TICKET_SECRET}" \
    --env ORBIT_AI_USER_SECRET="${ORBIT_AI_USER_SECRET}"
}

if [[ ! ${PUBLIC_PORT} =~ ^[0-9]+$ ]] || ((PUBLIC_PORT < 1024 || PUBLIC_PORT > 65535)); then
  printf 'ORBIT_PUBLIC_PORT must be an integer between 1024 and 65535\n' >&2
  exit 2
fi

mkdir -p "${DEPLOY_ROOT}" "${DATA_ROOT}/postgres" "${DATA_ROOT}/redis" \
  "${DATA_ROOT}/minio" "${DATA_ROOT}/runtime/tmp"
chmod 700 "${DEPLOY_ROOT}"
chmod 1777 "${DATA_ROOT}/runtime/tmp"

if [[ ! -f ${ENV_FILE} ]]; then
  umask 077
  {
    printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'S3_ACCESS_KEY=%s\n' "orbit_$(openssl rand -hex 8)"
    printf 'S3_SECRET_KEY=%s\n' "$(openssl rand -hex 24)"
    printf 'MATCH_TICKET_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'ORBIT_AI_USER_SECRET=%s\n' "$(openssl rand -hex 32)"
  } >"${ENV_FILE}"
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

log "building release ${RELEASE}"
docker build --tag "${PLATFORM_IMAGE}" \
  --file "${ROOT_DIR}/infra/containers/Dockerfile.platform" "${ROOT_DIR}"
docker build --tag "${WEB_IMAGE}" \
  --build-arg ORBIT_API_INTERNAL_BASE=http://orbit-api:8000 \
  --build-arg NEXT_PUBLIC_ORBIT_DEV_SUBJECT=preview-commander \
  --file "${ROOT_DIR}/infra/containers/Dockerfile.web" "${ROOT_DIR}"
docker build --tag "${SANDBOX_IMAGE}" \
  "${ROOT_DIR}/services/agent-sandbox"

docker network inspect "${NETWORK}" >/dev/null 2>&1 || docker network create "${NETWORK}"

replace_container orbit-postgres
docker run --detach --name orbit-postgres --network "${NETWORK}" --restart=always \
  --env POSTGRES_DB=orbit_wars \
  --env POSTGRES_USER=orbit_wars \
  --env POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --volume "${DATA_ROOT}/postgres:/var/lib/postgresql/data:Z" \
  public.ecr.aws/docker/library/postgres:16-alpine
wait_for postgres docker exec orbit-postgres pg_isready --username orbit_wars --dbname orbit_wars

replace_container orbit-redis
docker run --detach --name orbit-redis --network "${NETWORK}" --restart=always \
  --volume "${DATA_ROOT}/redis:/data:Z" \
  public.ecr.aws/docker/library/redis:7.4-alpine redis-server --appendonly yes
wait_for redis docker exec orbit-redis redis-cli ping

replace_container orbit-minio
docker run --detach --name orbit-minio --network "${NETWORK}" --restart=always \
  --env MINIO_ROOT_USER="${S3_ACCESS_KEY}" \
  --env MINIO_ROOT_PASSWORD="${S3_SECRET_KEY}" \
  --volume "${DATA_ROOT}/minio:/data:Z" \
  quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z server /data

mapfile -t APP_ENV_ARGS < <(common_app_env)

log 'applying database migrations'
docker run --rm --network "${NETWORK}" "${APP_ENV_ARGS[@]}" \
  "${PLATFORM_IMAGE}" python -m alembic -c services/api/alembic.ini upgrade head

SOCKET_ARGS=()
if command -v podman >/dev/null 2>&1; then
  systemctl enable --now podman.socket >/dev/null
  SOCKET_ARGS=(--volume /run/podman/podman.sock:/var/run/docker.sock)
elif [[ -S /var/run/docker.sock ]]; then
  SOCKET_ARGS=(--volume /var/run/docker.sock:/var/run/docker.sock)
fi

replace_container orbit-api
docker run --detach --name orbit-api --network "${NETWORK}" --restart=always \
  --publish 127.0.0.1:18000:8000 \
  "${APP_ENV_ARGS[@]}" \
  --env TMPDIR="${DATA_ROOT}/runtime/tmp" \
  --volume "${DATA_ROOT}/runtime/tmp:${DATA_ROOT}/runtime/tmp:z" \
  "${SOCKET_ARGS[@]}" \
  "${PLATFORM_IMAGE}"

replace_container orbit-worker
docker run --detach --name orbit-worker --network "${NETWORK}" --restart=always \
  "${APP_ENV_ARGS[@]}" \
  --env ORBIT_TURN_SECONDS=2.5 \
  "${PLATFORM_IMAGE}" python -m orbit_match_worker.worker

replace_container orbit-web
docker run --detach --name orbit-web --network "${NETWORK}" --restart=always \
  --publish "0.0.0.0:${PUBLIC_PORT}:3000" \
  --env ORBIT_API_INTERNAL_BASE=http://orbit-api:8000 \
  "${WEB_IMAGE}"

wait_for api curl --fail --silent http://127.0.0.1:18000/health/dependencies
wait_for web curl --fail --silent "http://127.0.0.1:${PUBLIC_PORT}/zh"

log 'provisioning warm-up agents and matches'
docker run --rm --network "${NETWORK}" "${APP_ENV_ARGS[@]}" \
  "${PLATFORM_IMAGE}" python scripts/warmup_agents.py

log "ready on http://0.0.0.0:${PUBLIC_PORT}"
docker ps --filter 'name=orbit-' --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
