# Base de datos — Terceros

Terceros es el módulo dueño de 6 tablas propias, y comparte `clientes`/`proveedores`
(angostas, rol únicamente) con `services/presupuestacion/`. Las 8 tablas nacen todas en
`supabase/migrations/0008_terceros_modelo.sql`; ver ese archivo para el DDL completo y
`openspec/changes/terceros-modelo/design.md` sección "Interfaces / Contracts — DDL"
para el contrato documentado.

## `terceros`

La raíz de identidad. `codigo_interno`, `razon_social`, `nombre_fantasia`, `cuit`,
`email`, `telefono`, `sitio_web`, `notas`, `activo`. Únicos que llevan
`deleted_at`/`deleted_by` (soft-delete auditado) en todo el módulo — D4.

- `uq_terceros_codigo` — `UNIQUE(drogueria_id, codigo_interno)`. Sin componente de
  `entidad_legacy`; ver D-TERCEROS-001 para el defecto que esto produce en el import
  legado cuando dos entidades distintas comparten `codigo_legacy`.
- `uq_terceros_cuit` — índice único parcial `(drogueria_id, cuit) WHERE cuit IS NOT NULL
  AND deleted_at IS NULL`. Es la clave que usa el RPC de import para vincular una
  empresa ya cargada bajo un rol con la misma empresa apareciendo bajo el otro rol.

## `terceros_legacy_map`

Trazabilidad del import legado. `tercero_id`, `sistema_origen`, `entidad_legacy`
(`'cliente' | 'proveedor'`), `codigo_legacy`, `datos_legacy` (JSONB, la fila cruda del
CSV). `uq_tlm_codigo` — `UNIQUE(drogueria_id, sistema_origen, entidad_legacy,
codigo_legacy)` — es la clave real de idempotencia del import (D1), no
`terceros.codigo_interno`. `ON DELETE CASCADE` desde `terceros`.

## `clientes` / `proveedores` (rol, compartidas con `presupuestacion/clientes` y `catalogo`)

Tras la migración, angostas: solo `id` (PK + FK compuesta a `terceros(id,
drogueria_id)`), `drogueria_id`, `tipo`, `condicion_pago_id`, `forma_pago_id`,
`activo` (+ para `proveedores`: `es_competidor`, `es_proveedor_compra`), auditoría.
Perdieron `nombre`/`razon_social`, `direccion`/`ciudad`/`provincia`/`codigo_postal`,
`plazo_pago_dias`/`condiciones_pago` (texto libre) y `codigo_interno` — ver
[`../clientes/base_de_datos.md`](../clientes/base_de_datos.md) y
[`../catalogo/base_de_datos.md`](../catalogo/base_de_datos.md).

## `sectores_contacto`, `condiciones_pago`, `formas_pago`

Catálogos por droguería (`terceros/catalogos/`). `condiciones_pago.plazos_dias` es
`SMALLINT[]` — reemplaza el `plazo_pago_dias INTEGER` anterior: un pago en cuotas se
expresa como `{30,60,90}`, uno de plazo único como `{30}`.

## `tercero_direcciones` / `direccion_usos`

`terceros/direcciones/`. Relación N:M entre una dirección y sus usos
(`'facturacion' | 'entrega' | 'documentacion' | 'otra'`) vía `direccion_usos`.
`uq_du_principal` — índice único parcial `(tercero_id, uso) WHERE es_principal` —
garantiza como máximo una dirección principal por uso y por tercero a nivel de base.
Única tabla del módulo con `activo` sin baja lógica expuesta por API: `eliminar_direccion`
hace `DELETE` físico (cascadea a `direccion_usos`), ver D-TERCEROS-004.

## `terceros_contactos`

`terceros/contactos/`. `nombre`, `apellido`, `sector_id` (FK a `sectores_contacto`),
`cargo`, `email`, `telefono`, `celular`, `es_principal`, `notas`, `activo`.
`uq_tc_principal` — índice único parcial `(tercero_id) WHERE es_principal AND activo` —
un segundo contacto marcado `es_principal=true` desplaza automáticamente al anterior
(a diferencia de `direccion_usos`, que rechaza el conflicto con `ConflictError` — ver
`terceros/direcciones/service.py` y `terceros/contactos/service.py` para la
justificación de por qué cada tabla resuelve el conflicto distinto).

## RLS y versión de Postgres

Las 8 tablas llevan el conjunto unión de roles de escritura de `clientes` y
`proveedores` (`admin`, `gerencia`, `lider_comercial`, `comercial`, `compras`) — un
tercero puede cumplir ambos roles, restringir a uno solo bloquearía al otro. `DELETE`
reservado a `superadmin()`. El guard `M0` de la migración exige
`server_version_num >= 150000` (requerido por `WITH (security_invoker = true)`, D6): la
migración 0008 se aplicó con éxito contra el proyecto de test
(`grnamollopxdlstcpxhc`), lo que confirma indirectamente que ese proyecto corre
Postgres ≥ 15 — el guard habría abortado la migración entera de no ser así, cerrando
la pregunta abierta que design.md dejaba pendiente por falta de acceso directo al MCP
de Supabase en esa sesión.

## RPC `upsert_terceros_legacy`

Ver `services/presupuestacion/imports/`
([`docs/modulos/terceros/decisiones.md`](./decisiones.md) D-TERCEROS-001) y
`supabase/migrations/0008_terceros_modelo.sql` / `0009_fix_upsert_terceros_legacy_ambiguous_column.sql`
para el contrato completo y el fix aplicado en Fase 9.
