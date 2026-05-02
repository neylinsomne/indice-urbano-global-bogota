# Scripts auxiliares

## `generar_cotizacion_sample.py`

Genera un PDF de muestra del Análisis Comparativo de Mercado (ACM) usando los datos del **Apto 5700 (Puente Largo, Chapinero)** que aparece en el Capítulo 4 de la tesis.

### Por qué este script existe

El sistema productivo (`services/api/services/acm_pdf.py` en el repo del proyecto principal) genera el PDF a partir de la base de datos PostGIS. Este script reproduce el mismo formato visual de manera **autocontenida**: no requiere base de datos, ni API, ni Docker. Solo Python + `fpdf2`.

### Uso

```bash
pip install fpdf2
python scripts/generar_cotizacion_sample.py
```

Salida: `samples/cotizacion_ejemplo.pdf`

### Por qué los datos son del Apto 5700

Coherencia con la tesis: el lector que abra el PDF reconoce inmediatamente el inmueble porque ya lo vio en la "Ficha de inmueble individual" del Capítulo 4. Esto evita que el sample parezca desconectado del documento académico.

### Sobre la imagen del inmueble

El sample usa un **placeholder con marca de agua** ("MUESTRA ACADÉMICA"). En el sistema productivo, la imagen se descarga automáticamente del listado original. Para esta muestra pública se omite por:

- Derechos de uso de las imágenes de los portales inmobiliarios.
- Buenas prácticas académicas (la muestra no representa un inmueble específico en venta actualmente).

Si quieres regenerar el sample con una imagen real (foto stock royalty-free, por ejemplo), puedes modificar la función `render_subject` para que cargue una imagen desde disco vía `self.image(path, ...)`.
