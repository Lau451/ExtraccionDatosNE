# Propuesta: Modelo de terceros

## Intent

`clientes` y `proveedores` son hoy dos tablas planas independientes con identidad duplicada (CUIT solo
en proveedores, `codigo_interno` en ambas) y sin forma de expresar que una misma empresa cumpla los dos
roles. Los contactos existen solo para clientes (`cliente_contactos`, un único campo `nombre`, sin
apellido ni sector); no hay direcciones ni forma de pago en el esquema, y la condición de pago es texto
libre más un entero suelto. Ambas tablas están vacías (0 filas, verificado contra la base real): es la
última ventana para reescribir el modelo sin backfill ni downtime. Además, estas entidades solo nacen
hoy por el import CSV del sistema legado; el sistema nuevo debe gestionarlas de forma nativa.

## Scope

### En alcance

- Reescritura en una sola migración: `terceros` (identidad) + `clientes`/`proveedores` como subtipos de
  rol con PK compartida (`id` = `tercero_id`).
- `tercero_direcciones` con usos N:M (facturación / entrega / documentación / otra).
- `terceros_contactos` generalizado, que reemplaza `cliente_contactos` y cubre también proveedores:
  nombre + apellido separados, `sector_id`, cargo, email, teléfono, celular, `es_principal`, `activo`.
- Catálogos por droguería: `sectores_contacto`, `condiciones_pago` (`plazos_dias smallint[]`),
  `formas_pago`, con FK "habitual" en `clientes` y `proveedores`.
- Baja de `plazo_pago_dias` (int) y `condiciones_pago` (texto) en ambas tablas de rol.
- CRUD nativo completo (models / repository / service / router) para todo lo anterior, siguiendo los
  patrones de `services/presupuestacion/clientes/` y `services/presupuestacion/catalogo/`.
- `terceros_legacy_map` para trazabilidad hacia el sistema legado.
- `services/presupuestacion/imports/` adaptado al nuevo esquema, preservando la idempotencia por
  `codigo_interno`.

### Fuera de alcance

- `ordenes_compra`, `oc_items`, `entregas_oc`, `entregas_oc_items` — propiedad del change paralelo
  `orden-compra`.
- Snapshot de condición y forma de pago *aplicada* a un documento — change futuro.
- `es_competidor` / `es_proveedor_compra`: se trasladan tal cual a la nueva `proveedores`, sin rediseño.
- El ETL del sistema legado más allá de mantener `imports/` funcionando.
- La deuda preexistente registrada en `docs/modulos/*/decisiones.md`.

## Capabilities

### Nuevas capacidades

- `terceros-identidad`: alta, edición, baja lógica de un tercero y asignación de roles cliente/proveedor.
- `terceros-direcciones`: direcciones de un tercero con asignación N:M de usos.
- `terceros-contactos`: contactos de cualquier tercero, con sector y contacto principal.
- `catalogos-comerciales`: CRUD por droguería de `sectores_contacto`, `condiciones_pago` y `formas_pago`.
- `terceros-legacy-import`: import CSV idempotente contra el nuevo esquema y mapa de trazabilidad legada.

### Capacidades modificadas

- Ninguna. `openspec/specs/` está vacío.

## Approach

Reescritura clean-slate (Approach 1 de la exploración), habilitada por el estado de 0 filas. Toda tabla
nueva conserva el patrón multi-tenant vigente: `drogueria_id` + `UNIQUE(id, drogueria_id)` + FK compuesta
`(x_id, drogueria_id) → tabla(id, drogueria_id)`, con RLS habilitada. La PK compartida mantiene válidas,
sin tocarlas, todas las FK existentes hacia `clientes.id` / `proveedores.id` (`procesos_comerciales`,
`cliente_producto_alias`, `cliente_observaciones`, `precios_proveedor`, `compras_proveedor`, `eventos`,
`ordenes_compra`).

Decisión de ubicación (post-proposal, confirmada por el usuario): terceros/direcciones/contactos/roles/
catálogos NO se anidan dentro de `services/presupuestacion/`. Nacen como módulo propio de nivel superior
`services/terceros/`, hermano de `services/presupuestacion/` y `services/extraccion/` — son datos maestros
compartidos, no una submateria de presupuestación. `services/presupuestacion/clientes/` y
`services/presupuestacion/catalogo/` dejan de ser dueños de esos datos y pasan a consumir
`services/terceros/` (vía import interno de Python, no HTTP) para lo que hoy resuelven solos. El desglose
interno de `services/terceros/` (submódulos por subdominio vs. paquete plano) queda para `sdd-design`.

