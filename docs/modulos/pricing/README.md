# Módulo Pricing — `services/presupuestacion/pricing/`

## Qué es

Pricing es el motor de cálculo de precio de venta por ítem de un proceso comercial
(cotización o licitación) y el generador/regenerador del presupuesto asociado. Para
cada ítem con producto identificado, resuelve un costo (especial o estándar), le
aplica una regla de margen (`reglas_pricing`) y decide el precio final entre precio de
mercado (con descuento) y un piso de margen mínimo, con fallback a un margen objetivo
si no hay dato de mercado.

El módulo tiene 4 archivos con código (`__init__.py` vacío), 590 líneas en total
(`models.py` 46, `repository.py` 167, `service.py` 329, `router.py` 48 — verificado
leyendo cada archivo completo en esta sesión), 2 endpoints, 7 tests de integración.

## Qué NO hace

- **No gestiona el ciclo de vida del presupuesto después de generado.** Pricing
  inserta la fila de `presupuestos` en estado `"generado"` (`service.py:258`) y sus
  `presupuesto_items`; todo lo que viene después —revisión, ajuste manual de ítems,
  aprobación, presentación al cliente, compromiso de stock al presentar— lo hace
  `services/presupuestacion/presupuestos/`, un módulo ya existente en el código
  (`presupuestos/service.py`, `presupuestos/router.py`) pero **aún sin documentación
  formal en `docs/modulos/`** — se documentará como próximo módulo. Ver
  [`arquitectura.md`](./arquitectura.md) para el detalle exacto de dónde termina la
  responsabilidad de uno y empieza la del otro, incluyendo un caso concreto donde
  ambos recalculan de forma independiente los mismos campos derivados
  (`monto_total`, `items_sin_precio`) con criterios distintos.
- **No expone CRUD para `reglas_pricing` ni `precios_proveedor`.** Confirmado por
  grep exhaustivo en esta sesión sobre todo `services/presupuestacion/`: las únicas
  operaciones sobre estas dos tablas en todo el backend son las 3 lecturas de
  `pricing/repository.py` (`buscar_regla_aplicable`, `buscar_precio_especial_puntual`,
  `buscar_precio_especial_general`) — ningún módulo inserta, actualiza ni elimina
  filas de ninguna de las dos. Ver [`pendientes.md`](./pendientes.md) P1.
- **No lee `productos`/`costos_productos`/`stock_productos` a través de
  `catalogo.service` ni `catalogo.repository`.** Construye sus propias queries
  Supabase directo sobre esas 3 tablas — mismo patrón de acoplamiento de tabla ya
  documentado para `matching/`, `comparativas/` e `imports/` en
  [`../catalogo/arquitectura.md`](../catalogo/arquitectura.md), que ya menciona a
  `pricing/` como uno de los 5 consumidores.
- **No tiene `estados.md`.** `metodo_precio` (`Literal["mercado", "piso_margen",
  "margen_objetivo", "sin_precio"]`, `models.py:8`) es la clasificación del resultado
  de un cálculo puntual — no hay transiciones reguladas entre sus 4 valores, ni un
  campo que se actualice de un valor a otro con guardas: cada corrida de
  `calcular_item` produce un `metodo_precio` nuevo, independiente del anterior, y
  `generar_presupuesto` lo sobrescribe por completo en cada regeneración (borra e
  inserta de nuevo, ver [`reglas.md`](./reglas.md) RN-PRICING-008). Mismo criterio de
  omisión ya aplicado en Core, Catálogo, Usuarios y Clientes. La máquina de estados
  real del presupuesto (`generado → en_revision → aprobado → presentado → ...`) es
  responsabilidad de `presupuestos/`, no de este módulo.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `pricing/__init__.py` | Vacío. |
| `pricing/models.py` | 2 `Literal` (`OrigenCosto`, `MetodoPrecio`) y 4 modelos Pydantic: `DetalleCalculo`, `ResultadoPricingItem`, `ResultadoGenerarPresupuesto`. |
| `pricing/repository.py` | Acceso a datos puro, solo lectura, sobre 8 tablas/vistas: `precios_proveedor`, `costos_productos`, `reglas_pricing`, `v_precio_mercado_producto`, `stock_productos`, `productos`, `procesos_comerciales`, `presupuestos`, `items_proceso`. Recibe siempre un `Client` inyectado. Contiene `_alcance_or`, el helper de filtro dinámico con el riesgo de inyección analizado en [`pendientes.md`](./pendientes.md) P1. |
| `pricing/service.py` | Toda la lógica de negocio: `resolver_costo`, `calcular_precio`, `verificar_stock`, `calcular_item` (orquesta las tres anteriores para un ítem) y `generar_presupuesto` (orquesta `calcular_item` para todos los ítems de un proceso y escribe `presupuestos`/`presupuesto_items`). |
| `pricing/router.py` | 2 endpoints: `POST /procesos/{id}/generar-presupuesto` y `GET /precios-especiales`. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:21,42`
(`app.include_router(pricing_router, tags=["pricing"])`), sin prefijo adicional.
Ningún otro módulo de `presupuestacion/` **importa** código de `pricing/` como
paquete Python (confirmado por grep en esta sesión: los únicos imports de
`services.presupuestacion.pricing.*` están dentro del propio paquete y en
`main.py`). El detalle completo de consumidores está en
[`casos_de_uso.md`](./casos_de_uso.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, acoplamiento de
  tabla con Catálogo, y el solapamiento de responsabilidad con `presupuestos/`.
- [`base_de_datos.md`](./base_de_datos.md) — las 9 tablas/vistas tocadas, columnas y
  CRUD (todo lectura salvo `presupuestos`/`presupuesto_items`).
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-PRICING-NNN): la cascada de
  cálculo de precio completa.
- [`flujo.md`](./flujo.md) — flujo de `calcular_precio` para un ítem y de
  `generar_presupuesto` para un proceso comercial completo.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 2 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-PRICING-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3, con foco en el
  riesgo de `_alcance_or` y el solapamiento con `presupuestos/`.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client`, las excepciones
de dominio y el mecanismo de auditoría, ver [`../core/`](../core/) — no se repite esa
documentación acá.
