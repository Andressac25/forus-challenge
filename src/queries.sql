-- ============================================================
-- Challenge Forus - Queries SQL Parte 1
-- Motor: SQLite (compatible con Postgres salvo strftime)
-- Dependencias: tablas creadas por src/load_data.py
--   ventas_final (sin devoluciones)
--   tiendas, trafico_imputado, presupuesto, inventario, productos
--   vistas: v_dia_tienda, v_yoy_tienda
-- ============================================================

-- ------------------------------------------------------------
-- 1.1 Ranking de cadenas (Feb 2026) + YoY
-- ------------------------------------------------------------
-- Venta neta total, unidades, ticket promedio y variacion YoY vs Feb 2025.
-- Extra (profundidad): margen bruto y participacion % del total retail.
WITH actual AS (
    SELECT
        cadena,
        SUM(venta_neta)  AS venta_2026,
        SUM(unidades)    AS unid_2026,
        SUM(num_boletas) AS bol_2026,
        SUM(costo)       AS costo_2026
    FROM v_dia_tienda
    WHERE anio = 2026
    GROUP BY cadena
),
anterior AS (
    SELECT cadena, SUM(venta_neta) AS venta_2025
    FROM v_dia_tienda
    WHERE anio = 2025
    GROUP BY cadena
),
total AS (
    SELECT SUM(venta_2026) AS venta_total FROM actual
)
SELECT
    a.cadena,
    a.venta_2026,
    a.unid_2026,
    ROUND(CAST(a.venta_2026 AS REAL) / NULLIF(a.bol_2026, 0), 0)           AS ticket_promedio,
    ROUND((a.venta_2026 - p.venta_2025) * 100.0 / NULLIF(p.venta_2025, 0), 2) AS yoy_pct,
    ROUND((a.venta_2026 - a.costo_2026) * 100.0 / NULLIF(a.venta_2026, 0), 2) AS margen_bruto_pct,
    ROUND(a.venta_2026 * 100.0 / t.venta_total, 2)                          AS participacion_pct
FROM actual a
JOIN anterior p USING (cadena)
CROSS JOIN total t
ORDER BY a.venta_2026 DESC;


-- ------------------------------------------------------------
-- 1.2 Top 5 tiendas con mayor caida YoY en venta neta
-- ------------------------------------------------------------
-- Extra (profundidad): caida absoluta en CLP y contribucion % de la cadena.
WITH tienda_yoy AS (
    SELECT
        cod_local,
        nombre_tienda,
        cadena,
        venta_2026,
        venta_2025,
        (venta_2026 - venta_2025) AS delta_clp,
        ROUND((venta_2026 - venta_2025) * 100.0 / NULLIF(venta_2025, 0), 2) AS yoy_pct
    FROM v_yoy_tienda
),
cadena_caida AS (
    SELECT cadena, SUM(CASE WHEN delta_clp < 0 THEN delta_clp ELSE 0 END) AS caida_cadena
    FROM tienda_yoy
    GROUP BY cadena
)
SELECT
    t.nombre_tienda,
    t.cadena,
    t.venta_2026,
    t.venta_2025,
    t.yoy_pct,
    t.delta_clp,
    ROUND(t.delta_clp * 100.0 / NULLIF(c.caida_cadena, 0), 2) AS pct_caida_cadena
FROM tienda_yoy t
JOIN cadena_caida c USING (cadena)
WHERE t.yoy_pct IS NOT NULL
ORDER BY t.yoy_pct ASC
LIMIT 5;


