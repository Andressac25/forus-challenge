# Handoff de QA — correcciones al entregable Forus

**Para:** la próxima instancia de Claude Code que trabaje sobre este proyecto
**De:** una instancia previa que hizo una revisión QA profunda de [challenge-andres-albornoz.md](challenge-andres-albornoz.md) contra los CSVs crudos de [data/](data/)
**Objetivo:** aplicar **solo los cambios listados abajo**. El 98% del entregable es correcto y no debe tocarse.

---

## Cómo usar este documento

1. Lee el resumen de la sección "Contexto" para entender qué se verificó y cómo.
2. Aplica las correcciones en orden de severidad (Crítico → Alto → Medio → Bajo → Observación).
3. Cada corrección tiene: (a) el bloque exacto que existe hoy en el `.md`, (b) el bloque de reemplazo, (c) la justificación con el cálculo que la respalda.
4. **No modifiques nada que no esté en esta lista.** La sección "Qué NO cambiar" al final es explícita.
5. Al terminar, re-lee el entregable y verifica que las frases del TL;DR y síntesis queden consistentes con los números corregidos.

Herramientas sugeridas: `Read` + `Edit` de Claude Code. Todos los `old_string` abajo son literales del archivo actual y únicos.

---

## Contexto — cómo se hizo la verificación

- **Datasets:** 6 CSVs en [data/](data/) (`ventas.csv` 337 filas, `trafico.csv` 336 filas con 3 nulls, `presupuesto.csv` 168 filas, `inventario.csv` 12 filas, `productos.csv` 192 filas, `tiendas.csv` 12 filas). Los conteos coinciden con el PDF del challenge.
- **Método:** para cada tabla, dato y conclusión numérica del entregable, se recomputó la misma métrica con Python + pandas sobre los CSVs crudos y se comparó valor a valor.
- **Lo que quedó verificado ✅:** las 4 queries SQL (1.1–1.4), toda la descomposición log-delta de Oceano en 2.2, la tabla comparativa cruda del evento Costanera en 2.3, los montos de margen incremental ($1.56M + $882K = $2.44M), YoY 14-feb (canibalización), y el bonus quality score completo.
- **Lo que hay que corregir ❌:** 5 errores y 4 observaciones, detallados abajo.

---

## Correcciones (aplicar en este orden)

### 🔴 Corrección 1 — [CRÍTICO] Anomalía A2: valores imputados T008 incorrectos en el texto

**Sección:** Parte 2.1, anomalía A2 (Tráfico faltante en T008).

**Ubicación aproximada:** línea 284 de [challenge-andres-albornoz.md](challenge-andres-albornoz.md).

**Problema:** el texto dice que los 3 días imputados quedan con "**170, 185 y 280** visitantes". La conversión de T008 = 17.73% reportada en la tabla 1.4 **solo cuadra si los valores imputados son 207, 268 y 299** (mediana DOW cross-year intra-tienda). Con 170/185/280 la conversión daría ~18.55%, no 17.73%. El cálculo final del entregable está bien; solo el texto describe mal los valores.

**Verificación:**
```python
# mediana DOW cross-year para T008, excluyendo nulls
# 2026-02-05 (jueves/dow=3): otros jueves T008 = [2026-02-12=207, 2025-02-06=192, 2025-02-13=208] → mediana = 207
# 2026-02-06 (viernes/dow=4):  [2026-02-13=264, 2025-02-07=276, 2025-02-14=268] → mediana = 268
# 2026-02-07 (sábado/dow=5):  [2026-02-14=290, 2025-02-01=299, 2025-02-08=322] → mediana = 299
```

**old_string:**
```
**Tratamiento:** imputé los valores faltantes con la **mediana por día de la semana** de la misma tienda, usando las otras dos semanas disponibles. Evito a propósito la media: el 7-feb (sábado) fue el día del evento Costanera, con un outlier positivo en toda la red, así que usar media mensual inflaría el imputado. La mediana DOW es robusta a ese outlier. También evité hacer imputación cruzada entre tiendas (T008 tiene escala de tráfico muy distinta a T001). Los 3 días quedan con valores aproximados a 170, 185 y 280 visitantes, consistentes con su historial.
```

