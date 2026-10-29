from dataclasses import dataclass
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


@dataclass
class MatchingResuelto:
    """Matching outcome for one descripción, computed before the item is
    written (see `resolver_matching`)."""

    descripcion_normalizada: str
    estado_matching: str
    confianza_matching: Decimal | None
    alias: dict[str, Any] | None
    candidatos: list[CandidatoMatching]

    def campos(self) -> dict[str, Any]:
        """items_proceso columns this outcome sets. The fuzzy path leaves
        producto_id/alias_id untouched, as it always did."""
        campos: dict[str, Any] = {
            "descripcion_normalizada": self.descripcion_normalizada,
            "estado_matching": self.estado_matching,
            "confianza_matching": (
                str(self.confianza_matching) if self.confianza_matching is not None else None
            ),
        }
        if self.alias is not None:
            campos["producto_id"] = self.alias["producto_id"]
            campos["alias_id"] = self.alias["id"]
        return campos


def resolver_matching(
    client: Client, *, descripciones: list[str], drogueria_id: str, cliente_id: str | None
) -> list[MatchingResuelto]:
    """Resolves the matching of a batch of descripciones against the cliente's
    aliases and the catalog, without writing anything. The catalog and the alias
    lookup run once for the whole batch. Results keep `descripciones` order."""
    normalizadas = [normalizar_descripcion(descripcion) for descripcion in descripciones]
    alias_por_descripcion = (
        repo.listar_alias_vigentes(
            client, cliente_id=cliente_id, descripciones_normalizadas=normalizadas
        )
        if cliente_id is not None and normalizadas
        else {}
    )

    choices: dict[str, str] | None = None
    resueltos: list[MatchingResuelto] = []
    for descripcion_normalizada in normalizadas:
        alias = alias_por_descripcion.get(descripcion_normalizada)
        if alias is not None:
            resueltos.append(
                MatchingResuelto(
                    descripcion_normalizada=descripcion_normalizada,
                    estado_matching="automatico",
                    confianza_matching=None,
                    alias=alias,
                    candidatos=[],
                )
            )
            continue

        if choices is None:
            productos = repo.listar_productos_activos(client, drogueria_id=drogueria_id)
            choices = {p["id"]: normalizar_descripcion(p["nombre"]) for p in productos}
        candidatos = _generar_candidatos(choices, descripcion_normalizada=descripcion_normalizada)
        mejor_confianza = max((c.confianza for c in candidatos), default=None)
        resueltos.append(
            MatchingResuelto(
                descripcion_normalizada=descripcion_normalizada,
                estado_matching=(
                    "sugerido"
                    if mejor_confianza is not None and mejor_confianza >= _UMBRAL_SUGERIDO
                    else "pendiente"
                ),
                confianza_matching=mejor_confianza,
                alias=None,
                candidatos=candidatos,
            )
        )
    return resueltos


def registrar_matching(
    client: Client,
    *,
    item_ids: list[str],
    resueltos: list[MatchingResuelto],
    drogueria_id: str,
) -> list[ResultadoMatchingItem]:
    """Stores what `resolver_matching` decided once the items exist: every
    candidato in one insert, and one use per item on each alias. `item_ids`
    pairs with `resueltos` by position."""
    filas_candidatos: list[dict[str, Any]] = []
    usos_por_alias: dict[str, tuple[dict[str, Any], int]] = {}
    resultados: list[ResultadoMatchingItem] = []

    for item_proceso_id, resuelto in zip(item_ids, resueltos, strict=True):
        if resuelto.alias is not None:
            alias, usos = usos_por_alias.get(resuelto.alias["id"], (resuelto.alias, 0))
            usos_por_alias[alias["id"]] = (alias, usos + 1)
        filas_candidatos.extend(
            {
                "item_proceso_id": item_proceso_id,
                "drogueria_id": drogueria_id,
                "producto_id": c.producto_id,
                "confianza": str(c.confianza),
                "metodo": c.metodo,
                "detalle_scoring": c.detalle_scoring,
            }
            for c in resuelto.candidatos
        )
        resultados.append(
            ResultadoMatchingItem(
                item_proceso_id=item_proceso_id,
                producto_id=resuelto.alias["producto_id"] if resuelto.alias else None,
                alias_id=resuelto.alias["id"] if resuelto.alias else None,
                estado_matching=resuelto.estado_matching,
                confianza_matching=resuelto.confianza_matching,
                candidatos=resuelto.candidatos,
            )
        )

    repo.insertar_candidatos(client, filas_candidatos)
    for alias, usos in usos_por_alias.values():
        repo.marcar_alias_usado(
            client, alias_id=alias["id"], veces_usado=alias["veces_usado"], usos=usos
        )
    return resultados


def procesar_matching_items(
    client: Client, *, items: list[dict[str, Any]], drogueria_id: str, cliente_id: str | None
) -> list[ResultadoMatchingItem]:
    """Matches items_proceso that already exist: resolves the batch, updates
    each item and stores candidatos and alias uses. A licitación being validated
    uses `resolver_matching` before inserting its items instead, so it needs no
    per-item update (see `extraccion.service._materializar_licitacion`)."""
    if not items:
        return []

    resueltos = resolver_matching(
        client,
        descripciones=[item["descripcion"] for item in items],
        drogueria_id=drogueria_id,
        cliente_id=cliente_id,
    )
    for item, resuelto in zip(items, resueltos):
        repo.actualizar_item_matching(client, item_proceso_id=item["id"], campos=resuelto.campos())
    return registrar_matching(
        client,
        item_ids=[item["id"] for item in items],
        resueltos=resueltos,
        drogueria_id=drogueria_id,
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
