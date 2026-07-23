# Casos de uso — Pricing

Los 2 endpoints montados en `services/presupuestacion/main.py:21,42`
(`app.include_router(pricing_router, tags=["pricing"])`), sin prefijo adicional.

Roles (`router.py:12-13`):

```python
_ROLES_GENERAR_PRESUPUESTO = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial")
_ROLES_PRECIOS_ESPECIALES = ("superadmin", "admin", "gerencia", "compras")
```

## `POST /procesos/{proceso_id}/generar-presupuesto`

- **Quién puede llamarlo**: los 5 roles de `_ROLES_GENERAR_PRESUPUESTO` — el rol
  comercial más amplio del backend para una escritura, incluye `comercial` y
  `lider_comercial` además de los roles administrativos (`router.py:19`).
- **Función**: `generar_presupuesto_endpoint`. Valida existencia y pertenencia del
  proceso comercial con `user_client` **antes** de delegar al service con
  `service_client` (`router.py:22-34`) — único endpoint del módulo con esta doble
  validación explícita en el router.
- **Cliente Supabase**: `user_client` para la validación de pertenencia
  (`router.py:20`); `service_client` para todo el cálculo y la escritura, resuelto
  internamente por `generar_presupuesto_para_endpoint` (`service.py:319-328`) — el
  router nunca lo importa directo.
- **Excepciones de dominio**: `NotFoundError` (404) si el proceso no existe
  (`router.py:29-30`, y también dentro de `generar_presupuesto` si el service no lo
  encuentra, `service.py:223-224`); `ForbiddenError` (403) si la droguería del
  proceso no coincide con la del usuario y el rol no es `superadmin`
  (`router.py:33-34`).
- **Archivo**: `router.py:16-40`.
- **Quién lo consume**: es el único punto de entrada HTTP para generar o regenerar
  un presupuesto — no se encontró en este repositorio ningún otro módulo ni
  frontend documentado que llame a `generar_presupuesto` por otra vía. Cualquier
  regeneración (por ejemplo, tras editar el costo de un producto o el precio de un
  ítem) requiere volver a invocar este mismo endpoint.

## `GET /precios-especiales`

- **Quién puede llamarlo**: `_ROLES_PRECIOS_ESPECIALES` — `superadmin`, `admin`,
  `gerencia`, `compras`. **No** incluye `lider_comercial` ni `comercial`, a
  diferencia del endpoint de generación de presupuesto (`router.py:45`).
- **Función**: `precios_especiales_endpoint`. Devuelve el contenido crudo de la
  vista `v_precios_especiales_vigentes`, sin transformación ni modelo de salida
  tipado (`list[dict]`, no un `BaseModel` de `models.py`) — único endpoint del
  módulo sin `response_model` explícito propio.
- **Cliente Supabase**: `user_client` (con RLS) — único endpoint de escritura o
  lectura de este módulo que consulta la base directo desde el router, sin pasar
  por `service.py` ni `repository.py`.
- **Archivo**: `router.py:43-48`.
- **Quién lo consume**: expone al rol `compras` (y a los roles administrativos) una
  vista de los precios especiales vigentes — sin relación de código con el motor de
  cálculo de precios del resto del módulo; no se encontró un test de integración
  para este endpoint en `tests/pricing/test_service.py` (los 7 tests existentes
  cubren únicamente `generar_presupuesto`). Ver [`pendientes.md`](./pendientes.md)
  P3.

## Consumidores

Ningún módulo de `presupuestacion/` **importa** código de `pricing/` como paquete
Python salvo `main.py` (confirmado por grep en esta sesión: 0 resultados fuera del
propio paquete y de `main.py`). `presupuestos/` no importa `pricing/` ni viceversa —
la única relación entre ambos es a nivel de tabla (`presupuestos`,
`presupuesto_items`), no de código Python — ver
[`arquitectura.md`](./arquitectura.md).
