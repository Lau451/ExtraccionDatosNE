# Módulo Presupuestos — `services/presupuestacion/presupuestos/`

## Qué es

Presupuestos gestiona el **ciclo de vida de un presupuesto ya generado**: su
transición de estado (aprobar, presentar), el ajuste manual de sus ítems (precio,
cantidad, exclusión) y el recálculo de los totales derivados que esos ajustes
disparan. Es el módulo que decide cuándo un presupuesto pasa de un borrador
calculado por el motor de pricing a un documento aprobado y, finalmente,
presentado al cliente — comprometiendo stock real en ese último paso si
corresponde.

El módulo tiene 4 archivos con código (`__init__.py` vacío), 534 líneas en total
(`models.py` 36, `repository.py` 92, `service.py` 291, `router.py` 115 —
verificado leyendo cada archivo completo en esta sesión), 4 endpoints, **17 tests
de integración en 593 líneas** (`tests/presupuestos/test_service.py`) — el
archivo de test más grande de todo el proyecto a la fecha de esta sesión.

## Qué NO hace

- **No genera el presupuesto inicial.** El primer `INSERT` en `presupuestos`
  (estado `"generado"`) y la primera carga de `presupuesto_items` los hace
  `services/presupuestacion/pricing/` (`pricing/service.py:generar_presupuesto`,
  `:219-316`), documentado en [`../pricing/`](../pricing/). Presupuestos solo
  opera sobre presupuestos que ya existen: `buscar_presupuesto` (`repository.py:6-15`)
  devuelve `None` si no hay fila, y las tres funciones de negocio
  (`aprobar_presupuesto`, `ajustar_item`, `presentar_presupuesto`) levantan
  `NotFoundError` en ese caso (`service.py:96`, `:143`, `:185`) en vez de crear
  nada.
- **No recalcula el precio de un ítem.** `ajustar_item` sobrescribe
  `precio_unitario` con el valor que manda el usuario (`service.py:149`); no
  vuelve a correr `pricing.calcular_precio` ni ninguna cascada de costo/margen —
  solo recalcula `margen_resultante_pct` contra el `costo_usado` que ya tenía la
  fila (`service.py:153-157`). Ver [`reglas.md`](./reglas.md) RN-PRESUPUESTOS-009.
