import csv
import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from supabase import Client

from services.presupuestacion.core.audit import registrar_cambio, registrar_evento_ciclo_vida
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import (
    ConflictError,
    ExtraccionNoDisponibleError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.extraccion import repository as repo
from services.presupuestacion.extraccion.models import (
    MAX_FILAS_EDITABLES,
    CandidatoCliente,
    CandidatoClienteOut,
    ExtraccionResumen,
    FilasExtraccionOut,
    ResultadoValidarExtraccion,
)
from services.presupuestacion.matching.service import procesar_matching_item
from services.presupuestacion.notificaciones.service import crear_notificacion

logger = logging.getLogger(__name__)

# document_type que materializan en items_proceso (mismo robot de extracción para ambos
# hoy — la distinción cotizacion/licitacion vive en procesos_comerciales.clase, no acá).
_TIPOS_ITEMS_PROCESO = {"licitacion", "cotizacion"}

_ROLES_NOTIFICACION_REEMPLAZO = ("admin", "gerencia", "lider_comercial")

# document_type que tienen lectura de filas implementada para GET .../filas
# (§8.2 -- orden_compra queda deliberadamente afuera, no hay CSV materializable).
_TIPOS_CON_LECTURA_DE_FILAS = {"licitacion", "cotizacion", "comparativa"}


def _leer_filas_csv_con_columnas(
    csv_disk_path: str | None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Origen único de lectura del CSV crudo -- columnas en el orden real del
    DictReader (§8.2) + filas. `_leer_filas_csv` es un atajo sobre esto para los
    callers que solo necesitan las filas (materialización)."""
    if not csv_disk_path:
        raise ExtraccionNoDisponibleError(
            "Esta extracción no tiene archivo de resultados asociado"
        )
    try:
        with open(csv_disk_path, encoding="utf-8", newline="") as archivo:
            reader = csv.DictReader(archivo, delimiter=";")
            filas = list(reader)
            columnas = list(reader.fieldnames or [])
    except OSError as exc:
        raise ExtraccionNoDisponibleError(
            "El archivo de la extracción no está disponible — "
            "puede que el volumen compartido no esté montado"
        ) from exc
    return columnas, filas


def _leer_filas_csv(csv_disk_path: str | None) -> list[dict[str, str]]:
    _, filas = _leer_filas_csv_con_columnas(csv_disk_path)
    return filas


def listar_extracciones(
    client: Client, *, validado: bool | None, limit: int, offset: int
) -> list[ExtraccionResumen]:
    filas = repo.listar_extracciones(client, validado=validado, limit=limit, offset=offset)
    resumenes = []
    for fila in filas:
        proceso_embed = fila.pop("procesos_comerciales", None) or {}
        resumenes.append(
            ExtraccionResumen(**fila, proceso_comercial_nombre=proceso_embed.get("nombre"))
        )
    return resumenes


def leer_filas_extraccion(extraction: dict[str, Any]) -> FilasExtraccionOut:
    document_type = extraction["document_type"]
    if document_type not in _TIPOS_CON_LECTURA_DE_FILAS:
        raise ValidationError(
            f"document_type='{document_type}' no tiene lectura de filas implementada"
        )

    columnas, filas_completas = _leer_filas_csv_con_columnas(extraction["csv_disk_path"])
    filas_leidas = len(filas_completas)
    editable = filas_leidas <= MAX_FILAS_EDITABLES

    return FilasExtraccionOut(
        extraction_id=extraction["id"],
        document_type=document_type,
        row_count=extraction["row_count"],
        filas_leidas=filas_leidas,
        editable=editable,
        columnas=columnas,
        # >500 filas: no se manda una lista gigante que la UI no va a renderizar
        # (§8.2) -- el frontend ya bloquea la edición antes de pedir esto, esto es
        # la red de seguridad del servidor.
        filas=filas_completas if editable else [],
    )


# -- Resolución de cliente (D3 / D3.1) ---------------------------------------


def _normalizar_cuit(cuit: str | None) -> str | None:
    """Saca guiones/puntos/espacios y exige exactamente 11 dígitos (D3/D6). Un
    CUIT extraído malformado no es un error: se saltea el nivel 2 en silencio
    (el caller registra la advertencia)."""
    if not cuit:
        return None
    digitos = re.sub(r"\D", "", cuit)
    if len(digitos) != 11:
        return None
    return digitos


def _candidato_desde_alias(alias: dict[str, Any]) -> CandidatoCliente | None:
    cliente_embed = alias.get("clientes")
    if cliente_embed is None:
        return None
    tercero_embed = cliente_embed.get("terceros") or {}
    return CandidatoCliente(
        cliente_id=alias["cliente_id"],
        razon_social=tercero_embed.get("razon_social") or "",
        cuit=tercero_embed.get("cuit"),
        codigo_interno=tercero_embed.get("codigo_interno"),
        tipo=cliente_embed.get("tipo") or "",
        activo=cliente_embed.get("activo", True),
        cuit_no_exclusivo=tercero_embed.get("cuit_no_exclusivo", False),
    )


def _candidatos_desde_cuit(filas: list[dict[str, Any]]) -> tuple[list[CandidatoCliente], bool]:
    """Mapea las filas de terceros ⋈ clientes (D3 nivel 2) a CandidatoCliente.
    Un tercero con ese CUIT pero sin fila en `clientes` (embed None) no es un
    candidato -- se omite y el segundo valor de la tupla avisa al caller que
    hubo al menos uno así, para que agregue la advertencia."""
    candidatos: list[CandidatoCliente] = []
    hubo_omitido = False
    for fila in filas:
        cliente_embed = fila.get("clientes")
        if cliente_embed is None:
            hubo_omitido = True
            continue
        candidatos.append(
            CandidatoCliente(
                cliente_id=cliente_embed["id"],
                razon_social=fila.get("razon_social") or "",
                cuit=fila.get("cuit"),
                codigo_interno=fila.get("codigo_interno"),
                tipo=cliente_embed.get("tipo") or "",
                activo=cliente_embed.get("activo", True),
                cuit_no_exclusivo=fila.get("cuit_no_exclusivo", False),
            )
        )
    return candidatos, hubo_omitido


def resolver_cliente_candidato(
    client: Client,
    *,
    drogueria_id: str,
    cuit_extraido: str | None,
    texto_extraido: str | None,
) -> CandidatoClienteOut:
    """Sugiere un cliente para una OC extraída (D3). Corre al abrir la pantalla
    de validación. NUNCA escribe, NUNCA ancla: la confirmación es siempre un
    click del usuario. NUNCA levanta excepción por "no encontrado" -- no
    encontrar es un resultado válido (origen='ninguno').

    Nivel 1 -- oc_cliente_alias por normalizar_descripcion(texto_extraido): exacto.
    Nivel 2 -- terceros.cuit ⋈ clientes: 1 fila (exclusivo) o N (cuit_no_exclusivo, C6).
    Nivel 3 -- sin candidatos; el front usa GET /terceros (D3.2).

    Corta en el primer nivel que devuelva algo (cortocircuito).
    """
    advertencias: list[str] = []

    cuit_normalizado = _normalizar_cuit(cuit_extraido)
    if cuit_extraido and cuit_normalizado is None:
        advertencias.append(
            f'El CUIT extraído ("{cuit_extraido}") no tiene 11 dígitos válidos '
            "— se omite la búsqueda por CUIT"
        )

    texto_normalizado = normalizar_descripcion(texto_extraido) if texto_extraido else ""

    # Nivel 1 -- alias exacto. Gana con cortocircuito aunque el nivel 2 también
    # resuelva (y difiera): es la fuente de más confianza, alguien ya confirmó
    # este texto.
    if texto_normalizado:
        alias = repo.buscar_alias_cliente(
            client, drogueria_id=drogueria_id, texto_normalizado=texto_normalizado
        )
        if alias is not None:
            candidato = _candidato_desde_alias(alias)
            if candidato is not None:
                return CandidatoClienteOut(
                    origen="alias",
                    candidatos=[candidato],
                    cuit_extraido=cuit_normalizado,
                    razon_social_extraida=texto_extraido,
                    advertencias=advertencias,
                )

    # Nivel 2 -- CUIT (exclusivo -> 1 candidato; compartido, C6 -> N candidatos).
    if cuit_normalizado is not None:
        filas = repo.buscar_clientes_por_cuit(
            client, drogueria_id=drogueria_id, cuit_normalizado=cuit_normalizado
        )
        candidatos, hubo_omitido = _candidatos_desde_cuit(filas)
        if hubo_omitido:
            advertencias.append(
                "El CUIT extraído corresponde a un tercero que no es cliente"
            )
        if len(candidatos) == 1:
            return CandidatoClienteOut(
                origen="cuit",
                candidatos=candidatos,
                cuit_extraido=cuit_normalizado,
                razon_social_extraida=texto_extraido,
                advertencias=advertencias,
            )
        if len(candidatos) > 1:
            return CandidatoClienteOut(
                origen="cuit_compartido",
                candidatos=candidatos,
                cuit_extraido=cuit_normalizado,
                razon_social_extraida=texto_extraido,
                advertencias=advertencias,
            )

    # Nivel 3 -- nada. No es un error (D3): el usuario busca a mano (D3.2).
    return CandidatoClienteOut(
        origen="ninguno",
        candidatos=[],
        cuit_extraido=cuit_normalizado,
        razon_social_extraida=texto_extraido,
        advertencias=advertencias,
    )


def obtener_cliente_candidato(client: Client, extraction: dict[str, Any]) -> CandidatoClienteOut:
    """GET /extracciones/{id}/cliente-candidato (D3). Lee `cuit_cliente`/
    `razon_social_cliente` de la primera fila del CSV -- cabecera repetida por
    renglón (D6) -- y delega en resolver_cliente_candidato(). Phase 3 no
    depende de la agrupación (Phase 4): lee solo el CSV propio de esta
    extracción, no _leer_filas_grupo()."""
    filas = _leer_filas_csv(extraction["csv_disk_path"])
    primera_fila = filas[0] if filas else {}
    cuit_extraido = (primera_fila.get("cuit_cliente") or "").strip() or None
    texto_extraido = (primera_fila.get("razon_social_cliente") or "").strip() or None
    return resolver_cliente_candidato(
        client,
        drogueria_id=extraction["drogueria_id"],
        cuit_extraido=cuit_extraido,
        texto_extraido=texto_extraido,
    )


def _registrar_alias_cliente(
    client: Client,
    *,
    drogueria_id: str,
    texto_extraido: str | None,
    cliente_id: str,
    usuario_id: str | None,
) -> None:
    """Aprende el mapeo encabezado -> cliente tras una confirmación EXITOSA
    (D3.1). Se invoca solo desde dentro de una confirmación que ya
    materializó la OC (Phase 5), nunca al abrir la pantalla. texto_extraido
    vacío/None/solo-puntuación -> no se aprende nada, no es un error (y
    tampoco llegaría a violar ck_oca_texto, que además ya lo rechazaría)."""
    if not texto_extraido:
        return
    texto_normalizado = normalizar_descripcion(texto_extraido)
    if not texto_normalizado:
        return
    repo.upsert_alias_cliente(
        client,
        drogueria_id=drogueria_id,
        texto_normalizado=texto_normalizado,
        texto_original=texto_extraido,
        cliente_id=cliente_id,
        usuario_id=usuario_id,
    )


# -- Agrupación multi-archivo (D13 / D13.1) ----------------------------------


def _leer_filas_grupo(
    client: Client, *, extraction: dict[str, Any]
) -> tuple[list[str], list[dict[str, str]], list[dict[str, Any]]]:
    """Solo para document_type='orden_compra' (D13). Devuelve (columnas,
    filas, miembros).

    Concatena las filas de los N miembros TAL CUAL, en orden de grupo. No
    deduplica, no suma cantidades, no renumera y no infiere nada (D13.1).

    grupo_id NULL -> se comporta exactamente como el caso de un archivo (un
    grupo de un solo miembro: la extracción misma).

    Cada fila lleva `_archivo` (source_filename) y `_extraction_id` para que
    el editor muestre de dónde vino y el usuario pueda corregir con
    contexto."""
    grupo_id = extraction.get("grupo_id")
    miembros = (
        repo.listar_miembros_de_grupo(client, grupo_id=grupo_id)
        if grupo_id is not None
        else [extraction]
    )

    columnas: list[str] = []
    filas: list[dict[str, str]] = []
    for miembro in miembros:
        columnas_miembro, filas_miembro = _leer_filas_csv_con_columnas(
            miembro["csv_disk_path"]
        )
        if not columnas:
            columnas = columnas_miembro
        for fila in filas_miembro:
            fila_con_origen = dict(fila)
            fila_con_origen["_archivo"] = miembro["source_filename"]
            fila_con_origen["_extraction_id"] = miembro["id"]
            filas.append(fila_con_origen)

    return columnas, filas, miembros


# Campos de cabecera desnormalizados por fila (D6) que D13.1 § Cabecera
# inconsistente entre archivos solo advierte -- nunca bloquean la
# confirmación. numero_oc es el único campo bloqueante (identifica de forma
# unívoca a la OC) y se trata aparte.
_CAMPOS_CABECERA_ADVERTENCIA = (
    "cuit_cliente",
    "razon_social_cliente",
    "fecha_emision",
    "direccion_entrega",
    "cantidad_entregas",
)


def _valor_mas_frecuente(valores: list[str]) -> str:
    """Empate -> gana el primer miembro (D13.1)."""
    conteo: dict[str, int] = {}
    for valor in valores:
        conteo[valor] = conteo.get(valor, 0) + 1
    mejor_valor = valores[0]
    mejor_conteo = 0
    for valor in valores:
        if conteo[valor] > mejor_conteo:
            mejor_valor = valor
            mejor_conteo = conteo[valor]
    return mejor_valor


def _conciliar_cabecera(
    filas_por_miembro: list[dict[str, str]],
) -> tuple[dict[str, str], list[str]]:
    """D13.1 § Cabecera inconsistente entre archivos. Recibe una fila
    representativa por miembro del grupo (la cabecera se repite por renglón,
    D6 -- el caller pasa una sola fila por `_extraction_id`, no todas).

    numero_oc discrepante bloquea con ValidationError, ANTES de cualquier
    write -- identifica de forma unívoca a la orden de compra. El resto de
    los campos de cabecera solo advierte: la cabecera final se precarga con
    el valor más frecuente entre miembros (empate -> el del primer
    miembro)."""
    valores_numero_oc = [fila.get("numero_oc", "") for fila in filas_por_miembro]
    if len(set(valores_numero_oc)) > 1:
        raise ValidationError(
            "Los archivos del grupo declaran números de orden de compra distintos "
            f"({sorted(set(valores_numero_oc))}) -- resolvé la discrepancia antes de confirmar"
        )

    cabecera: dict[str, str] = {"numero_oc": valores_numero_oc[0]}
    advertencias: list[str] = []

    for campo in _CAMPOS_CABECERA_ADVERTENCIA:
        valores = [fila.get(campo, "") for fila in filas_por_miembro]
        cabecera[campo] = _valor_mas_frecuente(valores)
        if len(set(valores)) > 1:
            advertencias.append(
                f"Los archivos del grupo declaran valores distintos de '{campo}' "
                f"-- se precargó el más frecuente (\"{cabecera[campo]}\")"
            )

    return cabecera, advertencias


def agrupar_extracciones(
    client: Client, *, extraction_ids: list[str], drogueria_id: str | None
) -> str:
    """D13 camino (b) -- POST /extracciones/agrupar. Todas las precondiciones
    se verifican ANTES del UPDATE. `drogueria_id` es la droguería del usuario
    que agrupa (None para superadmin, que no tiene una propia -- en ese caso
    se exige igual que los N miembros compartan drogueria_id ENTRE SÍ,
    porque el router ya no filtra por tenant a un superadmin)."""
    if len(extraction_ids) < 2 or len(set(extraction_ids)) != len(extraction_ids):
        raise ValidationError(
            "Hacen falta al menos 2 ids de extracciones distintos para agrupar"
        )

    extracciones: list[dict[str, Any]] = []
    for extraction_id in extraction_ids:
        extraction = repo.buscar_extraction_result(client, extraction_id=extraction_id)
        if extraction is None:
            raise NotFoundError(f"No se encontró la extracción {extraction_id}")
        extracciones.append(extraction)

    drogueria_ids = {extraction["drogueria_id"] for extraction in extracciones}
    if drogueria_id is not None:
        if drogueria_ids != {drogueria_id}:
            raise ForbiddenError(
                "Todas las extracciones a agrupar deben pertenecer a tu droguería"
            )
    elif len(drogueria_ids) > 1:
        raise ValidationError(
            "Las extracciones seleccionadas pertenecen a droguerías distintas"
        )

    for extraction in extracciones:
        if extraction["document_type"] != "orden_compra":
            raise ValidationError(
                "Solo se pueden agrupar extracciones de tipo 'orden_compra'"
            )
        if extraction["validado"]:
            raise ConflictError("No se puede agrupar una extracción ya validada")

    grupos_existentes = {
        extraction["grupo_id"] for extraction in extracciones if extraction.get("grupo_id")
    }
    if len(grupos_existentes) > 1:
        raise ConflictError(
            "Las extracciones ya pertenecen a grupos distintos "
            "-- fusionar grupos existentes no está soportado"
        )

    grupo_id = next(iter(grupos_existentes), None) or str(uuid.uuid4())

    for extraction in extracciones:
        if extraction.get("grupo_id") != grupo_id:
            repo.actualizar_grupo_id(client, extraction_id=extraction["id"], grupo_id=grupo_id)

    return grupo_id


def desagrupar_extracciones(
    client: Client, *, extraction_ids: list[str], drogueria_id: str | None
) -> None:
    """D13 -- POST /extracciones/desagrupar. Deja grupo_id=NULL en cada id
    recibido; si el grupo original queda con un solo miembro restante, ese
    miembro también se desagrupa (no debe existir un "grupo de uno" que se
    comporte distinto a una extracción suelta)."""
    if not extraction_ids:
        raise ValidationError("Hacen falta ids de extracciones para desagrupar")

    extracciones: list[dict[str, Any]] = []
    for extraction_id in extraction_ids:
        extraction = repo.buscar_extraction_result(client, extraction_id=extraction_id)
        if extraction is None:
            raise NotFoundError(f"No se encontró la extracción {extraction_id}")
        extracciones.append(extraction)

    drogueria_ids = {extraction["drogueria_id"] for extraction in extracciones}
    if drogueria_id is not None and drogueria_ids != {drogueria_id}:
        raise ForbiddenError(
            "Todas las extracciones a desagrupar deben pertenecer a tu droguería"
        )

    for extraction in extracciones:
        if extraction["validado"]:
            raise ConflictError("No se puede desagrupar una extracción ya validada")

    grupos_afectados: set[str] = set()
    for extraction in extracciones:
        grupo_id = extraction.get("grupo_id")
        if grupo_id is not None:
            grupos_afectados.add(grupo_id)
        repo.actualizar_grupo_id(client, extraction_id=extraction["id"], grupo_id=None)

    for grupo_id in grupos_afectados:
        restantes = repo.listar_miembros_de_grupo(client, grupo_id=grupo_id)
        if len(restantes) == 1:
            repo.actualizar_grupo_id(client, extraction_id=restantes[0]["id"], grupo_id=None)


def agrupar_extracciones_para_endpoint(
    *, extraction_ids: list[str], drogueria_id: str | None
) -> str:
    """Corre con service_role -- mismo criterio que validar_extraccion_para_endpoint:
    el router nunca importa el service client directamente."""
    return agrupar_extracciones(
        get_service_client(), extraction_ids=extraction_ids, drogueria_id=drogueria_id
    )


def desagrupar_extracciones_para_endpoint(
    *, extraction_ids: list[str], drogueria_id: str | None
) -> None:
    desagrupar_extracciones(
        get_service_client(), extraction_ids=extraction_ids, drogueria_id=drogueria_id
    )


def _chequear_entero(errores: list[str], numero: int, campo: str, valor: str) -> None:
    try:
        entero = int((valor or "").strip())
    except (TypeError, ValueError):
        errores.append(f"fila {numero}: '{campo}' no es un número entero válido (\"{valor}\")")
        return
    if entero <= 0:
        errores.append(f"fila {numero}: '{campo}' debe ser mayor a cero (\"{valor}\")")


def _chequear_texto(errores: list[str], numero: int, campo: str, valor: str) -> None:
    if not (valor or "").strip():
        errores.append(f"fila {numero}: '{campo}' no puede estar vacío")


def _chequear_decimal(
    errores: list[str], numero: int, campo: str, valor: str, *, minimo: Decimal
) -> None:
    try:
        decimal_valor = Decimal((valor or "").strip().replace(",", "."))
    except (TypeError, InvalidOperation):
        errores.append(f"fila {numero}: '{campo}' no es un número válido (\"{valor}\")")
        return
    if decimal_valor < minimo:
        errores.append(f"fila {numero}: '{campo}' no puede ser negativo (\"{valor}\")")


def _validar_filas_override(
    filas: list[dict[str, str]] | None, *, document_type: str
) -> None:
    """Corre en `validar_extraccion()` ANTES del primer write (§3 -- si esto revienta,
    `_resolver_proceso_comercial_id` nunca corre y la extracción queda intacta)."""
    if filas is None:
        return
    if not filas:
        raise ValidationError("La lista de filas no puede estar vacía")
    if len(filas) > MAX_FILAS_EDITABLES:
        raise ValidationError(
            f"No se pueden editar más de {MAX_FILAS_EDITABLES} filas en una validación "
            f"(recibidas {len(filas)})"
        )

    es_comparativa = document_type == "comparativa"
    esperado = "comparativa" if es_comparativa else "licitación/cotización"
    if es_comparativa != ("renglon" in filas[0]):
        raise ValidationError(
            f"Las filas enviadas no corresponden a un documento de tipo {esperado}"
        )

    errores: list[str] = []
    for numero, fila in enumerate(filas, start=1):
        if es_comparativa:
            _chequear_entero(errores, numero, "renglon", fila["renglon"])
            _chequear_texto(errores, numero, "proveedor", fila["proveedor"])
            _chequear_decimal(errores, numero, "precio", fila["precio"], minimo=Decimal(0))
        else:
            _chequear_entero(errores, numero, "item", fila["item"])
            _chequear_texto(errores, numero, "descripcion", fila["descripcion"])
            _chequear_decimal(errores, numero, "cantidad", fila["cantidad"], minimo=Decimal(0))

    if errores:
        detalle = "; ".join(errores[:10])
        extra = f" (y {len(errores) - 10} más)" if len(errores) > 10 else ""
        raise ValidationError(f"Filas con datos inválidos — {detalle}{extra}")


def _filas_a_materializar(
    extraction: dict[str, Any], filas_override: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    """Origen único de las filas. El CSV en disco nunca se reescribe (D2)."""
    if filas_override is not None:
        return filas_override
    return _leer_filas_csv(extraction["csv_disk_path"])


def _resolver_proceso_comercial_id(
    client: Client, *, extraction: dict[str, Any], proceso_comercial_id: str | None
) -> str:
    existente = extraction.get("proceso_comercial_id")
    if existente is not None:
        if proceso_comercial_id is not None and proceso_comercial_id != existente:
            raise ConflictError(
                "Esta extracción ya está vinculada a otro proceso_comercial_id"
            )
        return existente

    if proceso_comercial_id is None:
        raise ValidationError(
            "Esta extracción no tiene proceso_comercial_id — indicalo para poder validarla"
        )

    proceso = repo.buscar_proceso_comercial(client, proceso_comercial_id=proceso_comercial_id)
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial indicado")
    if proceso["drogueria_id"] != extraction["drogueria_id"]:
        raise ValidationError(
            "El proceso comercial indicado no pertenece a la misma droguería que la extracción"
        )

    repo.actualizar_extraction_result(
        client,
        extraction_id=extraction["id"],
        campos={"proceso_comercial_id": proceso_comercial_id},
    )
    return proceso_comercial_id


def _materializar_licitacion(
    client: Client,
    *,
    extraction: dict[str, Any],
    proceso_comercial_id: str,
    drogueria_id: str,
    cliente_id: str | None,
    filas_override: list[dict[str, str]] | None,
) -> int:
    filas_csv = _filas_a_materializar(extraction, filas_override)

    filas_items = []
    for fila in filas_csv:
        descripcion = fila["descripcion"].strip()
        filas_items.append(
            {
                "proceso_comercial_id": proceso_comercial_id,
                "drogueria_id": drogueria_id,
                "extraction_id": extraction["id"],
                "numero_renglon": int(fila["item"].strip()),
                "descripcion": descripcion,
                "descripcion_normalizada": normalizar_descripcion(descripcion),
                "cantidad": fila["cantidad"].strip(),
            }
        )

    items_creados = repo.insertar_items_proceso(client, filas_items)

    for item in items_creados:
        procesar_matching_item(
            client, item=item, drogueria_id=drogueria_id, cliente_id=cliente_id
        )

    return len(items_creados)


def _computar_posiciones(filas: list[dict[str, Any]]) -> list[tuple[str, int, bool]]:
    """Agrupa por renglon_id, ordena por precio_unitario ascendente y asigna
    posicion_precio (1 = más barato) + adjudicacion_estimada=TRUE al ganador de cada
    renglón (§5)."""
    por_renglon: dict[str, list[dict[str, Any]]] = {}
    for fila in filas:
        por_renglon.setdefault(fila["renglon_id"], []).append(fila)

    actualizaciones: list[tuple[str, int, bool]] = []
    for filas_del_renglon in por_renglon.values():
        ordenadas = sorted(filas_del_renglon, key=lambda f: Decimal(str(f["precio_unitario"])))
        for posicion, fila in enumerate(ordenadas, start=1):
            actualizaciones.append((fila["id"], posicion, posicion == 1))
    return actualizaciones


def _notificar_reemplazo_comparativa(
    client: Client,
    *,
    drogueria_id: str,
    proceso_comercial_id: str,
    comparativa_id: str,
    extraction_id: str,
    actor_id: str,
) -> None:
    """D6 -- corre DESPUÉS del flip de `validado=TRUE` (ver call site en
    `validar_extraccion`), envuelta en try/except: un aviso no es una aprobación y
    no puede revertir ni bloquear una validación ya confirmada en la DB."""
    destinatarios = repo.listar_usuarios_por_rol(
        client,
        drogueria_id=drogueria_id,
        roles=_ROLES_NOTIFICACION_REEMPLAZO,
        excluir_id=actor_id,
    )
    for usuario in destinatarios:  # sin destinatarios -> no pasa nada, no es error
        crear_notificacion(  # notificaciones.service, NO el insert directo del repo local
            client,
            drogueria_id=drogueria_id,
            destinatario_id=usuario["id"],
            tipo="comparativa_disponible",
            titulo="Comparativa reemplazada por una nueva extracción",
            mensaje=(
                "Se validó una nueva extracción que reemplazó la comparativa vigente "
                "de este proceso. La versión anterior quedó invalidada."
            ),
            prioridad="alta",
            url_destino=f"/comparativas/{comparativa_id}",
            origen="sistema",
            relaciones={
                "proceso_comercial_id": proceso_comercial_id,
                "comparativa_id": comparativa_id,
            },
            metadata={
                "extraction_result_id": extraction_id,
                "motivo": "reemplazo_por_validacion",
            },
        )


def _materializar_comparativa(
    client: Client,
    *,
    extraction: dict[str, Any],
    proceso_comercial_id: str,
    drogueria_id: str,
    usuario_id: str,
    filas_override: list[dict[str, str]] | None,
) -> tuple[str, int, bool]:
    filas_csv = _filas_a_materializar(extraction, filas_override)

    items_por_renglon = {
        item["numero_renglon"]: item["id"]
        for item in repo.listar_items_proceso_por_proceso(
            client, proceso_comercial_id=proceso_comercial_id
        )
    }

    vigente_previa = repo.buscar_comparativa_vigente(client, proceso_comercial_id=proceso_comercial_id)
    reemplazo = vigente_previa is not None

    proveedores = {f["proveedor"].strip() for f in filas_csv if f.get("proveedor")}
    renglones = {f["renglon"].strip() for f in filas_csv if f.get("renglon")}

    fila_comparativa: dict[str, Any] = {
        "proceso_comercial_id": proceso_comercial_id,
        "drogueria_id": drogueria_id,
        "extraction_id": extraction["id"],
        "cantidad_proveedores": len(proveedores),
        "items_analizados": len(renglones),
    }
    if reemplazo:
        fila_comparativa["version_numero"] = vigente_previa["version_numero"] + 1
        fila_comparativa["reemplaza_id"] = vigente_previa["id"]
        fila_comparativa["motivo_version"] = "nueva extracción validada"

    comparativa = repo.crear_comparativa(client, fila_comparativa)
    registrar_evento_ciclo_vida(
        client,
        entidad="comparativa",
        entidad_id=comparativa["id"],
        drogueria_id=drogueria_id,
        tipo_cambio="creacion",
        origen="usuario",
        usuario_id=usuario_id,
    )

    if reemplazo:
        repo.invalidar_comparativa(client, comparativa_id=vigente_previa["id"])
        registrar_cambio(
            client,
            entidad="comparativa",
            entidad_id=vigente_previa["id"],
            drogueria_id=drogueria_id,
            campo="es_vigente",
            valor_anterior=True,
            valor_nuevo=False,
            origen="usuario",
            usuario_id=usuario_id,
            batch_id=str(uuid.uuid4()),
        )

    # es_drogueria_propia NO se auto-detecta: el texto de "proveedor" no trae ningún
    # marcador confiable y un falso positivo dispara compras sobre una premisa falsa
    # (ver v_renglones_ganados). Queda para un PATCH manual, fuera de este alcance.
    filas_ofertas = []
    for fila in filas_csv:
        renglon_texto = fila["renglon"].strip()
        try:
            item_proceso_id = items_por_renglon.get(int(renglon_texto))
        except ValueError:
            item_proceso_id = None

        filas_ofertas.append(
            {
                "comparativa_id": comparativa["id"],
                "drogueria_id": drogueria_id,
                "item_proceso_id": item_proceso_id,
                "renglon_id": renglon_texto,
                "proveedor": fila["proveedor"].strip(),
                # No hay columna "marca" en ofertas_items ni "descripcion" en el CSV de
                # comparativa: reusamos marca como descripcion (mejor que perderla).
                "descripcion": (fila.get("marca") or "").strip() or None,
                "precio_unitario": fila["precio"].strip().replace(",", "."),
                "es_drogueria_propia": False,
            }
        )

    ofertas_creadas = repo.insertar_ofertas_items(client, filas_ofertas)

    for oferta_id, posicion, es_ganadora in _computar_posiciones(ofertas_creadas):
        repo.actualizar_oferta_item(
            client,
            oferta_item_id=oferta_id,
            campos={"posicion_precio": posicion, "adjudicacion_estimada": es_ganadora},
        )

    return comparativa["id"], len(ofertas_creadas), reemplazo


def validar_extraccion(
    client: Client,
    *,
    extraction_id: str,
    usuario_id: str,
    proceso_comercial_id: str | None,
    filas_override: list[dict[str, str]] | None = None,
) -> ResultadoValidarExtraccion:
    extraction = repo.buscar_extraction_result(client, extraction_id=extraction_id)
    if extraction is None:
        raise NotFoundError("No se encontró la extracción")
    if extraction["validado"]:
        raise ConflictError("Esta extracción ya fue validada")

    # §3 -- puro, sin tocar la DB, y ANTES del primer write (`_resolver_proceso_comercial_id`
    # abajo). Si `filas_override` trae datos inválidos, la extracción queda exactamente
    # como estaba: sin proceso_comercial_id, sin items_proceso/comparativas.
    _validar_filas_override(filas_override, document_type=extraction["document_type"])

    proceso_comercial_id_resuelto = _resolver_proceso_comercial_id(
        client, extraction=extraction, proceso_comercial_id=proceso_comercial_id
    )
    proceso = repo.buscar_proceso_comercial(
        client, proceso_comercial_id=proceso_comercial_id_resuelto
    )
    if proceso is None:
        raise NotFoundError("No se encontró el proceso comercial")

    document_type = extraction["document_type"]
    comparativa_id: str | None = None
    reemplazo = False

    if document_type in _TIPOS_ITEMS_PROCESO:
        filas_creadas = _materializar_licitacion(
            client,
            extraction=extraction,
            proceso_comercial_id=proceso_comercial_id_resuelto,
            drogueria_id=extraction["drogueria_id"],
            cliente_id=proceso["cliente_id"],
            filas_override=filas_override,
        )
    elif document_type == "comparativa":
        comparativa_id, filas_creadas, reemplazo = _materializar_comparativa(
            client,
            extraction=extraction,
            proceso_comercial_id=proceso_comercial_id_resuelto,
            drogueria_id=extraction["drogueria_id"],
            usuario_id=usuario_id,
            filas_override=filas_override,
        )
    else:
        raise ValidationError(
            f"document_type='{document_type}' todavía no tiene materialización implementada"
        )

    ahora = datetime.now(timezone.utc).isoformat()
    repo.actualizar_extraction_result(
        client,
        extraction_id=extraction_id,
        campos={"validado": True, "validado_por": usuario_id, "validado_at": ahora},
    )

    # Fire-and-forget (D6): un aviso no es una aprobación. Nada de lo que pase acá
    # puede revertir ni bloquear una validación que YA está confirmada en la DB.
    if reemplazo and comparativa_id is not None:
        try:
            _notificar_reemplazo_comparativa(
                client,
                drogueria_id=extraction["drogueria_id"],
                proceso_comercial_id=proceso_comercial_id_resuelto,
                comparativa_id=comparativa_id,
                extraction_id=extraction_id,
                actor_id=usuario_id,
            )
        except Exception:  # noqa: BLE001 — deliberado, ver comentario de arriba
            logger.exception(
                "No se pudo notificar el reemplazo de comparativa "
                "(extraction_id=%s, comparativa_id=%s)",
                extraction_id,
                comparativa_id,
            )

    return ResultadoValidarExtraccion(
        extraction_id=extraction_id,
        document_type=document_type,
        proceso_comercial_id=proceso_comercial_id_resuelto,
        filas_creadas=filas_creadas,
        comparativa_id=comparativa_id,
        reemplazo_version_anterior=reemplazo,
    )


def validar_extraccion_para_endpoint(
    *,
    extraction_id: str,
    usuario_id: str,
    proceso_comercial_id: str | None,
    filas_override: list[dict[str, str]] | None = None,
) -> ResultadoValidarExtraccion:
    """Corre con service_role: materializar toca items_proceso/comparativas/ofertas_items/
    notificaciones y dispara matching — mismo criterio que pricing/matching/presupuestos,
    el router nunca importa el service client directamente."""
    return validar_extraccion(
        get_service_client(),
        extraction_id=extraction_id,
        usuario_id=usuario_id,
        proceso_comercial_id=proceso_comercial_id,
        filas_override=filas_override,
    )
