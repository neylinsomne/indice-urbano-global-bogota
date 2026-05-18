# 📊 ETL Scripts - Procesamiento de Datos

Scripts de ETL (Extract, Transform, Load) para procesar datos de MongoDB, calcular indicadores y entrenar modelos.

## Scripts Disponibles

### 1. Características de Inmuebles
**`load_caracteristicas.py`** - Migración de amenidades

**Funcionalidad:**
- Extrae características de MongoDB (array `caracteristicas`)
- Limpia "Ver más" del final de los strings
- Crea catálogo único en `iug.cat_caracteristica`
- Relaciona inmuebles con características en `iug.inmueble_caracteristica`

**Uso:**
```bash
cd services/etl
python load_caracteristicas.py
```

**Resultado:**
- Catálogo de ~50-100 características únicas
- Relaciones many-to-many para I_Dot (indicador de dotación)

---

### 2. Indicador de Dimensión (PCA)
**`calculate_pca_dimension.py`** - Análisis de Componentes Principales

**Funcionalidad:**
- Calcula PCA de variables físicas (área, habitaciones, baños)
- Genera loadings por tipo de inmueble
- Guarda coeficientes en `iug.pca_loadings_dimension`

**Uso:**
```bash
python calculate_pca_dimension.py
```

**Variables usadas:**
- `area_construida`, `area_privada`
- `habitaciones`, `banos`

**Output:**
- Loadings φ (phi) de PC1
- Parámetros de estandarización (mean, std)
- % varianza explicada

---

### 3. Modelo Hedónico de Precios
**`train_hedonic_model.py`** - Regresión de precios

**Funcionalidad:**
- Entrena modelo ln(Precio/m²) = α + Σ(β·vars)
- Calcula coeficientes por tipo de inmueble
- Guarda en `iug.hedonic_model_coefs`

**Uso:**
```bash
python train_hedonic_model.py
```

**Métricas:**
- R², RMSE, MAE
- Coeficientes β para cada variable estructural

**Nota:** Este es el modelo "vista del mercado" para comparación, NO el indicador objetivo I_HED.

---

### 4. Pesos AHP para Criminalidad
**`calcular_ahp_crimen.py`** - Analytic Hierarchy Process

**Funcionalidad:**
- Calcula pesos AHP para tipos de delito
- Usa matriz de comparación par a par
- Verifica consistencia (CR < 0.10)

**Uso:**
```bash
python calcular_ahp_crimen.py
```

**Output:**
- Homicidios: ~0.566
- Delitos Sexuales: ~0.267
- Hurto Personas: ~0.120
- Otros: ~0.047

---

## Dependencias

### Python Packages
```bash
pip install pymongo psycopg2-binary numpy pandas scikit-learn
```

### Variables de Entorno

**MongoDB:**
```
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DATABASE=prueba
```

**PostgreSQL:**
```
PG_HOST=localhost
PG_PORT=5434
PG_DATABASE=postgres
PG_USER=postgres
PG_PASSWORD=postgres
```

---

## Orden de Ejecución

Para pipeline completo de indicadores:

```bash
# 1. Características (amenidades para I_Dot)
python load_caracteristicas.py

# 2. PCA (para I_Dim)
python calculate_pca_dimension.py

# 3. AHP criminalidad (para I_Seg)
python calcular_ahp_crimen.py

# 4. Modelo hedónico (comparación mercado)
python train_hedonic_model.py
```

---

## Estructura de Datos

### Entrada: MongoDB
```javascript
{
  "caracteristicas": [
    "Acceso Pavimentado",
    "Parqueadero VisitantesVer más",  // Se limpia
    "Gimnasio",
    ...
  ],
  "area_construida": 74.73,
  "habitaciones": 2,
  "banos": 2,
  "precio": 457733000
}
```

### Salida: PostgreSQL

**Catálogo:**
```sql
iug.cat_caracteristica
├── id_caracteristica (PK)
├── nombre_caracteristica (UNIQUE) - "Acceso Pavimentado"
└── tipo_dato - "boolean"
```

**Relaciones:**
```sql
iug.inmueble_caracteristica
├── id_inmueble (FK)
├── id_caracteristica (FK)
└── valor_boolean - TRUE
```

**Indicadores:**
```sql
iug.pca_loadings_dimension     -- Loadings PCA
iug.indicador_dimension_raw    -- PC1 scores
iug.indicador_dimension_final  -- I_Dim 0-5
```

---

## Notas

⚠️ **Estrato no va en PCA** - El estrato es una característica del barrio/zona, no una dimensión física. Debe ir a las amenidades/dotación.

✅ **PCA solo usa variables físicas** - area, habitaciones, baños (tamaño/envergadura)

📊 **I_HED tiene 2 componentes:**
- I_Dim (70%): PCA de variables físicas
- I_Dot (30%): Suma ponderada de amenidades
