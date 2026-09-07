"""Modelos de negociación de PCP (0011_pcp_modelo.sql M4, 0012_pcp_extras.sql M5,
design.md D4/D5, spec `pcp-negociacion`).

`RegistrarResultadoNegociacion` cubre los dos únicos resultados que este
módulo puede escribir -- `precio_obtenido` y `no_cotiza`. `sin_respuesta`
(0011_pcp_modelo.sql M4 `ck_ppr_resultado_val`) es el estado inicial que
`services/pcp/renglones/service.py::seleccionar_proveedores` ya deja escrito
(PR5, D4) al elegir un proveedor para negociar; este módulo nunca lo
escribe, solo lo transiciona a uno de los dos resultados finales.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator

ResultadoNegociacion = Literal["precio_obtenido", "no_cotiza"]

# Campos que solo tienen sentido para un resultado precio_obtenido -- spec
# "no_cotiza as a First-Class Outcome": "no price value is required or
# stored". Se interpreta en sentido amplio (precio Y condiciones de pago),
# no solo `precio_unitario`: una condición de pago sin precio asociado no
# tiene referente en precios_proveedor.
_CAMPOS_SOLO_PRECIO_OBTENIDO = (
    "precio_unitario",
    "cantidad_minima",
    "cantidad_maxima",
    "mantenimiento_hasta",
    "condicion_pago_id",
    "forma_pago_id",
)


class RegistrarResultadoNegociacion(BaseModel):
    """Alta/actualización de un resultado de negociación (spec
    `pcp-negociacion`, "Negotiation Result Recording" / "no_cotiza as a
    First-Class Outcome"). `pcp_renglon_id`/`proveedor_id` llegan por la URL
    (recurso anidado), mismo criterio que `PcpRenglonCreate.pcp_id` /
    `ProductoProveedorCreate.producto_id`.

    Validado acá, antes de llegar a la capa de servicio (mismo criterio que
    `PcpRenglonCreate` con `presupuesto_item_id`): `precio_obtenido` exige
    `precio_unitario` y `mantenimiento_hasta`; `no_cotiza` no admite ningún
    campo de precio/condiciones.
    """

    resultado: ResultadoNegociacion
    precio_unitario: Decimal | None = None
    cantidad_minima: Decimal | None = None
    cantidad_maxima: Decimal | None = None
    mantenimiento_hasta: date | None = None
    condicion_pago_id: str | None = None
    forma_pago_id: str | None = None
    notas: str | None = None
    motivo: str | None = None

    @model_validator(mode="after")
    def _validar_campos_segun_resultado(self) -> "RegistrarResultadoNegociacion":
        if self.resultado == "precio_obtenido":
            if self.precio_unitario is None or self.mantenimiento_hasta is None:
                raise ValueError(
                    "precio_obtenido requiere precio_unitario y mantenimiento_hasta"
                )
        else:  # no_cotiza
            provistos = [
                campo
                for campo in _CAMPOS_SOLO_PRECIO_OBTENIDO
                if getattr(self, campo) is not None
            ]
            if provistos:
                raise ValueError(
                    f"no_cotiza no admite valores de precio/condiciones: {provistos}"
                )
        return self


class ResultadoNegociacionOut(BaseModel):
    id: str
    drogueria_id: str
    pcp_renglon_id: str
    proveedor_id: str
    resultado: str
    precio_proveedor_id: str | None
    motivo: str | None
    registrado_por: str | None
