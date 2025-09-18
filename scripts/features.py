#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

INPUT_CLEAN = os.getenv("INPUT_CLEAN", "data/clean.csv")
OUTPUT_FEATS = os.getenv("OUTPUT_FEATS", "data/features.csv")

def _ensure_exists(path: str | Path):
    if not Path(path).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

def _to_datetime(s: pd.Series):
    if np.issubdtype(s.dtype, np.datetime64):
        return s
    return pd.to_datetime(s, errors="coerce", dayfirst=True, utc=False)

def _hash_exec_id(row: pd.Series) -> str:
    base = f"{row.get('projeto','')}|{row.get('job','')}|{row.get('inicio','')}"
    h = hashlib.sha1(base.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return h

def _minmax_01(x: pd.Series) -> pd.Series:
    v = x.astype(float)
    vmin, vmax = np.nanmin(v.values), np.nanmax(v.values)
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax == vmin:
        # tudo igual ou inválido -> vira zeros
        return pd.Series(np.zeros(len(v)), index=v.index, dtype=float)
    return (v - vmin) / (vmax - vmin)

def _zclip_to01(x: pd.Series, clip=3.0) -> pd.Series:
    v = x.astype(float)
    mu = np.nanmean(v.values)
    sd = np.nanstd(v.values)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.full(len(v), 0.5), index=v.index, dtype=float)
    z = (v - mu) / sd
    z = np.clip(z, -clip, clip)
    return (z + clip) / (2 * clip)

def _cyc_enc_01(vals: pd.Series, period: int):
    # seno/cosseno em [-1,1], depois remapeia para [0,1]
    ang = 2 * np.pi * (vals.astype(float) % period) / period
    s = np.sin(ang)
    c = np.cos(ang)
    return (s + 1.0) / 2.0, (c + 1.0) / 2.0

def _p95_flags_per_job(df: pd.DataFrame, dur_col="duration_sec", key_cols=("projeto","job")) -> pd.Series:
    tmp = df.copy()
    tmp[dur_col] = pd.to_numeric(tmp[dur_col], errors="coerce").fillna(0.0).clip(lower=0.0)
    if all(k in tmp.columns for k in key_cols):
        thr = tmp.groupby(list(key_cols))[dur_col].quantile(0.95)
        thr = thr.rename("thr").reset_index()
        j = tmp[list(key_cols) + [dur_col]].merge(thr, on=list(key_cols), how="left")
        # fallback pro global se alguma chave não tiver threshold
        global_thr = float(np.percentile(tmp[dur_col].values, 95)) if len(tmp) else np.inf
        j["thr"] = j["thr"].fillna(global_thr)
        flags = (j[dur_col] > j["thr"]).astype(int)
        flags.index = df.index
        return flags
    # fallback global direto
    gthr = float(np.percentile(tmp[dur_col].values, 95)) if len(tmp) else np.inf
    return (tmp[dur_col] > gthr).astype(int)

def main():
    _ensure_exists(INPUT_CLEAN)
    df = pd.read_csv(INPUT_CLEAN)

    # Normaliza nomes esperados pelo pipeline
    # Esperado (do ETL ajustado): projeto, job, exec_id, inicio, status, duration_sec, date, hour, weekday
    # Garante colunas mínimas:
    col_alias = {c.lower(): c for c in df.columns}
    # padroniza para lower para trabalhar
    df.columns = [c.strip().lower() for c in df.columns]

    # Mapeia possíveis nomes
    rename_map = {}
    if "project" in df.columns: rename_map["project"] = "projeto"
    if "job_name" in df.columns: rename_map["job_name"] = "job"
    if "start_time" in df.columns: rename_map["start_time"] = "inicio"
    if "duration_sec" not in df.columns and "duracao_s" in df.columns:
        rename_map["duracao_s"] = "duration_sec"
    if rename_map:
        df = df.rename(columns=rename_map)

    # Conserta datetime e deriva hora/weekday se faltar
    if "inicio" in df.columns:
        df["inicio"] = _to_datetime(df["inicio"])
        df["hour"] = df["hour"] if "hour" in df.columns else df["inicio"].dt.hour
        df["weekday"] = df["weekday"] if "weekday" in df.columns else df["inicio"].dt.weekday
    else:
        # se não houver 'inicio', cria hora/weekday nulos
        df["hour"] = df.get("hour", pd.Series([np.nan]*len(df)))
        df["weekday"] = df.get("weekday", pd.Series([np.nan]*len(df)))

    # duration_sec
    if "duration_sec" not in df.columns:
        raise ValueError("Coluna 'duration_sec' ausente em data/clean.csv (verifique o ETL).")
    df["duration_sec"] = pd.to_numeric(df["duration_sec"], errors="coerce").fillna(0.0).clip(lower=0.0)

    # status → failed
    if "status" in df.columns:
        st = df["status"].astype(str).str.lower().str.strip()
        failed = st.eq("failed").astype(int)
    else:
        failed = pd.Series(np.zeros(len(df), dtype=int), index=df.index)

    # projeto/job para agregações
    if "projeto" not in df.columns: df["projeto"] = "UNKNOWN"
    if "job" not in df.columns: df["job"] = "UNKNOWN"

    # exec_id (prioriza campo existente; senão tenta job_id; se não houver, hash determinístico)
    if "exec_id" in df.columns:
        exec_id = df["exec_id"].astype(str).fillna("").str.strip()
    elif "job_id" in df.columns:
        exec_id = df["job_id"].astype(str).fillna("").str.strip()
    else:
        # cria id determinístico
        if "inicio" not in df.columns:
            df["inicio"] = pd.NaT
        exec_id = df.apply(_hash_exec_id, axis=1)

    # features
    duration_sec_mm = _minmax_01(df["duration_sec"])
    duration_z_clipped_mm = _zclip_to01(df["duration_sec"], clip=3.0)

    # hora e weekday (tratando NaN como 0)
    hour = pd.to_numeric(df["hour"], errors="coerce").fillna(0).clip(lower=0, upper=23)
    wday = pd.to_numeric(df["weekday"], errors="coerce").fillna(0).clip(lower=0, upper=6)

    hour_sin_mm, hour_cos_mm = _cyc_enc_01(hour, period=24)
    wday_sin_mm, wday_cos_mm = _cyc_enc_01(wday, period=7)

    high_runtime = _p95_flags_per_job(df, dur_col="duration_sec", key_cols=("projeto","job"))

    feats = pd.DataFrame({
        "exec_id": exec_id.astype(str),
        "duration_sec_mm": duration_sec_mm.astype(float),
        "duration_z_clipped_mm": duration_z_clipped_mm.astype(float),
        "hour_sin_mm": hour_sin_mm.astype(float),
        "hour_cos_mm": hour_cos_mm.astype(float),
        "wday_sin_mm": wday_sin_mm.astype(float),
        "wday_cos_mm": wday_cos_mm.astype(float),
        "failed": failed.astype(int),
        "high_runtime": high_runtime.astype(int),
    })

    # Diagnóstico rápido
    print("[features] linhas:", len(feats))
    print("[features] nulos por coluna:\n", feats.isna().sum())
    print("[features] amostra:\n", feats.head(3).to_string(index=False))

    # Grava
    Path(OUTPUT_FEATS).parent.mkdir(parents=True, exist_ok=True)
    feats.to_csv(OUTPUT_FEATS, index=False)
    print(f"[features] Gravado {OUTPUT_FEATS} com {len(feats.columns)-1} features (+ exec_id).")

if __name__ == "__main__":
    main()
