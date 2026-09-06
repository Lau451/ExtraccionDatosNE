"""Implementación concreta de `PdfRenderer` (D9) con `reportlab`.

`reportlab==4.5.0` está pineado como dependencia directa en
`requirements.txt` (tasks.md 9.1). **Licencia confirmada BSD** antes de
agregar la dependencia (`pip show reportlab` -> "License: BSD license (see
license.txt for details), Copyright (c) 2000-2025, ReportLab Inc.") -- a
diferencia de `pymupdf` (ya dependencia transitiva del proyecto, pero
dual-licenciado AGPL-3.0/Artifex Comercial), rechazado explícitamente por el
usuario para este caso de uso más central (design.md D9). `reportlab` es
puro Python, sin librerías de sistema -- misma propiedad Docker/Windows-
friendly que motivó descartar WeasyPrint (GTK/Pango) y Chromium headless.

Jinja2 (ya una dependencia del proyecto, sin uso previo en el repo) arma el
texto dinámico del encabezado desde una plantilla de texto plano
(`templates/consulta.txt.j2`); `reportlab.platypus` arma el layout real del
PDF (título, encabezado, tabla de renglones). No hay HTML intermedio: Jinja2
solo resuelve texto, reportlab nunca parsea HTML.
"""

import io
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# autoescape=True: el texto que llega de datos de negocio (p.ej. la razón
# social de un proveedor) puede contener '&', '<', '>' -- reportlab.Paragraph
# interpreta un subconjunto de XML como markup, así que ese texto se escapa
# igual que HTML antes de insertarse. El único markup real (`<br/>`) se
# agrega DESPUÉS de renderizar la plantilla, nunca a través de una variable.
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def _nombre_proveedor(proveedor: dict[str, Any]) -> str:
    tercero = proveedor.get("terceros") or {}
    return tercero.get("razon_social") or proveedor.get("id", "")


def _nombre_item(renglon: dict[str, Any], producto: dict[str, Any] | None) -> str:
    if producto is not None:
        return producto["nombre"]
    # Matching de producto todavía pendiente (D2, producto_id nullable) --
    # se identifica por el item_proceso de origen en vez de dejar la fila en
    # blanco.
    return f"Ítem de proceso {renglon['item_proceso_id']}"


class ReportlabPdfRenderer:
    """Único punto de `services/pcp/documentos/` que importa `reportlab`
    (design.md D9: "el renderer se mantiene como un cambio de una sola
    clase")."""

    def render_consulta(self, datos: dict[str, Any]) -> bytes:
        consulta = datos["consulta"]
        proveedor = datos["proveedor"]
        renglones = datos["renglones"]

        plantilla = _env.get_template("consulta.txt.j2")
        encabezado_texto = plantilla.render(
            proveedor_nombre=_nombre_proveedor(proveedor),
            fecha_respuesta_esperada=consulta.get("fecha_respuesta_esperada") or "",
        )

        buffer = io.BytesIO()
        documento = SimpleDocTemplate(buffer, pagesize=A4)
        estilos = getSampleStyleSheet()

        elementos: list[Any] = [
            Paragraph("Consulta de Cotización", estilos["Title"]),
            Spacer(1, 0.5 * cm),
            Paragraph(encabezado_texto.strip().replace("\n", "<br/>"), estilos["Normal"]),
            Spacer(1, 0.5 * cm),
        ]

        filas: list[list[str]] = [["Producto", "Cantidad", "Precio de referencia"]]
        for item in renglones:
            renglon = item["renglon"]
            producto = item.get("producto")
            cantidad = item.get("cantidad_consultada")
            if cantidad is None:
                cantidad = renglon.get("cantidad")
            precio_referencia = renglon.get("precio_referencia")
            filas.append(
                [
                    _nombre_item(renglon, producto),
                    str(cantidad) if cantidad is not None else "",
                    str(precio_referencia) if precio_referencia is not None else "",
                ]
            )

        tabla = Table(filas, hAlign="LEFT")
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        elementos.append(tabla)

        documento.build(elementos)
        return buffer.getvalue()
