"""
Dashboard Streamlit - Challenge Forus Data Analyst.

Ejecutar:
    streamlit run src/dashboard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.load_data import CADENA_COLORS, build_database


st.set_page_config(
    page_title="Forus Retail Intelligence",
    page_icon="📊",
    layout="wide",
)


@st.cache_data
def load():
    conn, datasets = build_database()
    dia = pd.read_sql("SELECT * FROM v_dia_tienda", conn)
    dia["fecha"] = pd.to_datetime(dia["fecha"])
    yoy = pd.read_sql("SELECT * FROM v_yoy_tienda", conn)
    presup = datasets["presupuesto"]
    inventario = datasets["inventario"].copy()
    inventario["ddi"] = inventario["stock_unidades"] / inventario["venta_promedio_diaria_unidades"]
    inventario = inventario.merge(datasets["tiendas"], on="cod_local")
    productos = datasets["productos"]
    return dia, yoy, presup, inventario, productos


dia, yoy, presup, inventario, productos = load()

# --- Sidebar filters ---
st.sidebar.title("🧭 Filtros")
cadenas = st.sidebar.multiselect(
    "Cadena", sorted(dia["cadena"].unique()), default=sorted(dia["cadena"].unique())
)
regiones = st.sidebar.multiselect(
    "Región", sorted(dia["region"].unique()), default=sorted(dia["region"].unique())
)
tiendas_opts = sorted(dia[dia["cadena"].isin(cadenas) & dia["region"].isin(regiones)]["cod_local"].unique())
tiendas_sel = st.sidebar.multiselect("Tienda", tiendas_opts, default=tiendas_opts)

mask = dia["cadena"].isin(cadenas) & dia["region"].isin(regiones) & dia["cod_local"].isin(tiendas_sel)
df = dia[mask].copy()

st.title("📊 Forus Retail Intelligence — Feb 2026 vs 2025")
st.caption("Dashboard ejecutivo del challenge Data Analyst. 12 tiendas · 4 cadenas · 3 regiones.")

tabs = st.tabs(["📈 Overview", "🏆 Ranking cadenas", "🎯 Cumplimiento", "🌊 Oceano drill-down", "🎪 Evento Costanera"])

# ============================================================
# TAB 1: OVERVIEW
# ============================================================
with tabs[0]:
    df_2026 = df[df["anio"] == 2026]
    df_2025 = df[df["anio"] == 2025]

    col1, col2, col3, col4 = st.columns(4)
    v26 = df_2026["venta_neta"].sum()
    v25 = df_2025["venta_neta"].sum()
    yoy_pct = (v26 - v25) / v25 * 100 if v25 else 0
    col1.metric("Venta neta 2026", f"${v26/1e6:,.1f}M", f"{yoy_pct:+.1f}% YoY")

    margen = (df_2026["venta_neta"].sum() - df_2026["costo"].sum()) / df_2026["venta_neta"].sum() * 100
    col2.metric("Margen bruto 2026", f"{margen:.1f}%")

    trafic_26 = df_2026["visitantes"].sum()
    col3.metric("Tráfico 2026", f"{trafic_26:,.0f}")

    conv = df_2026["num_boletas"].sum() / df_2026["visitantes"].sum() * 100
    col4.metric("Conversión global", f"{conv:.1f}%")

    st.divider()

    # Evolucion diaria 2026 vs 2025
    daily = df.groupby(["fecha", "anio"])["venta_neta"].sum().reset_index()
    daily["dia_mes"] = daily["fecha"].dt.day
    fig_d = px.line(
        daily, x="dia_mes", y="venta_neta", color="anio",
        title="Venta diaria — Feb 2026 vs 2025",
        color_discrete_map={2026: "#1f77b4", 2025: "#999999"},
        labels={"venta_neta": "Venta neta (CLP)", "dia_mes": "Día del mes", "anio": "Año"},
    )
    fig_d.update_traces(mode="lines+markers")
    st.plotly_chart(fig_d, use_container_width=True)

    # Heatmap conversion dia x tienda
    st.subheader("Heatmap — Conversión diaria por tienda (2026)")
    hm = df_2026.pivot_table(
        index="cod_local", columns=df_2026["fecha"].dt.day,
        values="conversion", aggfunc="mean"
    ) * 100
    fig_hm = px.imshow(
        hm, text_auto=".1f", aspect="auto",
        color_continuous_scale="RdYlGn",
        labels=dict(x="Día", y="Tienda", color="Conv %"),
    )
    st.plotly_chart(fig_hm, use_container_width=True)


# ============================================================
# TAB 2: RANKING CADENAS
# ============================================================
with tabs[1]:
    st.subheader("Ranking de cadenas — Feb 2026")
    cad = df_2026.groupby("cadena").agg(
        venta=("venta_neta", "sum"),
        unidades=("unidades", "sum"),
        boletas=("num_boletas", "sum"),
        costo=("costo", "sum"),
    ).reset_index()
    cad_ant = df_2025.groupby("cadena")["venta_neta"].sum().rename("venta_2025").reset_index()
    cad = cad.merge(cad_ant, on="cadena")
    cad["ticket"] = cad["venta"] / cad["boletas"]
    cad["yoy_pct"] = (cad["venta"] - cad["venta_2025"]) / cad["venta_2025"] * 100
    cad["margen_pct"] = (cad["venta"] - cad["costo"]) / cad["venta"] * 100
    cad = cad.sort_values("venta", ascending=False)

    st.dataframe(
        cad[["cadena", "venta", "venta_2025", "yoy_pct", "unidades", "ticket", "margen_pct"]],
        column_config={
            "venta": st.column_config.NumberColumn("Venta 2026", format="$%d"),
            "venta_2025": st.column_config.NumberColumn("Venta 2025", format="$%d"),
            "yoy_pct": st.column_config.NumberColumn("YoY %", format="%.2f%%"),
            "ticket": st.column_config.NumberColumn("Ticket prom", format="$%d"),
            "margen_pct": st.column_config.NumberColumn("Margen %", format="%.2f%%"),
        },
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(cad, x="cadena", y="venta", color="cadena",
                     color_discrete_map=CADENA_COLORS, title="Venta 2026 por cadena")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(cad, x="cadena", y="yoy_pct", color="yoy_pct",
                     color_continuous_scale="RdYlGn", title="YoY % por cadena")
        fig.add_hline(y=0, line_dash="dash")
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 3: CUMPLIMIENTO
# ============================================================
with tabs[2]:
    st.subheader("Cumplimiento de presupuesto — Feb 2026")
    df_p = df_2026.groupby("cod_local").agg(
        venta=("venta_neta", "sum"),
        nombre_tienda=("nombre_tienda", "first"),
        cadena=("cadena", "first"),
    ).reset_index()
    presup_agg = presup.groupby("cod_local")["presupuesto_venta"].sum().reset_index()
    df_p = df_p.merge(presup_agg, on="cod_local")
    df_p["cumplimiento"] = df_p["venta"] / df_p["presupuesto_venta"] * 100
    df_p["gap"] = df_p["venta"] - df_p["presupuesto_venta"]
    df_p["clasificacion"] = pd.cut(
        df_p["cumplimiento"], bins=[-1, 90, 100, 1000],
        labels=["Bajo meta", "En riesgo", "Sobre meta"]
    )
    df_p = df_p.sort_values("cumplimiento", ascending=False)

    col1, col2, col3 = st.columns(3)
    col1.metric("Sobre meta", (df_p["clasificacion"] == "Sobre meta").sum())
    col2.metric("En riesgo", (df_p["clasificacion"] == "En riesgo").sum())
    col3.metric("Bajo meta", (df_p["clasificacion"] == "Bajo meta").sum())

    color_map = {"Sobre meta": "#2ca02c", "En riesgo": "#ff7f0e", "Bajo meta": "#d62728"}
    fig = px.bar(
        df_p.sort_values("cumplimiento"), x="cumplimiento", y="nombre_tienda",
        color="clasificacion", color_discrete_map=color_map, orientation="h",
        title="% Cumplimiento por tienda",
    )
    fig.add_vline(x=100, line_dash="dash", line_color="green")
    fig.add_vline(x=90, line_dash="dash", line_color="orange")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df_p, use_container_width=True)


# ============================================================
# TAB 4: OCEANO
# ============================================================
with tabs[3]:
    st.subheader("🌊 Diagnóstico cadena Oceano — descomposición YoY")
    oc = df[df["cadena"] == "Oceano"].copy()
    agg = oc.groupby(["cod_local", "anio"]).agg(
        venta=("venta_neta", "sum"),
        boletas=("num_boletas", "sum"),
        traf=("visitantes", "sum"),
        unidades=("unidades", "sum"),
    ).reset_index()
    import numpy as np
    agg["conv"] = agg["boletas"] / agg["traf"]
    agg["ticket"] = agg["venta"] / agg["boletas"]
    pivot = agg.pivot(index="cod_local", columns="anio")
    pivot.columns = [f"{m}_{a}" for m, a in pivot.columns]
    for m in ["traf", "conv", "ticket", "venta"]:
        pivot[f"ln_{m}"] = np.log(pivot[f"{m}_2026"] / pivot[f"{m}_2025"]) * 100
    drivers = pivot[["ln_traf", "ln_conv", "ln_ticket"]].reset_index()
    drivers.columns = ["cod_local", "Δ Tráfico (log%)", "Δ Conversión (log%)", "Δ Ticket (log%)"]
    drivers_m = drivers.melt(id_vars="cod_local", var_name="driver", value_name="valor")

    col1, col2 = st.columns([2, 1])
    with col1:
        fig = px.bar(drivers_m, x="cod_local", y="valor", color="driver", barmode="group",
                     title="Descomposición log-YoY por tienda Oceano",
                     color_discrete_map={
                         "Δ Tráfico (log%)": "#1f77b4",
                         "Δ Conversión (log%)": "#2ca02c",
                         "Δ Ticket (log%)": "#d62728",
                     })
        fig.add_hline(y=0)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        inv_oceano = inventario[inventario["cadena"] == "Oceano"]
        fig = px.bar(inv_oceano, x="cod_local", y="ddi", color="ddi",
                     color_continuous_scale="RdYlGn_r",
                     title="DDI Oceano (días de inventario)")
        fig.add_hline(y=30, line_dash="dash")
        fig.add_hline(y=60, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    **Lectura rápida:**
    - **T007 Mall Marina** — driver principal es **ticket (-9.2%)**: probablemente liquidación por sobrestock (DDI 72.5d).
    - **T008 Plaza Oeste** — mixto ticket + tráfico. Stock crítico (DDI 6.5d) perdiendo ventas.
    - **T009 Outlet Buenaventura** — driver es **tráfico (-9.0%)**: pierde atractivo, no es problema operativo.
    """)

    # Mix T007
    t007_prod = productos[productos["cod_local"] == "T007"].groupby("clase").agg(
        unidades=("unidades", "sum"),
        venta=("venta_neta", "sum"),
    ).reset_index()
    fig = px.pie(t007_prod, values="venta", names="clase",
                 title="Mix de venta T007 por clase — Parkas (27%) en Feb = desajuste de temporada")
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 5: COSTANERA
# ============================================================
with tabs[4]:
    st.subheader("🎪 Evento Costanera — Sáb 7-feb 2026")
    cost = df[df["cod_local"].isin(["T001", "T010"])].copy()
    cost_sab = cost[cost["fecha"].isin(pd.to_datetime(["2026-02-07", "2026-02-14"]))].copy()
    cost_sab["label"] = cost_sab["fecha"].dt.strftime("%d-%b") + cost_sab["fecha"].dt.strftime(" %a")

    col1, col2, col3 = st.columns(3)
    for tienda, c in zip(["T001", "T010"], [col1, col2]):
        ev = cost_sab[(cost_sab["cod_local"] == tienda) & (cost_sab["fecha"] == "2026-02-07")].iloc[0]
        ct = cost_sab[(cost_sab["cod_local"] == tienda) & (cost_sab["fecha"] == "2026-02-14")].iloc[0]
        d_venta = ev["venta_neta"] - ct["venta_neta"]
        margen_incr = (ev["venta_neta"] - ev["costo"]) - (ct["venta_neta"] - ct["costo"])
        c.metric(f"{tienda} — ΔVenta evento", f"${d_venta/1e6:.2f}M",
                 f"+{(d_venta/ct['venta_neta'])*100:.0f}%")
        c.metric(f"{tienda} — Margen incremental", f"${margen_incr/1e6:.2f}M")

    col3.metric("Margen total incremental del evento",
                f"${(cost_sab[cost_sab['fecha'] == '2026-02-07']['venta_neta'].sum() - cost_sab[cost_sab['fecha'] == '2026-02-07']['costo'].sum()) - (cost_sab[cost_sab['fecha'] == '2026-02-14']['venta_neta'].sum() - cost_sab[cost_sab['fecha'] == '2026-02-14']['costo'].sum()):,.0f}")

    fig = px.bar(
        cost_sab, x="cod_local", y=["venta_neta", "visitantes"],
        facet_col="label", title="Comparativo evento (7-feb) vs control (14-feb)",
        barmode="group",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Conversion
    cost_sab["conv_pct"] = cost_sab["conversion"] * 100
    fig = px.bar(
        cost_sab, x="cod_local", y="conv_pct", color="label",
        barmode="group", title="Conversión %: cae en el evento a pesar del tráfico extra",
        color_discrete_map={"07-Feb Sat": "#d62728", "14-Feb Sat": "#1f77b4"},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.info("""
    **Insight clave**: el evento trajo +68% tráfico en T001 y +54% en T010, pero
    **la conversión cayó** (T001: 24%→17%, T010: 20%→16%). La gente entró pero no compró al
    mismo ritmo. **Sí fue comercialmente positivo**: margen bruto incremental de ~$2.4M CLP
    combinado. Pero se perdió una parte del potencial por no prepararse para la demanda extra.
    """)
