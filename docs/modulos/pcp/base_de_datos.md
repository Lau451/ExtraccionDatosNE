# Base de datos — PCP

PCP es dueño de **9 tablas** nuevas, repartidas en dos migraciones, más una
columna FK agregada a una tabla existente. El proposal/design originales
decían "siete tablas nuevas" en su prosa, pero las decisiones D2-D9 nombran
nueve — `tasks.md` 1.2 reconcilió esa discrepancia contra el esquema en vivo
y trató las nueve como autoritativas antes de escribir cualquier DDL. Ver
`supabase/migrations/0011_pcp_modelo.sql` / `0012_pcp_extras.sql` /
`0013_pcp_notificacion_tipo.sql` para el DDL completo.

## PR1 — `0011_pcp_modelo.sql` (cuatro tablas más tempranas)

### `pcp`

El header. `presupuesto_id` FK a `presupuestos(id, drogueria_id)`,
`proceso_comercial_id` denormalizado (filtro de listado sin JOIN), `estado`
`CHECK IN ('nueva','en_gestion','esperando_respuesta','cerrada')` default
`nueva`, `fecha_entrega_solicitada DATE` (filtro primario del listado),
`solicitante_id`/`sector_id`, `origen CHECK IN ('manual','regla',
'import_legado')` (cómo se originó el PCP en sí — no confundir con el
`origen` de `pcp_renglones`, que es por renglón), `regla_pcp_id` (FK diferida
a `reglas_pcp`, ver M4b abajo), `cerrada_at`/`cerrada_por`.

- `uq_pcp_presupuesto_abierto` — índice único parcial `(presupuesto_id) WHERE
  estado <> 'cerrada'`: como máximo un PCP abierto por presupuesto (confirmado
  por el usuario). Permite reabrir con un PCP nuevo una vez que el anterior
  cerró.
- `idx_pcp_listado` — parcial `(drogueria_id, estado, fecha_entrega_solicitada)
  WHERE estado <> 'cerrada'`.

### `pcp_renglones`

`pcp_id` FK `ON DELETE CASCADE`, **`item_proceso_id NOT NULL`** — nunca
`presupuesto_items.id`, que la regeneración de presupuesto borra e
inserta de nuevo (RN-PRICING-008). `producto_id` nullable (el matching puede
estar pendiente). `cantidad`/`precio_referencia` son **snapshots** tomados al
momento de la selección: sin FK a `presupuesto_items`, inmunes a la
regeneración. `origen CHECK IN ('manual','regla','import_legado')`,
`estado CHECK IN ('pendiente','resuelto','descartado')`.

- `uq_pcpr_pcp_item` — `UNIQUE (pcp_id, item_proceso_id)`.
- `idx_pcpr_producto` — `(drogueria_id, producto_id)`, usado por la
  sugerencia de agrupación (`sugerencias/`, D12).

### `producto_proveedores`

El catálogo real producto↔proveedor. `producto_id`, `proveedor_id`,
`codigo_proveedor` (SKU del proveedor), `preferido`, `activo`, `notas`.
Arranca vacío; el alta ad-hoc durante la gestión de un PCP es una escritura
normal. **Deliberadamente NO derivado de `precios_proveedor`** — eso es un
log de cotizaciones, no un catálogo (un proveedor que nunca cotizó no podría
aparecer nunca).

- `uq_ppv_producto_prov` — `UNIQUE (drogueria_id, producto_id, proveedor_id)`.
- `uq_ppv_preferido` — parcial `(drogueria_id, producto_id) WHERE preferido
  AND activo`.
- `idx_ppv_producto_activo` — parcial `(drogueria_id, producto_id) WHERE
  activo`, la consulta por defecto de "proveedores disponibles".

### `pcp_renglon_resultados`

**El mecanismo de selección, reusado tres veces.** Esta es la única fila en
todo el esquema que prueba que "un renglón está siendo negociado con el
proveedor P": `renglones/service.py::seleccionar_proveedores` (PR5) la crea
en estado `sin_respuesta` al elegir uno, varios o "todos los disponibles"
como destino de negociación (sin tabla de selección aparte); `negociacion/
service.py::registrar_resultado` (PR7) la transiciona a `precio_obtenido` o
`no_cotiza`; `consultas/service.py::agrupar_renglones` (PR9) la usa como
prueba de "renglón asignado al proveedor P" antes de agrupar, en vez de leer
una columna dedicada.