- **No define la máquina de estados nominal de `procesos_comerciales`.** Ese tipo
  (`Estado`, 8 valores) vive en `procesos_comerciales/models.py` y está
  documentado en [`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md).
  Presupuestos es, sin embargo, el **único módulo de todo el repositorio que
  escribe** la columna `procesos_comerciales.estado` — sin guarda de transición
  sobre el estado anterior del proceso. Ver la sección "Escritura cruzada" más
  abajo y [`estados.md`](./estados.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `presupuestos/__init__.py` | Vacío. |
| `presupuestos/models.py` | `EstadoPresupuesto` (`Literal` de 7 valores), `AjustarItemRequest` (body del `PATCH`) y dos modelos de salida: `ResultadoPresupuestoItem`, `ResultadoPresupuesto`. |
| `presupuestos/repository.py` | Acceso a datos puro sobre `presupuestos`, `presupuesto_items`, `procesos_comerciales` (lectura acotada + el único `UPDATE` de `estado` de todo el repositorio) y las dos vistas de lectura `v_presupuesto_comercial`/`v_presupuesto_revision`. Recibe siempre un `Client` inyectado. |
| `presupuestos/service.py` | Las 3 funciones de negocio (`aprobar_presupuesto`, `ajustar_item`, `presentar_presupuesto`) más `_recalcular_totales_presupuesto` (helper interno) y sus 3 wrappers `_para_endpoint` que resuelven `service_role`. Único módulo de `presupuestacion/`, junto con `compras/`, que importa `core/stock.py`. |
| `presupuestos/router.py` | 4 endpoints: `GET /presupuestos/{id}` (matriz de visibilidad por rol), `POST /presupuestos/{id}/aprobar`, `POST /presupuestos/{id}/presentar`, `PATCH /presupuesto-items/{id}`. Valida pertenencia a la droguería antes de delegar en cada uno de los 3 endpoints de escritura. |

## Escritura cruzada hacia `procesos_comerciales`

`presentar_presupuesto` (`service.py:180-255`), al comprometer stock y marcar el
presupuesto como `"presentado"`, también hace
`repo.actualizar_proceso_comercial(client, proceso_comercial_id=proceso["id"],
campos={"estado": "presentado"})` (`service.py:239-241`,
`repository.py:actualizar_proceso_comercial`, `:68-71`) — un `UPDATE` genérico sin
`SELECT FOR UPDATE` previo ni condición `WHERE estado=...`. Este es el mismo
hallazgo que [`../procesos_comerciales/estados.md`](../procesos_comerciales/estados.md)
y [`../procesos_comerciales/arquitectura.md`](../procesos_comerciales/arquitectura.md)
ya documentaron desde el otro lado — confirmado acá con la misma cita exacta
(`service.py:239-241`) y sin guarda sobre el estado anterior del proceso
comercial. Ver [`arquitectura.md`](./arquitectura.md) y
[`pendientes.md`](./pendientes.md) para el detalle desde este lado.

## Dependencias

- **Core** (`../core/`): `core/audit.py` (auditoría de todos los cambios de
  campo), `core/database.py` (`get_service_client`), `core/exceptions.py`
  (`ConflictError`, `NotFoundError`, `ValidationError`), `core/auth.py`
  (`UsuarioPerfil`, `require_roles`, solo en `router.py`), y **`core/stock.py`**
  (`comprometer_stock_producto`, `liberar_o_reportar`) — Presupuestos es una de
  las 2 únicas funciones de negocio de todo el repositorio que usa el motor de
  stock de Core, junto con `compras/`. Ver [`../core/flujo.md`](../core/flujo.md)
  Flujo A, ya documentado desde el lado de Core y confirmado desde este lado en
  [`arquitectura.md`](./arquitectura.md).
- **Pricing** (`../pricing/`): no hay import de código Python en ningún sentido
  entre ambos módulos — la relación es exclusivamente de tabla compartida
  (`presupuestos`, `presupuesto_items`). Pricing crea; Presupuestos gestiona el
  ciclo de vida posterior. Ya documentado desde el lado de Pricing en
  [`../pricing/arquitectura.md`](../pricing/arquitectura.md) ("Solapamiento de
  responsabilidad con `presupuestos/`"), confirmado desde este lado en
  [`arquitectura.md`](./arquitectura.md).
- **Procesos Comerciales** (`../procesos_comerciales/`): sin import de código
  Python; escritura cruzada de tabla, ver sección anterior.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core y Pricing, el
  patrón de dos vistas SQL por rol, la escritura cruzada hacia
  `procesos_comerciales.estado`.
- [`base_de_datos.md`](./base_de_datos.md) — tablas `presupuestos`,
  `presupuesto_items`, el `UPDATE` acotado de `procesos_comerciales`, y el uso
  indirecto de `stock_productos` vía `core/stock.py`.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-PRESUPUESTOS-NNN).
- [`flujo.md`](./flujo.md) — flujo de aprobación, presentación (con compromiso y
  reversión de stock) y ajuste manual de ítem.
- [`estados.md`](./estados.md) — la máquina de estados de `presupuestos.estado`,
  con las guardas de transición reales (a diferencia de
  [`../procesos_comerciales/`](../procesos_comerciales/), que no tiene ninguna).
- [`casos_de_uso.md`](./casos_de_uso.md) — los 4 endpoints, roles y la matriz de
  visibilidad por vista SQL.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-PRESUPUESTOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client`, las
excepciones de dominio, el mecanismo de auditoría y el motor de stock, ver
[`../core/`](../core/) — no se repite esa documentación acá.
