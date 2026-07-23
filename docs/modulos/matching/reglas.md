# Reglas de negocio — Matching

## RN-MATCHING-001 — Alias del cliente tiene prioridad absoluta sobre el fuzzy matching [IMPLEMENTADO]

`procesar_matching_item` (`service.py:39-110`) solo intenta el fuzzy matching
(`_generar_candidatos`, `service.py:71-73`) si **no** hay un alias vigente para el
`cliente_id` recibido. Si `cliente_id is not None` y existe un alias vigente
(`repo.buscar_alias_vigente`, `service.py:45-49`), el método retorna inmediatamente
con `estado_matching="automatico"` (`service.py:49-69`) — nunca se genera ningún
candidato ni se calcula ningún score en ese camino. Si `cliente_id is None` (el
renglón no tiene proceso comercial con cliente asociado), se salta directo al fuzzy.
Confirmado por test:
`test_procesar_matching_item_usa_alias_vigente_y_marca_automatico`
(`tests/matching/test_service.py:13-38`, `resultado.candidatos == []` en línea 28).

## RN-MATCHING-002 — Umbral de confianza para sugerir un match: 70 [IMPLEMENTADO]

`_UMBRAL_SUGERIDO = Decimal("70")` (`service.py:13`). Tras generar los candidatos
fuzzy, `procesar_matching_item` toma el de mayor `confianza`
(`mejor_confianza = max((c.confianza for c in candidatos), default=None)`,
`service.py:88`) y decide (`service.py:89-91`):

```python
estado = (
    "sugerido" if mejor_confianza is not None and mejor_confianza >= _UMBRAL_SUGERIDO else "pendiente"
)
```

- `mejor_confianza >= 70` → `estado_matching = "sugerido"` (el sistema propone un
  candidato, requiere confirmación humana vía `confirmar_matching`).
- `mejor_confianza < 70`, o no hay candidatos (`default=None`) → `estado_matching =
  "pendiente"`.

Es una comparación `>=`, no `>`: un candidato con confianza exactamente `70.00`
cuenta como `sugerido`. Confirmado por 3 tests:
`test_procesar_matching_item_genera_candidatos_fuzzy_y_marca_sugerido` (candidato con
confianza ≥ 70 → `sugerido`, `tests/matching/test_service.py:66-99`),
`test_procesar_matching_item_marca_pendiente_si_mejor_candidato_es_bajo`
(`:102-120`) y `test_procesar_matching_item_sin_catalogo_queda_pendiente_sin_candidatos`
(`:123-138`, sin productos activos → `candidatos == []`, `confianza_matching is None`,
`pendiente`).

## RN-MATCHING-003 — Top-5 candidatos por fuzzy matching [IMPLEMENTADO]

`_TOP_K = 5` (`service.py:14`), pasado como `limit=_TOP_K` a
`rapidfuzz.process.extract` (`service.py:25-27`). Nunca se generan más de 5
candidatos por renglón en una corrida de `procesar_matching_item` — si hay menos de 5
productos activos en la droguería, se generan tantos como productos existan (el
`limit` de `rapidfuzz` no falla con menos elementos que el límite).

## RN-MATCHING-004 — Scorer fijo: `rapidfuzz.fuzz.WRatio`, único método de matching implementado [IMPLEMENTADO]

`_generar_candidatos` usa `scorer=fuzz.WRatio` (`service.py:4,26`) sin parametrizar
por caller. `MetodoMatching` (`models.py:7`) declara 4 valores posibles —
`"exact" | "fuzzy" | "embedding" | "manual"` — pero el único valor que este módulo
asigna en cualquier punto de su código es `"fuzzy"` (`service.py:32`, la única
ocurrencia de un valor de `MetodoMatching` en todo `matching/`). No se encontró en
esta sesión ningún camino que produzca `"exact"`, `"embedding"` ni `"manual"` — son
valores reservados en el tipo (y permitidos por el `CHECK` de schema,
`ck_mc_metodo`, `docs/schema/extractor_final.sql:459`) sin implementación
correspondiente. Ver D-MATCHING-003 en [`decisiones.md`](./decisiones.md).

## RN-MATCHING-005 — Confirmar un matching versiona el alias del cliente [IMPLEMENTADO]

`_upsert_alias` (`service.py:113-141`), llamada desde `confirmar_matching` solo si
`cliente_id is not None` (`service.py:158-170`):

1. Busca el alias vigente actual para `(cliente_id, descripcion_normalizada)`
   (`service.py:123-125`).
2. Si existe y **ya apunta al mismo `producto_id`** que se está confirmando → lo
   reusa tal cual, sin escribir nada (`service.py:126-127`). Confirmado por test:
   `test_confirmar_matching_no_duplica_alias_si_ya_apunta_al_mismo_producto`
   (`tests/matching/test_service.py:222-249`).
3. Si existe pero apunta a **otro** `producto_id` → se invalida
   (`repo.invalidar_alias`, `vigente=False`, `service.py:129-130`) y se crea uno
   nuevo con el producto recién confirmado (`service.py:132-140`). Confirmado por
   test: `test_confirmar_matching_invalida_alias_viejo_si_cambia_producto`
   (`tests/matching/test_service.py:179-218`, verifica `vigente is False` en el
   viejo y `vigente is True` en el nuevo).
