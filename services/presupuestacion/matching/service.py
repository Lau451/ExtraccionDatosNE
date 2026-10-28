from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz, process
from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.matching import repository as repo
from services.presupuestacion.matching.models import CandidatoMatching, ResultadoMatchingItem

_UMBRAL_SUGERIDO = Decimal("70")
_TOP_K = 5


def _generar_candidatos(
    choices: dict[str, str], *, descripcion_normalizada: str
) -> list[CandidatoMatching]:
    """`choices` maps producto_id to its normalized name -- built once per batch
    from the active catalog (see `procesar_matching_items`)."""
    if not choices:
        return []

    resultados = process.extract(
        descripcion_normalizada, choices, scorer=fuzz.WRatio, limit=_TOP_K
    )
    return [
        CandidatoMatching(
            producto_id=producto_id,
            confianza=Decimal(str(round(score, 2))),
            metodo="fuzzy",
            detalle_scoring={"scorer": "WRatio"},
        )
        for _, score, producto_id in resultados
    ]


def procesar_matching_item(
    client: Client, *, item: dict[str, Any], drogueria_id: str, cliente_id: str | None
) -> ResultadoMatchingItem:
    return procesar_matching_items(
        client, items=[item], drogueria_id=drogueria_id, cliente_id=cliente_id
    )[0]


def procesar_matching_items(
    client: Client, *, items: list[dict[str, Any]], drogueria_id: str, cliente_id: str | None
) -> list[ResultadoMatchingItem]:
    """Matches a batch of items_proceso (a licitación's renglones) against the
    cliente's aliases and the catalog. The catalog, the alias lookup and the
    candidatos insert run once for the whole batch: per item they cost ~1 s of
    round trips each, which made validating a licitación grow linearly with its
    renglones. Only the per-item update stays per item. Results keep `items`
    order."""
    if not items:
        return []

    descripciones = [normalizar_descripcion(item["descripcion"]) for item in items]
    alias_por_descripcion = (
        repo.listar_alias_vigentes(
            client, cliente_id=cliente_id, descripciones_normalizadas=descripciones
        )
        if cliente_id is not None
        else {}
    )

    choices: dict[str, str] | None = None
    usos_por_alias: dict[str, int] = {}
    filas_candidatos: list[dict[str, Any]] = []
    resultados: list[ResultadoMatchingItem] = []

    for item, descripcion_normalizada in zip(items, descripciones):
        alias = alias_por_descripcion.get(descripcion_normalizada)
        if alias is not None:
            usos_por_alias[alias["id"]] = usos_por_alias.get(alias["id"], 0) + 1
            resultados.append(
                _aplicar_alias(
                    client,
                    item_proceso_id=item["id"],
                    descripcion_normalizada=descripcion_normalizada,
                    alias=alias,
                )
            )
            continue

        if choices is None:
            productos = repo.listar_productos_activos(client, drogueria_id=drogueria_id)
            choices = {p["id"]: normalizar_descripcion(p["nombre"]) for p in productos}
        candidatos = _generar_candidatos(choices, descripcion_normalizada=descripcion_normalizada)
        filas_candidatos.extend(
            {
                "item_proceso_id": item["id"],
                "drogueria_id": drogueria_id,
                "producto_id": c.producto_id,
                "confianza": str(c.confianza),
                "metodo": c.metodo,
                "detalle_scoring": c.detalle_scoring,
            }
            for c in candidatos
        )
        resultados.append(
            _aplicar_candidatos(
                client,
                item_proceso_id=item["id"],
                descripcion_normalizada=descripcion_normalizada,
                candidatos=candidatos,
            )
        )

    repo.insertar_candidatos(client, filas_candidatos)
    for alias in alias_por_descripcion.values():
        usos = usos_por_alias.get(alias["id"], 0)
        if usos:
            repo.marcar_alias_usado(
                client, alias_id=alias["id"], veces_usado=alias["veces_usado"], usos=usos
            )

    return resultados


def _aplicar_alias(
    client: Client, *, item_proceso_id: str, descripcion_normalizada: str, alias: dict[str, Any]
) -> ResultadoMatchingItem:
    repo.actualizar_item_matching(
        client,
        item_proceso_id=item_proceso_id,
        campos={
            "descripcion_normalizada": descripcion_normalizada,
            "producto_id": alias["producto_id"],
            "alias_id": alias["id"],
            "estado_matching": "automatico",
            "confianza_matching": None,
        },
    )
    return ResultadoMatchingItem(
        item_proceso_id=item_proceso_id,
        producto_id=alias["producto_id"],
        alias_id=alias["id"],
        estado_matching="automatico",
        confianza_matching=None,
        candidatos=[],
    )


