#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.neural_network import BernoulliRBM
from sklearn.preprocessing import MinMaxScaler

# Paths (podem ser sobrescritos por env vars)
INPUT_FEATS = os.getenv("INPUT_FEATS", "data/features.csv")
FEATURE_META = os.getenv("FEATURE_META", "models/feature_meta.json")
MODEL_PATH  = os.getenv("MODEL_PATH", "models/rbm.joblib")

# Hiperparâmetros RBM
N_COMPONENTS  = int(os.getenv("RBM_COMPONENTS", "32"))
LEARNING_RATE = float(os.getenv("RBM_LR", "0.01"))
N_ITER        = int(os.getenv("RBM_EPOCHS", "50"))
BATCH_SIZE    = int(os.getenv("RBM_BATCH", "64"))
RANDOM_STATE  = int(os.getenv("RBM_SEED", "42"))

# Pré-processamento
BINARIZE        = os.getenv("RBM_BINARIZE", "0") == "1"   # se "1", aplica limiar
BIN_THRESHOLD   = float(os.getenv("RBM_BIN_THRESHOLD", "0.5"))
DROP_CONST_COLS = os.getenv("DROP_CONST_COLS", "1") == "1"

def ensure_dir(p: str | Path):
    d = Path(p).parent
    d.mkdir(parents=True, exist_ok=True)

def load_feature_meta(feats: pd.DataFrame) -> dict:
    """Carrega FEATURE_META se existir; senão infere colunas numéricas."""
    if Path(FEATURE_META).exists():
        with open(FEATURE_META, "r", encoding="utf-8") as f:
            meta = json.load(f)
        cols = meta.get("feature_cols", [])
        missing = [c for c in cols if c not in feats.columns]
        if missing:
            raise ValueError(f"Colunas do FEATURE_META ausentes no CSV: {missing}")
        # filtra só numéricas
        num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(feats[c])]
        if len(num_cols) != len(cols):
            diff = sorted(set(cols) - set(num_cols))
            print(f"[warn] Colunas não numéricas removidas: {diff}")
        meta["feature_cols"] = num_cols
        return meta
    else:
        # Inferir: todas numéricas, exceto ids/timestamps comuns
        blacklist = {"exec_id", "job", "projeto", "status", "inicio", "fim", "data", "timestamp"}
        num_cols = [c for c in feats.columns
                    if pd.api.types.is_numeric_dtype(feats[c]) and c not in blacklist]
        if not num_cols:
            raise ValueError("Não há colunas numéricas utilizáveis para treinar a RBM.")
        meta = {"feature_cols": num_cols}
        ensure_dir(FEATURE_META)
        with open(FEATURE_META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"[info] FEATURE_META criado com colunas: {num_cols}")
        return meta

def preprocess_for_rbm(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    X = df[cols].copy()

    # Imputação simples (mediana)
    for c in cols:
        if not pd.api.types.is_numeric_dtype(X[c]):
            X[c] = pd.to_numeric(X[c], errors="coerce")
        med = X[c].median(skipna=True)
        X[c] = X[c].fillna(med)

    # Remover colunas constantes (opcional)
    if DROP_CONST_COLS:
        nunique = X.nunique(dropna=False)
        const_cols = nunique[nunique <= 1].index.tolist()
        if const_cols:
            X = X.drop(columns=const_cols)
            print(f"[warn] Colunas constantes removidas: {const_cols}")

    # Escala para [0,1]
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X.values.astype(np.float64))

    # Clip duro (garantia)
    X_scaled = np.clip(X_scaled, 0.0, 1.0)

    # Binarização opcional (para RBM estritamente Bernoulli)
    if BINARIZE:
        X_bin = (X_scaled >= BIN_THRESHOLD).astype(np.float64)
        X_out = X_bin
    else:
        X_out = X_scaled

    # Diags
    print(f"[diag] X shape: {X_out.shape}, min={X_out.min():.4f}, max={X_out.max():.4f}")
    if np.isnan(X_out).any() or np.isinf(X_out).any():
        raise ValueError("Ainda existem NaN/inf após o pré-processamento.")

    # Persistir scaler para uso futuro (opcional)
    ensure_dir("models/scalers.joblib")
    joblib.dump({"scaler": scaler, "binarize": BINARIZE, "threshold": BIN_THRESHOLD,
                 "used_cols": list(X.columns)}, "models/scalers.joblib")
    return X_out

def main():
    if not Path(INPUT_FEATS).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {INPUT_FEATS}")

    feats = pd.read_csv(INPUT_FEATS)
    meta = load_feature_meta(feats)

    X = preprocess_for_rbm(feats, meta["feature_cols"])

    rbm = BernoulliRBM(
        n_components=N_COMPONENTS,
        learning_rate=LEARNING_RATE,
        batch_size=BATCH_SIZE,
        n_iter=N_ITER,
        random_state=RANDOM_STATE,
        verbose=True,
    )
    rbm.fit(X)

    ensure_dir(MODEL_PATH)
    joblib.dump(rbm, MODEL_PATH)
    print(f"[train_rbm] Modelo salvo em {MODEL_PATH}")

if __name__ == "__main__":
    main()
