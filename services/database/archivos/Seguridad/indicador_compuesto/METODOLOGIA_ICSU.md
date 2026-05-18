# Indicador Compuesto de Seguridad Urbana (ICSU)

## Metodologia de construccion basada en PCA

**Proyecto:** Estudio Inmobiliario — INMU
**Ambito:** 18 localidades urbanas de Bogota D.C.
**Fecha de construccion:** Marzo 2026
**Fuentes de datos:** Criminalidad 2024 (Secretaria de Seguridad) + EPV 2024 (Camara de Comercio de Bogota)

---

## 1. Introduccion

El ICSU (Indicador Compuesto de Seguridad Urbana) es un indice sintetico que combina **datos objetivos de criminalidad** con **datos subjetivos de percepcion y victimizacion** para producir una medida unica de (in)seguridad por localidad en Bogota.

### 1.1 Por que un indicador compuesto?

Los indicadores compuestos permiten sintetizar fenomenos multidimensionales complejos en una unica medida comparable. Segun la OECD:

> *"A composite indicator is formed when individual indicators are compiled into a single index on the basis of an underlying model of the multi-dimensional concept that is being measured."*
> — OECD/JRC, Handbook on Constructing Composite Indicators (2008), p. 13

En el contexto inmobiliario, la seguridad afecta directamente la valoracion de inmuebles. Sin embargo, medir "seguridad" requiere integrar multiples dimensiones: criminalidad real, percepcion ciudadana, victimizacion encuestada, confianza institucional y seguridad en espacios publicos.

### 1.2 Indicador anterior (IPI — pesos fijos)

El indicador previo del proyecto (IPI) usaba **pesos arbitrarios fijos** asignados manualmente:

| Componente | Peso |
|---|---|
| % Barrio inseguro | 30% |
| Score barrio (invertido) | 25% |
| Tasa de victimizacion | 20% |
| Aumento percibido | 15% |
| % Testigos | 10% |

**Problemas:**
- Los pesos no reflejan la estructura real de varianza de los datos
- Solo usaba variables de percepcion (subjetivas), ignorando criminalidad objetiva
- No validaba la idoneidad de las variables para agregarse (KMO/Bartlett)
- Sin analisis de sensibilidad para verificar robustez

### 1.3 Indicador ISEG actual del proyecto (AHP)

El ISEG (Indicador de Seguridad a nivel de inmueble) usa AHP con pesos expertos:

| Componente | Peso |
|---|---|
| Proximidad CAI (policia) | 35% |
| Masa de crimen (localidad) | 45% |
| Proximidad sector priorizado | 20% |

El ISEG es valido para comparaciones **intra-localidad** (gravedad espacial), pero no incorpora percepcion ciudadana ni victimizacion encuestada.

---

## 2. Marco teorico

### 2.1 Modelo conceptual

La seguridad urbana es un constructo bidimensional:

```
SEGURIDAD URBANA
    |
    +-- Dimension 1: OBJETIVA (criminalidad registrada)
    |       Homicidios, lesiones, hurtos, delitos sexuales,
    |       violencia intrafamiliar — datos policiales 2024
    |
    +-- Dimension 2: SUBJETIVA (percepcion + victimizacion encuestada)
            % barrio inseguro, victimizacion directa, testigos,
            percepcion de aumento, confianza policial,
            seguridad en espacios publicos — EPV 2024 (CCB)
```

La literatura muestra que criminalidad objetiva y percepcion de inseguridad **no siempre se correlacionan linealmente**. Localidades con baja criminalidad pueden tener alta percepcion de inseguridad y viceversa. Esto se conoce como la **"paradoja de la inseguridad"** (Dammert, 2012; Gaviria & Pages, 2002).

> *"The relationship between exposure to crimes such as theft (of persons and residences), homicides and fights, and the perception of insecurity in the neighborhood [shows that] women and the low-income population tend to feel more insecure in their place of residence."*
> — Beltran-Gomez, L. (2019). Cuales determinantes se relacionan con la percepcion de inseguridad? Un analisis estadistico y espacial para la ciudad de Bogota, D.C.

