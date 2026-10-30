from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz, process
from supabase import Client

from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.core.exceptions import NotFoundError
from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.matching import repository as repo
from services.presupuestacion.matching.models import (
    CandidatoMatching,
    CandidatoRenglon,
    MatchingProceso,
    ProcesoConMatchingPendiente,
    RenglonMatching,
    ResultadoMatchingItem,
)

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
        """items_proceso columns this outcome sets. The fuzzy path does not
        include producto_id/alias_id: an update leaves them as they are, and
        an insert has to set them (to None) itself."""
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

    # The alias that matched this renglón points to the wrong producto: left
    # vigente, the next licitación of the cliente would match it automatically.
    if item.get("alias_id"):
        repo.invalidar_alias(client, alias_id=item["alias_id"])
    repo.desmarcar_candidatos(client, item_proceso_id=item_proceso_id)
    repo.actualizar_item_matching(
        client,
        item_proceso_id=item_proceso_id,
        campos={"producto_id": None, "alias_id": None, "estado_matching": "sin_match"},
    )

    return ResultadoMatchingItem(
        item_proceso_id=item_proceso_id,
        producto_id=None,
        alias_id=None,
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


def _decimal_2(valor: Any) -> Decimal | None:
    """PostgREST returns NUMERIC(_,2) columns as JSON numbers (92.00 -> 92.0);
    the API keeps the column's two decimals."""
    if valor is None:
        return None
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def obtener_matching_proceso(
    client: Client, *, proceso_comercial_id: str, drogueria_id: str | None
) -> MatchingProceso:
    """Every renglón of the proceso with its matching, best candidato first.
    `drogueria_id` None means any droguería (superadmin). A proceso of another
    droguería is reported as not found, without confirming it exists."""
    proceso = repo.buscar_proceso_para_matching(client, proceso_comercial_id=proceso_comercial_id)
    if proceso is None or (drogueria_id is not None and proceso["drogueria_id"] != drogueria_id):
        raise NotFoundError("No se encontró el proceso comercial")

    renglones = [
        RenglonMatching(
            item_proceso_id=fila["id"],
            numero_renglon=fila["numero_renglon"],
            descripcion=fila["descripcion"],
            cantidad=_decimal_2(fila["cantidad"]),
            estado_matching=fila["estado_matching"],
            confianza_matching=_decimal_2(fila["confianza_matching"]),
            producto=fila["producto"],
            candidatos=sorted(
                (
                    CandidatoRenglon(
                        producto=candidato["producto"],
                        confianza=_decimal_2(candidato["confianza"]),
                        metodo=candidato["metodo"],
                        elegido=candidato["elegido"],
                    )
                    for candidato in fila["candidatos"]
                ),
                key=lambda candidato: candidato.confianza,
                reverse=True,
            ),
        )
        for fila in repo.listar_renglones_con_matching(
            client, proceso_comercial_id=proceso_comercial_id
        )
    ]
    cliente = (
        repo.buscar_razon_social(client, tercero_id=proceso["cliente_id"])
        if proceso["cliente_id"]
        else None
    )
    return MatchingProceso(
        proceso_comercial_id=proceso["id"],
        nombre=proceso["nombre"],
        clase=proceso["clase"],
        cliente=cliente,
        renglones=renglones,
    )


def listar_procesos_con_matching_pendiente(client: Client) -> list[ProcesoConMatchingPendiente]:
    """Procesos with renglones still pendiente or sugerido, in the view's order
    (closest vencimiento first)."""
    por_proceso: dict[str, ProcesoConMatchingPendiente] = {}
    for fila in repo.listar_matching_pendiente(client):
        proceso = por_proceso.setdefault(
            fila["proceso_comercial_id"],
            ProcesoConMatchingPendiente(
                proceso_comercial_id=fila["proceso_comercial_id"],
                proceso=fila["proceso"],
                clase=fila["clase"],
                cliente=fila["cliente"],
                pendientes=0,
                sugeridos=0,
            ),
        )
        if fila["estado_matching"] == "sugerido":
            proceso.sugeridos += 1
        else:
            proceso.pendientes += 1
    return list(por_proceso.values())