**new_string:**
```
**Tratamiento:** imputé los valores faltantes con la **mediana por día de la semana** de la misma tienda, tomada sobre el historial disponible de T008 (2025 + 2026 no-nulos). Evito a propósito la media: el 7-feb (sábado) fue el día del evento Costanera, con un outlier positivo en toda la red, así que usar media mensual inflaría el imputado. La mediana DOW es robusta a ese outlier. También evité hacer imputación cruzada entre tiendas (T008 tiene escala de tráfico muy distinta a T001). Los 3 días quedan con valores **207 (jue 05-feb), 268 (vie 06-feb) y 299 (sáb 07-feb)** visitantes, consistentes con su historial. Con estos valores, la conversión T008 del período = 17.73% (consistente con la tabla 1.4).
```

---

### 🔴 Corrección 2 — [ALTO] 2.3 Costanera: gap T010 y combinado mal calculados

**Sección:** Parte 2.3, subsección "¿Valió la pena comercialmente?" y síntesis.

**Problema:** el texto afirma que en T010 "se perdieron ~$1.1M" por saturación de conversión, y luego que el valor combinado perdido es "~$5.9M" y "2.4 veces mayor que el margen capturado". Los números correctos son:

| Tienda | Fórmula (tráfico_evento × conv_control × ticket_evento) | Venta teórica | Venta real | Gap |
|---|---|---:|---:|---:|
| T001 | 798 × 24.00% × $83.850 | $16.058.995 | $11.152.080 | **$4.906.915 ≈ $4.9M** |
| T010 | 621 × 20.10% × $66.848 | $8.343.767 | $6.818.530 | **$1.525.237 ≈ $1.5M** |
| **Total** | | | | **~$6.4M** |

Razón valor perdido / margen capturado: $6.4M / $2.44M = **~2.6×**, no 2.4×.

**Verificación Python:**
```python
# T010
621 * 0.2010 * 66848  # = 8,343,768 teórico
- 6818530              # gap = 1,525,238 ≈ $1.5M
```

#### Cambio 2a — viñeta T010 dentro de la pregunta "¿Valió la pena?"

**old_string:**
```
Pero — si la conversión del evento se hubiera mantenido en el baseline del sábado control (24% en T001), T001 habría facturado $15.9M en vez de $11.15M. **El evento dejó ~$4.8M CLP sobre la mesa solo en T001 por falta de conversión.** Análogamente en T010, se perdieron ~$1.1M.
```

**new_string:**
```
Pero — si la conversión del evento se hubiera mantenido en el baseline del sábado control (24.00% en T001), T001 habría facturado $16.06M en vez de $11.15M. **El evento dejó ~$4.9M CLP sobre la mesa solo en T001 por falta de conversión.** Análogamente en T010 (baseline 20.10%), se perdieron ~$1.5M. Combinado: ~$6.4M de venta no capturada por saturación.
```

#### Cambio 2b — síntesis, conclusión 2

**old_string:**
```
2. **La conversión es el talón de Aquiles operativo**. El valor perdido por saturación (~$5.9M combinado entre ambas tiendas) es **2.4 veces mayor que el margen que efectivamente se capturó**. No es un detalle menor — es el principal driver de ROI futuro del formato evento.
```

**new_string:**
```
2. **La conversión es el talón de Aquiles operativo**. El valor perdido por saturación (~$6.4M combinado entre ambas tiendas) es **~2.6 veces mayor que el margen que efectivamente se capturó** ($2.44M). No es un detalle menor — es el principal driver de ROI futuro del formato evento.
```

#### Cambio 2c — Recomendación 2 (hereda la cifra de T001)

**old_string:**
```
**Hallazgo:** el evento Costanera del 7-feb trajo +68% de tráfico a T001 y +54% a T010, pero la conversión cayó 7.3 pp en T001 y 3.7 pp en T010. Si la conversión hubiera mantenido el baseline, T001 habría facturado **$4.8M adicionales en un solo día**.
```

**new_string:**
```
**Hallazgo:** el evento Costanera del 7-feb trajo +68% de tráfico a T001 y +54% a T010, pero la conversión cayó 7.3 pp en T001 y 3.7 pp en T010. Si la conversión hubiera mantenido el baseline, T001 habría facturado **~$4.9M adicionales en un solo día** (y T010 ~$1.5M; combinado ~$6.4M).
```

---

### 🟡 Corrección 3 — [MEDIO] Recomendación 1: cumplimiento Oceano agregado

**Sección:** Parte 3, Recomendación 1, lista de métricas objetivo.

