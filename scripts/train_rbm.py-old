import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import BernoulliRBM

INPUT_FEATS = os.getenv("INPUT_FEATS", "data/features.csv")
FEATURE_META = os.getenv("FEATURE_META", "models/feature_meta.json")
MODEL_PATH = os.getenv("MODEL_PATH", "models/rbm.joblib")

N_COMPONENTS = int(os.getenv("RBM_COMPONENTS", "32"))
LEARNING_RATE = float(os.getenv("RBM_LR", "0.01"))
N_ITER = int(os.getenv("RBM_EPOCHS", "50"))
BATCH_SIZE = int(os.getenv("RBM_BATCH", "64"))
RANDOM_STATE = int(os.getenv("RBM_SEED", "42"))

def main():
    if not os.path.exists(INPUT_FEATS):
        raise FileNotFoundError(f"Arquivo não encontrado: {INPUT_FEATS}")

    with open(FEATURE_META) as f:
        meta = json.load(f)
    feats = pd.read_csv(INPUT_FEATS)

    X = feats[meta["feature_cols"]].astype(float).values

    rbm = BernoulliRBM(n_components=N_COMPONENTS, learning_rate=LEARNING_RATE,
                       batch_size=BATCH_SIZE, n_iter=N_ITER, random_state=RANDOM_STATE, verbose=True)
    rbm.fit(X)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(rbm, MODEL_PATH)
    print(f"[train_rbm] Modelo salvo em {MODEL_PATH}")

if __name__ == "__main__":
    main()
