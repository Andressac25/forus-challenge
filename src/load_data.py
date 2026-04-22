"""
Carga, limpieza y creacion de BD SQLite in-memory para el challenge Forus.

Uso:
    from src.load_data import build_database, load_raw, DATA_DIR
    conn, datasets = build_database()

    # Query SQL
    df = pd.read_sql("SELECT * FROM ventas LIMIT 5", conn)

    # O acceso directo a los DataFrames limpios
    datasets["ventas_final"]
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


CADENA_COLORS = {
    "Nordica": "#1f77b4",
    "Summit": "#2ca02c",
    "Oceano": "#ff7f0e",
    "Urbana": "#9467bd",
}


def load_raw() -> dict[str, pd.DataFrame]:
    """Carga los 6 CSVs sin modificar."""
    names = ["tiendas", "ventas", "trafico", "presupuesto", "inventario", "productos"]
    return {n: pd.read_csv(DATA_DIR / f"{n}.csv") for n in names}


def clean_datasets(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Aplica limpieza estandar y retorna DataFrames listos para analisis.

    Tratamientos aplicados:
    - ventas: separa la fila de devolucion T009 2026-02-10 (-285000) en tabla devoluciones.
              ventas_final = ventas sin devoluciones.
    - trafico: marca nulls pero NO imputa (la imputacion se hace en vistas segun el uso).
    - fechas: parseadas como datetime64.
    """
    out: dict[str, pd.DataFrame] = {}

    tiendas = raw["tiendas"].copy()
    out["tiendas"] = tiendas

    ventas = raw["ventas"].copy()
    ventas["fecha"] = pd.to_datetime(ventas["fecha"])
    ventas["is_return"] = ventas["venta_neta"] < 0
    out["ventas"] = ventas
    out["devoluciones"] = ventas[ventas["is_return"]].copy().reset_index(drop=True)
    # ventas_final: "venta neta diaria" por tienda = suma de TODAS las filas del dia
    # (ventas brutas + devoluciones como negativas). Esto respeta la definicion
    # estandar de venta_neta = ingresos - devoluciones. La devolucion de T009
    # 2026-02-10 reduce la venta neta de ese dia de $1.414.010 a $1.129.010.
    out["ventas_final"] = (
        ventas.groupby(["fecha", "cod_local"], as_index=False)
        .agg(
            venta_neta=("venta_neta", "sum"),
            unidades=("unidades", "sum"),
            costo=("costo", "sum"),
            num_boletas=("num_boletas", "sum"),
        )
    )

    trafico = raw["trafico"].copy()
    trafico["fecha"] = pd.to_datetime(trafico["fecha"])
    trafico["is_missing"] = trafico["visitantes"].isna()
    out["trafico"] = trafico

    presupuesto = raw["presupuesto"].copy()
    presupuesto["fecha"] = pd.to_datetime(presupuesto["fecha"])
    out["presupuesto"] = presupuesto

    out["inventario"] = raw["inventario"].copy()

    productos = raw["productos"].copy()
    productos["fecha"] = pd.to_datetime(productos["fecha"])
    out["productos"] = productos

    return out


def impute_trafico(trafico: pd.DataFrame) -> pd.DataFrame:
    """
    Imputa visitantes NaN con la mediana por (tienda, DOW).

    Justificacion: T008 tiene nulls 2026-02-05/06/07. Esos son jue/vie/sab.
    Usamos la mediana del mismo DOW de la misma tienda (otras 2 semanas disponibles)
    para no sesgar con dias atipicos.
    """
    df = trafico.copy()
    df["dow"] = df["fecha"].dt.dayofweek
    medians = (
        df.dropna(subset=["visitantes"])
        .groupby(["cod_local", "dow"])["visitantes"]
        .median()
    )
    mask = df["visitantes"].isna()
    df.loc[mask, "visitantes"] = df.loc[mask].apply(
        lambda r: medians.get((r["cod_local"], r["dow"]), np.nan), axis=1
    )
    df["visitantes"] = df["visitantes"].astype(float)
    return df.drop(columns=["dow"])


