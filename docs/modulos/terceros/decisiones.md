# Decisiones de diseño — Terceros

Numeración D-TERCEROS-NNN. Corresponde 1:1 con las decisiones D1-D6 de
`openspec/changes/terceros-modelo/design.md`; se referencian con su letra original
entre paréntesis para poder cruzar contra ese documento.

### D-TERCEROS-001 (D1) — `codigo_interno` se muda a `terceros`; la idempotencia del import se ancla en `terceros_legacy_map`

- **Decisión**: `terceros.codigo_interno` es el único código interno nativo; el import
  legado por CSV no se identifica por ese campo sino por
  `terceros_legacy_map (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy)`.
- **Motivo**: mantener `codigo_interno` como clave de import habría fusionado dos
  empresas distintas si el CSV de clientes y el de proveedores del sistema legado
  usaban el mismo código para entidades distintas — los dos espacios de códigos
  legados son independientes.
- **Ventajas**: reimportar el mismo CSV es idempotente por construcción
  (`terceros_legacy_map` + RPC `upsert_terceros_legacy`, un lote por llamada); un
  tercero creado nativamente puede ser alcanzado más tarde por el import sin
  duplicarse, si comparte CUIT con la fila importada.
- **Desventajas / defecto encontrado en Fase 9**: `terceros.uq_terceros_codigo` es
  `UNIQUE(drogueria_id, codigo_interno)` **sin** componente de `entidad_legacy`. El RPC
  solo desambigua colisiones vía `terceros_legacy_map` (por entidad) o CUIT — nunca por
  `codigo_interno`. Si dos empresas *distintas* (sin CUIT en común) comparten el mismo
  `codigo_legacy` en el CSV de clientes y en el de proveedores, el segundo `INSERT` en
  `terceros` viola `uq_terceros_codigo` y el RPC entero falla, en vez de crear dos
  terceros distintos como exige esta misma decisión. Test de regresión (`xfail` a
  propósito, documentado en el propio test):
  `tests/imports/test_service.py::test_codigo_legacy_colisiona_entre_cliente_y_proveedor_produce_dos_terceros_distintos`.
  Requiere una migración de seguimiento fuera del alcance de este change.
- **Defecto adicional encontrado y corregido en Fase 9**: el RPC tal como quedó
  aplicado en la migración 0008 rompía con
  `column reference "codigo_legacy" is ambiguous` en **toda** llamada, porque
  `RETURNS TABLE (codigo_legacy TEXT, ...)` crea un parámetro `OUT` que colisiona sin
  calificar con `terceros_legacy_map.codigo_legacy` dentro del `ON CONFLICT (...)` de
  ese `INSERT`. Corregido en
  `supabase/migrations/0009_fix_upsert_terceros_legacy_ambiguous_column.sql`
  (`#variable_conflict use_column`); ver el comentario de ese archivo para el análisis
  completo. **Esta migración debe aplicarse a la base de test antes de poder confirmar
  en verde el resto de los tests de `tests/imports/test_service.py`.**
- **Contrato cruzado**: el change `orden-compra` resolvía el cliente por
  `clientes.codigo_interno`; tras esta migración esa columna vive en `terceros`. Ver
  `openspec/changes/orden-compra/HANDOFF-terceros-modelo.md`.
- **Fix del defecto de `uq_terceros_codigo`** (post-verify, Fase 12): corregido en
  `supabase/migrations/0010_fix_terceros_codigo_interno_import_collision.sql`. El paso 3
  (alta) de `upsert_terceros_legacy` ahora verifica, antes del `INSERT INTO terceros`, si
  `codigo_interno = fila->>'codigo_legacy'` ya existe para OTRO tercero en esa
  `drogueria_id`; si es así, inserta con `codigo_interno = NULL` en vez de fallar
  `uq_terceros_codigo` (la constraint ya tolera NULL). El alta nativa vía `crear_tercero()`
  puede setear `codigo_interno` a mano más adelante si hace falta desambiguar. Sin cambio
  de DDL — `CREATE OR REPLACE FUNCTION`, mismo patrón que la migración 0009. **Resuelto**: el
  orquestador aplicó la migración 0010 contra la base de test (`grnamollopxdlstcpxhc`) vía
  `mcp__supabase__apply_migration`, la verificó con una llamada de prueba envuelta en
  `BEGIN;...ROLLBACK;` (dos empresas sin CUIT compartido, mismo `codigo_legacy`, produjeron dos
  `terceros` distintos — uno con `codigo_interno` seteado, el otro `NULL`), y quitó el
  `xfail(strict=True)` de
  `tests/imports/test_service.py::test_codigo_legacy_colisiona_entre_cliente_y_proveedor_produce_dos_terceros_distintos`
  (cuya propia aserción también hubo que corregir: filtraba por `codigo_interno` compartido
  esperando 2 filas, pero el fix deja `NULL` en la segunda a propósito — ahora identifica ambos
  terceros por `razon_social` y verifica el par de `codigo_interno` como
  `{codigo_compartido, None}`). `pytest tests/imports/ tests/terceros/` → 72 passed, 0 xfailed.

