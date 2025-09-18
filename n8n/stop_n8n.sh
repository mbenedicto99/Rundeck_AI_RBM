#!/usr/bin/env bash
set -euo pipefail

# sempre execute a partir da pasta do compose
cd "$(dirname "$0")"

# Nome do serviço/contêiner
CONTAINER_NAME="n8n-ai"

echo "[stop] derrubando stack via docker compose..."
# Para os serviços, mas preserva volumes/arquivos da pasta ./data
docker compose down

# Se quiser garantir a remoção do contêiner residual (normalmente desnecessário):
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "[stop] removendo contêiner residual ${CONTAINER_NAME}..."
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

# Opcional: remover imagens *somente* da stack atual (comente se não quiser)
# echo "[stop] removendo imagens não usadas..."
# docker image prune -f

echo "[stop] ok."
echo "  docker ps | grep ${CONTAINER_NAME} || echo 'container parado'"

echo "Clean Files:"
docker compose down -v
rm -rf ./data
