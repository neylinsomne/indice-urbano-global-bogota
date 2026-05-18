# Indicador de Dimensión (I_DIM)

## Descripción
Mide la **calidad dimensional** del inmueble usando **PCA (Principal Component Analysis)** sobre características físicas:
- Área construida
- Número de habitaciones
- Número de baños
- Antigüedad

---

## 📊 Tablas en Base de Datos

| Tabla | Descripción | Registros |
|-------|-------------|-----------|
| `iug.pca_pesos_dimension` | Pesos PCA entrenados | 4 componentes |
| `iug.indicador_dimension_raw` | Scores PCA raw | N inmuebles |
| `iug.indicador_dimension_final` | Vista materializada 0-5 | N inmuebles |

---

## 🧮 Fórmula

### PCA (Principal Component Analysis)
```
I_DIM_raw = Σ (w_i × x_i_normalizado)

Donde:
- x_i: Característica i (área, habitaciones, baños, antigüedad)
- w_i: Peso PCA del componente i (entrenado)
- Normalización: z-score por tipo de inmueble
```

### Entrenamiento PCA
```python
# services/indicators/hedonic/dimension/train_pca.py

# 1. Normalizar features por tipo
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 2. Entrenar PCA
pca = PCA(n_components=1)  # 1 componente principal
pca.fit(X_scaled)

# 3. Guardar pesos en BD
INSERT INTO iug.pca_pesos_dimension (feature, peso)
VALUES ('area_construida', w1), ...
```

### Normalización Final
```sql
I_DIM_normalizado = 5.0 × PERCENT_RANK() OVER (
    PARTITION BY tipo_inmueble 
    ORDER BY I_DIM_raw
)
```

---

## 📏 Features Utilizadas

| Feature | Peso Típico | Descripción |
|---------|-------------|-------------|
| **area_construida** | ~0.45 | Área en m² (mayor peso) |
| **habitaciones** | ~0.25 | Número de habitaciones |
| **banos** | ~0.20 | Número de baños |
| **antiguedad** | ~0.10 | Años desde construcción (negativo) |

**Nota**: Pesos exactos se calculan con PCA y varían según datos.

---

## 🔧 Scripts y Funciones

### Entrenamiento PCA (Mensual/Trimestral)
```python
# Entrenar con datos actuales
python services/indicators/hedonic/dimension/train_pca.py

# Guarda pesos en iug.pca_pesos_dimension
```

### Funciones SQL
```sql
-- Calcula I_DIM usando pesos PCA
iug.calcular_dimension_pca(area, habitaciones, banos, antiguedad, tipo)

-- Trigger automático
CREATE TRIGGER trg_inmueble_dimension
AFTER INSERT OR UPDATE ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.trg_calcular_dimension();
```

---

## 🔄 Actualización

### Automática
- ✅ **INSERT/UPDATE individual**: Trigger calcula I_DIM
- ✅ **Batch scraping**: Orquestador refresca vista

### Manual (Re-entrenar PCA)
```bash
# 1. Re-entrenar con datos nuevos
python services/indicators/hedonic/dimension/train_pca.py

# 2. Recalcular scores
SELECT iug.recalcular_dimension_masivo();

# 3. Refresh vista
REFRESH MATERIALIZED VIEW CONCURRENTLY iug.indicador_dimension_final;
```

**Frecuencia recomendada**: Trimestral o cuando haya cambios significativos en distribución de datos.

---

## 📈 Interpretación

| I_DIM | Interpretación |
|-------|----------------|
| **0.0 - 1.0** | Dimensión muy pequeña/básica |
| **1.0 - 2.5** | Dimensión pequeña |
| **2.5 - 3.5** | Dimensión media |
| **3.5 - 4.5** | Dimensión grande |
| **4.5 - 5.0** | Dimensión muy grande/premium |

---

## 🗂️ Archivos Relacionados

```
services/
├── indicators/hedonic/dimension/
│   ├── README.md                    # Este archivo
│   ├── train_pca.py                 # Entrenamiento PCA
│   └── calculator.py                # Utilidades Python
│
├── database/migrations/
│   └── V23__dimension_pca_indicator.sql  # Tablas/funciones
│
└── orchestrator/
    └── post_scraping.py             # Refresh automático
```

---

## 🔍 Consultas Útiles

```sql
-- Ver pesos PCA actuales
SELECT feature, peso, fecha_entrenamiento
FROM iug.pca_pesos_dimension
ORDER BY ABS(peso) DESC;

-- Distribución por tipo
SELECT tipo_inmueble,
       COUNT(*) n,
       ROUND(AVG(area_construida)) avg_area,
       ROUND(AVG(habitaciones)) avg_hab,
       ROUND(AVG(idim_normalizado), 2) avg_dim
FROM iug.inmueble i
JOIN iug.indicador_dimension_final d ON i.id_inmueble = d.id_inmueble
GROUP BY tipo_inmueble;

-- Top 10 mejor dimensión
SELECT id_inmueble, tipo_inmueble, 
       area_construida, habitaciones, banos,
       idim_normalizado
FROM iug.indicador_dimension_final d
JOIN iug.inmueble i USING (id_inmueble)
ORDER BY idim_normalizado DESC
LIMIT 10;
```

---

## 🔬 Validación del Modelo

```python
# Verificar varianza explicada
from services.indicators.hedonic.dimension.train_pca import validate_pca

# Debe explicar > 70% de varianza
variance_explained = validate_pca()
print(f"Varianza explicada: {variance_explained:.2%}")
```

---

## ⚠️ Consideraciones

1. **Normalización por tipo**: PCA se entrena **separadamente** por tipo de inmueble (Apartamento vs Casa tienen escalas diferentes)

2. **Outliers**: Valores extremos se filtran antes de entrenar (percentiles 1-99)

3. **Missing values**: Inmuebles sin `area_construida` o `habitaciones` no pueden calcular I_DIM

4. **Re-entrenamiento**: Necesario cuando:
   - Hay cambios en distribución de datos (nuevo scraping masivo)
   - Se agregan nuevos tipos de inmueble
   - Cada 3-6 meses para mantener actualizado