### D-TERCEROS-002 (D2) — Submódulos por subdominio, no paquete plano

- **Decisión**: `services/terceros/` se divide en `identidad/`, `catalogos/`,
  `direcciones/`, `contactos/`, cada uno con su propio `models.py`/`repository.py`/
  `service.py`/`router.py`.
- **Motivo**: `services/presupuestacion/catalogo/` es la evidencia en contra del
  paquete plano — acumulaba productos, categorías, costos, stock y proveedores en un
  solo `service.py` de 24 funciones (`D-CATALOGO-001`), al punto de que `proveedores`
  quedó sepultado en un módulo llamado "catálogo". `services/terceros/` gobierna 8
  tablas y 4 raíces de agregado; en plano repetiría exactamente ese defecto.
- **Ventajas**: cada subdominio es testeable y navegable de forma aislada; el aggregator
  (`terceros/router.py`, `terceros/api.py`) es la única pieza que conoce a los 4.
- **Desventajas**: más archivos (16 en total para los 4 subdominios) que un único
  `service.py` — trade-off aceptado explícitamente en `design.md`.

### D-TERCEROS-003 (D3) — Un único patrón de error, invocado una sola vez en la capa de servicio

- **Decisión**: `services/terceros/errors.py::asegurar_tercero_de_la_drogueria(...)` es
  el único guard de tenant/rol del módulo, invocado una sola vez por operación y
  siempre desde `service.py` — nunca desde `router.py`.
- **Motivo**: no replicar la deuda ya documentada en
  [`../clientes/decisiones.md`](../clientes/decisiones.md) D-CLIENTES-004, donde la
  misma situación de fondo ("el recurso es de otra droguería") producía tres
  resultados HTTP distintos (404/422/403) según qué capa la detectara primero.
- **Regla fija**: fila inexistente o de otra droguería (sin ser `superadmin`) →
  `NotFoundError` (404); rol insuficiente en la misma droguería → `ForbiddenError`
  (403); input inválido o regla de negocio violada → `ValidationError` (422);
  violación de unicidad → `ConflictError` (409).
- **Ventajas**: un cliente de la API obtiene siempre el mismo status HTTP para el mismo
  escenario, sin importar qué subdominio lo detecte. Además corrigió, de paso, el
  propio D-CLIENTES-004 en la Fase 8: `services/presupuestacion/clientes/service.py`
  ahora enruta todo a través de `services.terceros.api`, que siempre lanza
  `NotFoundError` — el `ValidationError`/`ForbiddenError` inconsistente que documentaba
  D-CLIENTES-004 dejó de existir para los casos que ya pasan por la fachada.
- **Desventajas**: ninguna identificada — es la corrección deliberada de una deuda ya
  señalada, no un trade-off nuevo.

### D-TERCEROS-004 (D4) — `activo` con semántica real y obligatoria

- **Decisión**: toda tabla nueva que lleve `activo` cumple 4 reglas fijas: (1) todo
  `listar_*` acepta `activo: bool | None` y lo aplica como filtro, con `True` por
  defecto en la capa de servicio; (2) existe baja lógica (`PATCH .../{id}` con
  `activo=false`), nunca `DELETE` físico de sub-recursos (excepción documentada:
  `tercero_direcciones`, ver [`README.md`](./README.md)); (3) los índices únicos
  parciales ignoran filas inactivas (`WHERE es_principal AND activo`); (4) toda tabla
  con `activo` tiene un test que confirma que una fila desactivada desaparece del
  listado por defecto — sin ese test, la columna no se agrega.
- **Motivo**: corregir la deuda ya documentada para `cliente_contactos.activo` en
  [`../clientes/README.md`](../clientes/README.md) — un campo escribible y expuesto que
  ningún query filtraba.