def build_database(conn: sqlite3.Connection | None = None) -> tuple[sqlite3.Connection, dict[str, pd.DataFrame]]:
    """
    Crea una BD SQLite in-memory con los datasets limpios y vistas utiles.

    Retorna (conn, datasets) donde datasets es el dict de DataFrames limpios.
    """
    raw = load_raw()
    datasets = clean_datasets(raw)
    datasets["trafico_imputado"] = impute_trafico(datasets["trafico"])

    if conn is None:
        conn = sqlite3.connect(":memory:")

    for name in [
        "tiendas",
        "ventas",
        "ventas_final",
        "devoluciones",
        "trafico",
        "trafico_imputado",
        "presupuesto",
        "inventario",
        "productos",
    ]:
        df = datasets[name].copy()
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%Y-%m-%d")
            elif df[c].dtype == "bool":
                df[c] = df[c].astype(int)
        df.to_sql(name, conn, index=False, if_exists="replace")

    # Vista maestra dia x tienda con todas las metricas pre-calculadas
    conn.executescript(
        """
        DROP VIEW IF EXISTS v_dia_tienda;
        CREATE VIEW v_dia_tienda AS
        SELECT
            v.fecha,
            v.cod_local,
            t.nombre_tienda,
            t.cadena,
            t.zona,
            t.region,
            t.mall,
            t.tipo_tienda,
            CAST(strftime('%Y', v.fecha) AS INTEGER) AS anio,
            CAST(strftime('%w', v.fecha) AS INTEGER) AS dow,
            v.venta_neta,
            v.unidades,
            v.costo,
            v.num_boletas,
            tr.visitantes,
            CAST(v.venta_neta AS REAL) / NULLIF(v.num_boletas, 0) AS ticket_promedio,
            CAST(v.unidades AS REAL) / NULLIF(v.num_boletas, 0) AS upt,
            CAST(v.num_boletas AS REAL) / NULLIF(tr.visitantes, 0) AS conversion,
            (CAST(v.venta_neta AS REAL) - v.costo) / NULLIF(v.venta_neta, 0) AS margen_bruto
        FROM ventas_final v
        JOIN tiendas t USING (cod_local)
        LEFT JOIN trafico_imputado tr USING (fecha, cod_local);
        """
    )

    # Vista YoY: ventas 2026 vs 2025 por tienda (agregado quincena)
    conn.executescript(
        """
        DROP VIEW IF EXISTS v_yoy_tienda;
        CREATE VIEW v_yoy_tienda AS
        WITH agg AS (
            SELECT
                cod_local,
                anio,
                SUM(venta_neta)  AS venta,
                SUM(unidades)    AS unidades,
                SUM(num_boletas) AS boletas,
                SUM(costo)       AS costo,
                SUM(visitantes)  AS visitantes
            FROM v_dia_tienda
            GROUP BY cod_local, anio
        )
        SELECT
            a.cod_local,
            t.nombre_tienda,
            t.cadena,
            MAX(CASE WHEN a.anio = 2026 THEN a.venta      END) AS venta_2026,
            MAX(CASE WHEN a.anio = 2025 THEN a.venta      END) AS venta_2025,
            MAX(CASE WHEN a.anio = 2026 THEN a.unidades   END) AS unid_2026,
            MAX(CASE WHEN a.anio = 2025 THEN a.unidades   END) AS unid_2025,
            MAX(CASE WHEN a.anio = 2026 THEN a.boletas    END) AS bol_2026,
            MAX(CASE WHEN a.anio = 2025 THEN a.boletas    END) AS bol_2025,
            MAX(CASE WHEN a.anio = 2026 THEN a.visitantes END) AS traf_2026,
            MAX(CASE WHEN a.anio = 2025 THEN a.visitantes END) AS traf_2025,
            MAX(CASE WHEN a.anio = 2026 THEN a.costo      END) AS costo_2026,
            MAX(CASE WHEN a.anio = 2025 THEN a.costo      END) AS costo_2025
        FROM agg a
        JOIN tiendas t USING (cod_local)
        GROUP BY a.cod_local, t.nombre_tienda, t.cadena;
        """
    )

    return conn, datasets


if __name__ == "__main__":
    conn, datasets = build_database()
    print("Tablas creadas en SQLite in-memory:")
    for row in conn.execute("SELECT name, type FROM sqlite_master ORDER BY type, name"):
        print(f"  {row[1]:6s}  {row[0]}")
    print()
    print("Shape por dataset:")
    for name, df in datasets.items():
        print(f"  {name:20s}  shape={df.shape}")
    print()
    print("Primera fila de v_dia_tienda:")
    print(pd.read_sql("SELECT * FROM v_dia_tienda LIMIT 1", conn).T)
