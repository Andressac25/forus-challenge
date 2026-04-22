"""
Analisis exploratorio profundo (Parte 2 + insights para Parte 3).

Genera:
- outputs/figures/*.png      -> charts de alta calidad para embeber en el .md
- outputs/tables/*.csv        -> tablas intermedias usadas en el reporte
- Imprime hallazgos clave en stdout

Uso:
    python3 src/analysis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.load_data import CADENA_COLORS, ROOT, build_database

FIG_DIR = ROOT / "outputs" / "figures"
TAB_DIR = ROOT / "outputs" / "tables"
FIG_DIR.mkdir(parents=True, exist_ok=True)
TAB_DIR.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["font.family"] = "DejaVu Sans"


def save(fig: plt.Figure, name: str) -> Path:
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def fmt_clp(v: float) -> str:
    return f"${v:,.0f}".replace(",", ".")


# ============================================================
# 2.1 ANOMALIAS
# ============================================================
def anomalias(datasets: dict[str, pd.DataFrame]) -> None:
    section("2.1 ANOMALIAS EN LOS DATOS")

    ventas = datasets["ventas"]
    trafico = datasets["trafico"]
    productos = datasets["productos"]

    # Anomalia 1: devolucion T009
    dev = datasets["devoluciones"]
    print(f"\n[A1] Fila con venta negativa (devolucion) en ventas.csv:")
    print(dev.to_string(index=False))

    # Anomalia 2: nulls en trafico
    null_traf = trafico[trafico["visitantes"].isna()]
    print(f"\n[A2] Tráfico con valores null (sensor caido):")
    print(null_traf.to_string(index=False))

    # Anomalia 3: outliers estadisticos (z-score) por tienda-metrica
    vf = datasets["ventas_final"].copy()
    vf["z_venta"] = vf.groupby("cod_local")["venta_neta"].transform(
        lambda s: (s - s.mean()) / s.std(ddof=0)
    )
    outliers = vf[vf["z_venta"].abs() > 2].copy()
    print(f"\n[A3] Outliers de venta (|z-score| > 2 intra-tienda):")
    print(outliers[["fecha", "cod_local", "venta_neta", "z_venta"]]
          .sort_values("z_venta", key=abs, ascending=False)
          .head(10).to_string(index=False))

    # Anomalia 4: inventario T008 vs T007 (mismo ratio DDI)
    inv = datasets["inventario"]
    inv["ddi"] = inv["stock_unidades"] / inv["venta_promedio_diaria_unidades"]
    print(f"\n[A4] DDI extremo en Oceano (T007 sobre-stock / T008 quiebre):")
    print(inv[inv["cod_local"].isin(["T007", "T008", "T009"])].to_string(index=False))

    # Anomalia 5: productos solo tiene 4 tiendas pero el challenge dice ~192 filas
    print(f"\n[A5] Cobertura de productos.csv:")
    print(f"  Tiendas con detalle SKU: {sorted(productos['cod_local'].unique().tolist())}")
    print(f"  Filas: {len(productos)} (esperado ~192)")

    # Guardar tabla de anomalias
    anomalias_tbl = pd.DataFrame([
        ["A1", "ventas.csv", "T009 2026-02-10", "Venta negativa -285.000 CLP (devolucion)",
         "Separar como devoluciones, no incluir en agregados de venta bruta"],
        ["A2", "trafico.csv", "T008 2026-02-05 a 07", "3 dias sin visitantes (sensor caido)",
         "Imputar con mediana por DOW de la misma tienda (otras 2 semanas disponibles)"],
        ["A3", "ventas.csv", "Sab 2026-02-07 en T001/T010", "Outliers positivos (+45% / +35% vs media)",
         "NO remover: es el evento Costanera (senal real). Analizar por separado"],
        ["A4", "inventario.csv", "T007 DDI=72.5 / T008 DDI=6.5", "Desbalance extremo intra-cadena Oceano",
         "Flag de riesgo operacional. Analizar redistribucion de stock"],
        ["A5", "productos.csv", "Solo T001/T004/T007/T010", "Cobertura parcial (4 de 12 tiendas)",
         "Documentar como limitante. No extrapolar conclusiones SKU al resto"],
    ], columns=["id", "tabla", "registros", "hallazgo", "tratamiento"])
    anomalias_tbl.to_csv(TAB_DIR / "2_1_anomalias.csv", index=False)


# ============================================================
# 2.2 DIAGNOSTICO OCEANO
# ============================================================
def diagnostico_oceano(conn, datasets: dict[str, pd.DataFrame]) -> None:
    section("2.2 DIAGNOSTICO OCEANO - analisis de drivers")

    # Descomposicion YoY por tienda
    q = """
    WITH a AS (
        SELECT cod_local, anio,
               SUM(venta_neta)   AS venta,
               SUM(unidades)     AS unidades,
               SUM(num_boletas)  AS boletas,
               SUM(visitantes)   AS visitantes,
               SUM(costo)        AS costo
        FROM v_dia_tienda
        WHERE cadena = 'Oceano'
        GROUP BY cod_local, anio
    )
    SELECT cod_local, anio, venta, unidades, boletas, visitantes, costo,
           boletas * 1.0 / NULLIF(visitantes, 0) AS conv,
           venta   * 1.0 / NULLIF(boletas, 0)    AS ticket,
           unidades * 1.0 / NULLIF(boletas, 0)   AS upt,
           (venta - costo) * 1.0 / NULLIF(venta, 0) AS margen
    FROM a ORDER BY cod_local, anio;
    """
    drv = pd.read_sql(q, conn)
    drv_wide = drv.pivot(index="cod_local", columns="anio").reset_index()
    drv_wide.columns = ["cod_local"] + [f"{a}_{b}" for a, b in drv_wide.columns[1:]]

    # Atribucion (log-decomposition): log(V2026/V2025) = log(T) + log(C) + log(Ti) + log(UPT)
    # OJO: V = Traf * Conv * Ticket; Upt no entra en venta monetaria
    def log_delta(curr, prev):
        return np.log(curr / prev) * 100

    for m in ["visitantes", "conv", "ticket", "venta"]:
        drv_wide[f"ln_{m}_pct"] = log_delta(drv_wide[f"{m}_2026"], drv_wide[f"{m}_2025"])

    drv_wide["check_suma"] = (drv_wide["ln_visitantes_pct"] + drv_wide["ln_conv_pct"] +
                              drv_wide["ln_ticket_pct"])
    print("\nDescomposicion log-YoY (Oceano). Suma ln(traf)+ln(conv)+ln(ticket) == ln(venta):")
    cols = ["cod_local", "venta_2025", "venta_2026", "ln_visitantes_pct",
            "ln_conv_pct", "ln_ticket_pct", "ln_venta_pct", "check_suma"]
    print(drv_wide[cols].round(2).to_string(index=False))

    drv_wide.to_csv(TAB_DIR / "2_2_oceano_drivers.csv", index=False)

    # Venta perdida estimada T008 por quiebre
    inv = datasets["inventario"]
    ddi_t008 = inv[inv["cod_local"] == "T008"].iloc[0]
    ddi_t007 = inv[inv["cod_local"] == "T007"].iloc[0]
    print(f"\nVenta perdida estimada T008 (Plaza Oeste) por quiebre:")
    print(f"  Stock: {ddi_t008['stock_unidades']} uds / vta diaria prom: {ddi_t008['venta_promedio_diaria_unidades']} => DDI={ddi_t008['stock_unidades']/ddi_t008['venta_promedio_diaria_unidades']:.1f} dias")
    print(f"  Comparativo T007 (misma cadena): DDI={ddi_t007['stock_unidades']/ddi_t007['venta_promedio_diaria_unidades']:.1f} dias (exceso de 40+ dias)")

    # Charts Oceano
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    colors = {"T007": "#ff7f0e", "T008": "#d62728", "T009": "#ffbb78"}

    # Chart 1: drivers bar comparativo
    drivers_df = drv_wide.set_index("cod_local")[["ln_visitantes_pct", "ln_conv_pct", "ln_ticket_pct"]]
    drivers_df.columns = ["Δ Tráfico", "Δ Conversión", "Δ Ticket"]
    drivers_df.plot(kind="bar", ax=axes[0], color=["#1f77b4", "#2ca02c", "#d62728"], width=0.7)
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].set_title("Oceano — Descomposición YoY (log-delta %)", fontsize=13)
    axes[0].set_xlabel("Tienda"); axes[0].set_ylabel("Contribución log-% al cambio")
    axes[0].legend(loc="best", fontsize=10)
    axes[0].tick_params(axis="x", rotation=0)

    # Chart 2: DDI stacked bars
    ddi = inv.copy()
    ddi["ddi"] = ddi["stock_unidades"] / ddi["venta_promedio_diaria_unidades"]
    ddi = ddi.merge(datasets["tiendas"][["cod_local", "cadena", "nombre_tienda"]], on="cod_local")
    ddi_sorted = ddi.sort_values("ddi")
    bars = axes[1].barh(ddi_sorted["cod_local"], ddi_sorted["ddi"],
                        color=[CADENA_COLORS[c] for c in ddi_sorted["cadena"]])
    axes[1].axvline(30, ls="--", color="gray", alpha=0.7, label="Zona sana 30d")
    axes[1].axvline(60, ls="--", color="red", alpha=0.5, label="Sobrestock 60d+")
    axes[1].set_title("DDI por tienda (días de inventario)", fontsize=13)
    axes[1].set_xlabel("Días")
    axes[1].legend(loc="lower right", fontsize=9)
    for bar, v in zip(bars, ddi_sorted["ddi"]):
        axes[1].text(v + 1, bar.get_y() + bar.get_height()/2, f"{v:.1f}",
                     va="center", fontsize=9)

    fig.tight_layout()
    save(fig, "fig_oceano_drivers_y_ddi")

    # Productos T007 (unica tienda Oceano con detalle SKU)
    prod = datasets["productos"]
    t007_prod = prod[prod["cod_local"] == "T007"].groupby("clase").agg(
        unidades=("unidades", "sum"),
        venta=("venta_neta", "sum"),
        costo=("costo", "sum"),
    )
    t007_prod["ticket_medio"] = t007_prod["venta"] / t007_prod["unidades"]
    t007_prod["participacion_pct"] = t007_prod["venta"] * 100 / t007_prod["venta"].sum()
    print(f"\nMix T007 (Oceano Mall Marina) por clase:")
    print(t007_prod.round(0).to_string())


# ============================================================
# 2.3 EVENTO COSTANERA
# ============================================================
def evento_costanera(conn, datasets: dict[str, pd.DataFrame]) -> None:
    section("2.3 EVENTO COSTANERA - Sab 7-feb 2026")

    # Comparativa sabados
    q = """
    SELECT fecha, cod_local, nombre_tienda, cadena,
           venta_neta, num_boletas, visitantes, costo,
           ticket_promedio, upt, conversion, margen_bruto
    FROM v_dia_tienda
    WHERE cod_local IN ('T001','T010')
      AND (fecha = '2026-02-07' OR fecha = '2026-02-14' OR fecha = '2025-02-08' OR fecha = '2025-02-01')
    ORDER BY cod_local, fecha;
    """
    df = pd.read_sql(q, conn)
    print("\nSabados comparables (evento + control + dobles-control YoY):")
    print(df.round(3).to_string(index=False))

    # Impacto evento vs control (14-feb) por tienda
    pivot = df[df["fecha"].isin(["2026-02-07", "2026-02-14"])].set_index(["cod_local", "fecha"])
    print("\nImpacto evento (7-feb vs control 14-feb):")
    for tienda in ["T001", "T010"]:
        ev = pivot.loc[(tienda, "2026-02-07")]
        ctrl = pivot.loc[(tienda, "2026-02-14")]
        d_venta = ev["venta_neta"] - ctrl["venta_neta"]
        d_traf = ev["visitantes"] - ctrl["visitantes"]
        d_bol = ev["num_boletas"] - ctrl["num_boletas"]
        d_conv = ev["conversion"] - ctrl["conversion"]
        d_ticket = ev["ticket_promedio"] - ctrl["ticket_promedio"]
        d_margen_clp = (ev["venta_neta"] - ev["costo"]) - (ctrl["venta_neta"] - ctrl["costo"])
        print(f"  {tienda}:")
        print(f"    ΔVenta    : {fmt_clp(d_venta)} ({d_venta/ctrl['venta_neta']*100:+.1f}%)")
        print(f"    ΔTrafico  : {d_traf:+.0f} ({d_traf/ctrl['visitantes']*100:+.1f}%)")
        print(f"    ΔBoletas  : {d_bol:+.0f} ({d_bol/ctrl['num_boletas']*100:+.1f}%)")
        print(f"    ΔConv     : {d_conv*100:+.2f} pp (de {ctrl['conversion']*100:.1f}% a {ev['conversion']*100:.1f}%)")
        print(f"    ΔTicket   : {fmt_clp(d_ticket)} ({d_ticket/ctrl['ticket_promedio']*100:+.1f}%)")
        print(f"    ΔMargen bruto (CLP incremental): {fmt_clp(d_margen_clp)}")

    # Canibalizacion: comparar 14-feb 2026 vs 14-feb 2025 en T001/T010 vs el resto
    q2 = """
    SELECT cod_local, cadena, anio, SUM(venta_neta) AS venta, SUM(visitantes) AS traf
    FROM v_dia_tienda
    WHERE strftime('%Y-%m-%d', fecha) IN ('2026-02-14', '2025-02-14')
    GROUP BY cod_local, cadena, anio;
    """
    canib = pd.read_sql(q2, conn)
    canib_p = canib.pivot(index=["cod_local", "cadena"], columns="anio").reset_index()
    canib_p.columns = ["cod_local", "cadena"] + [f"{a}_{b}" for a, b in canib_p.columns[2:]]
    canib_p["yoy_venta_14feb"] = (canib_p["venta_2026"] / canib_p["venta_2025"] - 1) * 100
    print("\nYoY 14-feb (sab siguiente al evento) — ¿canibalizacion en T001/T010?")
    print(canib_p[["cod_local", "cadena", "venta_2025", "venta_2026", "yoy_venta_14feb"]]
          .sort_values("yoy_venta_14feb").round(1).to_string(index=False))

    # Chart evento
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    eventos = pivot.reset_index()

    # Venta
    plot_df = eventos[["cod_local", "fecha", "venta_neta"]].pivot(
        index="cod_local", columns="fecha", values="venta_neta")
    plot_df.columns = ["Sab 7-feb (evento)", "Sab 14-feb (control)"]
    plot_df.plot(kind="bar", ax=axes[0], color=["#d62728", "#1f77b4"], width=0.7)
    axes[0].set_title("Venta neta", fontsize=12)
    axes[0].set_ylabel("CLP"); axes[0].tick_params(axis="x", rotation=0)
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1e6:.0f}M"))

    # Trafico
    plot_df2 = eventos[["cod_local", "fecha", "visitantes"]].pivot(
        index="cod_local", columns="fecha", values="visitantes")
    plot_df2.columns = ["Sab 7-feb (evento)", "Sab 14-feb (control)"]
    plot_df2.plot(kind="bar", ax=axes[1], color=["#d62728", "#1f77b4"], width=0.7)
    axes[1].set_title("Tráfico (visitantes)", fontsize=12)
    axes[1].set_ylabel("Visitantes"); axes[1].tick_params(axis="x", rotation=0)

    # Conversion
    plot_df3 = eventos[["cod_local", "fecha", "conversion"]].pivot(
        index="cod_local", columns="fecha", values="conversion") * 100
    plot_df3.columns = ["Sab 7-feb (evento)", "Sab 14-feb (control)"]
    plot_df3.plot(kind="bar", ax=axes[2], color=["#d62728", "#1f77b4"], width=0.7)
    axes[2].set_title("Conversión (%)", fontsize=12)
    axes[2].set_ylabel("%"); axes[2].tick_params(axis="x", rotation=0)

    fig.suptitle("Evento Costanera — 7-feb (evento) vs 14-feb (control)", fontsize=14, y=1.02)
    fig.tight_layout()
    save(fig, "fig_evento_costanera")


# ============================================================
# CHARTS GENERALES para Parte 1
# ============================================================
def charts_generales(conn, datasets: dict[str, pd.DataFrame]) -> None:
    section("CHARTS GENERALES (para embeber en la Parte 1)")

    # Chart 1: Ranking cadenas YoY
    q = """
    WITH agg AS (
        SELECT cadena, anio, SUM(venta_neta) AS venta
        FROM v_dia_tienda GROUP BY cadena, anio
    )
    SELECT cadena,
           MAX(CASE WHEN anio=2026 THEN venta END) AS v2026,
           MAX(CASE WHEN anio=2025 THEN venta END) AS v2025
    FROM agg GROUP BY cadena;
    """
    ranking = pd.read_sql(q, conn).set_index("cadena")
    ranking["yoy_pct"] = (ranking["v2026"] / ranking["v2025"] - 1) * 100
    ranking = ranking.sort_values("v2026", ascending=True)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    colors = [CADENA_COLORS[c] for c in ranking.index]
    axes[0].barh(ranking.index, ranking["v2026"] / 1e6, color=colors)
    axes[0].barh(ranking.index, ranking["v2025"] / 1e6, color="gray", alpha=0.35, label="2025")
    axes[0].set_title("Venta neta por cadena 2026 (color) vs 2025 (gris)")
    axes[0].set_xlabel("MM CLP")
    axes[0].legend(loc="lower right")

    axes[1].barh(ranking.index, ranking["yoy_pct"], color=[
        "green" if v > 0 else "red" for v in ranking["yoy_pct"]])
    for i, (idx, v) in enumerate(ranking["yoy_pct"].items()):
        axes[1].text(v + (1 if v >= 0 else -1), i, f"{v:+.1f}%",
                     va="center", ha="left" if v >= 0 else "right", fontsize=11)
    axes[1].axvline(0, color="black", lw=0.8)
    axes[1].set_title("Variación YoY de venta neta")
    axes[1].set_xlabel("%")
    fig.tight_layout(); save(fig, "fig_ranking_cadenas")

    # Chart 2: Patron semanal
    q = """
    SELECT CAST(strftime('%w', fecha) AS INT) AS dow, anio,
           SUM(venta_neta) AS venta, COUNT(DISTINCT fecha) AS dias
    FROM v_dia_tienda GROUP BY dow, anio;
    """
    sem = pd.read_sql(q, conn)
    sem["venta_prom"] = sem["venta"] / sem["dias"]
    sem_p = sem.pivot(index="dow", columns="anio", values="venta_prom") / 1e6
    dias_nombre = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
    sem_p.index = [dias_nombre[i] for i in sem_p.index]
    # Reordenar Lun-Dom
    sem_p = sem_p.reindex(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"])

    fig, ax = plt.subplots(figsize=(10, 4.5))
    sem_p.plot(kind="bar", ax=ax, color=["gray", "#1f77b4"], width=0.75)
    ax.set_title("Venta neta promedio por día de la semana")
    ax.set_xlabel(""); ax.set_ylabel("MM CLP (promedio)")
    ax.tick_params(axis="x", rotation=0)
    ax.legend(["2025", "2026"])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:.0f}M"))
    fig.tight_layout(); save(fig, "fig_patron_semanal")

    # Chart 3: Cumplimiento presupuesto
    q = """
    WITH agg AS (
        SELECT v.cod_local, t.nombre_tienda, t.cadena,
               SUM(v.venta_neta) AS venta,
               SUM(p.presupuesto_venta) AS presup
        FROM ventas_final v
        JOIN tiendas t USING (cod_local)
        LEFT JOIN presupuesto p USING (fecha, cod_local)
        WHERE strftime('%Y', v.fecha) = '2026'
        GROUP BY v.cod_local, t.nombre_tienda, t.cadena
    )
    SELECT cod_local, nombre_tienda, cadena,
           venta * 1.0 / NULLIF(presup, 0) * 100 AS pct
    FROM agg ORDER BY pct ASC;
    """
    cump = pd.read_sql(q, conn)
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = [
        "#d62728" if v < 90 else "#ff7f0e" if v < 100 else "#2ca02c"
        for v in cump["pct"]
    ]
    ax.barh(cump["nombre_tienda"], cump["pct"], color=colors)
    ax.axvline(90, ls="--", color="orange", alpha=0.6, label="Meta riesgo 90%")
    ax.axvline(100, ls="--", color="green", alpha=0.6, label="Meta 100%")
    for i, v in enumerate(cump["pct"]):
        ax.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=10)
    ax.set_title("Cumplimiento presupuesto por tienda — Feb 2026")
    ax.set_xlabel("% cumplimiento")
    ax.legend(loc="lower right")
    fig.tight_layout(); save(fig, "fig_cumplimiento_presupuesto")


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    conn, datasets = build_database()
    anomalias(datasets)
    diagnostico_oceano(conn, datasets)
    evento_costanera(conn, datasets)
    charts_generales(conn, datasets)
    print(f"\nCharts guardados en {FIG_DIR}")
    print(f"Tablas guardadas en {TAB_DIR}")


if __name__ == "__main__":
    main()