Fuente: [Scielo Colombia](http://www.scielo.org.co/scielo.php?script=sci_arttext&pid=S1794-31082019000100069)

### 2.2 Justificacion de PCA vs AHP

| Criterio | AHP (actual) | PCA (propuesto) |
|---|---|---|
| Origen de pesos | Juicio de expertos | Estructura de varianza de los datos |
| Reproducibilidad | Depende del panel de expertos | 100% reproducible dado el dataset |
| Correlaciones entre variables | Las ignora (posible doble conteo) | Las detecta y compensa automaticamente |
| Validacion estadistica | No tiene mecanismo intrinseco | KMO, Bartlett, % varianza explicada |
| Referencia academica | Saaty (1980), valido pero subjetivo | Estandar OECD/JRC para indices compuestos |
| Sensibilidad | No se evalua formalmente | Monte Carlo sobre perturbacion de pesos |

> *"PCA is the most common approach to extract principal components for composite indicators, as it has the virtue of simplicity and allows the construction of weights representing the information content of individual indicators."*
> — OECD/JRC (2008), Handbook on Constructing Composite Indicators, p. 89

Fuente: [OECD Handbook](https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf)

---

## 3. Datos utilizados

### 3.1 Fuente 1: Criminalidad objetiva (DAILoc.geojson)

**Origen:** Secretaria Distrital de Seguridad, Convivencia y Justicia de Bogota
**Periodo:** 2024
**Formato:** GeoJSON con poligonos de 19 localidades
**Variables seleccionadas (7):**

| Variable | Campo original | Descripcion |
|---|---|---|
| Homicidios/km2 | CMH24CONT | Homicidios 2024, normalizado por area |
| Lesiones personales/km2 | CMLP24CONT | Lesiones personales, normalizado |
| Hurto a personas/km2 | CMHP24CONT | Hurto a personas, normalizado |
| Hurto a residencias/km2 | CMHR24CONT | Hurto a residencias, normalizado |
| Hurto a automotores/km2 | CMHA24CONT | Hurto vehiculos, normalizado |
| Delitos sexuales/km2 | CMDS24CONT | Delitos sexuales, normalizado |
| Violencia intrafamiliar/km2 | CMVI24CONT | VIF, normalizado |

**Normalizacion espacial:** Todos los conteos se dividen por el area en km2 de la localidad (campo SHAPE_AREA) para obtener **tasas por km2**, eliminando el sesgo por tamano de localidad.

### 3.2 Fuente 2: Percepcion y victimizacion (EPV 2024)

**Origen:** Encuesta de Percepcion y Victimizacion 2024, Camara de Comercio de Bogota
**Muestra:** 19,354 encuestas en Bogota (26,064 total incluyendo municipios aledanos)
**Variables seleccionadas (8):**

| Variable | Campo | Descripcion |
|---|---|---|
| % Barrio inseguro | pct_barrio_inseguro | % que considera su barrio inseguro |
| Score barrio (inv.) | 5 - score_barrio_1a5 | Percepcion 1-5 invertida (mayor=peor) |
| % Victima de delito | pct_victima_delito | Tasa de victimizacion personal |
| % Testigo de delito | pct_testigo_delito | % que presencio un delito |
| % Percibe aumento | pct_inseg_aumento | % que percibe aumento de inseguridad |
| Score esp. publicos (inv.) | 5 - promedio espacios | Inseguridad en calles, parques, etc. |
| Score policia (inv.) | 5 - score_policia_1a5 | Desconfianza policial (mayor=peor) |
| % Hogar victima | pct_hogar_victima | % cuyo hogar fue victima |

**Inversion de scores:** Las variables medidas como "seguridad" (donde mayor=mas seguro) se invierten para que en todas las variables, **mayor valor = mayor inseguridad**.

---

## 4. Metodologia paso a paso

### 4.1 Paso 1 — Normalizacion (z-score)

Todas las variables se estandarizan mediante z-score:

```
z_i = (x_i - mean(x)) / std(x)
```

Esto elimina diferencias de escala y unidades entre variables. La OECD recomienda z-score para indicadores compuestos cuando las distribuciones no tienen outliers extremos:

> *"Standardisation (or z-scores) converts indicators to a common scale with a mean of zero and standard deviation of one [...] extreme values can have a greater effect on the composite indicator."*
> — OECD/JRC (2008), p. 83

Fuente: [OECD Handbook](https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf)

### 4.2 Paso 2 — Tests de adecuacion muestral

Antes de aplicar PCA, se valida que las variables estan suficientemente correlacionadas para justificar la reduccion dimensional:

#### Test de Kaiser-Meyer-Olkin (KMO)

Mide la proporcion de varianza que es comun entre las variables:

```
KMO = sum(r_ij^2) / (sum(r_ij^2) + sum(q_ij^2))
```

Donde `r_ij` son correlaciones de Pearson y `q_ij` correlaciones parciales (anti-image).

| KMO | Interpretacion |
|---|---|
| > 0.9 | Excelente |
| > 0.8 | Bueno |
| > 0.7 | Aceptable |
| > 0.6 | Mediocre |
| > 0.5 | Pobre |
| < 0.5 | Inaceptable — no usar PCA |

> *"A high KMO value (close to 1.0) suggests excellent sampling adequacy, indicating that the data is suitable for factor analysis."*
> — Enhancing Urban Quality of Life Evaluation Using Spatial Multi Criteria Analysis, Scientific Reports (2025)

Fuente: [Nature Scientific Reports](https://www.nature.com/articles/s41598-025-05468-1)

#### Test de Bartlett

Prueba la hipotesis nula de que la matriz de correlacion es una identidad (variables no correlacionadas):

```
Chi2 = -((n-1) - (2p+5)/6) * ln(det(R))
```

Si p-value < 0.05, se rechaza H0 y las variables estan significativamente correlacionadas.

**Resultados obtenidos:**

| Dimension | KMO | Bartlett Chi2 | p-value | Conclusion |
|---|---|---|---|---|
| Dim.1 (Criminalidad) | **0.7440** (Aceptable) | 192.21 | < 0.000001 | PCA adecuado |
| Dim.2 (Percepcion) | **0.6453** (Mediocre) | 67.84 | 0.000012 | PCA aceptable |

### 4.3 Paso 3 — PCA por dimension

Se aplica PCA sobre la matriz de correlacion (datos estandarizados) de cada dimension independientemente.

#### Criterio de retencion: Regla de Kaiser

Se retienen los componentes con eigenvalue >= 1.0 (Kaiser, 1960). Un eigenvalue >= 1 indica que el componente explica mas varianza que una sola variable original.

> *"The eigenvalue-one criterion, or Kaiser criterion, recommends retaining only the components whose eigenvalues exceed unity."*
> — Kaiser, H.F. (1960). The application of electronic computers to factor analysis. Educational and Psychological Measurement, 20, 141-151.

#### Resultados PCA — Dimension 1 (Criminalidad)

| Componente | Eigenvalue | % Varianza | % Acumulada |
|---|---|---|---|
| **PC1** | **5.4993** | **78.6%** | **78.6%** |
| PC2 | 0.8255 | 11.8% | 90.4% |
| PC3-PC7 | < 0.45 | < 6.5% | 100% |

**1 componente retenido** — PC1 explica el **78.6%** de la varianza total.

Esto indica que las 7 variables de criminalidad estan **fuertemente correlacionadas** entre si: localidades con altos homicidios tienden a tener tambien altos hurtos, delitos sexuales, etc. Un solo componente captura esta estructura.

**Pesos PCA derivados (Dimension 1):**

| Variable | Peso PCA | Peso AHP previo |
|---|---|---|
| Lesiones personales/km2 | **17.7%** | No incluida |
| Delitos sexuales/km2 | **16.4%** | 26.7% (sobreestimado) |
| Violencia intrafamiliar/km2 | **16.1%** | 4.7% (subestimado) |
| Hurto a personas/km2 | **15.4%** | 12.0% |
| Homicidios/km2 | **13.3%** | 56.6% (muy sobreestimado) |
| Hurto a residencias/km2 | **12.4%** | No incluida |
| Hurto a automotores/km2 | **8.7%** | No incluida |

**Hallazgo clave:** El AHP anterior asignaba 56.6% a homicidios, pero el PCA muestra que su contribucion a la varianza inter-localidad es solo del 13.3%. Las lesiones personales y la violencia intrafamiliar, variables ignoradas por el AHP, resultan ser las mas discriminantes entre localidades.

#### Resultados PCA — Dimension 2 (Percepcion)

| Componente | Eigenvalue | % Varianza | % Acumulada |
|---|---|---|---|
| **PC1** | **3.0854** | **38.6%** | **38.6%** |
| **PC2** | **2.4425** | **30.5%** | **69.1%** |
| PC3 | 0.9690 | 12.1% | 81.2% |
| PC4-PC8 | < 0.57 | < 7.1% | 100% |

**2 componentes retenidos** — PC1+PC2 explican el **69.1%** de la varianza total.

La estructura bidimensional de la percepcion indica dos sub-constructos:
1. **PC1 (38.6%):** Dominado por score_barrio, espacios_publicos, pct_inseguro — la "percepcion ambiental" de inseguridad
2. **PC2 (30.5%):** Dominado por victimizacion y testigos — la "experiencia directa" con el delito

**Pesos PCA derivados (Dimension 2):**

| Variable | Peso PCA |
|---|---|
| Score barrio (invertido) | **16.4%** |
| % Victima de delito | **15.3%** |
| % Testigo de delito | **14.4%** |
| % Barrio inseguro | **12.5%** |
| Score espacios publicos (inv.) | **11.7%** |
| Score policia (invertido) | **11.5%** |
| % Percibe aumento | **10.4%** |
| % Hogar victima | **7.7%** |

### 4.4 Paso 4 — PCA global (combinacion de dimensiones)

Las puntuaciones de cada dimension se estandarizan y se combinan mediante un segundo PCA de nivel superior.

**Correlacion entre dimensiones:**

```
r(Dim.Objetiva, Dim.Subjetiva) = 0.3174
```

Correlacion **debil** — las dimensiones son relativamente independientes. Esto confirma la "paradoja de la inseguridad": la criminalidad registrada y la percepcion ciudadana no se mueven juntas.

Cuando las dimensiones son ortogonales, el PCA global asigna pesos iguales:

| Dimension | Peso |
|---|---|
| Objetiva (criminalidad) | **50.0%** |
| Subjetiva (percepcion) | **50.0%** |

> *"When sub-indicators are uncorrelated, PCA degenerates to equal weighting, since each sub-indicator contributes equally to the overall variance."*
> — Greco, S. et al. (2019). On the Methodological Framework of Composite Indices: A Review of the Issues of Weighting, Aggregation, and Robustness.

Fuente: [Springer Social Indicators Research](https://link.springer.com/article/10.1007/s11205-017-1832-9)

### 4.5 Paso 5 — Escalamiento final

El score compuesto se escala a 0-5 mediante min-max:

```
ICSU_i = 5 * (score_i - min(scores)) / (max(scores) - min(scores))
```

Escala: **0 = mas seguro, 5 = mas inseguro**

### 4.6 Paso 6 — Analisis de sensibilidad (Monte Carlo)

Se ejecutan **1,000 iteraciones** perturbando aleatoriamente los pesos de cada dimension en +-30%:

```python
w_obj_perturbed = w_obj * (1 + U(-0.3, 0.3))
w_sub_perturbed = w_sub * (1 + U(-0.3, 0.3))
# Re-normalizar
```

Se registra el ranking de cada localidad en cada iteracion.

> *"Sensitivity analysis should assess the robustness of the composite indicator in terms of the mechanism for including or excluding single indicators, the normalisation scheme, the imputation of missing data, the choice of weights."*
> — OECD/JRC (2008), Handbook on Constructing Composite Indicators, p. 36

Fuente: [OECD Handbook](https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf)

**Resultado:** 17 de 18 localidades mantienen ranking **estable** (variacion <= 4 posiciones). Solo San Cristobal muestra variacion parcial (rango 4-9 en las simulaciones).

### 4.7 Paso 7 — Clustering post-hoc (K-means)

Se aplica K-means (k=4) sobre los scores estandarizados de ambas dimensiones para identificar perfiles tipologicos de seguridad:

> *"Hierarchical Clustering [is used] to delineate security profiles [...] integrating quantitative data with residents' lived experiences allows for a richer, more grounded understanding of urban security."*
> — From Planning to Perception: A Study of Urban Security in New Towns (2025)

Fuente: [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2665972725004568)

---

## 5. Resultados

### 5.1 Ranking ICSU

| Pos | Localidad | ICSU (0-5) | Dim. Objetiva | Dim. Subjetiva | Cluster |
|---|---|---|---|---|---|
| 1 | **Los Martires** | **5.00** | +3.103 | +0.733 | 3 |
| 2 | Bosa | 2.70 | +0.307 | +0.519 | 4 |
| 3 | Engativa | 2.52 | +0.041 | +0.528 | 4 |
| 4 | Tunjuelito | 2.36 | -0.039 | +0.443 | 4 |
| 5 | Kennedy | 2.36 | +0.511 | +0.090 | 2 |
| 6 | Barrios Unidos | 2.32 | +0.044 | +0.354 | 4 |
| 7 | San Cristobal | 2.26 | -0.621 | +0.723 | 4 |
| 8 | Antonio Narino | 2.10 | +0.401 | -0.063 | 2 |
| 9 | Rafael Uribe Uribe | 1.95 | +0.575 | -0.305 | 2 |
| 10 | Usaquen | 1.87 | -0.623 | +0.388 | 4 |
| 11 | Ciudad Bolivar | 1.74 | -0.659 | +0.294 | 4 |
| 12 | Puente Aranda | 1.59 | +0.034 | -0.271 | 2 |
| 13 | Suba | 1.51 | -0.589 | +0.053 | 4 |
| 14 | Usme | 0.97 | -0.929 | -0.194 | 2 |
| 15 | Fontibon | 0.93 | -0.438 | -0.544 | 1 |
| 16 | Santa Fe | 0.89 | -0.576 | -0.490 | 2 |
| 17 | Teusaquillo | 0.75 | +0.053 | -1.011 | 1 |
| 18 | Chapinero | 0.00 | -0.595 | -1.246 | 1 |

### 5.2 Perfiles de seguridad (Clusters)

| Cluster | Perfil | n | Localidades |
|---|---|---|---|
| **1** | Baja criminalidad + Baja percepcion inseg. | 3 | Chapinero, Fontibon, Teusaquillo |
| **2** | Alta criminalidad + Baja percepcion inseg. | 6 | Antonio Narino, Kennedy, Puente Aranda, Rafael Uribe Uribe, Santa Fe, Usme |
| **3** | Alta criminalidad + Alta percepcion inseg. | 1 | Los Martires |
| **4** | Baja criminalidad + Alta percepcion inseg. | 8 | Barrios Unidos, Bosa, Ciudad Bolivar, Engativa, San Cristobal, Suba, Tunjuelito, Usaquen |

**Hallazgo critico — Cluster 4 (paradoja de inseguridad):**
8 localidades (44%) tienen **baja criminalidad objetiva** pero **alta percepcion de inseguridad**. Esto incluye localidades populares para el mercado inmobiliario como Suba, Engativa y Usaquen. La percepcion de inseguridad en estas zonas esta influenciada por factores no capturados en estadisticas policiales: presencia de habitantes de calle (factor #1 en EPV 2024), deterioro del espacio publico, y cobertura mediatica.

**Hallazgo — Cluster 2 (criminalidad sin percepcion proporcional):**
6 localidades tienen criminalidad superior al promedio pero percepcion de inseguridad menor. Posibles explicaciones: habitacion a la violencia, menor exposicion mediatica, o diferencias sociodemograficas en la forma de reportar.

### 5.3 Comparacion con el IPI anterior

| Metrica | Valor |
|---|---|
| Correlacion de Spearman (rankings) | **rho = 0.9112** |
| Interpretacion | Correlacion FUERTE |

Los rankings son muy similares — ambos metodos coinciden en el top 3 y bottom 3. Las principales diferencias:

- **Antonio Narino** sube 6 posiciones: el PCA captura criminalidad objetiva que el IPI (solo percepcion) ignoraba
- **Suba** baja 5 posiciones: su alta percepcion de inseguridad no se acompana de criminalidad objetiva proporcionalmente alta

---

## 6. Validacion y limitaciones

### 6.1 Validaciones realizadas

| Test | Resultado | Umbral | Status |
|---|---|---|---|
| KMO Dim.1 | 0.7440 | > 0.6 | PASS |
| KMO Dim.2 | 0.6453 | > 0.6 | PASS |
| Bartlett Dim.1 | p < 0.000001 | p < 0.05 | PASS |
| Bartlett Dim.2 | p = 0.000012 | p < 0.05 | PASS |
| Varianza PC1 Dim.1 | 78.6% | > 60% | PASS |
| Varianza PC1+PC2 Dim.2 | 69.1% | > 60% | PASS |
| Sensibilidad Monte Carlo | 17/18 estables | > 80% | PASS |
| Spearman vs IPI | 0.9112 | > 0.7 | PASS |

### 6.2 Limitaciones

1. **n = 18 localidades:** Muestra pequena para PCA (ideal: n > 50). Los resultados son indicativos pero con intervalos de confianza amplios. Solucion futura: aplicar a nivel de UPZ (112 unidades).

2. **Granularidad:** El indicador opera a nivel de localidad. Dentro de una localidad, la variabilidad puede ser significativa (ej: Chapinero estrato 1 vs estrato 6).

3. **Temporalidad:** Los datos son de corte transversal (2024). No captura tendencias temporales.

4. **Cifra oculta:** Los datos objetivos solo incluyen delitos denunciados. Segun la EPV 2024, aproximadamente 70% de los delitos no se denuncian.

5. **KMO Dim.2 mediocre (0.6453):** La dimension subjetiva tiene estructura factorial menos clara. Dos componentes con eigenvalue >= 1 (percepcion ambiental vs experiencia directa) sugieren que podria descomponerse en sub-dimensiones.

---

## 7. Recomendaciones de mejora futura

### 7.1 Corto plazo
- **Integrar el ICSU en PostgreSQL** como campo calculado en `iug.criminalidad_localidad`
- **Combinar con ISEG** a nivel de inmueble: ISEG (micro-espacial) + ICSU (meso-localidad) = indicador hibrido multi-escala

### 7.2 Mediano plazo
- **Escalar a UPZ:** Aplicar la misma metodologia a las 112 UPZ de Bogota usando datos de la Policia Metropolitana por cuadrante
- **Agregar dimension temporal:** Series de tiempo 2018-2025 para capturar tendencias
- **Validacion espacial con Moran's I:** Verificar autocorrelacion espacial del indicador

### 7.3 Largo plazo
- **Modelo geoespacialmente ponderado (GWR):** Los pesos del PCA podrian variar espacialmente — las variables que mas importan para la seguridad pueden diferir entre el norte y el sur de Bogota
- **Machine Learning:** Random Forest para predecir percepcion a partir de criminalidad + variables socioeconomicas, identificando las features mas predictivas

---

## 8. Referencias bibliograficas

1. **OECD/JRC (2008).** Handbook on Constructing Composite Indicators: Methodology and User Guide. OECD Publishing, Paris.
   [https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf](https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf)

2. **Beltran-Gomez, L. (2019).** Cuales determinantes se relacionan con la percepcion de inseguridad? Un analisis estadistico y espacial para Bogota D.C. Revista Criminalidad, 61(1), 69-84.
   [http://www.scielo.org.co/scielo.php?script=sci_arttext&pid=S1794-31082019000100069](http://www.scielo.org.co/scielo.php?script=sci_arttext&pid=S1794-31082019000100069)

3. **Greco, S., Ishizaka, A., Tasiou, M. & Torrisi, G. (2019).** On the Methodological Framework of Composite Indices: A Review of the Issues of Weighting, Aggregation, and Robustness. Social Indicators Research, 141, 61-94.
   [https://link.springer.com/article/10.1007/s11205-017-1832-9](https://link.springer.com/article/10.1007/s11205-017-1832-9)

4. **JRC European Commission (2005).** Tools for Composite Indicators Building. EUR 21682 EN, Ispra.
   [https://publications.jrc.ec.europa.eu/repository/bitstream/JRC31473/EUR%2021682%20EN.pdf](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC31473/EUR%2021682%20EN.pdf)

5. **Demiroz, F. & Ekmekci, B. (2021).** Measuring local competitiveness: comparing and integrating two methods PCA and AHP. Quality & Quantity, 56, 2021-2041.
   [https://link.springer.com/article/10.1007/s11135-021-01181-z](https://link.springer.com/article/10.1007/s11135-021-01181-z)

6. **Mousavizadeh, H. et al. (2025).** From Planning to Perception: A Study of Urban Security in New Towns Using Machine Learning, Spatial Clustering, and Lived Experiences. Sustainable Cities and Society.
   [https://www.sciencedirect.com/science/article/pii/S2665972725004568](https://www.sciencedirect.com/science/article/pii/S2665972725004568)

7. **Demsar, U. et al. (2013).** Principal Component Analysis on Spatial Data: An Overview. Annals of the Association of American Geographers, 103(1), 106-128.
   [https://www.tandfonline.com/doi/abs/10.1080/00045608.2012.689236](https://www.tandfonline.com/doi/abs/10.1080/00045608.2012.689236)

8. **Ahmed, T. et al. (2025).** Enhancing Urban Quality of Life Evaluation Using Spatial Multi Criteria Analysis. Scientific Reports.
   [https://www.nature.com/articles/s41598-025-05468-1](https://www.nature.com/articles/s41598-025-05468-1)

9. **Tate, E. (2012).** Social vulnerability indices: a comparative assessment using uncertainty and sensitivity analysis. Natural Hazards, 63(2), 325-347.
   [https://pmc.ncbi.nlm.nih.gov/articles/PMC6448355/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6448355/)

10. **Camara de Comercio de Bogota (2024).** Encuesta de Percepcion y Victimizacion 2024. Base anonimizada, 26,064 registros.

11. **Kaiser, H.F. (1960).** The application of electronic computers to factor analysis. Educational and Psychological Measurement, 20, 141-151.

12. **Saaty, T.L. (1980).** The Analytic Hierarchy Process. McGraw-Hill, New York.

---

## 9. Archivos generados

| Archivo | Descripcion |
|---|---|
| `indicador_compuesto_pca.py` | Script completo de calculo del ICSU |
| `icsu_indicador_compuesto.json` | Resultados: ranking, pesos, clusters, sensibilidad |
| `epv_2024_analisis_completo.json` | Datos EPV procesados por localidad |
| `METODOLOGIA_ICSU.md` | Este documento |

---

## 10. Reproducibilidad

Para reproducir el calculo:

```bash
cd services/database/archivos/archivos/Seguridad/
python indicador_compuesto_pca.py
```

Requisitos: Python 3.8+ (sin dependencias externas — el script implementa PCA, KMO, Bartlett y K-means desde cero usando solo la libreria estandar + `json` y `math`).
