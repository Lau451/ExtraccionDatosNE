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

    def render_resultado_pcp(self, datos: dict[str, Any]) -> bytes:
        """PR11 (tasks.md 11.7, design.md D10) -- genera el PDF de "resumen
        de cierre" de un PCP completo, adjuntado al email que
        `negociacion/service.py::cerrar_pcp` manda al usuario solicitante.

        A diferencia de `render_consulta` (un proveedor, un subconjunto de
        renglones agrupados), este método cubre TODO el PCP: su encabezado y
        cada renglón con TODOS los resultados de negociación registrados por
        proveedor (D4) -- no solo el proveedor ganador, para que el
        solicitante vea el panorama completo de la negociación.

        `datos` tiene la forma que arma
        `services/pcp/negociacion/service.py::_armar_datos_resultado_pdf`:
        `{"pcp": dict, "renglones": [{"renglon": dict, "producto": dict | None,
        "resultados": list[dict]}, ...]}`. Devuelve los bytes del PDF
        generado. Método separado en vez de sobrecargar `render_consulta`
        con datos opcionales: las dos formas de `datos` no comparten
        estructura (una tiene "consulta"/"proveedor", la otra "pcp"), así
        que forzarlas a un único método las volvería mutuamente opcionales y
        más difíciles de tipar -- mismo criterio que D9 ya documenta para
        mantener el renderer intercambiable "como un cambio de una sola
        clase": agregar un método nuevo, no ramificar uno existente.
        """
        ...
