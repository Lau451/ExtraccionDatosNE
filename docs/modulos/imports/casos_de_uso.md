# Casos de uso — Imports

Los 5 endpoints montados en `services/presupuestacion/main.py:17,50`
(`app.include_router(imports_router, tags=["imports"])`), prefijo `/imports`.

Roles: un único tuple para los 5 endpoints, `_ROLES_IMPORT = ("admin", "gerencia",
"compras")` (`router.py:26`) — ver RN-IMPORTS-013 en [`reglas.md`](./reglas.md) para la
comparación con el resto de los módulos. No hay distinción de lectura: los 5 endpoints
son `POST`, no existe ningún `GET` en este módulo (no hay forma de consultar el
resultado de una importación anterior salvo por lo que devuelve la misma llamada
`POST`).

## `POST /imports/productos`

- **Quién puede llamarlo**: `_ROLES_IMPORT`.
- **Función**: `importar_productos_endpoint` → `importar_productos_para_endpoint` →
  `importar_productos`. Aplica RN-IMPORTS-001, RN-IMPORTS-011, RN-IMPORTS-012.
- **Cliente Supabase**: `service_client` (sin RLS) — único cliente usado en todo el
  módulo.
- **Request**: `ImportProductosRequest { productos: list[ImportProductoRow] }`.
- **Response**: `ImportProductosResultado { creados, actualizados, desactivados }`.
- **Archivo**: `router.py:29-37`.

## `POST /imports/costos`

- **Quién puede llamarlo**: `_ROLES_IMPORT`.
- **Función**: `importar_costos_endpoint` → `importar_costos_para_endpoint` →
  `importar_costos`. Aplica RN-IMPORTS-004, RN-IMPORTS-009, RN-IMPORTS-010,
  RN-IMPORTS-012.
- **Cliente Supabase**: `service_client`.
- **Request**: `ImportCostosRequest { costos: list[ImportCostoRow] }`.
- **Response**: `ImportCostosResultado { nuevos, actualizados, sin_cambios,
  no_encontrados }`.
- **Archivo**: `router.py:40-46`.

## `POST /imports/stock`

- **Quién puede llamarlo**: `_ROLES_IMPORT`.
- **Función**: `importar_stock_endpoint` → `importar_stock_para_endpoint` →
  `importar_stock`. Aplica RN-IMPORTS-005, RN-IMPORTS-006, RN-IMPORTS-012.
- **Cliente Supabase**: `service_client`.
- **Request**: `ImportStockRequest { stock: list[ImportStockRow] }`.
- **Response**: `ImportStockResultado { upserted, no_encontrados }`.
- **Archivo**: `router.py:49-55`.

## `POST /imports/proveedores`

- **Quién puede llamarlo**: `_ROLES_IMPORT`.
- **Función**: `importar_proveedores_endpoint` → `importar_proveedores_para_endpoint` →
  `importar_proveedores`. Aplica RN-IMPORTS-002, RN-IMPORTS-008, RN-IMPORTS-011,
  RN-IMPORTS-012.
- **Cliente Supabase**: `service_client`.
- **Request**: `ImportProveedoresRequest { proveedores: list[ImportProveedorRow] }`.
- **Response**: `ImportProveedoresResultado { creados, actualizados, desactivados,
  sin_codigo_interno }`.
- **Archivo**: `router.py:58-66`.

## `POST /imports/clientes`

- **Quién puede llamarlo**: `_ROLES_IMPORT`.
- **Función**: `importar_clientes_endpoint` → `importar_clientes_para_endpoint` →
  `importar_clientes`. Aplica RN-IMPORTS-003, RN-IMPORTS-007, RN-IMPORTS-012.
- **Cliente Supabase**: `service_client`.
- **Request**: `ImportClientesRequest { clientes: list[ImportClienteRow] }`.
- **Response**: `ImportClientesResultado { creados, actualizados, desactivados }`.
- **Archivo**: `router.py:69-75`.

## Quién dispara una importación: sin evidencia de consumidor en este repositorio

Se buscó explícitamente en esta sesión:

- **`scripts/`**: no existe ese directorio en el repositorio (confirmado con `Glob`).
- **`frontend/`**: un grep de rutas `/imports/*` y de nombres de función
  (`importarProductos`, `importarCostos`, `importarStock`, `importarProveedores`,
  `importarClientes`) sobre `frontend/src/lib/api/presupuestacion.ts` — el archivo
  donde el frontend define sus llamadas al backend de presupuestación — no encontró
  ninguna coincidencia.
- Un grep más amplio de `/imports` sobre todo el repositorio solo encontró
  coincidencias en los propios archivos de este módulo, sus tests y la documentación
  de otros módulos que lo mencionan como hallazgo cruzado (`catalogo/`, `clientes/`).

**Conclusión**: los 5 endpoints existen y están montados en `main.py`, pero no hay
ningún consumidor identificable dentro de este repositorio — ni un script batch, ni una
pantalla de frontend, ni un cron. La forma de uso real (¿un sistema externo llama a
estos endpoints directo por HTTP con una API key de servicio? ¿un proceso manual vía
Postman/curl que corre alguien de operaciones? ¿una integración pendiente de
construirse?) queda como **pendiente de definición funcional** — no verificable desde
el código de este repositorio. Ver [`pendientes.md`](./pendientes.md) P3.
