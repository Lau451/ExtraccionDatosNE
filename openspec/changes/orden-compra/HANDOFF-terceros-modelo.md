# Handoff: `terceros-modelo` → `orden-compra`

`terceros-modelo` se aplicó y mergeó **antes** que `orden-compra` (design.md,
`openspec/changes/terceros-modelo/design.md`, D1: "Secuenciación"). Este documento
resume qué cambió que afecta directamente a `orden-compra`, que a la fecha de este
handoff todavía no está commiteado. **No se modificó ningún archivo de
`orden-compra/` — solo se deja esta nota.**

## 1. `clientes.codigo_interno` se mudó a `terceros.codigo_interno`

`orden-compra/proposal.md` y `specs/orden-compra-validacion/spec.md` (requirement
"Anclaje a cliente por `codigo_interno`") asumen que el lookup de cliente por
`codigo_interno` se hace directo contra `clientes`, y que
`uq_cli_codigo UNIQUE (drogueria_id, codigo_interno)` vive en esa tabla.

Ambas cosas cambiaron:

- `codigo_interno` ya no existe en `clientes` — vive en `terceros.codigo_interno`, con
  `uq_terceros_codigo UNIQUE (drogueria_id, codigo_interno)` (mismo nombre de
  restricción semántica, tabla distinta).
- `clientes` es ahora una tabla de **rol** angosta: `id` (PK + FK compuesta a
  `terceros(id, drogueria_id)`), `drogueria_id`, `tipo`, `condicion_pago_id`,
  `forma_pago_id`, `activo`, auditoría. No tiene `nombre` ni `codigo_interno`.

**Ajuste requerido en `orden-compra`**: el lookup por `codigo_interno` (requirement
"Anclaje a cliente por `codigo_interno`", `specs/orden-compra-validacion/spec.md:10-27`)
debe resolver contra `terceros` (`WHERE codigo_interno = ...`) y **luego verificar que
ese tercero tiene una fila activa en `clientes`** (el rol cliente) — no alcanza con que
exista el tercero, tiene que tener el rol asignado y activo. El escenario
"`codigo_interno` ambiguo" del spec (`clientes.codigo_interno` sin restricción de
unicidad) queda obsoleto tal como está escrito: la restricción de unicidad SÍ existe,
pero está en `terceros`, no en `clientes` — revisar si ese escenario sigue teniendo
sentido de negocio (¿puede un `codigo_interno` de `terceros` mapear a más de un
`cliente_id`? No, porque `clientes.id` = `terceros.id` 1:1) o si debe eliminarse.

Vía de acceso recomendada: `services.terceros.api.obtener_cliente_con_tercero` /
`listar_clientes_con_tercero` (`services/terceros/api.py`) ya devuelven el embed
`clientes.select("*, terceros(*)")` — evita reimplementar el join a mano. Ver
`services/presupuestacion/clientes/service.py` para el patrón de uso.

## 2. `cliente_contactos` ya no existe — es `terceros_contactos`

Si `orden-compra` llega a necesitar contactos de cliente (no se detectó una referencia
explícita en `proposal.md`/`specs/` a la fecha de este handoff, pero se deja
documentado por si surge durante la implementación): la tabla es `terceros_contactos`,
compartida entre `clientes` y `proveedores` (columna `tercero_id`, no `cliente_id`).
Acceso recomendado: `services.terceros.api.listar_contactos`/`obtener_contacto` con
`tercero_id=cliente_id`.

## 3. `services/presupuestacion/imports/` cambió de contrato (relevante para `entregas-import`)

`orden-compra/specs/entregas-import/spec.md` importa entregas por CSV. No toca
`clientes`/`proveedores` directamente según lo revisado en este handoff, pero si llega
a necesitar resolver un cliente por su código legado durante esa importación: el
import de clientes/proveedores (`services/presupuestacion/imports/service.py`,
`importar_clientes`/`importar_proveedores`) ya no hace upsert directo contra
`clientes`/`proveedores` — llama al RPC `upsert_terceros_legacy`
(`supabase/migrations/0008_terceros_modelo.sql` M10,
`0009_fix_upsert_terceros_legacy_ambiguous_column.sql` para un fix aplicado en esa
misma fase). `ImportClienteRow`/`ImportProveedorRow` (`imports/models.py`) también
cambiaron de forma: `codigo_interno` es obligatorio para ambos (antes opcional para
proveedores), `nombre` se renombró a `razon_social`, y se eliminaron
`direccion`/`ciudad`/`provincia`/`codigo_postal`/`plazo_pago_dias`/`condiciones_pago`
(fuera del contrato del RPC).

## 4. Defecto conocido, pendiente de una migración de seguimiento

`terceros.uq_terceros_codigo` es `UNIQUE(drogueria_id, codigo_interno)` sin componente
de origen/entidad. Si dos empresas *distintas* llegan a compartir el mismo
`codigo_interno` por casualidad (p. ej. un `codigo_interno` asignado a mano en
`orden-compra` que coincide con uno ya usado por `terceros-modelo`), la escritura
falla con violación de unicidad en vez de un error de negocio más claro. No debería
afectar el flujo normal de `orden-compra` (que consulta, no crea terceros), pero queda
documentado por si `orden-compra` llega a crear terceros nuevos. Ver
`openspec/changes/terceros-modelo/docs...` → `docs/modulos/terceros/decisiones.md`
D-TERCEROS-001 para el detalle completo y el test de regresión asociado
(`tests/imports/test_service.py::test_codigo_legacy_colisiona_entre_cliente_y_proveedor_produce_dos_terceros_distintos`,
`xfail` a propósito).

## Dónde mirar

- `openspec/changes/terceros-modelo/design.md` — diseño completo, decisiones D1-D6.
- `docs/modulos/terceros/` — documentación del módulo nuevo.
- `docs/modulos/clientes/decisiones.md`, `docs/modulos/catalogo/decisiones.md` —
  notas de actualización agregadas en esta misma fase, con el estado anterior/posterior
  a la migración.
- `services/terceros/api.py` — fachada única para leer/escribir identidad, roles,
  direcciones y contactos desde cualquier módulo de `services/presupuestacion/`.