Entrega acordada: `auto-chain`, con presupuesto de revisión de 1000 líneas cambiadas antes de forzar la
división en PRs. Secuenciación: este change se aplica antes de mergear `orden-compra`.

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `docs/schema/extractor_final.sql` | Modificado | 7 tablas nuevas; `clientes`/`proveedores` angostas con `id` FK a `terceros`; baja de `cliente_contactos` |
| `services/terceros/` | Nuevo | Módulo de nivel superior (hermano de `presupuestacion/`/`extraccion/`): CRUD de identidad, roles cliente/proveedor, direcciones, contactos y catálogos (`sectores_contacto`, `condiciones_pago`, `formas_pago`) |
| `services/presupuestacion/clientes/` | Modificado | Deja de ser dueño de identidad/contactos; consume `services/terceros/` para lo que hoy resuelve solo |
| `services/presupuestacion/catalogo/` | Modificado | Pierde `proveedores` (se muda a `services/terceros/`); no gana los catálogos nuevos, que viven en `services/terceros/` |
| `services/presupuestacion/imports/` | Modificado | Upsert dividido entre `terceros` y la tabla de rol, idempotencia preservada |
| `services/extraccion/routers/clientes.py` | Sin cambios | Lee `id, nombre`; ambas columnas sobreviven a la división |
| `tests/test_clientes_api.py`, `tests/catalogo/`, `tests/imports/` | Modificado | Hoy afirman la forma plana actual |

## Risks

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| `imports/` duplica filas de `terceros` al reejecutar un CSV | Media | Upsert por `(drogueria_id, codigo_interno)` sobre `terceros`; tests de idempotencia para clientes, proveedores y contactos (hoy inexistentes) |
| Colisión con el change `orden-compra`, sin commitear | Media | Sin solapamiento de DDL verificado; la PK compartida deja intacta `ordenes_compra.cliente_id`; aplicar `terceros-modelo` primero |
| Una vista de compatibilidad para lectura evadiría RLS | Baja | No se crean vistas; si design las requiere, `WITH (security_invoker = true)` y confirmar antes la versión de Postgres |
| El volumen de código supera el presupuesto de revisión | Alta | `auto-chain` con corte por capa: DDL + catálogos → terceros + roles → direcciones + contactos → imports |
| La deuda de `clientes/` (tres excepciones para el mismo chequeo de tenant, `activo` sin efecto) se copia a las tablas nuevas | Media | Design debe fijar un único patrón de error y semántica de `activo` antes de escribir código |

## Rollback Plan

1. La migración es una sola transacción; si falla, no deja estado parcial.
2. Después de aplicada, revertir consiste en `DROP` de las siete tablas nuevas y restaurar el snapshot
   DDL previo de `clientes`, `proveedores` y `cliente_contactos` desde git. Es seguro únicamente
   mientras las tablas nuevas sigan vacías.
3. Si ya se cargaron terceros de forma nativa, exportarlos antes del `DROP`: la reversión pierde
   direcciones, contactos y catálogos, que no tienen destino en el esquema plano.
4. El código se revierte por commit; ningún flujo existente lee las columnas nuevas.

## Dependencies

- El change `orden-compra` no debe mergearse antes que este; ambos tocan esquema adyacente a `clientes`.
- `docs/schema/extractor_final.sql` está desactualizado para `clientes` — la migración se escribe contra
  la base real verificada, no contra el snapshot.

## Success Criteria

- [ ] Una misma empresa existe como un solo `tercero` y cumple los roles cliente y proveedor a la vez.
- [ ] Alta, edición y baja de terceros, direcciones, contactos y catálogos por API, sin pasar por import.
- [ ] Una dirección declara varios usos simultáneos y se consulta por uso.
- [ ] Un contacto de proveedor se registra con sector, apellido y celular.
- [ ] `condiciones_pago` y `formas_pago` habituales se resuelven por FK; `plazo_pago_dias` ya no existe.
- [ ] Reejecutar el CSV legado no duplica filas en `terceros` ni en las tablas de rol.
- [ ] Toda tabla nueva tiene `drogueria_id`, `UNIQUE(id, drogueria_id)`, FK compuesta y RLS habilitada.
- [ ] Las FK preexistentes hacia `clientes.id` / `proveedores.id` siguen resolviendo sin modificación.
