#!/usr/bin/env bash
set -euo pipefail
C=n8n-ai
# 1) deps de sistema
docker exec -it -u root "$C" sh -lc '
set -e
apk update
apk add --no-cache build-base gfortran python3-dev musl-dev openblas-dev lapack-dev cmake ninja meson
'
# 2) deps Python + build sklearn
docker exec -it "$C" sh -lc "
set -e
. /home/node/venv/bin/activate
pip install --no-cache-dir numpy==2.2.3 scipy==1.14.1
export SKLEARN_NO_OPENMP=1
export NPY_BLAS_ORDER=openblas
export NPY_LAPACK_ORDER=openblas
pip install --no-binary=scikit-learn --no-cache-dir scikit-learn==1.5.2 \
|| pip install --no-binary=scikit-learn --no-cache-dir scikit-learn==1.4.2
python - <<'PY'
import numpy, scipy, sklearn
print('ready:', numpy.__version__, scipy.__version__, sklearn.__version__)
PY
"
