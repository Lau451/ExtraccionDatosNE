from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal["comparativa", "licitacion", "cotizacion", "orden_compra"]

# D7 — mismo valor que frontend/constants.ts (Phase 6). Introducida acá porque
# GET .../filas (Phase 3) ya necesita el tope para decidir `editable`; Phase 4
# reusa esta misma constante para el chequeo de `filas` en el body de validar.
MAX_FILAS_EDITABLES = 500


class FilaLicitacionIn(BaseModel):
    """Mismos nombres de columna que el CSV de licitación/cotización."""

    model_config = ConfigDict(extra="forbid")
    item: str
    descripcion: str
    cantidad: str


class FilaComparativaIn(BaseModel):
    """Mismos nombres de columna que el CSV de comparativa."""

    model_config = ConfigDict(extra="forbid")
    renglon: str
    proveedor: str
    marca: str | None = None
    precio: str


class FilaOrdenCompraIn(BaseModel):
    """Un renglón de orden de compra confirmado por el usuario (D7/D13.1)."""

    model_config = ConfigDict(extra="forbid")
    # Solo referencia visual (C10): el número de línea que el documento declaró,
    # si lo declaró. NO se persiste tal cual -- oc_items.numero_renglon es un
    # ordinal 1..N que _materializar_orden_compra() asigna por POSICIÓN en esta
    # lista, al confirmar (D13.1).
    numero_renglon_documento: str | None = None
    descripcion: str
    cantidad: str
    precio_unitario: str  # obligatorio; manual si la extracción no lo detectó
    producto_id: str | None = None  # opcional (D11)


class EntregaPlanIn(BaseModel):
    """Una entrega del plan de una orden de compra (D8)."""

    model_config = ConfigDict(extra="forbid")
    numero_entrega: int
    plazo_dias: int | None = None
    # None -> reparto automático parejo de cada renglón entre todas las entregas
    # (D8, repartir_cantidad). La clave es la POSICIÓN 1-based de la fila en
    # OrdenCompraOverride.filas -- el mismo numero_renglon que se asigna al
    # confirmar (D13.1).
    cantidades_por_posicion: dict[str, str] | None = None


class OrdenCompraOverride(BaseModel):
    """Payload de confirmación de una orden de compra (D7) -- bloque propio,
    no una extensión del campo `filas` existente (licitación/comparativa)."""

    model_config = ConfigDict(extra="forbid")
    numero_oc: str
    # El id del cliente que el usuario CONFIRMÓ en pantalla -- venga de un
    # alias, de un CUIT o de la búsqueda manual, el backend no distingue ni lo
    # infiere (D3).
    cliente_id: str
    # Texto de cabecera que originó la confirmación. Es lo que se aprende en
    # oc_cliente_alias (D3.1). None -> no se aprende nada, no es un error.
    razon_social_extraida: str | None = None
    fecha_emision: date | None = None
    direccion_entrega: str | None = None
    notas: str | None = None
    filas: list[FilaOrdenCompraIn]
    entregas: list[EntregaPlanIn] = Field(min_length=1)


class ValidarExtraccionRequest(BaseModel):
    proceso_comercial_id: str | None = None
    # None  -> materializa desde el CSV (comportamiento actual, retrocompatible)
    # lista -> materializa desde acá; el CSV en disco NO se toca (D2)
    filas: list[FilaLicitacionIn] | list[FilaComparativaIn] | None = Field(default=None)
    orden_compra: OrdenCompraOverride | None = None  # NUEVO (D7)


class ResultadoValidarExtraccion(BaseModel):
    extraction_id: str
    document_type: DocumentType
    proceso_comercial_id: str | None  # CAMBIO: era `str` -- NULL en la ruta OC
    filas_creadas: int
    comparativa_id: str | None = None
    reemplazo_version_anterior: bool = False
    orden_compra_id: str | None = None  # NUEVO
    entregas_creadas: int = 0  # NUEVO
    renglones_sin_producto: int = 0  # NUEVO (D11)
    extracciones_validadas: int = 1  # NUEVO (D13) -- miembros del grupo marcados


class ExtraccionResumen(BaseModel):
    id: str
    document_type: DocumentType
    source_filename: str
    row_count: int
    status: str
    validado: bool
    proceso_comercial_id: str | None
    proceso_comercial_nombre: str | None
    created_at: datetime
    # D13/D13.1 (gap post-Phase 7, task 7.13) -- persistido, para que el
    # indicador de agrupación del listado sobreviva a un refetch/recarga sin
    # depender solo del estado en memoria del front (`gruposLocales`).
    grupo_id: str | None = None


class MiembroGrupo(BaseModel):
    """Un miembro de un grupo de extracciones de orden de compra (D13)."""

    extraction_id: str
    source_filename: str


class FilasExtraccionOut(BaseModel):
    extraction_id: str
    document_type: DocumentType
    row_count: int
    filas_leidas: int
    editable: bool
    columnas: list[str]
    filas: list[dict[str, str]]
    # D13/D13.1 -- solo relevante para document_type='orden_compra'. grupo_id
    # None y miembros=[] para el resto de los tipos (comportamiento actual,
    # retrocompatible).
    grupo_id: str | None = None
    miembros: list[MiembroGrupo] = Field(default_factory=list)
    advertencias_cabecera: list[str] = Field(default_factory=list)


# -- Resolución de cliente (D3 / D3.1 / D3.2, Phase 3) -----------------------

OrigenCandidato = Literal["alias", "cuit", "cuit_compartido", "ninguno"]


class CandidatoCliente(BaseModel):
    cliente_id: str
    razon_social: str
    cuit: str | None
    codigo_interno: str | None
    tipo: str
    activo: bool  # false -> el front lo muestra deshabilitado con el motivo
    cuit_no_exclusivo: bool  # true -> es una sede de un CUIT institucional (C6)


class CandidatoClienteOut(BaseModel):
    origen: OrigenCandidato
    # 1 elemento  -> sugerencia única (alias, o CUIT exclusivo)
    # N elementos -> candidatos de un CUIT compartido; el usuario elige (C6)
    # 0 elementos -> el usuario busca a mano (D3.2)
    candidatos: list[CandidatoCliente]
    cuit_extraido: str | None  # ya normalizado a 11 dígitos, o None
    razon_social_extraida: str | None  # texto crudo, tal cual salió del documento
    advertencias: list[str]  # CUIT malformado, tercero sin rol cliente, etc.


# -- Agrupación multi-archivo (D13 / D13.1, Phase 4) -------------------------


class AgruparExtraccionesRequest(BaseModel):
    """Cuerpo de POST /extracciones/agrupar y POST /extracciones/desagrupar
    (D13 § Agrupar después -- mismo shape para las dos operaciones, no se
    justifica un modelo separado para la inversa)."""

    extraction_ids: list[str] = Field(min_length=2)
