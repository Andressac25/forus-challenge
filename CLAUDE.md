# CLAUDE.md — Challenge Técnico Data Analyst · Forus

Contexto y guía para Claude Code al trabajar en este repositorio.

---

## 1. Contexto del challenge

Challenge técnico de Data Analyst para **Forus** (retail de moda en Chile). Analizamos la primera quincena de febrero 2026 vs la misma quincena de 2025 para evaluar desempeño operacional.

- **12 tiendas**, **4 cadenas**: Nordica, Summit, Oceano, Urbana
- **3 regiones**: Metropolitana, Valparaíso, Biobío
- **Períodos**: 1–14 feb 2026 (actual) vs 1–14 feb 2025 (anterior)
- **Plazo**: 3 días corridos desde recepción del PDF
- **Entregable oficial**: `challenge-andres-albornoz.md`

Distribución de puntos: SQL 40% · Análisis exploratorio 35% · Negocio + IA 25%. Bonus: notebook reproducible + 1 query extra.

---

## 2. Datasets (carpeta `data/`)

| Archivo | Filas | Grano | Columnas clave | Rango fechas |
|---|---|---|---|---|
| `tiendas.csv` | 12 | 1 fila × tienda | cod_local, nombre_tienda, cadena, zona, región, mall, tipo_tienda | — |
| `ventas.csv` | ~337 | tienda × día | fecha, cod_local, venta_neta, unidades, costo, num_boletas | 2025-02-01 a 2025-02-14 + 2026-02-01 a 2026-02-14 |
| `trafico.csv` | ~336 | tienda × día | fecha, cod_local, visitantes | idem |
| `presupuesto.csv` | 168 | tienda × día | fecha, cod_local, presupuesto_venta, presupuesto_unidades | **solo 2026** |
| `inventario.csv` | 12 | 1 fila × tienda | cod_local, stock_unidades, costo_inventario, venta_promedio_diaria_unidades | snapshot puntual |
| `productos.csv` | ~192 | tienda × día × SKU | fecha, cod_local, sku, nombre_producto, clase, unidades, venta_neta, costo | solo 2026, solo T001/T004/T007/T010 |

**Relaciones** (schema): `cod_local` es la clave que une todo. `ventas`, `trafico`, `presupuesto` se unen por `(fecha, cod_local)`. `inventario` y `tiendas` por `cod_local`. `productos` se une a `ventas` por `(fecha, cod_local)` pero sólo cubre 4 tiendas.

---

## 3. Métricas clave (fórmulas del enunciado)

| Métrica | Fórmula |
|---|---|
| Ticket promedio | `venta_neta / num_boletas` |
| UPT | `unidades / num_boletas` |
| Conversión | `num_boletas / visitantes` |
| Cumplimiento presupuesto | `venta_neta / presupuesto_venta` |
| DDI (Días De Inventario) | `stock_unidades / venta_promedio_diaria_unidades` |
| Margen bruto | `(venta_neta - costo) / venta_neta` |
| Variación YoY | `(actual - anterior) / anterior` |

**Regla crítica**: toda división debe usar `NULLIF(denominador, 0)` en SQL o `np.where(denom==0, np.nan, num/denom)` en pandas para no reventar.

---

## 4. Hallazgos preliminares (validados sobre los CSVs)

Estos puntos ya están confirmados vía exploración directa — no especulación:

### Anomalías de datos
1. **Venta negativa en T009 (Oceano Outlet)**: `ventas.csv` contiene la fila `2026-02-10, T009, -285000, -2, -165000, 1`. Es una devolución (return) registrada como venta negativa. **Debe mantenerse en el cálculo** (la columna se llama `venta_neta` — ingresos menos devoluciones), pero agregar por `(fecha, cod_local)` para unificar con la venta bruta del mismo día (queda venta neta diaria = $1.129.010 en vez de $1.414.010 bruta). También flaguear como `is_return` para análisis diagnóstico separado.
2. **3 nulls de tráfico en T008 (Oceano Plaza Oeste)**: los días 2026-02-05, 06, 07 no tienen visitantes registrados aunque sí hay ventas. Probable sensor caído. Imputar con mediana por DOW de la misma tienda o excluir esos días del cálculo de conversión.

### Inventario (DDI por tienda)

| Tienda | Cadena | Stock | Vta/día prom | DDI | Estado |
|---|---|---|---|---|---|
| T001 | Nordica | 4200 | 130 | 32.3 | Sano |
| T002 | Nordica | 3600 | 115 | 31.3 | Sano |
| T003 | Nordica | 2800 | 100 | 28.0 | Sano |
| T004 | Summit | 3100 | 85 | 36.5 | Sano |
| T005 | Summit | 2400 | 72 | 33.3 | Sano |
| T006 | Summit | 1800 | 60 | 30.0 | Sano |
| **T007** | **Oceano** | **5800** | **80** | **72.5** | **Sobre-stock crítico** |
| **T008** | **Oceano** | **420** | **65** | **6.5** | **Quiebre inminente** |
| T009 | Oceano | 3200 | 90 | 35.6 | Sano |
| T010 | Urbana | 2900 | 95 | 30.5 | Sano |
| T011 | Urbana | 2200 | 80 | 27.5 | Sano |
| T012 | Urbana | 1100 | 48 | 22.9 | Sano |

