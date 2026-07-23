# Reglas de negocio — Comparativas

## RN-COMPARATIVAS-001 — El proveedor asignado debe pertenecer a la misma droguería que la oferta [IMPLEMENTADO]

`asignar_proveedor` (`service.py:10-25`) es la **única** validación de negocio de todo
el módulo:

```python
if proveedor["drogueria_id"] != oferta["drogueria_id"]:
    raise ValidationError("El proveedor no pertenece a la misma droguería que la oferta")
```

(`service.py:20-21`). Antes de esta comparación, ya se validó que la oferta exista
(`NotFoundError`, `service.py:14-15`) y que el proveedor exista
(`NotFoundError`, `service.py:18-19`). Confirmado por 3 tests:
`test_asignar_proveedor_actualiza_la_oferta`,
`test_asignar_proveedor_oferta_inexistente`,
`test_asignar_proveedor_proveedor_inexistente`,
`test_asignar_proveedor_de_otra_drogueria_falla`
(`tests/comparativas/test_service.py:11-99`).

Es una validación de **integridad de datos** (que el proveedor elegido sea coherente
con la droguería dueña de la oferta), no de autorización — la autorización del
solicitante la resuelve el router por separado (RN-COMPARATIVAS-002).

## RN-COMPARATIVAS-002 — El router valida pertenencia de la oferta a la droguería del usuario antes de delegar [IMPLEMENTADO]

`asignar_proveedor_endpoint` (`router.py:38-59`) hace, con `user_client` (RLS-aware),
un `SELECT id, drogueria_id` sobre `ofertas_items` (`router.py:45-51`) **antes** de
llamar a `asignar_proveedor_para_endpoint` (que corre con `service_role`, sin RLS):

```python
if usuario.rol != "superadmin" and oferta_drogueria_id != usuario.drogueria_id:
    raise ForbiddenError("La oferta no pertenece a tu droguería")
```

(`router.py:56-57`). Si la oferta no existe siquiera bajo RLS →
`NotFoundError("No se encontró la oferta")` (`router.py:52-53`).

Este es el mismo patrón `_validar_*_de_la_drogueria` inline en el router, ya
documentado en [`../presupuestos/reglas.md`](../presupuestos/reglas.md)
RN-PRESUPUESTOS-016, [`../matching/`](../matching/README.md) y
[`../clientes/`](../clientes/README.md) — necesario porque
`asignar_proveedor_para_endpoint` corre sin RLS (ver
[`arquitectura.md`](./arquitectura.md)): sin este chequeo previo, cualquier
solicitante con rol habilitado podría reasignar el proveedor de una oferta de otra
droguería. A diferencia de `presupuestos/router.py`, acá el chequeo está inline dentro
del propio endpoint (`router.py:45-57`), no extraído a una función `_validar_*`
separada — el módulo tiene un solo endpoint de escritura, así que no hay duplicación
que factorizar. Confirmado por test:
`test_asignar_proveedor_de_otra_drogueria_falla` ejercita la ruta de `service.py`
directamente, no el router — no hay test HTTP de este chequeo específico en este
módulo (ver [`pendientes.md`](./pendientes.md)).

**Nota importante**: esta validación (usuario vs. droguería de la oferta) es distinta
de RN-COMPARATIVAS-001 (proveedor vs. droguería de la oferta). No son el mismo chequeo
duplicado dos veces — son dos comparaciones diferentes, con propósitos diferentes
(autorización del solicitante vs. integridad del dato elegido), que casualmente
comparten la forma `X.drogueria_id != Y.drogueria_id`.

## RN-COMPARATIVAS-003 — Roles distintos para leer y para escribir [IMPLEMENTADO]

```python
_ROLES_ASIGNAR = ("admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
```

(`router.py:17-18`). `_ROLES_LECTURA` es un superconjunto de `_ROLES_ASIGNAR` con 2
roles adicionales:

- `superadmin` puede leer ambas vistas pero **no** puede ejecutar `asignar_proveedor`
  vía `require_roles(*_ROLES_ASIGNAR)` (`router.py:42`) — sí puede, en cambio, saltear
  RN-COMPARATIVAS-002 (esa condición explícitamente exceptúa a `superadmin`,
  `router.py:56`). Es decir: si `superadmin` pudiera pasar el filtro de rol de
  `_ROLES_ASIGNAR` (no puede, hoy), no tendría problema con el chequeo de tenant. Los
  dos mecanismos son independientes.
- `compras` puede leer ambas vistas pero no puede asignar proveedor — consistente con
  que `compras/` es el módulo consumidor de `v_renglones_ganados` (anticipar compras,
  ver [`arquitectura.md`](./arquitectura.md)) pero no el responsable de corregir el
  matching de proveedores.

Sin test de integración HTTP que ejercite el ruteo por rol de los 3 endpoints — ver
[`pendientes.md`](./pendientes.md).

## RN-COMPARATIVAS-004 — `v_renglones_ganados` solo muestra ofertas propias, ganadoras y de la versión vigente [IMPLEMENTADO]

La vista filtra `WHERE oi.es_drogueria_propia = TRUE AND (oi.adjudicada OR
oi.adjudicacion_estimada)` y hace `JOIN comparativas c ON ... AND c.es_vigente = TRUE`
(`extractor_final.sql:1591,1594-1595`). Tres condiciones simultáneas para que una
oferta aparezca:

1. Es de la propia droguería (`es_drogueria_propia = TRUE`).
2. Ganó, oficial o estimado (`adjudicada OR adjudicacion_estimada`).
3. Pertenece a la versión vigente de su comparativa (`es_vigente = TRUE`) — una oferta
   de una versión reemplazada nunca aparece, aunque haya ganado en su momento.

`nivel` distingue cuál de las dos condiciones de "ganó" aplicó: `'oficial'` si
`adjudicada`, `'estimado'` si no `adjudicada` pero sí `adjudicacion_estimada`
(`extractor_final.sql:1588-1589`) — el `CASE` no tiene rama `ELSE`, pero es
inalcanzable: la fila ya pasó el filtro `WHERE ... (adjudicada OR
adjudicacion_estimada)`, así que al menos una de las dos siempre es verdadera.
Confirmado por test: `test_v_renglones_ganados_muestra_ofertas_propias_ganadoras`
(`tests/comparativas/test_service.py:102-134`), que verifica las 3 condiciones por
separado (una oferta no-propia-pero-ganadora no aparece, una propia-pero-no-ganadora
tampoco) y que `nivel == "estimado"` para una oferta con solo
`adjudicacion_estimada=True`.

## RN-COMPARATIVAS-005 — `v_ofertas_sin_matchear` solo cuenta ofertas de terceros sin vincular [IMPLEMENTADO]

La vista filtra `WHERE oi.proveedor_id IS NULL AND oi.es_drogueria_propia = FALSE`
(`extractor_final.sql:1620`). Una oferta deja de aparecer en esta vista en cuanto se le
asigna `proveedor_id` (vía `POST /ofertas/{id}/asignar-proveedor`, el único punto de
escritura de ese campo en todo el repositorio auditado en esta sesión) — no hace falta
ninguna acción adicional para "sacarla de la lista de sin matchear", el `UPDATE` de
`proveedor_id` ya la excluye del filtro. No hay test de integración específico contra
la vista en `tests/comparativas/` (los tests cubren `asignar_proveedor` y
`v_renglones_ganados`, no `v_ofertas_sin_matchear` — ver
[`pendientes.md`](./pendientes.md)).
