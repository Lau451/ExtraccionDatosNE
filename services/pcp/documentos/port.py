"""Puerto de generación de PDF para consultas de PCP (design.md D9, spec
`pcp-consultas-agrupadas`, "Consulta PDF Generation").

Definido como un `Protocol` para que reemplazar el renderer concreto sea un
cambio de una sola clase (design.md D9: "detrás de un puerto `PdfRenderer`
... para que el renderer se mantenga como un cambio de una sola clase si
esta decisión cambia más adelante"). Ningún otro código de
`services/pcp/consultas/` importa `reportlab` directamente -- solo
`services/pcp/documentos/renderer_reportlab.py`.
"""

from typing import Any, Protocol


class PdfRenderer(Protocol):
    def render_consulta(self, datos: dict[str, Any]) -> bytes:
        """Genera el PDF de una consulta agrupada.

        `datos` tiene la forma que arma
        `services/pcp/consultas/service.py::_armar_datos_pdf`:
        `{"consulta": dict, "proveedor": dict, "renglones": [{"renglon": dict,
        "producto": dict | None, "cantidad_consultada": Decimal | None}, ...]}`.
        Devuelve los bytes del PDF generado.
        """
        ...
