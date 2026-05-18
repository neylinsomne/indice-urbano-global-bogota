# Metro de Bogotá (PLMB) — Decisión metodológica para el indicador de transporte

## Contexto

La Primera Línea del Metro de Bogotá (PLMB) es la infraestructura de transporte más importante
construida en la ciudad desde Transmilenio. Al momento de este estudio (2026) está en construcción
con apertura comercial confirmada para marzo de 2028.

La pregunta metodológica es: **¿se incluye o no en el indicador de transporte (I_ACC)?**

---

## Estado de la obra (marzo 2026)

- **Avance físico:** 73.75% (cierre febrero 2026)
- **Trenes:** primer tren llegó septiembre 2025; 30 trenes esperados octubre 2026
- **Pruebas operativas:** mayo 2026 en tramo Bosa–Kennedy (5.7 km)
- **Marcha blanca:** septiembre 2027 – marzo 2028
- **Apertura comercial:** 14 de marzo de 2028

---

## Ruta y localidades afectadas

**Longitud:** 23.96 km elevados (viaducto) | **Estaciones:** 16, de las cuales 10 integradas con TM

Trayecto oeste–este:
**Bosa → Kennedy → Puente Aranda → Los Mártires → Antonio Nariño → Santa Fe → Teusaquillo → Chapinero → Barrios Unidos**

Inicia en Av. Villavicencio con ALO (Bosa) y termina en Av. Caracas con Calle 72.

- Mapa oficial de estaciones: https://metrodebogota.gov.co/content/estaciones/estaciones-PLMB
- Trazado en IDECA: https://www.ideca.gov.co/recursos/mapas/trazado-primera-linea-del-metro-de-bogota

---

## Evidencia académica: el efecto anticipación es real

La literatura es consistente: las propiedades cerca de infraestructura de transporte en construcción
ya muestran efectos precio antes de la apertura. Excluir el metro sería ignorar un fenómeno
documentado y medible.

| Estudio | Fuente | Hallazgo principal |
|---|---|---|
| Cárdenas, Gallego & Urrutia (2022) | *Case Studies on Transport Policy* | +10.5% apartamentos y +6.5% casas dentro de 1.5 km tras anuncio del contrato (oct 2019) |
| Bogotank / U. de los Andes + Lincoln Institute (2023–24) | Reporte de política | +11.7% valor suelo en zona 800m tras anuncio; **+8.8% aún durante construcción** |
| JTLU — efectos anticipación 2007–2023 | *Journal of Transport and Land Use* | Efecto precio positivo desde 2016, antes de iniciar obras formalmente |
| Yiu & Wong (2005) | *Urban Studies* | Referencia canónica: mejoras de transporte esperadas capitalizadas antes de operar |
| Laval, Canadá (2016) | *Journal of Transport Geography* | +4% en apartamentos dentro de 800m, cinco años antes de la apertura |

Fuentes completas:
- https://www.sciencedirect.com/science/article/abs/pii/S2213624X22002413
- https://jtlu.org/index.php/jtlu/article/view/2593
- https://www.infobae.com/colombia/2026/02/21/el-metro-de-bogota-aun-no-arranca-y-ya-disparo-la-valorizacion-inmobiliaria-en-zonas-aledanas-estas-son-las-cifras/
- https://www.elespectador.com/bogota/el-metro-aun-no-opera-pero-ya-impulsa-la-valorizacion-del-suelo-en-bogota/

---

## Decisión: incluir con peso reducido y nota metodológica

El metro **se incluye** en I_ACC, no como transporte operativo sino como **variable de anticipación**,
diferenciado explícitamente de Transmilenio y SITP.

### Variables a agregar

```
dist_metro_km       →  distancia en km a la estación PLMB más cercana
metro_zone_800m     →  1/0 si el inmueble está dentro del buffer regulatorio de 800m
```

El buffer de 800m es el establecido por la regulación urbana de Bogotá alrededor de la Línea 1
y es el umbral utilizado en los estudios de Bogotank y JTLU.

### Peso en el gravity model

| Capa de transporte | Peso relativo |
|---|---|
| Transmilenio (operativo) | 1.0 |
| SITP / bus_stop (operativo) | 0.5 |
| **Metro L1 (en construcción)** | **0.65** |

El peso de 0.65 refleja que el efecto anticipación existe y es significativo (~8–11%)
pero es menor que el de infraestructura ya operativa. Se actualizará a 1.0 cuando abra en 2028.

### Nota metodológica obligatoria

Toda visualización o reporte que use I_ACC debe incluir:

> *El indicador de accesibilidad incluye la Primera Línea del Metro de Bogotá
> como infraestructura en construcción con apertura prevista en marzo de 2028.
> Su ponderación refleja el efecto de anticipación documentado en la literatura
> (Cárdenas et al. 2022; Bogotank/Lincoln Institute 2023–24) y será actualizada
> a peso operativo pleno tras la apertura comercial.*

---

## Pendiente de implementación

- [ ] Obtener shapefile oficial del trazado PLMB (IDECA o Metro de Bogotá)
- [ ] Cargar capa `iug.estacion_metro` con las 16 estaciones y sus coordenadas
- [ ] Agregar migración Flyway para la nueva tabla
- [ ] Actualizar función del gravity model para incluir la nueva capa con peso 0.65
- [ ] Agregar `dist_metro_km` y `metro_zone_800m` como columnas en `indicador_transporte_raw`