**Problema:** el texto dice "Cumplimiento Oceano agregado: de **93% actual** → ≥100%". El valor real es 91.96% ≈ 92%, no 93%.

**Verificación:**
- Venta Oceano 2026 = $96.908.103 (T007+T008+T009)
- Presupuesto Oceano 2026 = $105.382.544
- Cumplimiento = 96.908.103 / 105.382.544 = **0.9196 = 91.96%**

**old_string:**
```
- **Cumplimiento Oceano agregado**: de 93% actual → **≥100%** próxima quincena, recuperando ≥$6M del gap combinado de T007+T008.
```

**new_string:**
```
- **Cumplimiento Oceano agregado**: de 92% actual → **≥100%** próxima quincena, recuperando ≥$6M del gap combinado de T007+T008 (gap actual combinado de los dos: $10.95M).
```

---

### 🟡 Corrección 4 — [MEDIO] TL;DR: actualizar viñeta 4 con la cifra corregida

**Sección:** TL;DR ejecutivo, viñeta 4.

**Problema:** la viñeta habla de "~$4.8M sobre la mesa por saturación operativa"; al aplicar la Corrección 2, este número pasa a ~$4.9M (T001) o mejor, a ~$6.4M combinado. Sugerido: usar el combinado para que el TL;DR represente a las dos tiendas del evento.

**old_string:**
```
4. **Evento Costanera 7-feb** generó +$5.2M de venta y +$2.4M de margen bruto incremental, pero la conversión cayó 7 pp en T001. Valió la pena, pero se dejaron otros ~$4.8M sobre la mesa por saturación operativa.
```

**new_string:**
```
4. **Evento Costanera 7-feb** generó +$5.2M de venta y +$2.4M de margen bruto incremental, pero la conversión cayó 7.3 pp en T001 y 3.7 pp en T010. Valió la pena, pero se dejaron otros ~$6.4M de venta sobre la mesa por saturación operativa (~$4.9M T001 + ~$1.5M T010).
```

---

### 🟢 Corrección 5 — [BAJO] 1.2 análisis: frase lógicamente inconsistente

**Sección:** Parte 1.2, párrafo de análisis.

**Problema:** "T007 ... explica el 47% de la caída total de Oceano en CLP absolutos, **más que T008 (30%) y T009 (23%) sumadas individualmente**". La suma 30+23 = 53 > 47, lo que hace la frase autocontradictoria. La intención es decir "más que cualquiera de T008 o T009 por separado".

**old_string:**
```
Solo 3 tiendas caen YoY, y las 3 son Oceano. Las posiciones 4 y 5 del ranking de "peor desempeño" en realidad están creciendo (+1.7% y +2.5%). La columna `pct_caida_cadena` muestra que T007 es prioritaria: explica el 47% de la caída total de Oceano en CLP absolutos, más que T008 (30%) y T009 (23%) sumadas individualmente.
```

**new_string:**
```
Solo 3 tiendas caen YoY, y las 3 son Oceano. Las posiciones 4 y 5 del ranking de "peor desempeño" en realidad están creciendo (+1.7% y +2.5%). La columna `pct_caida_cadena` muestra que T007 es prioritaria: explica el 47% de la caída total de Oceano en CLP absolutos, más que T008 (30%) o T009 (23%) por separado — y solo ligeramente por debajo de la suma de ambas (53%).
```

---

### 🟢 Corrección 6 — [BAJO] 2.1 A3: mencionar outliers secundarios del 2026-02-07

**Sección:** Parte 2.1, Anomalía A3.

**Problema:** el texto solo menciona T001 (z=3.43) y T010 (z=3.29) como outliers del 7-feb. En realidad el mismo día también tienen z>2: **T003 (z=2.31), T012 (z=2.16), T005 (z=2.05)**. Mencionarlo fortalece la lección "no filtrar outliers sin contexto", porque muestra que el efecto sábado + eventos promocionales genera outliers en toda la red, no solo en Costanera.

**old_string:**
```
Al aplicar z-score intra-tienda (crítico: intra-store, no global, porque las escalas de venta entre tiendas son muy distintas), aparecen outliers extremos en **T001 (z=+3.4)** y **T010 (z=+3.3)** exactamente el mismo día: sábado 7-feb 2026. Estadísticamente son outliers, pero **no son errores de datos**: corresponden al evento especial en el Mall Costanera Center.
```