-- ------------------------------------------------------------
-- 1.3 Patron semanal - venta neta promedio por DOW (Feb 2026)
-- ------------------------------------------------------------
-- dow SQLite: 0=Dom, 1=Lun, ..., 6=Sab. Renombramos a Lun..Dom.
-- Extra (profundidad): participacion % del total semanal y comparacion YoY.
WITH por_dow AS (
    SELECT
        CAST(strftime('%w', fecha) AS INTEGER) AS dow,
        anio,
        SUM(venta_neta) AS venta_total,
        COUNT(DISTINCT fecha) AS dias
    FROM v_dia_tienda
    GROUP BY dow, anio
),
pivot AS (
    SELECT
        dow,
        MAX(CASE WHEN anio = 2026 THEN venta_total END) AS venta_2026,
        MAX(CASE WHEN anio = 2026 THEN dias        END) AS dias_2026,
        MAX(CASE WHEN anio = 2025 THEN venta_total END) AS venta_2025,
        MAX(CASE WHEN anio = 2025 THEN dias        END) AS dias_2025
    FROM por_dow
    GROUP BY dow
),
total_semana AS (
    SELECT SUM(venta_2026) AS total_2026 FROM pivot
)
SELECT
    CASE p.dow
        WHEN 0 THEN '7-Dom' WHEN 1 THEN '1-Lun' WHEN 2 THEN '2-Mar' WHEN 3 THEN '3-Mie'
        WHEN 4 THEN '4-Jue' WHEN 5 THEN '5-Vie' WHEN 6 THEN '6-Sab'
    END AS dia_semana,
    ROUND(CAST(p.venta_2026 AS REAL) / NULLIF(p.dias_2026, 0), 0) AS venta_prom_2026,
    ROUND(CAST(p.venta_2025 AS REAL) / NULLIF(p.dias_2025, 0), 0) AS venta_prom_2025,
    ROUND((CAST(p.venta_2026 AS REAL) / NULLIF(p.dias_2026,0) -
           CAST(p.venta_2025 AS REAL) / NULLIF(p.dias_2025,0)) * 100.0
          / NULLIF(CAST(p.venta_2025 AS REAL) / NULLIF(p.dias_2025,0), 0), 2) AS yoy_pct,
    ROUND(p.venta_2026 * 100.0 / ts.total_2026, 2) AS pct_total_semana
FROM pivot p
CROSS JOIN total_semana ts
ORDER BY p.dow;


-- ------------------------------------------------------------
-- 1.4 Cumplimiento de presupuesto por tienda (Feb 2026) + clasificacion
-- ------------------------------------------------------------
-- Window function RANK() sobre % cumplimiento.
-- Extra (profundidad): gap en CLP y conversion promedio para diagnosticar driver.
WITH agg AS (
    SELECT
        v.cod_local,
        t.nombre_tienda,
        t.cadena,
        SUM(v.venta_neta)        AS venta_2026,
        SUM(p.presupuesto_venta) AS presup_2026,
        SUM(v.num_boletas)       AS boletas,
        SUM(tr.visitantes)       AS visitantes
    FROM ventas_final v
    JOIN tiendas t USING (cod_local)
    LEFT JOIN presupuesto p USING (fecha, cod_local)
    LEFT JOIN trafico_imputado tr USING (fecha, cod_local)
    WHERE strftime('%Y', v.fecha) = '2026'
    GROUP BY v.cod_local, t.nombre_tienda, t.cadena
)
SELECT
    cod_local,
    nombre_tienda,
    cadena,
    venta_2026,
    presup_2026,
    ROUND(venta_2026 * 100.0 / NULLIF(presup_2026, 0), 2) AS pct_cumplimiento,
    (venta_2026 - presup_2026) AS gap_clp,
    RANK() OVER (ORDER BY venta_2026 * 1.0 / NULLIF(presup_2026, 0) DESC) AS ranking,
    CASE
        WHEN venta_2026 * 1.0 / NULLIF(presup_2026, 0) >= 1.00 THEN 'Sobre meta'
        WHEN venta_2026 * 1.0 / NULLIF(presup_2026, 0) >= 0.90 THEN 'En riesgo'
        ELSE 'Bajo meta'
    END AS clasificacion,
    ROUND(boletas * 100.0 / NULLIF(visitantes, 0), 2) AS conv_pct
FROM agg
ORDER BY pct_cumplimiento DESC;


