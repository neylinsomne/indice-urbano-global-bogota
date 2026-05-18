# Indicador Normativo (I_PNU)

## Descripción

Mide el **potencial de desarrollo inmobiliario** según la normativa del Plan de Ordenamiento Territorial (POT 555) de Bogotá. Califica cada predio según tratamiento urbanístico, edificabilidad permitida y área de actividad.

---

## 📊 Tablas en Base de Datos

| Tabla                    | Descripción                                               | Registros        |
| ------------------------ | --------------------------------------------------------- | ---------------- |
| `iug.pot_tratamiento`    | Tratamiento urbanístico (renovación, consolidación, etc.) | ~5,700 polígonos |
| `iug.pot_edificabilidad` | Rango de edificabilidad (pisos permitidos)                | ~2,700 polígonos |
| `iug.pot_area_actividad` | Zonificación de uso del suelo                             | ~1,100 polígonos |
| `iug.pot_upl`            | Unidades de Planeamiento Local                            | ~197 polígonos   |

---

## 🧮 Fórmula

```
I_PNU = (0.4 × S_Trat) + (0.4 × S_Alt) + (0.2 × S_Uso)
```

Donde:

- **S_Trat**: Score de Tratamiento Urbanístico (1-5)
- **S_Alt**: Score de Edificabilidad/Altura (1-5)
- **S_Uso**: Score de Área de Actividad (1-5)

**Resultado**: Escala 0-5, donde 5 = máximo potencial de desarrollo normativo.

---

## 📏 Componentes y Scoring

### 1. Tratamiento Urbanístico (40%)

| Tratamiento           | Score | Descripción                                                |
| --------------------- | ----- | ---------------------------------------------------------- |
| Renovación Urbana     | 5.0   | Máximo potencial. Permite demolición y construcción nueva. |
| Desarrollo            | 4.5   | Alto potencial. Zonas de expansión urbana.                 |
| Consolidación         | 3.0   | Potencial medio. Mejoras y densificación moderada.         |
| Mejoramiento Integral | 2.0   | Potencial medio-bajo. Intervenciones limitadas.            |
| Conservación          | 1.0   | Restricciones fuertes. Protección patrimonial/ambiental.   |

### 2. Edificabilidad (40%)

| Rango       | Pisos Aprox. | Score | Descripción                              |
| ----------- | ------------ | ----- | ---------------------------------------- |
| 4 (A/B/C/D) | >12 pisos    | 5.0   | Torres permitidas. Alto aprovechamiento. |
| 3           | 7-12 pisos   | 4.0   | Edificios medios-altos. Buena densidad.  |
| 2           | 4-6 pisos    | 3.0   | Edificios bajos. Densidad media.         |
| 1           | 1-3 pisos    | 2.0   | Casas/unifamiliar. Densidad limitada.    |

### 3. Área de Actividad (20%)

| Código  | Nombre                           | Score | Descripción                         |
| ------- | -------------------------------- | ----- | ----------------------------------- |
| AAERAE  | Actividad Económica              | 5.0   | Comercio y servicios. Máximo flujo. |
| AAGSM   | Grandes Servicios Metropolitanos | 4.5   | Centros comerciales, hospitales.    |
| AAERVIS | Vivienda y Servicios             | 4.0   | Uso mixto residencial-comercial.    |
| AAPGSU  | Proximidad Generadora            | 3.5   | Servicios de proximidad.            |
| AAPRSU  | Proximidad Receptora             | 3.0   | Principalmente residencial.         |
| PEMP    | Patrimonio                       | 1.0   | Restricciones fuertes.              |

---

## 🔧 Scripts y Funciones

### Carga de Datos POT 555

```bash
cd services/database/loaders
python load_pot555.py
```

### Transformación de Coordenadas

Los archivos POT usan proyección personalizada de Bogotá (PCS_CarMAGBOG), registrada como SRID 900001 y transformada a WGS84 (EPSG:4326).

### Funciones SQL

```sql
-- Funciones de scoring
iug.score_tratamiento(nombre) → 1.0 a 5.0
iug.score_edificabilidad(rango) → 1.0 a 5.0
iug.score_area_actividad(codigo) → 1.0 a 5.0

-- Cálculo del indicador
psql -U postgres -d postgres -f loaders/calcular_ipnu.sql
```

### Recálculo Manual

```sql
-- Re-ejecutar cálculo completo
\i services/database/loaders/calcular_ipnu.sql
```

---

## 🔄 Actualización

### Automática

El indicador se calcula una vez para todos los inmuebles en Bogotá con geometría.

### Manual (Si se actualiza POT)

