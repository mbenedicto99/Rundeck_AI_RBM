#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import hashlib
from pathlib import Path
import pandas as pd
import numpy as np
from dateutil import parser

# Entradas/Saídas
INPUT_FILE   = os.getenv("INPUT_CSV", "data/slice.csv")   # pode ser .txt ou .csv
CLEAN_CSV    = os.getenv("OUTPUT_CSV", "data/clean.csv")
EXECUCOES_CSV = os.getenv("EXECUCOES_CSV", "data/execucoes.csv")

def _ensure_exists(p: str | Path):
    if not Path(p).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")

def _try_read(path: str | Path) -> pd.DataFrame:
    """
    Lê CSV/TXT com robustez:
      1) tenta ; (slice.txt geralmente vem com ;) e BOM
      2) tenta , como fallback
    """
    # tentativa 1: ;
    try:
        return pd.read_csv(path, sep=';', encoding='utf-8-sig', quotechar='"', engine='python')
    except Exception:
        pass
    # tentativa 2: ,
    return pd.read_csv(path, sep=',', encoding='utf-8-sig', quotechar='"', engine='python')

def _parse_dt(x):
    if pd.isna(x) or x is None:
        return pd.NaT
    try:
        # datas pt-BR: dayfirst=True
        return parser.parse(str(x), dayfirst=True)
    except Exception:
        return pd.NaT

def _norm_status(s: pd.Series) -> pd.Series:
    st = s.astype(str).str.lower().str.strip()
    return st.replace({
        "succeeded": "success",
        "succeed":   "success",
        "successful":"success",
        "ok":        "success",
        "pass":      "success",
        "completed": "success",
        "done":      "success",
        "fail":      "failed",
        "failed":    "failed",
        "error":     "failed",
        "ko":        "failed"
    })

def _hash_exec_id(proj: str, job: str, inicio) -> str:
    base = f"{proj}|{job}|{inicio}"
    return hashlib.sha1(base.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]

def main():
    _ensure_exists(INPUT_FILE)

    df_raw = _try_read(INPUT_FILE)
    if df_raw.empty:
        raise ValueError(f"{INPUT_FILE} lido mas sem linhas.")

    # normaliza cabeçalhos
    df_raw.columns = [c.strip().lower() for c in df_raw.columns]

    # mapeia possíveis nomes (aliases) vindos do slice
    # ex.: "Ended Status", "Start Time", "End Time", "Application", "Sub-Application"
    colmap = {
        "job_id":     ["job_id", "id", "execution_id"],
        "job":        ["job", "job_name", "name", "application"],
        "projeto":    ["projeto", "project", "project_name", "sub-application", "folder"],
        "status":     ["status", "result", "state", "ended status"],
        "inicio":     ["inicio", "start_time", "started_at", "start", "start time"],
        "fim":        ["fim", "end_time", "ended_at", "end", "finish_time", "end time"],
    }

    def pick(keys):
        for k in keys:
            if k in df_raw.columns:
                return df_raw[k]
        return pd.Series([None] * len(df_raw))

    df = pd.DataFrame({
        "job_id":  pick(colmap["job_id"]),
        "job":     pick(colmap["job"]),
        "projeto": pick(colmap["projeto"]),
        "status":  pick(colmap["status"]),
        "inicio":  pick(colmap["inicio"]),
        "fim":     pick(colmap["fim"]),
    })

    # parsing de datas e duração
    df["inicio"] = df["inicio"].apply(_parse_dt)
    df["fim"]    = df["fim"].apply(_parse_dt)
    df["duration_sec"] = (df["fim"] - df["inicio"]).dt.total_seconds()

    # normalização de status + saneamento
    df["status"] = _norm_status(df["status"])
    df = df.dropna(subset=["inicio"])
    df["duration_sec"] = pd.to_numeric(df["duration_sec"], errors="coerce").fillna(0.0).clip(lower=0.0)

    # defaults para texto
    df["job"] = df["job"].fillna("UNKNOWN").astype(str).str.strip()
    df["projeto"] = df["projeto"].fillna("UNKNOWN").astype(str).str.strip()

    # derivações de tempo
    df["date"]    = df["inicio"].dt.date
    df["hour"]    = df["inicio"].dt.hour
    df["weekday"] = df["inicio"].dt.weekday

    # exec_id: usa job_id se existir; senão hash determinístico de projeto|job|inicio ISO
    if df["job_id"].notna().any():
        df["exec_id"] = df["job_id"].astype(str).str.strip()
    else:
        df["exec_id"] = df.apply(lambda r: _hash_exec_id(r["projeto"], r["job"], getattr(r["inicio"], "isoformat", lambda: r["inicio"])()), axis=1)

    # ordena por inicio (opcional)
    df = df.sort_values("inicio").reset_index(drop=True)

    # salva clean.csv (mantém colunas úteis ao features.py)
    cols_clean = [
        "projeto", "job", "exec_id", "inicio", "fim", "status",
        "duration_sec", "date", "hour", "weekday"
    ]
    Path(CLEAN_CSV).parent.mkdir(parents=True, exist_ok=True)
    df[cols_clean].to_csv(CLEAN_CSV, index=False)
    print(f"[etl] Gravado {CLEAN_CSV} com {len(df)} linhas.")

    # salva execucoes.csv (layout esperado pelo build_ai_json.py)
    execucoes = df.rename(columns={
        "inicio": "inicio",
        "duration_sec": "duracao_s"
    })[["projeto", "job", "exec_id", "inicio", "status", "duracao_s"]]

    Path(EXECUCOES_CSV).parent.mkdir(parents=True, exist_ok=True)
    execucoes.to_csv(EXECUCOES_CSV, index=False)
    print(f"[etl] Gravado {EXECUCOES_CSV} com {len(execucoes)} linhas.")

    # diagnóstico rápido
    print("[etl] Amostra clean.csv:")
    print(df[cols_clean].head(3).to_string(index=False))

if __name__ == "__main__":
    main()
