# Módulo Catálogo — `services/presupuestacion/catalogo/`

## Qué es

Catálogo gestiona el maestro de productos, categorías y proveedores de una droguería,
más el costo histórico de cada producto y el stock disponible por depósito. Es el
módulo dueño de las 5 tablas `productos`, `categorias`, `proveedores`,
`costos_productos` y `stock_productos`.

El módulo tiene 5 archivos, 801 líneas en total (`models.py` 134, `repository.py` 192,
`service.py` 259, `router.py` 216, `__init__.py` 0 — verificado leyendo cada archivo en
esta sesión), 12 endpoints, sin máquina de estados propia.

## Qué NO hace

- **No ejecuta auditoría.** Confirmado por grep en esta sesión: 0 referencias a
  `core.audit`, `registrar_cambio`, `registrar_cambios` o
  `registrar_evento_ciclo_vida` en los 4 archivos fuente. Ninguna mutación (alta/baja
  de producto o proveedor, edición de categoría, versionado de costo, ajuste de stock)
  queda registrada en `historial_cambios` — mismo hallazgo que en
  [`../clientes/`](../clientes/) y [`../usuarios/`](../usuarios/). Ver
  [`../core/`](../core/) para el mecanismo de auditoría que otros módulos sí usan, y
  [`pendientes.md`](./pendientes.md) P1.
- **No compromete stock.** `ajustar_stock` solo escribe `cantidad_disponible`; la
  columna `cantidad_comprometida` de `stock_productos` la mantiene exclusivamente el
  motor de compromiso de `core/stock.py` — comentario explícito en el código, ver
  RN-CATALOGO-010 en [`reglas.md`](./reglas.md). Para el detalle de ese motor
  (optimistic locking, liberar/comprometer/descontar), ver [`../core/`](../core/).
- **No gestiona la baja de categorías.** `categorias` no tiene soft-delete ni
  operación de borrado en `repository.py`, y `router.py` no expone
  `DELETE /categorias/{id}` — confirmado por grep en esta sesión. Ver
  RN-CATALOGO-004 en [`reglas.md`](./reglas.md) y D-CATALOGO-005 en
  [`decisiones.md`](./decisiones.md).
- **No tiene `estados.md`.** No hay una máquina de estados: los campos `activo`
  (productos, proveedores) y `activa` (categorías) son booleanos de negocio sin
  transiciones reguladas por este módulo — se pueden reactivar manualmente vía
  `PATCH` sin ninguna guarda. La vigencia de un costo se resuelve con
  `fecha_hasta IS NULL`, no con un enum de estados. Mismo criterio de omisión ya
  aplicado en Core, Usuarios y Clientes.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `catalogo/__init__.py` | Vacío. |
| `catalogo/models.py` | 2 `Literal` (`Clasificacion`, `TipoProveedor`) y modelos Pydantic `Create`/`Update`/`Out` para Producto, Categoria, Proveedor, Costo y Stock. |
| `catalogo/repository.py` | Acceso a datos puro sobre las 5 tablas, recibe siempre un `Client` inyectado. Único archivo del módulo con un import cruzado hacia otro paquete de negocio: `DEPOSITO_SENTINEL` de `services/presupuestacion/imports/service.py`. |
| `catalogo/service.py` | Reglas de negocio (tenant isolation, actualización parcial, versionado de costo, ajuste de stock) más 12 pares de wrappers `*_para_endpoint` que fijan `get_service_client()`. |
| `catalogo/router.py` | 12 endpoints HTTP, con roles en 4 constantes (`_ROLES_LECTURA_CATALOGO`, `_ROLES_ESCRITURA_CATALOGO`, `_ROLES_ESCRITURA_CATEGORIAS`, `_ROLES_LECTURA_COSTOS`) más una excepción hardcodeada para los 2 `DELETE`. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:51`
(`app.include_router(catalogo_router, tags=["catalogo"])`), sin prefijo adicional.
Ningún otro módulo de `presupuestacion/` **importa** código de `catalogo/` como
paquete Python (confirmado por grep en esta sesión: 0 resultados fuera del propio
paquete y de `main.py`).

Sin embargo, es el módulo con más acoplamiento a nivel de tabla documentado hasta
ahora en este proyecto: **5 módulos** leen o escriben directo sobre las mismas 5
tablas, sin pasar por este código — `matching/`, `comparativas/`, `pricing/`,
`core/stock.py` e `imports/`. Ver [`arquitectura.md`](./arquitectura.md) para el
detalle completo con evidencia de línea, incluyendo un caso más grave que el
documentado en [`../clientes/arquitectura.md`](../clientes/arquitectura.md): la
misma regla de negocio de versionado de costo (RN-CATALOGO-006) está reimplementada
de forma independiente en `imports/service.py`.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, el acoplamiento
  hacia `imports/service.py` (`DEPOSITO_SENTINEL`), y el diagrama del acoplamiento de
  tabla con los 5 módulos consumidores.
- [`base_de_datos.md`](./base_de_datos.md) — las 5 tablas, columnas, CRUD y quién más
  las toca.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-CATALOGO-NNN).
- [`flujo.md`](./flujo.md) — los 6 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 12 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-CATALOGO-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client`, las excepciones
de dominio y el mecanismo de auditoría que este módulo NO usa, ver
[`../core/`](../core/) — no se repite esa documentación acá. Para un caso más chico
del mismo patrón de acoplamiento de tabla, ver
[`../clientes/arquitectura.md`](../clientes/arquitectura.md).