**new_string:**
```
Al aplicar z-score intra-tienda (crítico: intra-store, no global, porque las escalas de venta entre tiendas son muy distintas), aparecen outliers extremos en **T001 (z=+3.43)** y **T010 (z=+3.29)** exactamente el mismo día: sábado 7-feb 2026. Además ese día T003 (z=2.31), T012 (z=2.16) y T005 (z=2.05) también cruzan el umbral |z|>2 aunque con menor intensidad — no están en Costanera Center, pero el sábado es estructuralmente el día más fuerte y pudo haber halo promocional macro. Estadísticamente son outliers, pero **no son errores de datos**: los dos primeros corresponden al evento especial en el Mall Costanera Center.
```

---

### 🟢 Corrección 7 — [BAJO] 2.1 A5: caveat de cobertura de productos.csv dentro de las 4 tiendas

**Sección:** Parte 2.1, Anomalía A5.

**Problema:** el texto explica que productos.csv cubre 4 de 12 tiendas, pero no menciona que **dentro de esas 4 tiendas, solo cubre un sample pequeño de SKUs (~10–16% de la venta total de cada tienda)**. Sin este caveat, las conclusiones del tipo "27.5% de la venta de T007 viene de parkas" pueden malinterpretarse como absolutas.

**Verificación:**
| Tienda | Venta total 2026 (ventas.csv) | Venta trackeada (productos.csv) | % cobertura |
|---|---:|---:|---:|
| T001 | $81.399.893 | $7.101.033 | 8.7% |
| T004 | $57.491.910 | $9.139.170 | 15.9% |
| T007 | $41.589.751 | $5.741.042 | 13.8% |
| T010 | $51.987.277 | $5.249.981 | 10.1% |

**old_string:**
```
`productos.csv` solo tiene detalle SKU para 4 de las 12 tiendas (T001, T004, T007, T010). Las 192 filas cubren solo la primera quincena 2026 y solo esas tiendas.

**Tratamiento:** no hay corrección posible — es una decisión de diseño del dataset. Documenté esta limitante: las conclusiones a nivel de clase/SKU (ej. mix de parkas en T007) **no son extrapolables al resto de la red**. Por suerte, T007 sí está en la cobertura, así que el diagnóstico específico de Oceano sí puede usar este detalle. Pero cualquier afirmación sobre "el mix de Oceano completa" debe limitarse a lo que vemos en T007.
```

**new_string:**
```
`productos.csv` solo tiene detalle SKU para 4 de las 12 tiendas (T001, T004, T007, T010), y con cobertura parcial: las 192 filas capturan 8 SKUs y ~10–16% de la venta total de cada una de esas tiendas (T001 8.7%, T004 15.9%, T007 13.8%, T010 10.1%). No es el catálogo completo de lo vendido, es un SKU-sample.

**Tratamiento:** no hay corrección posible — es una decisión de diseño del dataset. Documenté la doble limitante: (a) 8 de 12 tiendas sin detalle, y (b) dentro de las 4 cubiertas, solo ~10–16% de la venta total está trackeada a nivel SKU. Las conclusiones a nivel de clase/SKU son **direccionales, no censales**. Por suerte, T007 sí está en la cobertura, así que el diagnóstico específico de Oceano puede usar este detalle, pero tratándolo como **señal de mix sobre un sample**, no como la composición exacta de las 5.800 unidades del stock de T007.
```

---

### 🔵 Corrección 8 — [OBSERVACIÓN] 2.1 A1: declarar la decisión sobre `num_boletas` de la devolución

**Sección:** Parte 2.1, Anomalía A1.

**Problema:** la fila de devolución (T009, 2026-02-10) tiene `num_boletas = +1` (no −1). El entregable agrega esa +1 al total de boletas de T009 (llegando a 763 boletas). Esto es defendible pero es una decisión: si se argumentara que una devolución no debe contar como "otra venta" en conversión, habría que restarla. El entregable no explicita la decisión, conviene agregarla.

