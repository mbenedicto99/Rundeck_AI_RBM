#!/usr/bin/env bash
set -euo pipefail

# ------------ Config ---------------
# Escolha a imagem/tag (pode sobrescrever na chamada):
#   N8N_IMAGE=docker.n8n.io/n8nio/n8n:latest-debian   ./start_n8n.sh
#   N8N_IMAGE=docker.n8n.io/n8nio/n8n:1.81.0-debian   ./start_n8n.sh
#   N8N_IMAGE=docker.n8n.io/n8nio/n8n:next-debian     ./start_n8n.sh   (se disponível)
N8N_IMAGE="${N8N_IMAGE:-docker.n8n.io/n8nio/n8n:1.81.0}"

CONTAINER="n8n-ai"
VENV_PATH="/home/node/venv"
REQ_FILE="/workspace/requirements.txt"

# usa docker com/sem sudo
dc() { if groups "$USER" | grep -q '\bdocker\b'; then docker "$@"; else sudo docker "$@"; fi; }

# ------------ Go! -------------------
cd "$(dirname "$0")"

echo "[start] preparando pasta de dados..."
mkdir -p ./data
sudo chown -R 1000:1000 ./data
chmod -R u+rwX,g+rwX ./data

echo "[start] puxando imagem base: $N8N_IMAGE"
dc pull "$N8N_IMAGE" || true

echo "[start] build com base $N8N_IMAGE ..."
dc compose build --no-cache --build-arg "N8N_IMAGE=$N8N_IMAGE"

echo "[start] subindo stack..."
dc compose up -d

echo "[start] aguardando container '$CONTAINER' ficar running..."
for i in {1..30}; do
  state="$(dc inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)"
  [ "$state" = "running" ] && break
  sleep 1
done
[ "${state:-}" = "running" ] || { echo "[erro] container não subiu"; dc logs --tail=200 "$CONTAINER" || true; exit 1; }

echo "[start] criando venv dentro do container em $VENV_PATH e instalando deps..."
dc exec -i "$CONTAINER" bash -lc "
set -euo pipefail
# preferir Debian para wheels; se for Alpine, pode compilar pacotes pesados
if [ -f /etc/alpine-release ]; then echo '[warn] base Alpine detectada – instalação pode compilar libs pesadas'; fi

python3 -m venv '$VENV_PATH' || true
source '$VENV_PATH/bin/activate'
python -m pip install --upgrade pip

if [ -f '$REQ_FILE' ]; then
  echo '[start] pip install -r $REQ_FILE'
  # tenta wheels-only primeiro (rápido); se falhar, fallback
  pip install --only-binary=:all: --no-cache-dir -r '$REQ_FILE' || pip install -r '$REQ_FILE'
else
  echo '[warn] $REQ_FILE não encontrado; pulando instalação.'
fi
"

echo "[ok] n8n em pé."
echo "UI: http://localhost:5678"
echo "Para rodar o pipeline manualmente:"
echo "  dc exec -it $CONTAINER bash -lc 'source $VENV_PATH/bin/activate && cd /workspace && python scripts/pipeline.py'"
