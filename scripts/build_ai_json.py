#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera ai_analysis.json a partir de:
  data/execucoes.csv (projeto, job, exec_id, inicio, status, duracao_s)
  data/score.csv     (exec_id, re)
"""

import argparse, json, sys
from pathlib import Path
import pandas as pd
import numpy as np

def _fail(msg: str, code: int = 2):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(code)

def _read_execucoes(exec_path: Path) -> pd.DataFrame:
    df = pd.read_csv(exec_path, dtype=str, keep_default_na=False, na_values=["", "NA", "NaN"])
    # normaliza cabeçalhos comuns (aliases) -> nomes esperados
    lower = {c.lower().strip(): c for c in df.columns}
    rename = {}
    if "project" in lower:      rename[lower["project"]]      = "projeto"
    if "job_name" in lower:     rename[lower["job_name"]]     = "job"
    if "start_time" in lower:   rename[lower["start_time"]]   = "inicio"
    if "duration_sec" in lower: rename[lower["duration_sec"]] = "duracao_s"
    df = df.rename(columns=rename)

    required = ["projeto", "job", "exec_id", "inicio", "status", "duracao_s"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        _fail(f"Coluna obrigatória ausente em execucoes.csv: {', '.join(missing)}")

    # tipos mínimos
    df["duracao_s"] = pd.to_numeric(df["duracao_s"], errors="coerce")
    try:
        df["inicio"] = pd.to_datetime(df["inicio"], errors="coerce", dayfirst=True)
    except Exception:
        pass

    # limpeza
    df["exec_id"] = df["exec_id"].astype(str).str.strip()
    df = df[df["exec_id"].notna() & (df["exec_id"] != "")]
    return df

def _read_score(score_path: Path) -> pd.DataFrame:
    df = pd.read_csv(score_path, dtype=str, keep_default_na=False, na_values=["", "NA", "NaN"])
    if "exec_id" not in df.columns or "re" not in df.columns:
        _fail("Colunas obrigatórias ausentes em score.csv: exec_id, re")
    df["exec_id"] = df["exec_id"].astype(str).str.strip()
    df["re"] = pd.to_numeric(df["re"], errors="coerce")
    df = df[df["exec_id"].notna() & (df["exec_id"] != "")]
    df = df[df["re"].notna()]
    return df

def build_analysis(df_exec: pd.DataFrame, df_score: pd.DataFrame) -> dict:
    df = df_exec.merge(df_score[["exec_id", "re"]], on="exec_id", how="left")

    total = len(df)
    por_status = df["status"].fillna("desconhecido").value_counts(dropna=False).to_dict()
    duracao_med = float(np.nanmean(df["duracao_s"])) if "duracao_s" in df else None
    re_p95_global = float(np.nanpercentile(df["re"], 95)) if df["re"].notna().any() else None

    resumo = {
        "total_execucoes": int(total),
        "por_status": por_status,
        "duracao_media_s": None if (duracao_med is None or np.isnan(duracao_med)) else duracao_med,
        "re_p95_global": re_p95_global,
    }

    chave_job = ["projeto","job"] if all(c in df.columns for c in ["projeto","job"]) else ["job"]
    risco_p95_por_job = (
        df.dropna(subset=["re"]).groupby(chave_job)["re"].quantile(0.95)
          .reset_index().rename(columns={"re":"re_p95"})
          .sort_values("re_p95", ascending=False).head(200)
          .to_dict(orient="records")
    )

    def _ser(v):
        if pd.isna(v): return None
        return v.isoformat() if hasattr(v,"isoformat") else v

    hotspots = (
        df.dropna(subset=["re"])
          .sort_values("re", ascending=False)
          .loc[:, ["projeto","job","exec_id","inicio","status","duracao_s","re"]]
          .head(50).to_dict(orient="records")
    )
    hotspots = [
        {"projeto":h.get("projeto"), "job":h.get("job"), "exec_id":h.get("exec_id"),
         "inicio":_ser(h.get("inicio")), "status":h.get("status"),
         "duracao_s": None if pd.isna(h.get("duracao_s")) else float(h.get("duracao_s")),
         "re": float(h.get("re"))}
        for h in hotspots
    ]

    return {
        "resumo": resumo,
        "risco_p95_por_job": risco_p95_por_job,
        "hotspots": hotspots,
        "top_amostras": hotspots[:100],
    }

def main():
    ap = argparse.ArgumentParser(description="Gera ai_analysis.json a partir de .csv em 'data/'.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="app/ai_analysis.json")  # padrão canônico
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    exec_path = data_dir / "execucoes.csv"
    score_path = data_dir / "score.csv"

    if not exec_path.exists():
        _fail(f"Arquivo obrigatório não encontrado: {exec_path}")
    if not score_path.exists():
        _fail(f"Arquivo obrigatório não encontrado: {score_path}")

    df_exec = _read_execucoes(exec_path)
    df_score = _read_score(score_path)

    result = build_analysis(df_exec, df_score)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "status": "ok",
        "out": str(out_path),
        "resumo": result["resumo"],
        "counts": {
            "hotspots": len(result["hotspots"]),
            "risco_p95_por_job": len(result["risco_p95_por_job"]),
            "top_amostras": len(result["top_amostras"])
        }
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
