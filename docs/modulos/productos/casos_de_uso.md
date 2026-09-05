# Casos de uso — Catálogo

Los 12 endpoints montados en `services/presupuestacion/main.py:51`
(`app.include_router(catalogo_router, tags=["catalogo"])`), sin prefijo adicional.

Roles (`router.py:43-46`):

```python
_ROLES_LECTURA_CATALOGO = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")
_ROLES_ESCRITURA_CATALOGO = ("admin", "gerencia", "compras")
_ROLES_ESCRITURA_CATEGORIAS = ("admin", "gerencia")
_ROLES_LECTURA_COSTOS = ("superadmin", "admin", "gerencia", "compras")
```

Los 2 endpoints `DELETE` (producto, proveedor) no usan ninguna de estas 4
constantes: usan la tupla hardcodeada `("admin", "gerencia")` directo en el
`Depends` — ver D-CATALOGO-... en [`decisiones.md`](./decisiones.md) y
[`pendientes.md`](./pendientes.md) P3(1).

## `GET /productos`

- **Quién puede llamarlo**: los 6 roles de `_ROLES_LECTURA_CATALOGO` (`router.py:55`).
- **Función**: `listar_productos_endpoint`, con `activo: bool | None` y
  `categoria_id: str | None` opcionales como query params.
- **Cliente Supabase**: `user_client` (con RLS).
- **Archivo**: `router.py:51-60`.

## `POST /productos`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATALOGO` — incluye `compras`
  (`router.py:66`).
- **Función**: `crear_producto_endpoint`. Sin validación de negocio adicional más
  allá de tipado Pydantic — ver Flujo 1 en [`flujo.md`](./flujo.md).
- **Cliente Supabase**: `service_client` (sin RLS, vía `crear_producto_para_endpoint`).
- **Archivo**: `router.py:63-68`.

## `GET /productos/{producto_id}`

- **Quién puede llamarlo**: `_ROLES_LECTURA_CATALOGO` (`router.py:74`).
- **Función**: `obtener_producto_endpoint`. Aplica RN-CATALOGO-001.
- **Cliente Supabase**: `user_client`.
- **Archivo**: `router.py:71-77`.

## `PATCH /productos/{producto_id}`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATALOGO` — incluye `compras`
  (`router.py:84`).
- **Función**: `actualizar_producto_endpoint`. Aplica RN-CATALOGO-001 (pertenencia) y
  RN-CATALOGO-002 (actualización parcial).
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:80-88`.

## `DELETE /productos/{producto_id}`

- **Quién puede llamarlo**: `("admin", "gerencia")` **hardcodeado**, no
  `_ROLES_ESCRITURA_CATALOGO` — excluye explícitamente a `compras`, que sí puede
  crear y editar productos pero no eliminarlos (`router.py:94`).
- **Función**: `eliminar_producto_endpoint`. Aplica RN-CATALOGO-001 y
  RN-CATALOGO-003 (soft-delete).
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:91-98`.

## `GET /categorias`

- **Quién puede llamarlo**: `_ROLES_LECTURA_CATALOGO` (`router.py:106`).
- **Función**: `listar_categorias_endpoint`, con `activa: bool | None` opcional.
- **Cliente Supabase**: `user_client`.
- **Archivo**: `router.py:103-109`.

## `POST /categorias`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATEGORIAS` — más restrictivo que
  `_ROLES_ESCRITURA_CATALOGO`, excluye `compras` (`router.py:115`).
- **Función**: `crear_categoria_endpoint`.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:112-117`.

## `PATCH /categorias/{categoria_id}`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATEGORIAS` (`router.py:124`).
- **Función**: `actualizar_categoria_endpoint`. Aplica pertenencia
  (RN-CATALOGO-001, variante categoría) y RN-CATALOGO-002.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:120-128`.

Sin `DELETE /categorias/{id}` — RN-CATALOGO-004.

## `GET /proveedores`

- **Quién puede llamarlo**: `_ROLES_LECTURA_CATALOGO` (`router.py:136`).
- **Función**: `listar_proveedores_endpoint`, con `activo: bool | None` opcional.
- **Cliente Supabase**: `user_client`.
- **Archivo**: `router.py:133-139`.

## `POST /proveedores`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATALOGO` — incluye `compras`
  (`router.py:145`).
- **Función**: `crear_proveedor_endpoint`.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:142-147`.

## `GET /proveedores/{proveedor_id}`

- **Quién puede llamarlo**: `_ROLES_LECTURA_CATALOGO` (`router.py:153`).
- **Función**: `obtener_proveedor_endpoint`. Aplica RN-CATALOGO-001.
- **Cliente Supabase**: `user_client`.
- **Archivo**: `router.py:150-156`.

## `PATCH /proveedores/{proveedor_id}`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATALOGO` — incluye `compras`
  (`router.py:163`).