-- ------------------------------------------------------------
-- Q_BONUS_1: Customer Quality Score
-- ------------------------------------------------------------
-- Cruza conversion x ticket x UPT x margen en un score comparable.
-- Insight no preguntado: hay tiendas con baja venta pero alto margen / conversion.
WITH tienda_metrics AS (
    SELECT
        t.cod_local,
        t.nombre_tienda,
        t.cadena,
        t.tipo_tienda,
        SUM(v.venta_neta)                                           AS venta,
        SUM(v.num_boletas)                                          AS boletas,
        SUM(tr.visitantes)                                          AS visitantes,
        SUM(v.unidades)                                             AS unidades,
        SUM(v.costo)                                                AS costo,
        CAST(SUM(v.num_boletas) AS REAL) / NULLIF(SUM(tr.visitantes), 0) AS conv,
        CAST(SUM(v.venta_neta)  AS REAL) / NULLIF(SUM(v.num_boletas), 0) AS ticket,
        CAST(SUM(v.unidades)    AS REAL) / NULLIF(SUM(v.num_boletas), 0) AS upt,
        (SUM(v.venta_neta) - SUM(v.costo)) * 1.0 / NULLIF(SUM(v.venta_neta), 0) AS margen
    FROM tiendas t
    JOIN ventas_final v USING (cod_local)
    LEFT JOIN trafico_imputado tr USING (fecha, cod_local)
    WHERE strftime('%Y', v.fecha) = '2026'
    GROUP BY t.cod_local, t.nombre_tienda, t.cadena, t.tipo_tienda
)
SELECT
    cod_local,
    nombre_tienda,
    cadena,
    tipo_tienda,
    ROUND(conv   * 100, 2)  AS conv_pct,
    ROUND(ticket)           AS ticket_prom,
    ROUND(upt, 2)           AS upt,
    ROUND(margen * 100, 2)  AS margen_pct,
    ROUND(conv * ticket * upt * margen, 0) AS quality_score
FROM tienda_metrics
ORDER BY quality_score DESC;


-- ------------------------------------------------------------
-- Q_BONUS_2: Oceano - descomposicion de drivers de caida YoY
-- ------------------------------------------------------------
-- Atribuye la caida total en cada tienda a cambios en tr x conv x ticket x UPT.
WITH por_anio AS (
    SELECT
        cod_local,
        cadena,
        anio,
        SUM(venta_neta)                                           AS venta,
        SUM(unidades)                                             AS unidades,
        SUM(num_boletas)                                          AS boletas,
        SUM(visitantes)                                           AS visitantes,
        SUM(num_boletas) * 1.0 / NULLIF(SUM(visitantes), 0)       AS conv,
        SUM(venta_neta) * 1.0 / NULLIF(SUM(num_boletas), 0)       AS ticket,
        SUM(unidades) * 1.0 / NULLIF(SUM(num_boletas), 0)         AS upt
    FROM v_dia_tienda
    WHERE cadena = 'Oceano'
    GROUP BY cod_local, cadena, anio
)
SELECT
    a.cod_local,
    ROUND(b.visitantes) AS traf_2025, ROUND(a.visitantes) AS traf_2026,
    ROUND((a.visitantes - b.visitantes) * 100.0 / NULLIF(b.visitantes, 0), 2) AS d_trafico_pct,
    ROUND(b.conv * 100, 2) AS conv_2025_pct, ROUND(a.conv * 100, 2) AS conv_2026_pct,
    ROUND((a.conv - b.conv) * 100.0 / NULLIF(b.conv, 0), 2) AS d_conv_pct,
    ROUND(b.ticket) AS ticket_2025, ROUND(a.ticket) AS ticket_2026,
    ROUND((a.ticket - b.ticket) * 100.0 / NULLIF(b.ticket, 0), 2) AS d_ticket_pct,
    ROUND((a.venta - b.venta)) AS delta_venta_clp,
    ROUND((a.venta - b.venta) * 100.0 / NULLIF(b.venta, 0), 2) AS yoy_pct
FROM por_anio a
JOIN por_anio b USING (cod_local)
WHERE a.anio = 2026 AND b.anio = 2025
ORDER BY a.cod_local;
