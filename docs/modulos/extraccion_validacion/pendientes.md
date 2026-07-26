# Pendientes — Extracción-Validación

Auditoría técnica P1 (bloqueante/riesgo alto) / P2 (riesgo medio, corregir pronto) /
P3 (mejora, sin urgencia).

## P2 — `_ROLES_VALIDAR` no incluye `superadmin` (código muerto en `router.py`)

Agregado por el change `validar-extraccion` (design.md §8.2/§14). `_ROLES_VALIDAR`
(`router.py:23`, también usado por `GET /extracciones/{id}/filas` desde este change)
es `("admin", "gerencia", "lider_comercial", "comercial")` — **no incluye
`"superadmin"`**. `require_roles(*_ROLES_VALIDAR)` le devuelve 403 a un `superadmin`
antes de que el handler corra, lo que vuelve **código muerto** la rama
`if usuario.rol != "superadmin"` de `_verificar_pertenencia`
(`router.py:48` — exime a `superadmin` del chequeo de `drogueria_id`, pero esa rama
nunca se alcanza porque el `Depends(require_roles(...))` ya cortó antes).

El patrón se replicó tal cual (mismo criterio que el resto del módulo) por
consistencia con `POST .../validar`, que ya tenía este mismo gap antes de este
change — no es una regresión introducida acá, es la misma brecha heredada,
ahora también presente en los dos endpoints nuevos de lectura.

**Pendiente de definición funcional**: decidir si `superadmin` debe poder
validar/leer extracciones de cualquier droguería (en cuyo caso `_ROLES_VALIDAR`
necesita agregar `"superadmin"` y la rama de `_verificar_pertenencia` deja de ser
código muerto) o si es intencional que solo pueda operar vía otro camino
(no identificado en esta sesión). Bugfix aparte, fuera del alcance de
`validar-extraccion`.

## P2 — Materialización de comparativa no es transaccional entre statements

Agregado por el change `validar-extraccion` (design.md §4, aclaración honesta sobre
lo que D3 garantiza y lo que no). PostgREST no da transacciones entre requests:
"atómico" en este módulo significa **una sola request HTTP**, no una sola transacción
de Postgres — eso ya era así antes de este change, no es una regresión.

Desglose real por statement dentro de `_materializar_comparativa`
(`service.py:310-407`):

| Etapa | Statements | Atomicidad real |
|---|---|---|
| `comparativas` (INSERT) | 1 | atómico |
| `ofertas_items` (INSERT multi-fila) | 1 | atómico: todas las filas entran o ninguna |
| Posiciones (`UPDATE` por oferta, `_computar_posiciones`) | N (una por oferta) | **no atómico entre sí ni con el INSERT anterior** |
| `validado = TRUE` (flip final) | 1 | último, siempre |

Si el proceso cae entre el `INSERT` de `comparativas`/`ofertas_items` y el `UPDATE`
final de `validado`, la comparativa queda creada con `validado=FALSE` en
`extraction_results` — reintentable, pero un reintento genera una **v+1** en vez de
reusar la fila ya creada (el versionado lo absorbe sin duplicar datos visibles, pero
deja una versión "huérfana" nunca marcada vigente). Para licitación/cotización el
riesgo es peor: un reintento tras una caída parcial **duplicaría** `items_proceso`
(no hay versionado ahí, cada `INSERT` es un alta nueva).

**Recomendación** [RECOMENDACIÓN], documentada explícitamente como fuera de alcance
de `validar-extraccion`: mover la materialización a una RPC transaccional de
Postgres (`BEGIN`/`COMMIT` server-side) es la solución correcta y merece su propio
change — el módulo actual no tiene ningún mecanismo de compensación/rollback
aplicativo para estos caminos.

## P2 — Bypass de `notificaciones/`: la notificación de reemplazo no genera entregas ni respeta preferencias

`repository.py:101-102` (`crear_notificacion`) inserta directo contra la tabla
`notificaciones`:

```python
def crear_notificacion(client: Client, fila: dict[str, Any]) -> None:
    client.table("notificaciones").insert(fila).execute()
```

en vez de llamar a `services/presupuestacion/notificaciones/service.py:crear_notificacion`
(`notificaciones/service.py:11-62`), que es la función que además:

1. Resuelve las preferencias de canal del destinatario para ese `tipo` de
   notificación (`notificaciones/service.py:45-49`).
2. Crea una fila en `notificacion_entregas` por cada canal habilitado
   (`notificaciones/service.py:51-60`), con `estado="pendiente"` — el mecanismo real
   de entrega (email, push, etc., fuera del alcance de esta documentación) presumiblemente
   procesa esa tabla, no `notificaciones` directamente.

**Impacto real**: los usuarios `admin`/`gerencia`/`lider_comercial` notificados por
`_notificar_reemplazo_comparativa` (`service.py:112-134`) reciben una fila en
`notificaciones` (visible si el frontend consulta esa tabla directamente o vía
`notificaciones.service.listar_no_leidas`, que sí lee de `notificaciones` —
`notificaciones/repository.py`, no auditado línea por línea en esta sesión) pero
**nunca** una fila en `notificacion_entregas`. Si el mecanismo de entrega real
(email/push/etc.) depende de `notificacion_entregas` para saber a quién y por qué
canal enviar, estas notificaciones de reemplazo de comparativa nunca se entregan por
ningún canal fuera de "verlas en la lista de notificaciones del sistema" — y aunque
un usuario haya deshabilitado explícitamente el tipo `comparativa_disponible` en sus
preferencias (`notificacion_preferencias`, gestionadas por
`notificaciones.service.upsert_preferencia`), esa preferencia nunca se consulta acá,
por lo que la notificación se crea igual.