**old_string:**
```
En `ventas.csv`, la fila `2026-02-10, T009` registra una venta de **-$285.000 CLP** con -2 unidades y -$165.000 de costo. No es un error de digitación: es una **devolución** que se guardó en la tabla de ventas como una fila adicional con signo negativo, compartiendo la misma clave `(fecha, cod_local)` con la venta bruta del mismo día. El resultado es que para T009 el 2026-02-10 hay dos filas en vez de una.

**Tratamiento:** mantengo la devolución en el cálculo pero agrego por `(fecha, cod_local)` para que haya una sola fila por día-tienda con la venta **neta de devoluciones** — que es precisamente lo que significa `venta_neta`. La venta neta diaria de T009 el 2026-02-10 pasa de $1.414.010 (bruta) a $1.129.010 (neta). Esto afecta a T009 Feb 2026: venta neta = **$25.103.586** (no $25.388.586 que saldría si se ignoraran las devoluciones). A su vez Oceano agregado = **$96.908.103** y YoY **-9.86%**. También guardo la fila en una tabla `devoluciones` para análisis diagnóstico (tasa de devolución por tienda, etc.) sin perder la trazabilidad.
```

**new_string:**
```
En `ventas.csv`, la fila `2026-02-10, T009` registra una venta de **-$285.000 CLP** con -2 unidades, -$165.000 de costo y `num_boletas = +1`. No es un error de digitación: es una **devolución** que se guardó en la tabla de ventas como una fila adicional con signos negativos en monetarios/unidades, compartiendo la misma clave `(fecha, cod_local)` con la venta bruta del mismo día. El resultado es que para T009 el 2026-02-10 hay dos filas en vez de una.

**Tratamiento:** mantengo la devolución en el cálculo pero agrego por `(fecha, cod_local)` para que haya una sola fila por día-tienda con la venta **neta de devoluciones** — que es precisamente lo que significa `venta_neta`. La venta neta diaria de T009 el 2026-02-10 pasa de $1.414.010 (bruta) a $1.129.010 (neta). Esto afecta a T009 Feb 2026: venta neta = **$25.103.586** (no $25.388.586 que saldría si se ignoraran las devoluciones). A su vez Oceano agregado = **$96.908.103** y YoY **-9.86%**. También guardo la fila en una tabla `devoluciones` para análisis diagnóstico (tasa de devolución por tienda, etc.) sin perder la trazabilidad. **Decisión explícita sobre `num_boletas`:** el +1 de la devolución se conserva en el agregado (763 boletas en T009), interpretando la devolución como una transacción adicional (boleta de devolución). La alternativa —netear la devolución a -1 boleta, llegando a 761— subiría la conversión de T009 marginalmente (de 28.42% a 28.47%), un efecto despreciable; por parsimonia se mantiene la versión aditiva.
```

---

### 🔵 Corrección 9 — [OBSERVACIÓN] 2.2 mix T007: reformular como hipótesis

**Sección:** Parte 2.2, subsección "Cruce con mix de productos — T007".

**Problema:** la conclusión "El stock está mal compuesto por temporada, no mal calibrado en volumen total" mezcla un dato observado (12 parkas vendidas sobre SKU sample) con una inferencia (composición del stock físico de 5.800 unidades, que el dataset NO desglosa por clase). La dirección es razonable, pero se presenta como si fuera una medición.

**old_string:**
```
**Conclusiones T007**: el 27.5% de la venta viene de **parkas** — en febrero chileno (verano). Solo 12 parkas vendidas en 14 días, pero a ticket $131K cada una. El mix de verano (shorts + poleras) junto solo llega al 34% cuando debería dominar. Esto explica directamente el DDI de 72.5 días: hay mucho inventario de alto valor unitario (parkas $131K) que rota a 1 unidad por día, mientras que las poleras rotan a 2.8/día pero representan menos inventario por unidad. **El stock está mal compuesto por temporada**, no mal calibrado en volumen total.
```

**new_string:**
```
**Conclusiones T007**: el 27.5% de la venta SKU-trackeada viene de **parkas** — en febrero chileno (verano). Solo 12 parkas vendidas en 14 días, pero a ticket $131K cada una. En el sample, el mix de verano (shorts + poleras) junto llega al 34% cuando debería dominar. Esto es consistente con un DDI de 72.5 días explicado por **stock mal compuesto por temporada** (hipótesis): las parkas que rotan a ~1 unidad/día por SKU, si representan una fracción alta del inventario físico, explicarían el acumulado. El dataset no desglosa las 5.800 unidades del stock por clase, así que esta es una inferencia direccional —plausible pero no censal— construida desde el SKU sample. El escenario alternativo (volumen total bien calibrado pero mix sesgado) es el más consistente con los datos disponibles.
```

