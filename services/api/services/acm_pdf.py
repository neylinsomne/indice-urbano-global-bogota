"""
Renderizador PDF para Análisis Comparativo de Mercado (ACM).

Genera un PDF profesional replicando el formato estándar de avalúos
inmobiliarios en Colombia, usando fpdf2.
"""
import os
import tempfile
import urllib.request
import logging
from fpdf import FPDF

logger = logging.getLogger(__name__)


# ── Generador de mapa estático ────────────────────────────────────

def _generate_static_map(subject: dict, comparables: list,
                          indicators: dict = None) -> str:
    """
    Genera un mapa estático PNG con el inmueble sujeto, comparables
    y opcionalmente indicadores de zona. Retorna path al archivo temporal.
    """
    try:
        import staticmap

        lat = subject.get('latitud') or subject.get('lat')
        lon = subject.get('longitud') or subject.get('lon')

        if not lat or not lon:
            return None

        m = staticmap.StaticMap(600, 350, url_template=(
            'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'
        ))

        # Circulo de zona de búsqueda (2km aprox)
        m.add_line(staticmap.CircleMarker(
            (float(lon), float(lat)), '#1B496520', 80,
        ))

        # Marcadores de comparables (azul)
        for comp_row in comparables:
            comp = comp_row.get('comparable', {})
            clat = comp.get('latitud') or comp.get('lat')
            clon = comp.get('longitud') or comp.get('lon')
            if clat and clon:
                m.add_marker(staticmap.CircleMarker(
                    (float(clon), float(clat)), '#5FA8D3', 10,
                ))

        # Marcador del sujeto (dorado, más grande)
        m.add_marker(staticmap.CircleMarker(
            (float(lon), float(lat)), '#E8C96A', 14,
        ))

        image = m.render(zoom=14)

        # Agregar leyenda con Pillow si está disponible
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(image)

            # Fondo semi-transparente para leyenda
            legend_x, legend_y = 10, 10
            draw.rectangle([legend_x, legend_y, legend_x + 160, legend_y + 55],
                           fill=(255, 255, 255, 220), outline=(200, 200, 200))

            # Texto leyenda
            draw.ellipse([legend_x + 8, legend_y + 8, legend_x + 22, legend_y + 22],
                         fill='#E8C96A')
            draw.text((legend_x + 28, legend_y + 8), 'Inmueble sujeto',
                      fill='#333333')
            draw.ellipse([legend_x + 8, legend_y + 28, legend_x + 22, legend_y + 42],
                         fill='#5FA8D3')
            draw.text((legend_x + 28, legend_y + 28), 'Comparables',
                      fill='#333333')

            # Indicadores si están disponibles
            if indicators:
                iurb = indicators.get('iurb', 0)
                label = f'IURB zona: {iurb:.1f}/10' if iurb else ''
                if label:
                    draw.text((legend_x + 8, legend_y + 45), label,
                              fill='#1B4965')
        except ImportError:
            pass

        # Guardar a temporal
        fd, tmp_path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        image.save(tmp_path)
        return tmp_path

    except Exception as e:
        logger.warning(f"No se pudo generar mapa estático: {e}")
        return None