- **Ventajas**: un contacto o dirección dado de baja nunca se filtra hacia
  presupuestación por accidente; `deleted_at`/`deleted_by` (soft-delete auditado)
  quedan reservados solo para `terceros`, la raíz — los hijos se retiran con `activo`.
- **Desventajas**: `tercero_direcciones` es la única tabla con `activo` sin un test
  D4 dedicado (ver `openspec/changes/terceros-modelo/tasks.md`, aprendizaje 11) —
  `eliminar_direccion` hace `DELETE` físico en su lugar, siguiendo el requisito de
  `terceros-direcciones/spec.md`.
- **Regla de cascada agregada post-`sdd-verify`**: la redacción original de D4 arriba
  solo exigía que cada `listar_*` filtrara por `activo` *de su propia tabla*. Nunca
  declaró que desactivar el `tercero` raíz también debía ocultarlo de
  `listar_clientes_con_tercero`/`listar_proveedores_con_tercero`, aunque la fila de
  rol siguiera con su propio `activo=true` — un desacople spec/diseño (la spec
  `terceros-identidad` sí exige esto en su escenario "Deactivation semantics apply
  consistently") que `sdd-verify` detectó como hallazgo CRITICAL (ver
  `openspec/changes/terceros-modelo/verify-report.md`). Regla D4 corregida: **(5) toda
  tabla de rol embebida junto a `terceros` (`clientes`, `proveedores`) filtra por
  `activo` propio Y por `terceros.activo`** — implementado en
  `services/terceros/identidad/repository.py` (`listar_clientes_con_tercero`/
  `listar_proveedores_con_tercero`) usando el embed `terceros!inner(*)` de PostgREST
  (join real, no el LEFT JOIN implícito por defecto) más
  `.eq("terceros.activo", activo)`. Ver `tasks.md` 3.16.

### D-TERCEROS-005 (D5) — Frontera de consumo: fachada unidireccional `services/terceros/api.py`

- **Decisión**: `services/presupuestacion/**` importa **exclusivamente**
  `services.terceros.api`, nunca un `repository`/`service` interno de un subdominio.
  `services/terceros/**` nunca importa `services.presupuestacion`.
- **Motivo**: evitar un ciclo de imports y mantener `services/terceros/` reusable por
  cualquier otro servicio futuro (no solo `presupuestacion`) sin arrastrar su núcleo.
- **Ventajas**: `services/shared/{config,database,exceptions,auth}.py` (extraídos de
  `services/presupuestacion/core/`, Fase 2 y aprendizaje 6 de `tasks.md`) permiten que
  `services/terceros/` no dependa de `presupuestacion/core/` en absoluto, con **cero**
  cambios en los ~20 módulos que ya importaban esos archivos (quedaron como shims de
  reexport).
- **Excepción documentada**: `services/presupuestacion/imports/repository.py` invoca
  el RPC `upsert_terceros_legacy` directo vía `client.rpc(...)`, sin pasar por
  `services.terceros.api`. No viola D5: el RPC vive en la base de datos, no es un
  módulo Python bajo `services/terceros/`, así que no hay ciclo de imports posible —
  `services/terceros/` ni siquiera sabe que ese RPC existe.
- **Guard automatizado**: `tests/terceros/test_dependencias.py` (`ast` sobre el árbol),
  verificado en verde en la Fase 7 y re-confirmado en la Fase 10 (10.1).

### D-TERCEROS-006 (D6) — Sin vistas de compatibilidad nuevas; las vistas existentes se recrean con `security_invoker`

- **Decisión**: no se crea ninguna vista de lectura de compatibilidad con el esquema
  plano anterior. Las 9 vistas preexistentes que dependían de columnas eliminadas
  (`clientes.nombre`, `proveedores.razon_social`, etc.) se recrean con
  `WITH (security_invoker = true)` — antes no lo declaraban y evadían RLS.
- **Motivo**: la migración es la oportunidad de corregir esa evasión de RLS de paso,
  no solo de resolver la dependencia de columnas.
- **Ventajas**: las 9 vistas ahora respetan RLS con los permisos de quien consulta, no
  con los del dueño de la vista.
- **Desventajas**: ninguna identificada — el guard `M0` (versión de Postgres ≥ 15,
  requerida por `security_invoker`) confirmó al aplicarse en Fase 1 que el proyecto de
  test cumple el mínimo (ver [`base_de_datos.md`](./base_de_datos.md)).