### YoY Feb 2026 vs Feb 2025 — Oceano
- T007: 46.6M → 41.6M (**-10.8%**)
- T008: 33.4M → 30.2M (**-9.4%**)
- T009: 27.5M → 25.1M (**-8.85%**)

Toda la cadena Oceano cae. No es una tienda puntual — es sistémico + problema de inventario asimétrico (T007 sobra, T008 falta).

### Evento Costanera — sábado 7-feb 2026 (T001 Nordica + T010 Urbana)

| Tienda | Sáb 14-feb (control) | Sáb 7-feb (evento) | Δ tráfico | Δ venta | Conversión |
|---|---|---|---|---|---|
| T001 | 7.68M / 475 traf / 114 bol | 11.15M / 798 traf / 133 bol | **+68%** | **+45%** | **24% → 17%** (cae 7pp) |
| T010 | 5.05M / 403 traf / 81 bol | 6.82M / 621 traf / 102 bol | **+54%** | **+35%** | **20% → 16%** (cae 4pp) |

**Insight**: el evento generó tráfico incremental pero la conversión bajó. El evento atrajo curiosos, no compradores — la operación no supo convertir esa demanda extra.

---

## 5. Stack técnico

- **Python 3.10+**
- **Carga/limpieza**: `pandas`
- **SQL**: `sqlite3` **in-memory** (window functions disponibles, sin setup externo)
- **Visualización estática**: `matplotlib` + `seaborn`
- **Dashboard interactivo**: `streamlit`
- **Notebook**: `jupyter` (reproducible end-to-end)

Dependencias mínimas instalables con:
```bash
pip install pandas numpy matplotlib seaborn jupyter streamlit ipykernel
```

---

## 6. Skills instaladas (ver `.claude/skills/`)

25 skills de 5 grupos. Cada una vive en `.claude/skills/<nombre>/SKILL.md` y se invoca bajo demanda.

### Grupo 1 — Anthropic oficiales (`github.com/anthropics/skills`)
| Skill | Para qué sirve | Cuándo invocarla |
|---|---|---|
| **xlsx** | Lee/edita/crea Excel y CSV, fórmulas, pivots, charts nativos | Si el usuario pide exportar tablas a Excel |
| **pdf** | Genera PDFs con charts, tablas, layouts ejecutivos | Export del reporte final |
| **pptx** | PowerPoint con charts, layouts profesionales | Slides ejecutivas (bonus) |

### Grupo 2 — Data analytics (`github.com/nimrodfisher/data-analytics-skills`)
| Skill | Para qué sirve | Cuándo invocarla |
|---|---|---|
| **programmatic-eda** | EDA sistemático con sanity checks | Primer pase sobre datasets nuevos |
| **data-quality-audit** | Auditoría reglas negocio (nulls, dup, rangos, FK) | Parte 2.1 anomalías |
| **query-validation** | Revisa SQL: correctness + performance + NULLs | Antes de entregar queries Parte 1 |
| **schema-mapper** | Mapea FK/relaciones entre tablas | Documentar joins de los 6 CSVs |
| **metric-reconciliation** | Discrepancias misma métrica en fuentes diferentes | Validar unidades `ventas` vs `productos` |
| **root-cause-investigation** | 5-why + descomposición de drivers | Parte 2.2 Oceano (driver analysis) |
| **time-series-analysis** | Estacionalidad, DOW, tendencia | Parte 1.3 patrón semanal |
| **business-metrics-calculator** | Ticket, UPT, conversión, margen, DDI, cumplim. | Unifica fórmulas en todo el análisis |
| **insight-synthesis** | Hallazgos → argumentos de negocio | Parte 3.1 recomendaciones |
| **executive-summary-generator** | TL;DR + bullets + next steps | Sección inicial del `challenge.md` |
| **visualization-builder** | Selección correcta de chart type | Qué gráfico usar para cada insight |
| **dashboard-specification** | Specs de dashboards ejecutivos | Diseño del Streamlit |

### Grupo 3 — Anomalías + SQL opt (`github.com/jeremylongshore/claude-code-plugins-plus-skills`)
| Skill | Para qué sirve | Cuándo invocarla |
|---|---|---|
| **anomaly-detector** | Isolation Forest, One-Class SVM, z-score, IQR | Parte 2.1 detección estadística de outliers |
| **sql-query-optimizer** | Reescribe SQL para performance y claridad | Optimizar window functions 1.4 |