def clean_text(text: str) -> str:
    """Limpia texto para compatibilidad con fpdf2 (Latin-1)."""
    if not text:
        return ''
    replacements = {
        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '--', '\u2026': '...', '\u00a0': ' ',
        '\u2022': '*', '\u2192': '->', '\u2264': '<=', '\u2265': '>=',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    result = []
    for ch in text:
        try:
            ch.encode('latin-1')
            result.append(ch)
        except UnicodeEncodeError:
            pass
    return ''.join(result)


def format_cop(value) -> str:
    """Formatea un número como peso colombiano: $ 580.000.000"""
    if value is None:
        return '$ 0'
    if isinstance(value, str):
        value = float(value)
    return f"$ {int(value):,}".replace(',', '.')


def format_number(value, decimals=0) -> str:
    """Formatea un número con separador de miles."""
    if value is None:
        return '0'
    if isinstance(value, str):
        value = float(value)
    if decimals == 0:
        return f"{int(value):,}".replace(',', '.')
    return f"{value:,.{decimals}f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def _is_safe_url(url: str) -> bool:
    """Validate URL to prevent SSRF attacks."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.hostname or ''
        # Block private/internal IPs
        if host in ('localhost', '127.0.0.1', '0.0.0.0', '::1', ''):
            return False
        if host.startswith('10.') or host.startswith('192.168.') or host.startswith('172.'):
            return False
        if host.endswith('.internal') or host.endswith('.local'):
            return False
        return True
    except Exception:
        return False


MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


def _download_image(url: str) -> str:
    """Descarga imagen a archivo temporal con proteccion SSRF. Retorna path o None."""
    if not url or not _is_safe_url(url):
        return None
    try:
        suffix = '.jpg'
        if '.png' in url.lower():
            suffix = '.png'
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        req = urllib.request.Request(url, headers={'User-Agent': 'INMU-PDF/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_IMAGE_SIZE:
                return None
            data = response.read(MAX_IMAGE_SIZE + 1)
            if len(data) > MAX_IMAGE_SIZE:
                os.unlink(tmp_path)
                return None
            with open(tmp_path, 'wb') as f:
                f.write(data)

        if os.path.getsize(tmp_path) < 100:
            os.unlink(tmp_path)
            return None
        return tmp_path
    except Exception as e:
        logger.warning(f"No se pudo descargar imagen: {e}")
        return None


class ACMPDF(FPDF):
    """PDF del Análisis Comparativo de Mercado."""

    def __init__(self, logo_path: str = None):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=15)
        self.logo_path = logo_path
        # Colores del tema (blue/gold palette)
        self.color_primary = (27, 73, 101)       # #1B4965
        self.color_primary_light = (95, 168, 211) # #5FA8D3
        self.color_gold = (232, 201, 106)          # #E8C96A
        self.color_dark = (51, 51, 51)
        self.color_gray = (100, 100, 100)
        self.color_light_gray = (240, 240, 240)
        self.color_white = (255, 255, 255)
        # Aliases para compatibilidad con secciones existentes
        self.color_green = self.color_primary
        self.color_green_light = self.color_primary_light

    def header(self):
        pass  # Header manual por sección

    def footer(self):
        self.set_y(-12)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'INMU - Estudio Inmobiliario | Pagina {self.page_no()}',
                  align='C')

    # ──────────────────────────────────────────────────────────────
    # Secciones del reporte
    # ──────────────────────────────────────────────────────────────

    def render_header(self):
        """Barra de título con logo opcional."""
        self.set_fill_color(*self.color_primary)
        self.rect(0, 0, 210, 22, style='F')

        # Logo del cliente (esquina izquierda)
        logo_offset = 10
        if self.logo_path:
            try:
                self.image(self.logo_path, x=5, y=2, h=18)
                logo_offset = 28  # Desplazar título
            except Exception:
                pass

        self.set_xy(logo_offset, 5)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(*self.color_white)
        title_w = 200 - logo_offset
        self.cell(title_w, 12,
                  clean_text('ANALISIS DE MERCADO Y PRECIO OBJETIVO DE VENTA'),
                  align='C')

        # Logo INMU (esquina derecha)
        inmu_logo = os.path.join(os.path.dirname(__file__), '..', 'static', 'logo-inmu.png')
        if os.path.exists(inmu_logo):
            try:
                self.image(inmu_logo, x=188, y=2, h=18)
            except Exception:
                pass

        self.ln(18)

    def render_property_info(self, subject: dict, img_path: str = None):
        """Ficha del inmueble sujeto + foto."""
        y_start = self.get_y() + 2
        self.set_xy(10, y_start)

        # Tabla de información (columna izquierda)
        # Extraer barrio de ubicacion (formato: "Barrio, Ciudad, Depto")
        ubicacion = subject.get('ubicacion', '')
        barrio = ubicacion.split(',')[0].strip() if ubicacion else ''
        ciudad = subject.get('ciudad', '')

        fields = [
            ('Tipo inmueble', subject.get('tipo_inmueble', '')),
            ('Barrio', barrio),
            ('Ciudad', ciudad),
            ('Estado', subject.get('estado', 'N/A') or 'N/A'),
            ('Antiguedad', subject.get('edad', 'N/A') or 'N/A'),
            ('Area (mt2)', format_number(subject.get('area_construida', 0))),
            ('Estrato', str(subject.get('estrato', 'N/A') or 'N/A')),
            ('Precio listado', format_cop(subject.get('precio'))),
        ]

        label_w = 35
        value_w = 55
        row_h = 6.5

        for i, (label, value) in enumerate(fields):
            y = y_start + i * row_h
            self.set_xy(10, y)
            # Label
            self.set_font('Helvetica', 'B', 8)
            self.set_text_color(*self.color_dark)
            self.set_fill_color(*self.color_light_gray)
            self.cell(label_w, row_h, clean_text(f' {label}'), border=1, fill=True)
            # Value
            self.set_font('Helvetica', '', 8)
            self.set_text_color(*self.color_gray)
            self.cell(value_w, row_h, clean_text(f' {value}'), border=1)

        # Foto (columna derecha)
        img_x = 110
        img_y = y_start
        img_w = 88
        img_h = len(fields) * row_h

        if img_path:
            try:
                self.image(img_path, x=img_x, y=img_y, w=img_w, h=img_h)
                # Borde alrededor de la imagen
                self.set_draw_color(200, 200, 200)
                self.rect(img_x, img_y, img_w, img_h)
            except Exception:
                self._draw_placeholder(img_x, img_y, img_w, img_h)
        else:
            self._draw_placeholder(img_x, img_y, img_w, img_h)

        self.set_y(y_start + len(fields) * row_h + 4)

    def _draw_placeholder(self, x, y, w, h):
        """Dibuja placeholder cuando no hay imagen."""
        self.set_fill_color(220, 220, 220)
        self.rect(x, y, w, h, style='F')
        self.set_xy(x, y + h / 2 - 4)
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(150, 150, 150)
        self.cell(w, 8, 'Sin imagen disponible', align='C')

    def render_subtitle(self, text: str):
        """Subtítulo con indicador de calidad."""
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(*self.color_gray)
        self.set_x(10)
        self.multi_cell(190, 4, clean_text(text))
        self.ln(2)

    def render_comparables_table(self, comparables: list):
        """Tabla de comparables con factores de homologación."""
        # Anchos de columna (total = 190mm)
        cols = [
            ('#', 6),
            ('Descripcion', 38),
            ('Fuente', 20),
            ('Fecha', 16),
            ('Valor', 24),
            ('Area (Mt2)', 14),
            ('Precio x Mt2', 20),
            ('F. Oferta', 14),
            ('F. Conserv.', 16),
            ('Precio Mt2\nHomologado', 22),
        ]

        # Header de la tabla
        self.set_fill_color(*self.color_green)
        self.set_text_color(*self.color_white)
        self.set_font('Helvetica', 'B', 6)
        self.set_draw_color(200, 200, 200)

        y_header = self.get_y()
        x = 10
        header_h = 10

        for col_name, col_w in cols:
            self.set_xy(x, y_header)
            self.multi_cell(col_w, header_h / 2, clean_text(col_name),
                            border=1, align='C', fill=True)
            x += col_w

        self.set_y(y_header + header_h)

        # Filas de datos
        row_h = 12
        for row_data in comparables:
            comp = row_data['comparable']
            hom = row_data['homologation']

            # Descripción: tipo + barrio + antigüedad
            desc = f"{comp.get('tipo_inmueble', '')} {comp.get('ubicacion', '')}"
            if comp.get('edad'):
                desc += f" / {comp['edad']}"

            fecha_str = ''
            if comp.get('fecha'):
                try:
                    fecha_str = comp['fecha'].strftime('%b/%Y')
                except AttributeError:
                    fecha_str = str(comp['fecha'])[:7]

            values = [
                str(row_data['numero']),
                desc[:50],
                clean_text(str(comp.get('pagina', '') or '').replace('_', ' ').title()[:20]),
                fecha_str,
                format_cop(comp.get('precio')),
                format_number(comp.get('area_construida')),
                format_cop(hom['precio_m2']),
                str(hom['factor_oferta']),
                str(hom['factor_conservacion']),
                format_cop(hom['precio_m2_hom']),
            ]

            # Alternar color de fondo
            if row_data['numero'] % 2 == 0:
                self.set_fill_color(248, 248, 248)
            else:
                self.set_fill_color(*self.color_white)

            y_row = self.get_y()
            x = 10
            self.set_font('Helvetica', '', 6)
            self.set_text_color(*self.color_dark)

            for i, (_, col_w) in enumerate(cols):
                self.set_xy(x, y_row)
                align = 'C' if i in (0, 5, 7, 8) else ('R' if i in (4, 6, 9) else 'L')
                val = clean_text(values[i])
                # Para descripción usar multi_cell con tamaño más pequeño
                if i == 1:
                    self.set_font('Helvetica', '', 5.5)
                    self.multi_cell(col_w, row_h / 3, f' {val}', border=1,
                                    align=align, fill=True)
                    self.set_font('Helvetica', '', 6)
                else:
                    self.cell(col_w, row_h, f' {val} ', border=1,
                              align=align, fill=True)
                x += col_w

            self.set_y(y_row + row_h)

        self.ln(2)

    def render_statistics(self, stats: dict):
        """Tabla de estadisticas a la derecha."""
        # t-Student o Z segun lo que devuelva compute_statistics
        n_comp = stats.get('n_comparables', '?')
        gl = stats.get('grados_libertad', '?')

        if 't_student' in stats:
            dist_label = f't-Student (gl={gl})'
            dist_value = f"{stats['t_student']:.4f}"
        else:
            dist_label = 'Z (Dist normal)'
            dist_value = f"{stats.get('z_dist_normal', 0):.6f}"

        # Asimetria: puede ser None si n < 8
        asimetria = stats.get('coeficiente_asimetria')
        if asimetria is not None:
            asimetria_str = f"{asimetria:.2f}%"
        else:
            nota = stats.get('nota_asimetria', f'n={n_comp} < 8')
            asimetria_str = f"N/A ({nota})"

        stat_rows = [
            ('Promedio aritmetico mt2', format_cop(stats['promedio_m2'])),
            ('Desviacion tipica (muestral)', format_cop(stats['desviacion_tipica'])),
            ('Coeficiente de variacion', f"{stats['coeficiente_variacion']:.2f}%"),
            ('Limite superior (IC 90%)', format_cop(stats['limite_superior'])),
            ('Limite inferior (IC 90%)', format_cop(stats['limite_inferior'])),
            ('Coeficiente de asimetria', asimetria_str),
            (dist_label, dist_value),
            ('N comparables', str(n_comp)),
        ]

        # Alinear a la derecha
        x_start = 105
        label_w = 50
        value_w = 45
        row_h = 5.5

        for i, (label, value) in enumerate(stat_rows):
            y = self.get_y() + i * row_h
            self.set_xy(x_start, y)

            self.set_font('Helvetica', '', 7)
            self.set_text_color(*self.color_dark)
            self.cell(label_w, row_h, clean_text(label), border=0, align='R')

            self.set_font('Helvetica', 'B', 7)
            self.set_text_color(*self.color_green)
            self.cell(value_w, row_h, clean_text(value), border=0, align='R')

        self.set_y(self.get_y() + len(stat_rows) * row_h + 3)

    def render_chart(self, comparables: list, stats: dict):
        """Gráfico de barras de precio/m2 homologado."""
        prices = [r['homologation']['precio_m2_hom'] for r in comparables]
        mean = stats['promedio_m2']

        if not prices or max(prices) == 0:
            return

        # Dimensiones del gráfico
        chart_x = 15
        chart_y = self.get_y() + 2
        chart_w = 120
        chart_h = 40

        # Verificar si necesitamos nueva página
        if chart_y + chart_h + 30 > 280:
            self.add_page()
            chart_y = self.get_y() + 2

        # Título del gráfico
        self.set_xy(chart_x, chart_y - 6)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(*self.color_dark)
        self.cell(chart_w, 5, 'Precio x Mt 2 (Homologado)', align='C')

        max_val = max(max(prices), mean) * 1.15
        min_val = min(min(prices), mean) * 0.5

        # Eje Y
        self.set_draw_color(200, 200, 200)
        self.line(chart_x, chart_y, chart_x, chart_y + chart_h)
        # Eje X
        self.line(chart_x, chart_y + chart_h, chart_x + chart_w, chart_y + chart_h)

        # Barras
        n = len(prices)
        bar_spacing = chart_w / (n + 1)
        bar_w = bar_spacing * 0.6

        for i, p in enumerate(prices):
            bar_h = ((p - min_val) / (max_val - min_val)) * chart_h if max_val > min_val else chart_h * 0.5
            bar_x = chart_x + (i + 1) * bar_spacing - bar_w / 2
            bar_y = chart_y + chart_h - bar_h

            self.set_fill_color(*self.color_green_light)
            self.rect(bar_x, bar_y, bar_w, bar_h, style='F')

            # Valor encima de la barra
            self.set_xy(bar_x - 5, bar_y - 5)
            self.set_font('Helvetica', '', 5.5)
            self.set_text_color(*self.color_dark)
            self.cell(bar_w + 10, 4, format_cop(p), align='C')

            # Etiqueta debajo
            self.set_xy(bar_x - 2, chart_y + chart_h + 1)
            self.set_font('Helvetica', '', 6)
            self.cell(bar_w + 4, 4, str(i + 1), align='C')

        # Línea de promedio (punteada)
        mean_y = chart_y + chart_h - ((mean - min_val) / (max_val - min_val)) * chart_h
        self.set_draw_color(200, 50, 50)
        self.set_line_width(0.3)
        self.dashed_line(chart_x, mean_y, chart_x + chart_w, mean_y, dash_length=2, space_length=1.5)
        self.set_line_width(0.2)

        self.set_y(chart_y + chart_h + 10)

    def render_price_objectives(self, objectives: dict):
        """Tabla de precios objetivo con rangos de tiempo."""
        # Verificar espacio
        if self.get_y() + 35 > 280:
            self.add_page()

        y_start = self.get_y() + 2

        rows = [
            ('PRECIO DE VENTA OBJETIVO', objectives['precio_objetivo'],
             objectives['rango_objetivo'], self.color_green),
            ('PRECIO DE VENTA MINIMO', objectives['precio_minimo'],
             objectives['rango_minimo'], (255, 152, 0)),
            ('PRECIO DE VENTA MAXIMO', objectives['precio_maximo'],
             objectives['rango_maximo'], (33, 150, 243)),
        ]

        # Header de la tabla
        x_start = 25
        label_w = 60
        price_w = 45
        range_w = 40
        row_h = 8

        self.set_xy(x_start + label_w, y_start)
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(*self.color_dark)
        self.cell(price_w + range_w, 6, 'RANGO TIEMPO VENTA', align='C')
        self.ln(7)

        for label, price, rango, color in rows:
            y = self.get_y()
            self.set_xy(x_start, y)

            # Label
            self.set_font('Helvetica', 'B', 7.5)
            self.set_text_color(*self.color_dark)
            self.set_fill_color(*self.color_light_gray)
            self.cell(label_w, row_h, clean_text(f' {label}'), border=1, fill=True)

            # Precio
            self.set_font('Helvetica', 'B', 8)
            self.set_text_color(*color)
            self.cell(price_w, row_h, clean_text(f' {format_cop(price)} '), border=1, align='C')

            # Rango
            self.set_font('Helvetica', '', 7.5)
            self.set_text_color(*self.color_gray)
            self.cell(range_w, row_h, clean_text(f' {rango}'), border=1, align='C')

            self.ln(row_h)

        self.ln(4)

    def render_zone_map(self, map_path: str, indicators: dict = None):
        """Mapa de ubicación con indicadores de zona."""
        if self.get_y() + 85 > 275:
            self.add_page()

        # Título de sección
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(*self.color_primary)
        self.set_x(10)
        self.cell(190, 6, 'UBICACION E INDICADORES DE ZONA', align='C')
        self.ln(7)

        y_start = self.get_y()

        # Mapa (columna izquierda)
        if map_path:
            try:
                self.image(map_path, x=10, y=y_start, w=120, h=65)
                self.set_draw_color(200, 200, 200)
                self.rect(10, y_start, 120, 65)
            except Exception:
                self._draw_placeholder(10, y_start, 120, 65)
        else:
            self._draw_placeholder(10, y_start, 120, 65)

        # Indicadores (columna derecha)
        if indicators:
            x_ind = 135
            ind_w = 65
            row_h = 8

            indicator_rows = [
                ('IURB', indicators.get('iurb'), self.color_primary),
                ('Accesibilidad', indicators.get('iacc'), (52, 183, 136)),
                ('Seguridad', indicators.get('iseg'), (239, 83, 80)),
                ('Dotaciones', indicators.get('idot'), self.color_primary_light),
                ('Hab. Hedonica', indicators.get('ihed'), self.color_gold),
                ('Precio Unit.', indicators.get('ipnu'), (100, 100, 100)),
            ]

            for i, (label, value, color) in enumerate(indicator_rows):
                y = y_start + i * row_h + 4
                self.set_xy(x_ind, y)

                # Label
                self.set_font('Helvetica', '', 7)
                self.set_text_color(*self.color_dark)
                self.cell(32, row_h, clean_text(label), border=0)

                # Barra de progreso
                if value is not None:
                    val = float(value)
                    bar_x = x_ind + 32
                    bar_y = y + 2
                    bar_max_w = 20
                    bar_h = 4
                    bar_fill_w = min(bar_max_w, (val / 10.0) * bar_max_w)

                    self.set_fill_color(230, 230, 230)
                    self.rect(bar_x, bar_y, bar_max_w, bar_h, style='F')
                    self.set_fill_color(*color)
                    self.rect(bar_x, bar_y, bar_fill_w, bar_h, style='F')

                    # Valor numérico
                    self.set_xy(bar_x + bar_max_w + 2, y)
                    self.set_font('Helvetica', 'B', 7)
                    self.set_text_color(*color)
                    self.cell(10, row_h, f'{val:.1f}', align='L')

            # IURB destacado al final
            iurb = indicators.get('iurb')
            if iurb is not None:
                y_iurb = y_start + 56
                self.set_xy(x_ind, y_iurb)
                self.set_font('Helvetica', 'B', 8)
                self.set_text_color(*self.color_primary)
                self.cell(ind_w, 6,
                          clean_text(f'Indice Urbano Global: {float(iurb):.2f} / 10'),
                          align='C')

        self.set_y(y_start + 70)

    def render_sources(self, comparables: list, subject: dict):
        """Sección de Fuentes con URLs de los anuncios."""
        # Recopilar todas las URLs
        urls = []
        if subject.get('url_anuncio'):
            urls.append(('Sujeto', subject['url_anuncio']))
        for row in comparables:
            comp = row['comparable']
            url = comp.get('url_anuncio', '')
            if url:
                urls.append((f"Comparable {row['numero']}", url))

        if not urls:
            return

        # Verificar espacio
        needed = 10 + len(urls) * 4
        if self.get_y() + needed > 275:
            self.add_page()

        self.set_font('Helvetica', 'B', 7)
        self.set_text_color(*self.color_dark)
        self.set_x(55)
        self.cell(40, 5, 'Fuentes')
        self.ln(5)

        for label, url in urls:
            self.set_font('Helvetica', '', 5.5)
            self.set_text_color(30, 100, 200)
            self.set_x(30)
            self.cell(0, 3.5, clean_text(url), link=url)
            self.ln(3.5)

        self.ln(3)

    def render_footer_info(self, generated_at: str):
        """Pie con fecha y elaborador."""
        # Verificar espacio
        if self.get_y() + 15 > 275:
            self.add_page()

        self.set_draw_color(*self.color_green_light)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

        self.set_font('Helvetica', 'B', 7)
        self.set_text_color(*self.color_dark)
        self.set_x(10)
        self.cell(30, 5, 'FECHA:', align='R')
        self.set_font('Helvetica', '', 7)
        self.cell(40, 5, f' {generated_at}')

        self.ln(5)
        self.set_font('Helvetica', 'B', 7)
        self.set_x(10)
        self.cell(30, 5, 'ELABORADO POR:', align='R')
        self.set_font('Helvetica', '', 7)
        self.cell(60, 5, ' INMU - Estudio Inmobiliario')


def generate_acm_pdf(acm_data: dict, logo_path: str = None) -> bytes:
    """
    Genera el PDF completo del ACM.

    Args:
        acm_data: Datos del ACM (subject, comparables, statistics, objectives)
        logo_path: Path opcional al logo del negocio del usuario

    Retorna bytes del PDF para StreamingResponse.
    """
    pdf = ACMPDF(logo_path=logo_path)
    pdf.alias_nb_pages()
    pdf.add_page()

    subject = acm_data['subject']
    comparables = acm_data['comparables']
    stats = acm_data['statistics']
    objectives = acm_data['objectives']

    # Descargar imagen del inmueble
    img_path = _download_image(subject.get('image'))

    # Generar mapa estático con ubicación + comparables
    indicators = acm_data.get('zone_indicators')
    map_path = _generate_static_map(subject, comparables, indicators)

    try:
        # 1. Header (con logo del cliente si existe)
        pdf.render_header()

        # 2. Ficha del inmueble + foto
        pdf.render_property_info(subject, img_path)

        # 3. Subtítulo con método
        metodo = acm_data.get('metodo', 'clasico')
        metodo_label = 'DBSCAN (clustering multidimensional)' if metodo == 'dbscan' else 'Clasico (rango precio/area)'
        pdf.render_subtitle(
            f'Metodo de seleccion: {metodo_label} | '
            'Factores de comercialidad: precio de admon, tipo de unidad, '
            'apreciacion del mercado entre otros'
        )

        # 4. Tabla de comparables
        pdf.render_comparables_table(comparables)

        # 5. Estadísticas
        pdf.render_statistics(stats)

        # 6. Gráfico de barras
        pdf.render_chart(comparables, stats)

        # 7. Mapa de zona con indicadores
        pdf.render_zone_map(map_path, indicators)

        # 8. Precios objetivo
        pdf.render_price_objectives(objectives)

        # 9. Fuentes (URLs de los anuncios)
        pdf.render_sources(comparables, subject)

        # 10. Footer con fecha
        pdf.render_footer_info(acm_data['generated_at'])

    finally:
        # Limpiar archivos temporales
        for path in (img_path, map_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    return pdf.output()