def _aplicar_candidatos(
    client: Client,
    *,
    item_proceso_id: str,
    descripcion_normalizada: str,
    candidatos: list[CandidatoMatching],
) -> ResultadoMatchingItem:
    mejor_confianza = max((c.confianza for c in candidatos), default=None)
    estado = (
        "sugerido" if mejor_confianza is not None and mejor_confianza >= _UMBRAL_SUGERIDO else "pendiente"
    )

    repo.actualizar_item_matching(
        client,
        item_proceso_id=item_proceso_id,
        campos={
            "descripcion_normalizada": descripcion_normalizada,
            "estado_matching": estado,
            "confianza_matching": str(mejor_confianza) if mejor_confianza is not None else None,
        },
    )

    return ResultadoMatchingItem(
        item_proceso_id=item_proceso_id,
        producto_id=None,
        alias_id=None,
        estado_matching=estado,
        confianza_matching=mejor_confianza,
        candidatos=candidatos,
    )


def _upsert_alias(
    client: Client,
    *,
    item: dict[str, Any],
    cliente_id: str,
    drogueria_id: str,
    producto_id: str,
    descripcion_normalizada: str,
    usuario_id: str,
) -> str:
    alias_vigente = repo.buscar_alias_vigente(
        client, cliente_id=cliente_id, descripcion_normalizada=descripcion_normalizada
    )
    if alias_vigente is not None and alias_vigente["producto_id"] == producto_id:
        return alias_vigente["id"]

    if alias_vigente is not None:
        repo.invalidar_alias(client, alias_id=alias_vigente["id"])

    nuevo_alias = repo.crear_alias(
        client,
        cliente_id=cliente_id,
        drogueria_id=drogueria_id,
        producto_id=producto_id,
        descripcion_original=item["descripcion"],
        descripcion_normalizada=descripcion_normalizada,
        creado_por=usuario_id,
    )
    return nuevo_alias["id"]


def confirmar_matching(
    client: Client, *, item_proceso_id: str, producto_id: str, usuario_id: str
) -> ResultadoMatchingItem:
    item = repo.buscar_item_proceso(client, item_proceso_id=item_proceso_id)
    if item is None:
        raise NotFoundError("No se encontró el renglón")

    proceso = repo.buscar_proceso_comercial(client, proceso_comercial_id=item["proceso_comercial_id"])
    cliente_id = proceso["cliente_id"] if proceso else None
    drogueria_id = item["drogueria_id"]

    repo.marcar_candidato_elegido(client, item_proceso_id=item_proceso_id, producto_id=producto_id)

    alias_id = item.get("alias_id")
    if cliente_id is not None:
        descripcion_normalizada = item.get("descripcion_normalizada") or normalizar_descripcion(
            item["descripcion"]
        )
        alias_id = _upsert_alias(
            client,
            item=item,
            cliente_id=cliente_id,
            drogueria_id=drogueria_id,
            producto_id=producto_id,
            descripcion_normalizada=descripcion_normalizada,
            usuario_id=usuario_id,
        )

    item_actualizado = repo.actualizar_item_matching(
        client,
        item_proceso_id=item_proceso_id,
        campos={
            "producto_id": producto_id,
            "alias_id": alias_id,
            "estado_matching": "confirmado",
        },
    )

    confianza_previa = item_actualizado.get("confianza_matching")
    return ResultadoMatchingItem(
        item_proceso_id=item_proceso_id,
        producto_id=producto_id,
        alias_id=alias_id,
        estado_matching="confirmado",
        confianza_matching=Decimal(str(confianza_previa)) if confianza_previa is not None else None,
        candidatos=[],
    )


def marcar_sin_match(client: Client, *, item_proceso_id: str) -> ResultadoMatchingItem:
    item = repo.buscar_item_proceso(client, item_proceso_id=item_proceso_id)
    if item is None:
        raise NotFoundError("No se encontró el renglón")

    repo.actualizar_item_matching(
        client,
        item_proceso_id=item_proceso_id,
        campos={"producto_id": None, "estado_matching": "sin_match"},
    )

    return ResultadoMatchingItem(
        item_proceso_id=item_proceso_id,
        producto_id=None,
        alias_id=item.get("alias_id"),
        estado_matching="sin_match",
        confianza_matching=None,
        candidatos=[],
    )


def confirmar_matching_para_endpoint(
    *, item_proceso_id: str, producto_id: str, usuario_id: str
) -> ResultadoMatchingItem:
    """Corre con service_role: además de actualizar el item, invalida/crea alias y marca el
    candidato elegido — la RLS de esas tablas no incluye 'superadmin' en INSERT/UPDATE, así que
    igual que en pricing, el router nunca importa el service client directamente."""
    return confirmar_matching(
        get_service_client(),
        item_proceso_id=item_proceso_id,
        producto_id=producto_id,
        usuario_id=usuario_id,
    )


def marcar_sin_match_para_endpoint(*, item_proceso_id: str) -> ResultadoMatchingItem:
    return marcar_sin_match(get_service_client(), item_proceso_id=item_proceso_id)
