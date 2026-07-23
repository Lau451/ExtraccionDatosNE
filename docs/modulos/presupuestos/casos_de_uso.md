# Casos de uso — Presupuestos

Los 4 endpoints montados en `services/presupuestacion/main.py:20,44`
(`app.include_router(presupuestos_router, tags=["presupuestos"])`), sin prefijo
adicional.

Roles (`router.py:17-21`):

```python
_ROLES_APROBAR = ("superadmin", "admin", "gerencia", "lider_comercial")
_ROLES_AJUSTAR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_PRESENTAR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_VEN_COSTO = ("superadmin", "admin", "gerencia")
```

## `GET /presupuestos/{presupuesto_id}`

- **Quién puede llamarlo**: los 5 roles de `_ROLES_LECTURA` — todo el ciclo
  comercial más los 3 roles administrativos.
- **Función**: `obtener_presupuesto_endpoint`. Selecciona la vista según el rol
  del solicitante (RN-PRESUPUESTOS-013): `v_presupuesto_revision` para
  `_ROLES_VEN_COSTO` (`superadmin`, `admin`, `gerencia`), `v_presupuesto_comercial`
  para el resto (`comercial`, `lider_comercial`).
- **Cliente Supabase**: `user_client` (con RLS) — único endpoint del módulo que
  no delega en ninguna función de `service.py`, va directo de `router.py` a
  `repository.py`.
- **Respuesta**: `list[dict]` — una fila por ítem del presupuesto (join contra
  `presupuesto_items`, ver [`base_de_datos.md`](./base_de_datos.md)), sin
  `response_model` explícito propio.
- **Excepciones de dominio**: `NotFoundError` si la vista no devuelve filas
  (`router.py:74-75`) — incluye tanto "el presupuesto no existe" como "existe
  pero RLS filtró todas las filas" (por ejemplo, otra droguería), sin distinguir
  ambos casos en el mensaje.
- **Archivo**: `router.py:60-76`.
- **Quién lo consume**: es la única vía de lectura estructurada de un
  presupuesto completo con sus ítems — no se encontró en este repositorio
  ningún otro módulo ni frontend documentado que consulte
  `v_presupuesto_comercial`/`v_presupuesto_revision` por otra vía.

## `POST /presupuestos/{presupuesto_id}/aprobar`

- **Quién puede llamarlo**: `_ROLES_APROBAR` — `superadmin`, `admin`,
  `gerencia`, `lider_comercial`. **No** incluye `comercial`, a diferencia de
  ajustar y presentar (`router.py:79-86`). Coincide con el comentario del
  schema: *"lider_comercial → [...] APRUEBA presupuestos (validación de
  aprobación en el BACKEND, no en la BD)"* (`docs/schema/rls_final.sql:10-11`).
- **Función**: `aprobar_endpoint`. Valida pertenencia a la droguería con
  `user_client` antes de delegar en `aprobar_presupuesto_para_endpoint`
  (`service_role`).
- **Cliente Supabase**: `user_client` para la validación de pertenencia
  (`router.py:83`); `service_client` para la escritura, resuelto internamente
  por `aprobar_presupuesto_para_endpoint` (RN-PRESUPUESTOS-014).
- **Excepciones de dominio**: `NotFoundError` (404, presupuesto inexistente,
  `router.py:35` o `service.py:96`); `ForbiddenError` (403, otra droguería,
  `router.py:39`); `ConflictError` (409, estado no aprobable,
  RN-PRESUPUESTOS-001); `ValidationError` (422, ítems `sin_precio` sin resolver,
  RN-PRESUPUESTOS-002).
- **Response**: `ResultadoPresupuesto`.
- **Archivo**: `router.py:79-86`.
- **Quién lo consume**: único punto de entrada HTTP para aprobar un
  presupuesto — no hay otra vía en el código para transicionar a `"aprobado"`.

## `POST /presupuestos/{presupuesto_id}/presentar`