- **Función**: `actualizar_proveedor_endpoint`. Aplica RN-CATALOGO-001 y
  RN-CATALOGO-002.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:159-167`.

## `DELETE /proveedores/{proveedor_id}`

- **Quién puede llamarlo**: `("admin", "gerencia")` **hardcodeado**, mismo patrón
  que `DELETE /productos/{id}` — excluye `compras` (`router.py:173`).
- **Función**: `eliminar_proveedor_endpoint`. Aplica RN-CATALOGO-001 y
  RN-CATALOGO-003.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:170-177`.

## `GET /productos/{producto_id}/costos`

- **Quién puede llamarlo**: `_ROLES_LECTURA_COSTOS` — **no** incluye
  `lider_comercial` ni `comercial`, a diferencia de `_ROLES_LECTURA_CATALOGO`
  (`router.py:185`).
- **Función**: `listar_costos_endpoint`. Valida pertenencia del producto
  (RN-CATALOGO-001) antes de listar.
- **Cliente Supabase**: `service_client` (vía `listar_costos_para_endpoint`, no hay
  variante con `user_client` para este endpoint).
- **Archivo**: `router.py:182-187`.

## `POST /productos/{producto_id}/costos`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATALOGO` — incluye `compras`, más
  amplio que `_ROLES_LECTURA_COSTOS` para el `GET` del mismo sub-recurso
  (`router.py:194`).
- **Función**: `crear_costo_endpoint`. Aplica RN-CATALOGO-001, RN-CATALOGO-005,
  RN-CATALOGO-006 y RN-CATALOGO-007.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:190-196`.

## `GET /productos/{producto_id}/stock`

- **Quién puede llamarlo**: `_ROLES_LECTURA_CATALOGO` (`router.py:204`) — a
  diferencia de costos, stock usa el mismo grupo de lectura amplio que
  productos/proveedores, no `_ROLES_LECTURA_COSTOS`.
- **Función**: `listar_stock_endpoint`. Valida pertenencia del producto.
- **Cliente Supabase**: `service_client` (vía `listar_stock_para_endpoint`).
- **Archivo**: `router.py:201-206`.

## `PATCH /productos/{producto_id}/stock`

- **Quién puede llamarlo**: `_ROLES_ESCRITURA_CATALOGO` (`router.py:213`).
- **Función**: `ajustar_stock_endpoint`. Aplica RN-CATALOGO-001, RN-CATALOGO-008,
  RN-CATALOGO-009 y RN-CATALOGO-010.
- **Cliente Supabase**: `service_client`.
- **Archivo**: `router.py:209-215`.

## Consumidores

Ningún módulo de `presupuestacion/` **importa** código de `catalogo/` salvo
`main.py` (confirmado por grep en esta sesión: 0 resultados fuera del propio
paquete). Fuera de ese Python, 5 módulos leen o escriben directo las mismas 5 tablas
— más consumidores que cualquier otro módulo documentado hasta ahora en este
proyecto:

- `services/presupuestacion/matching/repository.py:42` (`listar_productos_activos`):
  lee `productos` directo para el proceso de matching de ítems.
- `services/presupuestacion/comparativas/repository.py:15` (`buscar_proveedor`): lee
  `proveedores` directo.
- `services/presupuestacion/pricing/repository.py:57`
  (`buscar_costo_estandar_vigente`), `:114` (`buscar_stock_libre`), `:126`
  (`buscar_producto`): lee `costos_productos`, `stock_productos` y `productos`
  directo para el motor de pricing.
- `services/presupuestacion/core/stock.py:17,27,35,48`: motor de compromiso y
  descuento sobre `stock_productos`, ya documentado en [`../core/`](../core/) — ver
  [`arquitectura.md`](./arquitectura.md) de este módulo para su interacción concreta
  con `catalogo.ajustar_stock`.
- `services/presupuestacion/imports/repository.py`: CRUD masivo directo sobre las 4
  tablas con bloques propios (`-- productos --` líneas 5-61, `-- costos --`
  líneas 64-84, `-- stock --` líneas 87-91, `-- proveedores --` líneas 94-138),
  incluyendo un upsert masivo (`actualizar_productos_existentes`,
  `repository.py:37-39`) que no pasa por ninguna validación de `catalogo.service`.
- `services/presupuestacion/imports/service.py:87-138` (`importar_costos`):
  reimplementa el mismo algoritmo de versionado de costo que
  `catalogo.service.crear_costo` (RN-CATALOGO-005/006), de forma completamente
  independiente — ver [`arquitectura.md`](./arquitectura.md) para el detalle, es el
  hallazgo de acoplamiento más relevante de este módulo.
