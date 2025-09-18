import subprocess
import sys

STEPS = [
    ["python", "scripts/etl.py"],
    ["python", "scripts/features.py"],
    ["python", "scripts/train_rbm.py"],
    ["python", "scripts/detect_anomalies.py"],
    ["python", "scripts/build_ai_json.py"],
]

def run(cmd):
    print(f"[pipeline] Executando: {' '.join(cmd)}")
    p = subprocess.run(cmd, check=True)
    return p.returncode

def main():
    for step in STEPS:
        try:
            run(step)
        except subprocess.CalledProcessError as e:
            print(f"[pipeline] Erro no passo: {' '.join(step)}")
            sys.exit(e.returncode)
    print("[pipeline] Concluído com sucesso. Saída: app/ai_analysis.json")

if __name__ == "__main__":
    main()
