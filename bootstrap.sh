# Estrutura de pastas
mkdir -p scripts data app .github/workflows

# Ambiente local
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
#python scripts/simulate_data.py
python scripts/pipeline.py
# Abra app/index.html no navegador ou suba pro Amplify

# Git inicial
#git init && git add . && git commit -m "init mlops rundeck"
# Conecte ao repositório remoto (GitHub) e faça o primeiro push