```bash
# 1. Recargar archivos POT actualizados
python services/database/loaders/load_pot555.py

# 2. Recalcular I_PNU
psql -U postgres -d postgres -f services/database/loaders/calcular_ipnu.sql
```

---

## 📈 Interpretación

| I_PNU         | Categoría  | Descripción                                                   |
| ------------- | ---------- | ------------------------------------------------------------- |
| **4.5 - 5.0** | Muy Alto   | Desarrollo de torres/proyectos grandes. Máximo ROI potencial. |
| **4.0 - 4.5** | Alto       | Proyectos medianos/grandes. Buen potencial de valorización.   |
| **3.5 - 4.0** | Medio-Alto | Desarrollo residencial/comercial estándar. Potencial sólido.  |
| **3.0 - 3.5** | Medio      | Vivienda de densidad media. Crecimiento moderado.             |
| **2.5 - 3.0** | Medio-Bajo | Vivienda unifamiliar/bifamiliar. Limitaciones de altura.      |
| **2.0 - 2.5** | Bajo       | Zonas con restricciones. Inversión conservadora.              |
| **< 2.0**     | Muy Bajo   | Conservación/protección. No recomendado para desarrollo.      |

---

## 📊 Estadísticas

- **Promedio:** 3.41
- **Desviación Estándar:** 0.48
- **Mínimo:** 1.6
- **Mediana:** 3.5
- **Máximo:** 5.0
- **Cobertura:** 3,066 inmuebles en Bogotá (68.3% del total)

### Distribución por Tratamiento

- Consolidación: 70.6% (I_PNU promedio: 3.38)
- Renovación: 18.5% (I_PNU promedio: 3.85)
- Conservación: 4.2% (I_PNU promedio: 2.25)

---

## 🗂️ Archivos Relacionados

```
services/
├── indicators/normative/
│   ├── README.md                    # Este archivo
│   ├── calculator.py                # Utilidades Python
│   └── config.py                    # PESOS, SCORING

├── database/loaders/
│   ├── load_pot555.py               # Carga archivos POT
│   └── calcular_ipnu.sql            # Cálculo del indicador

└── database/archivos/POT 555/
    ├── areaactividad.json           # 9.1 MB
    ├── tratamientourbanistico.json  # 17.6 MB
    ├── rango_edificabilidad_desarro.geojson  # 16.5 MB
    └── unidadplaneamientolocal.json # 1.9 MB
```

---

## 🔍 Consultas Útiles

```sql
-- Inmuebles con alto potencial normativo
SELECT id_inmueble, ubicacion, precio, ipnu
FROM iug.inmueble
WHERE ipnu >= 4.0
ORDER BY ipnu DESC, precio ASC
LIMIT 20;

-- Distribución por tratamiento
SELECT
    t.nombre as tratamiento,
    COUNT(*) as n_inmuebles,
    ROUND(AVG(i.ipnu)::numeric, 2) as ipnu_promedio
FROM iug.inmueble i
JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
WHERE i.ipnu IS NOT NULL
GROUP BY t.nombre
ORDER BY ipnu_promedio DESC;

-- Inmuebles en zonas de renovación con alta edificabilidad
SELECT i.id_inmueble, i.ubicacion, i.ipnu,
       t.nombre as tratamiento,
       e.rango as edificabilidad
FROM iug.inmueble i
JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
WHERE t.nombre ILIKE '%renovaci%'
  AND e.rango IN ('4', '4A', '4B', '4C', '4D')
ORDER BY i.ipnu DESC;

-- Obtener información POT completa de un inmueble
SELECT
    i.id_inmueble,
    i.ipnu,
    t.nombre as tratamiento,
    e.rango as edificabilidad,
    a.codigo as area_actividad,
    u.nombre as upl
FROM iug.inmueble i
LEFT JOIN iug.pot_tratamiento t ON ST_Within(i.geom, t.geom)
LEFT JOIN iug.pot_edificabilidad e ON ST_Within(i.geom, e.geom)
LEFT JOIN iug.pot_area_actividad a ON ST_Within(i.geom, a.geom)
LEFT JOIN iug.pot_upl u ON ST_Within(i.geom, u.geom)
WHERE i.id_inmueble = 123;
```

---

## 📚 Documentación Adicional

Ver archivos en `/docs/`:

- `indicador_ipnu.md` - Metodología y casos de uso
- `implementacion_ipnu.md` - Detalles técnicos de implementación
- `troubleshooting_ipnu.md` - Solución de problemas
- `guia_uso_ipnu.md` - Queries SQL y ejemplos prácticos
