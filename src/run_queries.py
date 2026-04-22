"""
Ejecuta las queries de queries.sql, imprime resultados y valida paridad con pandas.

Uso:
    python3 src/run_queries.py

Guarda CSVs de resultado en outputs/tables/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.load_data import build_database, ROOT

TABLES_DIR = ROOT / "outputs" / "tables"
TABLES_DIR.mkdir(parents=True, exist_ok=True)


def split_sql(path: Path) -> list[tuple[str, str]]:
    """Divide el archivo SQL en (titulo, sentencia) por secciones delimitadas."""
    text = path.read_text()
    # Secciones delimitadas por bloque de --- y un -- 1.X titulo
    blocks = re.split(r"^-- -{50,}\s*\n-- (?P<t>[^\n]+)\s*\n-- -{50,}\s*\n", text, flags=re.M)
    # split devuelve [prefijo, titulo, cuerpo, titulo, cuerpo, ...]
    out: list[tuple[str, str]] = []
    for i in range(1, len(blocks), 2):
        titulo = blocks[i].strip()
        cuerpo = blocks[i + 1]
        # Quedarse solo con lo que viene antes de la siguiente sentencia (todo)
        out.append((titulo, cuerpo.strip()))
    return out


def print_section(title: str, df: pd.DataFrame) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")
    with pd.option_context("display.max_columns", None, "display.width", 200, "display.float_format", lambda v: f"{v:,.2f}"):
        print(df.to_string(index=False))


def main() -> None:
    conn, datasets = build_database()
    sql_path = ROOT / "src" / "queries.sql"
    sections = split_sql(sql_path)

    results: dict[str, pd.DataFrame] = {}
    for title, sql in sections:
        df = pd.read_sql(sql, conn)
        results[title] = df
        print_section(title, df)
        # Slug para CSV
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:60]
        df.to_csv(TABLES_DIR / f"{slug}.csv", index=False)

    # ==========================================================
    # Paridad SQL vs pandas: el sanity check que exige el plan
    # ==========================================================
    print("\n" + "=" * 80)
    print("PARIDAD SQL vs PANDAS (sanity checks)")
    print("=" * 80)

    vf = datasets["ventas_final"].copy()
    vf["fecha"] = pd.to_datetime(vf["fecha"])
    vf["anio"] = vf["fecha"].dt.year
    t = datasets["tiendas"]
    merged = vf.merge(t, on="cod_local", how="left")

    # Check 1.1: venta total y ticket por cadena 2026
    q11_pd = (
        merged[merged["anio"] == 2026]
        .groupby("cadena")
        .agg(venta_2026=("venta_neta", "sum"),
             bol_2026=("num_boletas", "sum"),
             unid_2026=("unidades", "sum"))
        .assign(ticket=lambda x: (x["venta_2026"] / x["bol_2026"]).round(0))
        .reset_index()
        .sort_values("venta_2026", ascending=False)
    )
    q11_sql = results["1.1 Ranking de cadenas (Feb 2026) + YoY"][
        ["cadena", "venta_2026", "unid_2026", "ticket_promedio"]
    ]
    check1 = np.allclose(
        q11_sql["venta_2026"].to_numpy(),
        q11_pd.set_index("cadena").reindex(q11_sql["cadena"])["venta_2026"].to_numpy(),
    )
    print(f"  [1.1] venta cadena paridad SQL=pandas: {'OK' if check1 else 'FAIL'}")

    # Check 1.2: la tienda con mayor caida YoY
    yoy_pd = (
        merged.groupby(["cod_local", "nombre_tienda", "cadena", "anio"])["venta_neta"]
        .sum()
        .unstack("anio")
        .assign(yoy=lambda x: (x[2026] - x[2025]) / x[2025] * 100)
        .sort_values("yoy")
        .head(5)
        .reset_index()
    )
    top5_sql = results["1.2 Top 5 tiendas con mayor caida YoY en venta neta"]
    check2 = list(yoy_pd["cod_local"]) == list(top5_sql["nombre_tienda"].map(
        datasets["tiendas"].set_index("nombre_tienda")["cod_local"]
    ))
    print(f"  [1.2] top5 tiendas caida paridad SQL=pandas: {'OK' if check2 else 'FAIL'}")

    # Check 1.4: cumplimiento top-1
    ppto_sum = datasets["presupuesto"].groupby("cod_local")["presupuesto_venta"].sum()
    venta_sum_2026 = merged[merged["anio"] == 2026].groupby("cod_local")["venta_neta"].sum()
    cumplimiento = (venta_sum_2026 / ppto_sum * 100).sort_values(ascending=False)
    top1_pd = cumplimiento.index[0]
    top1_sql = results["1.4 Cumplimiento de presupuesto por tienda (Feb 2026) + clasificacion"]["cod_local"].iloc[0]
    print(f"  [1.4] top1 cumplimiento SQL={top1_sql} pandas={top1_pd}: {'OK' if top1_sql == top1_pd else 'FAIL'}")

    print("\nResultados guardados en outputs/tables/")
    print("Done.")


if __name__ == "__main__":
    main()
