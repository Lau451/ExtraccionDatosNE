"""Servicio de historial de PCP (0012_pcp_extras.sql M1, design.md D6, spec
`pcp-historial`).

Append-only por diseño: este módulo expone únicamente `agregar_evento` y
`listar_eventos`. Deliberadamente NO existe `actualizar_evento` ni
`eliminar_evento` -- ni acá ni en ningún router futuro que consuma este
módulo -- porque `pcp_historial` no tiene políticas RLS de UPDATE/DELETE
(0012_pcp_extras.sql M7): la ausencia de esos métodos en la capa de servicio
es la primera línea de defensa (provable por la propia forma del módulo, ver
tests/pcp/historial/test_service.py), RLS es la segunda y la única real a
nivel de base (spec `pcp-historial`, "Append-Only Immutability").

Corrección post-PR3, verificada en vivo (information_schema.role_table_grants
+ pg_default_acl): el `GRANT SELECT, INSERT ON pcp_historial TO authenticated`
de 0012 M7 NO es lo que evita el UPDATE/DELETE -- Supabase ya le otorga
`ALL` (incluido DELETE) a `anon`/`authenticated`/`service_role` en toda tabla
nueva vía `ALTER DEFAULT PRIVILEGES` a nivel de proyecto, independiente de lo
que declare el GRANT explícito de cada migración. RLS es la ÚNICA barrera
real contra UPDATE/DELETE acá (y en toda tabla del proyecto, no solo esta) --
no hay defensa en profundidad de GRANT+RLS como sugería el comentario
original; el GRANT explícito es documentación de intención, no enforcement.

D2: ningún campo de costo entra nunca en un payload de pcp_historial. Por eso
`agregar_evento` no ofrece un parámetro de costo/precio dedicado -- solo un
`payload` de contexto libre que arma explícitamente quien llama (p.ej.
`pcp-gestion` en PR4 pasa old/new estado; `pcp-negociacion` en PR7 pasaría
proveedor/resultado, nunca un valor de costo crudo).
"""

from typing import Any

from supabase import Client

from services.pcp.historial import repository as repo
from services.pcp.historial.models import TipoEvento


def agregar_evento(
    client: Client,
    *,
    drogueria_id: str,
    pcp_id: str,
    tipo_evento: TipoEvento,
    payload: dict[str, Any] | None = None,
    usuario_id: str | None = None,
    pcp_renglon_id: str | None = None,
    origen: str | None = None,
) -> dict[str, Any]:
    fila = {
        "drogueria_id": drogueria_id,
        "pcp_id": pcp_id,
        "pcp_renglon_id": pcp_renglon_id,
        "tipo_evento": tipo_evento,
        "payload": payload or {},
        "origen": origen,
        "usuario_id": usuario_id,
    }
    return repo.crear_evento(client, fila)


def listar_eventos(client: Client, *, pcp_id: str, drogueria_id: str) -> list[dict[str, Any]]:
    return repo.listar_eventos(client, pcp_id=pcp_id, drogueria_id=drogueria_id)