**Módulo `notificaciones/` sin documentación propia todavía** (confirmado con `Glob
docs/modulos/notificaciones/` en esta sesión, sin resultados) — cuando se documente,
enlazar desde acá y desde ahí hacia este hallazgo.

**Recomendación** [RECOMENDACIÓN]: reemplazar la llamada a
`repo.crear_notificacion` en `_notificar_reemplazo_comparativa`
(`service.py:119-134`) por `notificaciones.service.crear_notificacion`, pasando
`relaciones={"proceso_comercial_id": ..., "comparativa_id": ...}` en vez de
incluirlos sueltos en el dict de fila.

## P2 — Uso parcial de auditoría (`core.audit`): solo dentro de `_materializar_comparativa`

Grep de `core.audit`/`registrar_cambio`/`registrar_evento_ciclo_vida` en los 4
archivos del módulo confirma que el único punto de importación y uso es
`service.py:9` (import) y `service.py:173,185` (las dos llamadas), ambas dentro de
`_materializar_comparativa` (`service.py:137-241`). Ni `models.py`, ni
`repository.py`, ni `router.py`, ni `_materializar_licitacion`
(`service.py:61-93`) generan ninguna fila en `historial_cambios`.

**Impacto**: la creación de `items_proceso` al validar una licitación/cotización —
que es, junto con la creación de comparativas, la otra mitad del propósito de este
módulo — no queda auditada. `GET /historial/{entidad}/{entidad_id}`
(`../core/`, módulo `auditoria/`) no puede mostrar "quién y cuándo creó estos
renglones" para ese camino, solo para comparativas. Tampoco se audita el `UPDATE`
final de `extraction_results.validado` (`service.py:292-296`) en ningún camino —
no hay traza en `historial_cambios` de qué extracción se validó y cuándo, más allá
de las columnas propias `validado_por`/`validado_at` de esa misma tabla.

**Consistencia con el resto del módulo**: `EntidadAuditable` (`core/audit.py:7-9`)
no incluye `"item_proceso"` ni `"extraction_result"` como valores válidos — el
`_COLUMNA_FK_POR_ENTIDAD` de `core/audit.py:12-18` solo mapea
`proceso_comercial`, `comparativa`, `orden_compra`, `presupuesto`, `evento`. Es
decir: aunque este módulo quisiera auditar la creación de `items_proceso`, la
infraestructura actual de `core.audit` no lo soporta sin extenderse primero. Esto
explica parcialmente (no justifica del todo) por qué solo se audita el camino de
comparativas.

**Recomendación** [RECOMENDACIÓN]: si se decide auditar la creación de
`items_proceso`, primero extender `EntidadAuditable`/`_COLUMNA_FK_POR_ENTIDAD` en
`core/audit.py` (fuera del alcance de este módulo) y evaluar si además conviene
auditar la transición `validado: False -> True` de `extraction_results` con
`entidad="proceso_comercial"` (ya soportada) o si amerita una entidad nueva.

## P2 — `_ROLES_NOTIFICACION_REEMPLAZO` excluye `comercial`, que sí puede validar

`_ROLES_VALIDAR` (`router.py:12`) incluye `comercial` entre los roles que pueden
ejecutar `POST /extracciones/{id}/validar`. `_ROLES_NOTIFICACION_REEMPLAZO`
(`service.py:21`) no lo incluye entre los destinatarios de la notificación de
reemplazo. Un usuario `comercial` puede validar una extracción, disparar un
reemplazo de comparativa, y no enterarse por notificación de que ocurrió — solo se
notifica a roles por encima de él en la jerarquía implícita. Motivo pendiente de
definición funcional: no hay evidencia en el código de si es intencional (el
reemplazo es información gerencial, no operativa) o una omisión.

## P3 — `orden_compra` sin materialización (alcance conocido, no un bug)

Documentado como decisión deliberada en
[`decisiones.md`](./decisiones.md) D-EXTRACCIONVALIDACION-003 — se lista acá solo
como recordatorio de trabajo pendiente, no como hallazgo nuevo. El propio schema de
`ordenes_compra` (`docs/schema/extractor_final.sql:607-630`) ya existe y tiene el
mismo patrón de versionado que `comparativas`, sugiriendo que la materialización
podría reusar buena parte de `_materializar_comparativa` cuando se implemente.

## P3 — `#5` en el docstring de `_computar_posiciones` referencia una spec externa no verificable

`service.py:99` ("...adjudicacion_estimada=TRUE al ganador de cada renglón (§5)")
referencia una sección "§5" de algún documento de especificación que no se encontró
en este repositorio en esta sesión (se buscó `prompt_backend.md` y "§5" en
`services/presupuestacion/ROADMAP.md`, sin resultados). No bloquea el entendimiento
del código — la lógica está completa y testeada — pero la referencia queda huérfana
para quien quiera rastrear la especificación original. Pendiente de definición
funcional: ubicar o archivar esa referencia.

## P3 — Ningún test cubre `router.py` directamente

Los 12 tests de `tests/extraccion/test_service.py` llaman a `validar_extraccion`
(el service) directamente con `service_client`, nunca al endpoint HTTP. No hay
evidencia en esta sesión de un test que ejercite `router.py:16-40` (el chequeo de
pertenencia de droguería vía `user_client`, `ForbiddenError` en caso de mismatch,
o el flujo completo vía FastAPI `TestClient`). El comportamiento del router está
documentado por lectura de código (ver [`casos_de_uso.md`](./casos_de_uso.md)), no
verificado por test automatizado dentro de este módulo.
