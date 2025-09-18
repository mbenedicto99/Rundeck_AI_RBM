cd ~/Documents/CanopusAI/RUNDECK_AI/n8n

# preparar pasta de dados e permissões (UID 1000 = 'node' no container)
mkdir -p ./data && sudo chown -R 1000:1000 ./data

# build e up
docker compose build --no-cache
docker compose up -d

# criar venv e instalar dependências Python dentro do container
docker exec -it n8n-ai sh -lc '
set -e
python3 -m venv /home/node/venv
. /home/node/venv/bin/activate
python -m pip install --upgrade pip

# wheels musllinux (rápidas) para numpy/scipy/pandas/matplotlib
pip install --no-cache-dir numpy==2.2.3 scipy==1.14.1 pandas==2.2.2 matplotlib==3.8.4 joblib==1.4.2 python-dateutil==2.9.0.post0 tqdm==4.66.4

# scikit-learn: geralmente PRECISA compilar no Alpine → desabilite OpenMP
export SKLEARN_NO_OPENMP=1
export NPY_BLAS_ORDER=openblas
export NPY_LAPACK_ORDER=openblas

# tente a versão mais nova; se falhar, tente 1.4.2
pip install --no-binary=scikit-learn --no-cache-dir scikit-learn==1.5.2 \
  || pip install --no-binary=scikit-learn --no-cache-dir scikit-learn==1.4.2

python - <<PY
import numpy, scipy, sklearn
print("OK:", numpy.__version__, scipy.__version__, sklearn.__version__)
PY
'