4. Si no existe ningún alias vigente → se crea uno nuevo directamente
   (`service.py:132-140`). Confirmado por test:
   `test_confirmar_matching_crea_alias_nuevo_si_no_habia`
   (`tests/matching/test_service.py:142-176`).

Si `cliente_id is None` (proceso sin cliente asociado), `confirmar_matching` no toca
`cliente_producto_alias` en absoluto — el `alias_id` del item queda como estaba
(`item.get("alias_id")`, `service.py:157`, sin reasignar).

## RN-MATCHING-006 — Confirmar marca el candidato elegido, exista o no como fila previa [IMPLEMENTADO]

`confirmar_matching` llama a `repo.marcar_candidato_elegido` incondicionalmente
(`service.py:155`), antes incluso de resolver el alias. Esa función hace un `UPDATE
matching_candidatos SET elegido=True WHERE item_proceso_id=? AND producto_id=?`
(`repository.py:97-100`) sin verificar si la fila existe. Si el `producto_id`
confirmado nunca apareció entre los candidatos generados por fuzzy (p. ej. el usuario
lo buscó manualmente en el catálogo, o el renglón venía de un alias sin candidatos),
el `UPDATE` no afecta ninguna fila y la llamada no falla — no hay verificación de
`rowcount` ni excepción. Confirmado por test:
`test_confirmar_matching_marca_candidato_elegido`
(`tests/matching/test_service.py:252-286`, que sí siembra manualmente una fila de
`matching_candidatos` antes de confirmar — no hay test que confirme el camino sin
fila previa).

## RN-MATCHING-007 — Marcar sin match limpia `producto_id` pero preserva `alias_id` [IMPLEMENTADO]

`marcar_sin_match` (`service.py:193-211`) hace `UPDATE items_proceso SET
producto_id=NULL, estado_matching='sin_match'` (`service.py:198-201`). No toca
`alias_id` en el `UPDATE` — la respuesta lo devuelve leyendo el valor previo del item
(`item.get("alias_id")`, `service.py:207`), sin limpiarlo en la base. Es decir: si un
renglón llegó a `sin_match` después de haber tenido un `alias_id` asignado (por
ejemplo, tras un matching automático que luego un humano decide descartar), la
columna `alias_id` de `items_proceso` sigue apuntando al alias viejo aunque
`producto_id` ya sea `NULL`. Confirmado por test:
`test_marcar_sin_match_deja_item_sin_producto`
(`tests/matching/test_service.py:290-308`, solo verifica `producto_id is None` y
`estado_matching == "sin_match"`, no hay assert sobre `alias_id`).

## RN-MATCHING-008 — Roles habilitados para confirmar/marcar sin match/listar pendientes [IMPLEMENTADO]

Los 3 endpoints de `router.py` comparten el mismo conjunto de roles,
`_ROLES_MATCHING = ("superadmin", "admin", "gerencia", "lider_comercial",
"comercial")` (`router.py:19`), aplicado vía `require_roles(*_ROLES_MATCHING)`
(`router.py:44,56,65`). A diferencia de `_ROLES_VALIDAR` de `extraccion/router.py:12`
(que no incluye `superadmin` explícitamente porque ese rol siempre pasa el check de
`require_roles` por otra vía — ver `core/auth.py`), este módulo sí lista
`"superadmin"` de forma explícita en su tupla de roles.

## RN-MATCHING-009 — El router valida pertenencia de droguería antes de delegar (solo en 2 de los 3 endpoints) [IMPLEMENTADO]

`_validar_item_de_la_drogueria` (`router.py:22-37`) hace un `SELECT id, drogueria_id`
sobre `items_proceso` con `user_client` (RLS-aware) **antes** de delegar en el
service (que corre con `service_role`, sin RLS). Si no se encuentra el item →
`NotFoundError`; si el usuario no es `superadmin` y el item pertenece a otra
droguería → `ForbiddenError("El renglón no pertenece a tu droguería")`
(`router.py:36-37`). Se invoca en `confirmar_matching_endpoint` (`router.py:47`) y en
`sin_match_endpoint` (`router.py:59`) — **no** en `listar_pendientes_endpoint`
(`router.py:63-69`), que no recibe ningún `item_id` como path param (lista todos los
pendientes visibles para el `user_client`, ya filtrados por RLS a nivel de fila). Esta
validación es responsabilidad exclusiva del router — `service.py` no vuelve a
chequear pertenencia de droguería del llamante en `confirmar_matching` ni en
`marcar_sin_match`.

## RN-MATCHING-010 — `GET /matching/pendientes` no pasa por `service.py` [IMPLEMENTADO]

`listar_pendientes_endpoint` (`router.py:63-69`) consulta directamente la vista
`v_matching_pendiente` con `user_client` (`router.py:68`) y retorna su resultado tal
cual, sin invocar ninguna función de `matching/service.py` ni `matching/repository.py`.
Es el único de los 3 endpoints que no delega en la capa de servicio del módulo —
depende enteramente de la definición de la vista
(`docs/schema/extractor_final.sql:1534-1552`, ver [`base_de_datos.md`](./base_de_datos.md))
y de las políticas RLS de `items_proceso`/`procesos_comerciales`/`clientes` para el
escopeo por tenant.