### Grupo 4 — Visualización científica (`github.com/K-Dense-AI/claude-scientific-skills`)
| Skill | Para qué sirve | Cuándo invocarla |
|---|---|---|
| **matplotlib** | Bar, line, heatmap, subplots 300+ DPI | Charts estáticos del notebook |
| **seaborn** | Plots estadísticos (boxplot, heatmap, pairplot) | Heatmaps conversión día×tienda |
| **scientific-visualization** | Helpers publicación + paletas colorblind | Estilo consistente profesional |
| **statistical-analysis** | Tests, IC, significancia | Validar si diferencias YoY son significativas |

### Grupo 5 — Streamlit (`github.com/streamlit/agent-skills`)
| Skill | Para qué sirve | Cuándo invocarla |
|---|---|---|
| **building-streamlit-dashboards** | KPI cards, metrics, layouts ejecutivos | Dashboard principal |
| **displaying-streamlit-data** | DataFrames, column config, charts inline | Tablas interactivas |
| **using-streamlit-layouts** | Sidebar/columns/tabs/containers | Estructura por secciones |
| **creating-streamlit-themes** | Theming branded | Look profesional |

---

## 7. Estructura de archivos

```
Challenge Forus v/
├── CLAUDE.md                       (este archivo)
├── FORUS_Data_Analyst_Challenge.pdf (enunciado)
├── .claude/skills/                 (25 skills instaladas)
├── data/                           (6 CSVs originales, read-only)
├── notebooks/
│   └── challenge.ipynb             (notebook reproducible end-to-end)
├── src/
│   ├── load_data.py                (load + limpieza + SQLite in-memory)
│   ├── queries.sql                 (queries Parte 1 + bonus)
│   └── dashboard.py                (Streamlit)
├── outputs/
│   ├── figures/                    (PNGs embebidos en el .md)
│   └── tables/                     (CSVs de resultados)
└── challenge-andres-albornoz.md    (entregable final)
```

---

## 8. Reglas de análisis — "profundidad máxima"

Instrucción explícita del usuario: actuar como **equipo completo de Data Scientists**. Eso significa:

1. **Nunca quedarse en la superficie.** Toda respuesta debe explicar el **por qué** al menos 2 niveles de profundidad. Ejemplo: "Oceano cae 10% YoY → porque conversión cae → porque el mix sobre-stockeado no matchea demanda → porque parkas fuera de temporada ocupan espacio de best-sellers de verano".
2. **Cruzar siempre ≥2 tablas.** Ventas sola no dice nada; hay que juntar con tráfico (para conversión), inventario (para stockout), presupuesto (para gap), productos (para mix).
3. **Validar outliers estadísticamente** (z-score, IQR), no solo visualmente.
4. **Paridad SQL ↔ pandas.** Cada resultado SQL se verifica con pandas — si difieren, hay un bug en uno de los dos.
5. **Controles múltiples.** Para el evento Costanera no basta con comparar vs el otro sábado; también vs sábado 7-feb 2025 (control YoY) y vs el promedio de otros sábados.
6. **Descomposición de drivers** cuando hay variación: ΔVenta = ΔTráfico × ΔConversión × ΔTicket × ΔUPT. No basta decir "ventas cayeron".
7. **Cuantificar impacto en CLP**, no sólo en %. Un 10% de caída en Nordica Costanera vale más que un 10% en Urbana Plaza Egaña.
8. **Recomendaciones accionables**: cada una debe tener (hallazgo concreto, acción concreta, métrica objetivo con número).

---

## 9. Convenciones

- **Moneda**: CLP (pesos chilenos). Formato display: `$1.234.567` (separador miles con `.`, no `,`).
- **Locale**: es-CL.
- **Días de la semana**: Lunes a Domingo (semana chilena estándar).
- **Colores por cadena** (usar siempre los mismos en todos los charts):
  - Nordica → `#1f77b4` (azul)
  - Summit → `#2ca02c` (verde)
  - Oceano → `#ff7f0e` (naranja) *[cadena con problema, resaltada]*
  - Urbana → `#9467bd` (violeta)
- **Nombres de queries**: `q1_1_ranking_cadenas`, `q1_2_top5_caidas`, `q1_3_patron_semanal`, `q1_4_cumplimiento`, `q_bonus_<tema>`.
- **Charts**: guardar en `outputs/figures/` con slug descriptivo (`fig_yoy_cadenas.png`, `fig_oceano_drivers.png`, etc.) a 300 DPI.

---

## 10. Criterios de evaluación (del PDF)

| Criterio | Peso | Qué se evalúa |
|---|---|---|
| SQL | 40% | Queries correctas, eficientes, legibles. CTEs, window functions, manejo NULLs |
| Análisis | 35% | Encontrar patrones, manejar anomalías, argumentar con datos |
| Negocio + IA | 25% | Recomendaciones accionables, uso inteligente de IA, validación de outputs |

**Bonus no requerido (haremos ambos):**
- Notebook Jupyter reproducible
- 1+ query extra con insight no preguntado