`resultado CHECK IN ('precio_obtenido','no_cotiza','sin_respuesta')`,
`precio_proveedor_id` (nullable, FK a `precios_proveedor`), `consulta_id`
(nullable, FK diferida a `pcp_consultas`, ver M4b). Invariante:
`CHECK ((resultado = 'precio_obtenido') = (precio_proveedor_id IS NOT
NULL))`. `UNIQUE (pcp_renglon_id, proveedor_id)`. Solo `precio_obtenido`
escribe una fila en `precios_proveedor` — `no_cotiza` es un outcome puro, sin
fabricar nunca un precio.

## PR2 — `0012_pcp_extras.sql` (cinco tablas restantes + extras)

### `pcp_historial`

Dedicada y **append-only** (D6) — nunca extiende el `EntidadAuditable` de 5
valores de `auditoria/models.py` (eso arrastraría PCP al router de auditoría
Comercial). `pcp_id`, `pcp_renglon_id` (nullable), `tipo_evento CHECK IN
('creada','estado_cambiado','renglon_agregado','renglon_quitado',
'consulta_enviada','resultado_registrado','sugerencia_aplicada',
'notificacion_enviada','importada')`, `payload JSONB NOT NULL DEFAULT '{}'`
(nunca un campo de costo). Sin `updated_at`. Append-only se logra **omitiendo
por completo las políticas RLS de UPDATE/DELETE** — no por el GRANT: Supabase
ya otorga `ALL` (incluido DELETE) a `authenticated` en toda tabla nueva vía
`ALTER DEFAULT PRIVILEGES` a nivel de proyecto, así que RLS es la única
barrera real, no el GRANT explícito (hallazgo documentado en
`services/pcp/historial/service.py`, corrigiendo un comentario original que
asumía defensa en profundidad GRANT+RLS).

### `reglas_pcp`

Seam únicamente (D7): forma de tabla + FKs referentes, sin motor, sin filas,
sin código de servicio. `nombre`, scopes nullable (`cliente_id`,
`categoria_id`, `producto_id`, `clase_proceso`), `condicion JSONB`,
`prioridad`, `activa`. Existe para que `pcp.regla_pcp_id`/
`pcp_renglones.regla_pcp_id` ya tengan un referente el día que
`origen='regla'` se escriba por primera vez.

### `pcp_legacy_map`

Clave de idempotencia del import legado (D8) — sin código Python que la
consuma todavía (Fase 8 pendiente, ver README). A diferencia de
`terceros_legacy_map`, sin discriminador `entidad_legacy`: PCP es una sola
entidad, los espacios de código no pueden colisionar entre sí.
`UNIQUE (drogueria_id, sistema_origen, codigo_legacy)`.

### `pcp_consultas` / `pcp_consulta_renglones`

Agrupamiento real many-to-many (D9). `pcp_consultas` **deliberadamente no
tiene `pcp_id`** — `proveedor_id`, `contacto_id`, `estado CHECK IN
('borrador','enviada','respondida','cancelada')`, `canal`, `fecha_envio`,
`documento_path`. `pcp_consulta_renglones` (`consulta_id`, `pcp_renglon_id`,
`cantidad_consultada`, `UNIQUE (consulta_id, pcp_renglon_id)`) es lo que
permite que renglones de PCPs distintos terminen en una sola consulta al
mismo proveedor — cada renglón sigue trazando a su PCP de origen vía
`pcp_consulta_renglones.pcp_renglon_id -> pcp_renglones.pcp_id`, nunca
denormalizado.

### FKs diferidas de PR1 (M4b)

`pcp.regla_pcp_id`/`pcp_renglones.regla_pcp_id -> reglas_pcp` y
`pcp_renglon_resultados.consulta_id -> pcp_consultas` se agregan recién acá
porque sus tablas referentes no existían en PR1.

## `precios_proveedor` — columna FK agregada (D5)

`ALTER TABLE precios_proveedor ADD condicion_pago_id UUID NULL, ADD
forma_pago_id UUID NULL` con FKs compuestas `(x_id, drogueria_id) ->
condiciones_pago/formas_pago(id, drogueria_id)` — mismo patrón que
`clientes`/`proveedores` en `0008_terceros_modelo.sql` M5. `plazo_pago_dias`
(el `INTEGER` original) queda en su lugar, **nullable y sin uso por código
nuevo**, por al menos un release — retirarlo es un change posterior
separado, así revertir esta pieza es code-only.

