# Samples

Ejemplos representativos del output del sistema.

## Cotizaciones (ACM)

- `cotizacion_ejemplo.pdf` — *(pendiente: generar desde la plataforma con un inmueble real)*

Para generar una nueva cotización:

1. Levantar el sistema localmente (ver [`docs/replicabilidad.md`](../docs/replicabilidad.md)).
2. Navegar a un inmueble en la interfaz.
3. Click en "Generar cotización".
4. Descargar el PDF.

O vía API:

```bash
curl -X POST http://localhost:8000/acm/generate \
  -H "Content-Type: application/json" \
  -d '{"id_inmueble": 5700}' \
  --output cotizacion.pdf
```