---

## Qué NO cambiar (para evitar regresiones)

Las siguientes secciones están matemáticamente correctas y deben quedar intactas:

- **Parte 1.1 Ranking de cadenas** — todas las cifras (venta, unidades, ticket, YoY, margen, participación) están OK al decimal.
- **Parte 1.2 tabla con 5 filas** — los 5 porcentajes YoY, deltas CLP y % caída cadena son correctos.
- **Parte 1.3 tabla patrón semanal** — las 7 filas (venta prom 2026, 2025, YoY, %semana) están OK.
- **Parte 1.4 tabla de cumplimiento** — las 12 filas están OK (asumiendo tráfico imputado para T008, como el entregable declara).
- **Parte 2.2 tablas de log-deltas y ratios costos** — las 3 descomposiciones por tienda (Δtotal = Δtráfico + Δconv + Δticket; Δticket = Δpxu + ΔUPT) se verifican por propiedad aditiva del logaritmo. Los ratios "costo vendido / costo en stock" (0.67 / 0.58 / 0.50) también son correctos.
- **Parte 2.3 tabla comparativa cruda** — las 8 filas (venta, tráfico, boletas, conversión, ticket, margen) para T001/T010 × 4 fechas están OK.
- **Parte 2.3 impacto vs control** — las 6 métricas por tienda (Δventa, Δtráfico, Δboletas, Δconv, Δticket, Δmargen incremental) están OK, incluyendo el total $2.44M.
- **Parte 2.3 "no hubo canibalización"** — YoY 14-feb T001 +45.2% y T010 +70.6% están OK.
- **Parte 3 Recomendación 2 protocolo operativo** — los pasos operativos (staffing +40%, queue-busting, etc.) no tienen cifras duras que verificar más allá del "+$4.8M" ya tratado en Corrección 2c.
- **Parte 3 Recomendación 3 tabla log-delta** — reproduce 2.2, OK.
- **Bonus quality score** — las 12 filas están OK al decimal, el insight T009 (mejor conversión 28.42%) es correcto, y la proyección "+$5.4M" del levantamiento de ticket también cuadra.
- **Sección 3.2 uso de IA, prompt, web app** — no son numéricas, no requieren verificación.

---

## Checklist final (para la instancia que ejecute)

- [ ] Corrección 1 aplicada (A2 valores imputados)
- [ ] Corrección 2a aplicada (gap T010 = $1.5M)
- [ ] Corrección 2b aplicada (síntesis: $6.4M / 2.6×)
- [ ] Corrección 2c aplicada (Rec 2 menciona T010)
- [ ] Corrección 3 aplicada (cumplimiento Oceano 92%)
- [ ] Corrección 4 aplicada (TL;DR viñeta 4)
- [ ] Corrección 5 aplicada (frase lógica 1.2)
- [ ] Corrección 6 aplicada (outliers secundarios A3)
- [ ] Corrección 7 aplicada (caveat cobertura productos.csv)
- [ ] Corrección 8 aplicada (decisión `num_boletas` devolución)
- [ ] Corrección 9 aplicada (mix T007 como hipótesis)
- [ ] Re-lectura: TL;DR y síntesis de 2.3 consistentes con nuevas cifras ($6.4M / 2.6×)
- [ ] Re-lectura: Rec 1 "92%" no entra en conflicto con TL;DR viñeta 2 (que sigue diciendo "-9.86% YoY Oceano", que es correcto)
- [ ] Revisar que el notebook / dashboard / scripts en [src/](src/) no hardcodeen "$5.9M", "170 185 280", "93%" o similares. Si los hardcodean, actualizar ahí también (fuera del alcance del .md pero coherente).

---

## Notas finales

- Las correcciones 1 y 2 son las que más impacto tienen en la legibilidad y defensibilidad del entregable; si hay que priorizar por tiempo, empezar por esas.
- Ninguna de las correcciones cambia conclusiones estratégicas. Todas mantienen intacto el diagnóstico (Oceano es el problema, T007 principal contribuyente, evento Costanera rentable pero con saturación, Urbana es la historia silenciosa de crecimiento).
- Si la instancia que corrija encuentra ambigüedad en alguno de los `old_string` (ej. porque el archivo ya fue editado previamente), parar y reportar antes de hacer `replace_all`.