**Backfill**: función nombrada e idempotente
`backfill_condicion_pago_desde_plazo(p_drogueria_id UUID DEFAULT NULL)` —no
un `DO` anónimo— crea (find-or-create) una `condiciones_pago` por cada
`plazo_pago_dias` distinto por droguería (`plazos_dias = '{N}'`, `nombre = N
|| ' dias'`) y setea la FK en las filas existentes. Nombrada a propósito para
que el test de integración pueda re-invocarla contra datos sembrados sin
depender de cuándo se aplicó la migración.

Las dos vistas que leían `pp.plazo_pago_dias` directo
(`v_precios_especiales_vigentes`, `v_presupuesto_revision`) se recrearon
(DROP+CREATE) para leer `COALESCE(cp_pp.plazos_dias[1], pp.plazo_pago_dias,
cp_prov.plazos_dias[1])` — prioriza la condición puntual del precio, cae al
entero legado, y por último a la condición general del proveedor.
`WITH (security_invoker = true)` preservado en ambas (verificado con
`pg_get_viewdef`/`pg_class.reloptions` después de aplicar, no solo leyendo la
fuente — exactamente la clase de error que `0008` documentó cometer una vez).

## `notificaciones` — CHECK ensanchado (`0013_pcp_notificacion_tipo.sql`)

Agrega `'pcp_cerrada'` al `CHECK (tipo IN (...))` de `notificaciones` —
ver [`decisiones.md`](./decisiones.md) para por qué esta migración no
apareció en el plan original.

## RPC `upsert_pcp_legacy` (D8)

Vive en la base desde `0012_pcp_extras.sql` M8 aunque `services/pcp/imports/`
todavía no existe (Fase 8 pendiente). Mirror de `upsert_terceros_legacy`
paso a paso: sin `SECURITY DEFINER` (la invoca `get_service_client()`, que ya
bypasea RLS), `SET search_path = public, pg_temp`, `#variable_conflict
use_column` desde el primer intento — evita repetir el bug de "column
reference is ambiguous" que `terceros-modelo` tuvo que corregir después en
`0009` (los parámetros `OUT` `codigo_legacy`/`pcp_id` colisionan con columnas
reales en los targets de `ON CONFLICT`). `REVOKE EXECUTE` de
`PUBLIC`/`anon`/`authenticated`, `GRANT` solo a `service_role`.

## RLS y roles (D11)

Las 9 tablas: `ENABLE ROW LEVEL SECURITY`;
`SELECT USING (get_rol() IN ('superadmin','admin','gerencia','compras') AND
mismo_tenant(drogueria_id))`; `INSERT`/`UPDATE` `WITH CHECK (get_rol() IN
('admin','gerencia','compras') AND mismo_tenant(drogueria_id))` — lado de
escritura idéntico a la política de `precios_proveedor`; `DELETE USING
(es_superadmin())`. **Excepción**: `pcp_historial` tiene únicamente políticas
SELECT + INSERT (D6, append-only) y sus GRANTs correspondientes solo cubren
esos dos verbos.

`comercial`/`lider_comercial` no ven pantallas de PCP en absoluto — ni
siquiera las propias. Esto no entra en conflicto con el feedback loop (D10):
Comercial se entera de su *presupuesto* (al que ya tiene acceso normal),
nunca a través de una pantalla de PCP. `superadmin` mantiene lectura como la
convención estándar de soporte cross-tenant ya usada por `terceros`/
`productos`.

`require_roles()` en cada router es el check autoritativo
(`services/pcp/roles.py`): `ROLES_LECTURA_PCP = (superadmin, admin,
gerencia, compras)`, `ROLES_ESCRITURA_PCP = (admin, gerencia, compras)` —
`superadmin` puede leer pero no escribir. Verificado end-to-end contra los 6
routers reales (`tests/pcp/test_matriz_roles.py`, tasks.md 12.2).

## Versión de Postgres

Las tres migraciones (`0011`/`0012`/`0013`) llevan el mismo guard M0 de
`0008_terceros_modelo.sql`: `server_version_num >= 150000` (requerido por
`WITH (security_invoker = true)`). Las tres se aplicaron con éxito contra el
proyecto de test (`grnamollopxdlstcpxhc`), confirmando indirectamente que
corre Postgres ≥ 15.
