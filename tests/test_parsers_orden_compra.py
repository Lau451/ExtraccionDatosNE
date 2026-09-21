"""
Tests unitarios para `_extract_native_pdf_orden_compra` en
services/extraccion/parsers.py — extracción de PDF dedicada a orden_compra
(NO comparte `_extract_native_pdf` con licitación/comparativa).

Bug real que este parser corrige: una OC real de cliente (impresa desde un
sistema web, sin bordes de tabla dibujados) mezcla texto libre de cabecera
(cliente, CUIT, número de orden, fecha) con una tabla chica de renglones en
la MISMA página. `_extract_native_pdf` (el parser compartido) descarta por
completo el texto libre de una página en cuanto pdfplumber detecta CUALQUIER
tabla en ella — con este documento real, eso dejaba pasar solo la fila de
encabezado de la tabla (0 renglones, 0 texto de cabecera). Ver
odd/tasks/orden-compra-parser-pdf-dedicado.md.

0 mocks — estas pruebas ejercitan pdfplumber real contra PDFs reales/sintéticos,
sin llamar a Gemini en ningún punto.
"""

from pathlib import Path

from services.extraccion.parsers import (
    _extract_native_pdf,
    _extract_native_pdf_orden_compra,
)

FIXTURE_REAL = (
    Path(__file__).parent
    / "fixtures"
    / "orden_compra"
    / "04_pdf_real_sin_bordes"
    / "documento.pdf"
)


def _generar_pdf_con_tabla_con_bordes(destino: Path) -> None:
    """PDF sintético: texto libre de cabecera + tabla CON bordes dibujados
    (GRID) en la MISMA página — la tabla detecta bien con la estrategia por
    defecto de pdfplumber (lines/lines), a diferencia del fixture real."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(destino), pagesize=A4)

    header = [
        Paragraph("ORDEN DE COMPRA", styles["Title"]),
        Paragraph("Numero de orden: OC-5555", styles["Normal"]),
        Paragraph("Cliente: CLINICA DE PRUEBA", styles["Normal"]),
        Paragraph("CUIT del cliente: 30-11112222-3", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    data = [
        ["Cod.", "Articulo", "Cantidad", "P.Unitario"],
        ["001", "PARACETAMOL 500MG", "50", "100,00"],
        ["002", "IBUPROFENO 400MG", "30", "150,00"],
    ]
    tabla = Table(data, colWidths=[2 * cm, 6 * cm, 3 * cm, 3 * cm])
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))

    doc.build(header + [tabla])


class TestExtractNativePdfOrdenCompra:
    def test_texto_libre_y_tabla_en_misma_pagina_se_capturan_ambos(self, tmp_path):
        pdf_path = tmp_path / "oc_con_tabla_con_bordes.pdf"
        _generar_pdf_con_tabla_con_bordes(pdf_path)

        resultado = _extract_native_pdf_orden_compra(pdf_path)

        # Texto libre de cabecera (se hubiera descartado con _extract_native_pdf,
        # que solo procesa la tabla cuando la página tiene una).
        assert "OC-5555" in resultado
        assert "CLINICA DE PRUEBA" in resultado
        assert "30-11112222-3" in resultado

        # Tabla detectada con la estrategia por defecto (tiene bordes dibujados).
        assert "PARACETAMOL 500MG" in resultado
        assert "IBUPROFENO 400MG" in resultado

    def test_reproduce_patron_real_tabla_sin_bordes(self):
        """Reproduce el patrón EXACTO del PDF real que motivó este fix: tabla
        impresa desde un sistema web, sin bordes dibujados — pdfplumber con la
        estrategia por defecto solo detecta la fila de encabezado de la tabla
        (0 filas de datos). La función dedicada debe recuperar los 2 renglones
        igual, vía texto libre + estrategia alternativa de detección de tabla."""
        assert FIXTURE_REAL.exists(), f"Fixture real no encontrado: {FIXTURE_REAL}"

        resultado = _extract_native_pdf_orden_compra(FIXTURE_REAL)

        # Cabecera de texto libre (cliente, CUIT, numero de orden) — se pierde
        # por completo con el parser compartido en este documento real.
        assert "SAMCo Rafaela Hospital" in resultado
        assert "30-67428388-8" in resultado
        assert "00104857" in resultado

        # Los 2 renglones reales — 0 con el parser compartido (RED confirmado
        # manualmente: parse_document() devuelve solo la fila de encabezado).
        assert "Hidroclorotiazida" in resultado
        assert "3000" in resultado
        assert "109,75" in resultado
        assert "Gemfibrozil" in resultado
        assert "4000" in resultado
        assert "187,00" in resultado

    def test_parser_compartido_sigue_fallando_con_el_mismo_pdf_no_regresion(self):
        """Documenta el bug original: `_extract_native_pdf` (compartido con
        licitación/comparativa, NO tocado por este fix) sigue devolviendo
        solo la fila de encabezado para este mismo PDF real — 0 renglones."""
        resultado = _extract_native_pdf(FIXTURE_REAL)

        assert "Hidroclorotiazida" not in resultado
        assert "Gemfibrozil" not in resultado
        assert "SAMCo Rafaela Hospital" not in resultado