- **Quién puede llamarlo**: `_ROLES_PRESENTAR` — `superadmin`, `admin`,
  `gerencia`, `lider_comercial`, `comercial`. Incluye `comercial` a diferencia
  de aprobar.
- **Función**: `presentar_endpoint`. Misma validación de pertenencia, delega en
  `presentar_presupuesto_para_endpoint` (`service_role`, RN-PRESUPUESTOS-015).
- **Cliente Supabase**: `user_client` para la validación; `service_client` para
  la escritura (necesario tanto por la RLS de `presupuestos` como por la de
  `stock_productos`, que ni siquiera `superadmin` satisface por `UPDATE`).
- **Excepciones de dominio**: `NotFoundError` (404, presupuesto o proceso
  comercial inexistente); `ForbiddenError` (403, otra droguería); `ConflictError`
  (409, estado no `"aprobado"` — RN-PRESUPUESTOS-003 — o falla de compromiso de
  stock sin cobertura suficiente/con contención — RN-PRESUPUESTOS-006).
- **Response**: `ResultadoPresupuesto`.
- **Archivo**: `router.py:89-96`.
- **Efecto colateral**: transiciona también `procesos_comerciales.estado` a
  `"presentado"` sin guarda (RN-PRESUPUESTOS-007) — ver
  [`../procesos_comerciales/casos_de_uso.md`](../procesos_comerciales/casos_de_uso.md)
  si existiera una sección equivalente desde ese lado, o
  [`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md).
- **Quién lo consume**: único punto de entrada HTTP para presentar un
  presupuesto al cliente; es también, indirectamente, el único punto de entrada
  HTTP de todo el repositorio (fuera de `compras/`) que puede comprometer stock
  real.

## `PATCH /presupuesto-items/{item_id}`

- **Quién puede llamarlo**: `_ROLES_AJUSTAR` — los mismos 5 roles que pueden
  presentar (incluye `comercial`).
- **Función**: `ajustar_item_endpoint`. `_validar_item_de_la_drogueria` (no
  `_validar_presupuesto_de_la_drogueria` — valida sobre `presupuesto_items`
  directo, no sobre `presupuestos`) antes de delegar en
  `ajustar_item_para_endpoint` (`service_role`).
- **Body**: `AjustarItemRequest` — `precio_unitario`, `cantidad_ofertada`,
  `excluido`, `motivo_exclusion`, todos opcionales (`models.py:11-15`).
- **Cliente Supabase**: `user_client` para la validación de pertenencia del
  ítem; `service_client` para la escritura.
- **Excepciones de dominio**: `NotFoundError` (404, ítem inexistente);
  `ForbiddenError` (403, otra droguería); `ValidationError` (422, ningún campo
  especificado — RN-PRESUPUESTOS-010).
- **Response**: `dict` crudo (la fila actualizada de `presupuesto_items`) — sin
  `response_model` explícito, único endpoint del módulo con este patrón (a
  diferencia de los otros 3, que sí devuelven `ResultadoPresupuesto`).
- **Archivo**: `router.py:99-114`.
- **Sin guarda de estado del presupuesto**: puede ajustarse un ítem en
  cualquier estado del presupuesto padre, incluyendo `"presentado"` (ver
  [`flujo.md`](./flujo.md) y [`pendientes.md`](./pendientes.md)).
- **Quién lo consume**: único punto de entrada HTTP para editar manualmente un
  ítem de presupuesto — no hay otra vía en el código para modificar
  `precio_unitario`/`cantidad_ofertada`/`excluido` de una fila de
  `presupuesto_items` ya creada por `pricing/`.

## Consumidores

Ningún módulo de `presupuestacion/` **importa** código de `presupuestos/` como
paquete Python salvo `main.py` (confirmado por grep en esta sesión). La relación
con `pricing/` y `procesos_comerciales/` es exclusivamente de tabla compartida —
ver [`arquitectura.md`](./arquitectura.md).
