#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import json

# Entradas/Saídas (podem ser sobrescritas por env vars)
FEATS_CSV  = os.getenv("FEATS_CSV", "data/features.csv")
SCALER_JOB = os.getenv("SCALER_JOB", "models/scalers.joblib")  # salvo no train_rbm.py
RBM_JOB    = os.getenv("RBM_JOB", "models/rbm.joblib")

SCORE_CSV  = os.getenv("SCORE_CSV", "data/score.csv")          # <- requerido pelo build_ai_json.py
OUT_JSON   = os.getenv("OUT_JSON", "app/ai_analysis.json")      # <- caminho canônico do painel

def _ensure_exists(path: str | Path, kind: str):
    if not Path(path).exists():
        raise FileNotFoundError(f"{kind} não encontrado: {path}")

def _load_inputs():
    _ensure_exists(FEATS_CSV, "CSV de features")
    _ensure_exists(SCALER_JOB, "Scaler/metadata")
    _ensure_exists(RBM_JOB, "Modelo RBM")
    df = pd.read_csv(FEATS_CSV)
    meta = joblib.load(SCALER_JOB)
    rbm  = joblib.load(RBM_JOB)

    used_cols = meta.get("used_cols")
    scaler    = meta.get("scaler")
    if used_cols is None or scaler is None:
        raise ValueError("models/scalers.joblib não possui 'used_cols' e/ou 'scaler'.")

    if not all(c in df.columns for c in used_cols):
        faltando = [c for c in used_cols if c not in df.columns]
        raise ValueError(f"Colunas de features ausentes no features.csv: {faltando}")

    return df, used_cols, scaler, rbm

def _prepare_matrix(df: pd.DataFrame, used_cols, scaler):
    X = df[used_cols].copy()
    # coerção robusta pra numérico
    for c in X.columns:
        if not pd.api.types.is_numeric_dtype(X[c]):
            # troca vírgula por ponto, tenta numérico
            X[c] = pd.to_numeric(X[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
        # imputação mediana
        med = X[c].median(skipna=True)
        X[c] = X[c].fillna(med)
    # escala igual ao treino e clipa a [0,1]
    Xn = scaler.transform(X.values.astype(np.float64))
    Xn = np.clip(Xn, 0.0, 1.0)
    return Xn

def main():
    df, used_cols, scaler, rbm = _load_inputs()

    # Garantir identificador por linha
    id_col = "exec_id" if "exec_id" in df.columns else None
    if id_col is None:
        df["exec_id"] = np.arange(len(df)).astype(str)
        id_col = "exec_id"

    X = _prepare_matrix(df, used_cols, scaler)

    # Reconstrução (usando passo de Gibbs do RBM)
    V_recon = rbm.gibbs(X)
    re = np.mean((X - V_recon) ** 2, axis=1)

    # Salva score.csv para o build final
    out_df = pd.DataFrame({"exec_id": df[id_col].astype(str), "re": re.astype(float)})
    Path(SCORE_CSV).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(SCORE_CSV, index=False)
    print(f"[detect_anomalies] Gravado {SCORE_CSV} com {len(out_df)} linhas.")

    # (opcional) JSON leve no caminho canônico; o build_ai_json.py sobrescreve depois com o layout completo
    resumo = {
        "total_execucoes": int(len(out_df)),
        "re_p95_global": float(np.percentile(re, 95)) if len(out_df) else None
    }
    payload = {"resumo": resumo, "scores_sample": out_df.head(10).to_dict(orient="records")}
    Path(OUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[detect_anomalies] Gravado JSON em {OUT_JSON}")

if __name__ == "__main__":
    main()
