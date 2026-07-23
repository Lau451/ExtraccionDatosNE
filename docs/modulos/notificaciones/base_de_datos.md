# Base de datos — Notificaciones

Tablas definidas en `docs/schema/extractor_final.sql:980-1049` (sección "CENTRO DE
NOTIFICACIONES") y sus policies RLS en `docs/schema/rls_final.sql:544-585`. Todas las
columnas, `CHECK`s y policies citadas fueron leídas directamente del DDL en esta
sesión.

## `notificaciones` (`extractor_final.sql:980-1009`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `drogueria_id` | UUID NOT NULL | |
| `destinatario_id` | UUID NOT NULL | FK `fk_no_dest` → `usuarios` (`rls_final.sql:415`) |
| `tipo` | TEXT NOT NULL | `CHECK ck_notif_tipo`: 13 valores (`:1001-1006`) — igual al `Literal TipoNotificacion` de `models.py:6-11` |
| `titulo` | TEXT NOT NULL | |
| `mensaje` | TEXT NULL | |
| `prioridad` | TEXT NOT NULL DEFAULT `'media'` | `CHECK ck_notif_prioridad`: `baja, media, alta, urgente` (`:1007`) |
| `url_destino` | TEXT NULL | |
| `origen` | TEXT NOT NULL DEFAULT `'sistema'` | `CHECK ck_notif_origen`: `usuario, ia, automatizacion, webhook, api, sistema` (`:1008`) |
| `proceso_comercial_id`, `comparativa_id`, `orden_compra_id`, `presupuesto_id`, `evento_id` | UUID NULL c/u | FKs polimórficas opcionales, sin `CHECK` de "exactamente una" (a diferencia de `acciones_ejecutadas.ck_ae_una_entidad` en `automatizaciones/`) — pueden estar todas NULL, o varias seteadas a la vez, nada en el schema ni en `crear_notificacion` lo impide |
| `accion_ejecutada_id` | UUID NULL | Enlace hacia `acciones_ejecutadas`; **ningún código Python del repositorio lo escribe** — confirmado por `Grep` de `accion_ejecutada_id` sobre `services/presupuestacion/`, sin resultados. Columna muerta a nivel de aplicación. |
| `leida_at` / `archivada_at` | TIMESTAMPTZ NULL | Ver [`estados.md`](./estados.md) |
| `metadata` | JSONB NULL | Aceptado por `crear_notificacion` (`service.py:40`) pero **no expuesto** en `NotificacionOut` (`models.py:19-31`) — un `GET` nunca lo devuelve |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

Comentario de tabla (`:1011`), citado completo: "Centro de notificaciones. Un EVENTO
es trabajo (tiene responsable, fechas, estado); una NOTIFICACIÓN es un aviso (se lee y
se archiva). Las entregas por canal viven en notificacion_entregas."

## `notificacion_entregas` (`extractor_final.sql:1013-1031`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `notificacion_id` | UUID NOT NULL | FK `fk_ne_notif` → `notificaciones` **ON DELETE CASCADE** (`extractor_final.sql:1181`) |
| `drogueria_id` | UUID NOT NULL | |
| `canal` | TEXT NOT NULL | `CHECK ck_ne_canal`: `web, email, whatsapp, sms, push, webhook` (6 valores, `:1028`) — igual al `Literal Canal` de `models.py:14` |
| `estado` | TEXT NOT NULL DEFAULT `'pendiente'` | `CHECK ck_ne_estado`: 5 valores: `pendiente, enviando, enviada, fallida, cancelada` (`:1029`) — **el código solo escribe `pendiente`**, ver [`estados.md`](./estados.md) |
| `destino` | TEXT NULL | Nunca escrito — `repo.crear_entrega` (`repository.py:11-12`) solo inserta `notificacion_id`, `drogueria_id`, `canal`, `estado` |
| `proveedor_externo` | TEXT NULL | Nunca escrito, misma razón |
| `referencia_externa` | TEXT NULL | Nunca escrito, misma razón |
| `intentos` | INTEGER NOT NULL DEFAULT 0 | `CHECK ck_ne_intentos >= 0`; queda siempre en `0` — nada lo incrementa |
| `enviado_at` | TIMESTAMPTZ NULL | Nunca escrito |
| `error_msg` | TEXT NULL | Nunca escrito |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

`CONSTRAINT uq_notif_canal UNIQUE (notificacion_id, canal)` (`:1027`): a lo sumo una
fila de entrega por canal para una misma notificación — coherente con que
`crear_notificacion` calcula `canales` como una lista sin duplicados (proviene de
`preferencias_de_tipo`, que ya filtra por `usuario_id`+`tipo`, o del default fijo
`("web",)`).

Comentario de tabla (`:1033`), citado completo: "Una fila por canal de envío. Permite
que la misma notificación esté leída en la web, enviada por mail y fallida en
WhatsApp, cada una con su estado." — describe la **intención** del modelo; hoy ningún
código produce esos estados variados (`enviada`/`fallida`), ver
[`README.md`](./README.md) y [`pendientes.md`](./pendientes.md).

## `notificacion_preferencias` (`extractor_final.sql:1035-1047`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `usuario_id` | UUID NOT NULL | FK `fk_np_user` → `usuarios` **ON DELETE CASCADE** (`rls_final.sql:416`) |
| `drogueria_id` | UUID NOT NULL | |
| `tipo` | TEXT NOT NULL | Sin `CHECK` de vocabulario a nivel de BD (a diferencia de `notificaciones.tipo`) — la validación de los 13 valores de `TipoNotificacion` ocurre solo en `NotificacionPreferenciaUpsert` (Pydantic, `models.py:34-37`) |
| `canal` | TEXT NOT NULL | `CHECK ck_np_canal`: mismos 6 valores que `ck_ne_canal` (`:1046`) |
| `habilitada` | BOOLEAN NOT NULL DEFAULT TRUE | |
| `created_at` / `updated_at` | TIMESTAMPTZ | `updated_at` mantenido por trigger `t_u_np` (`extractor_final.sql:1462`), mismo patrón que `reglas_automatizacion.t_u_ra` en `automatizaciones/` |
| `CONSTRAINT uq_notif_pref UNIQUE (usuario_id, tipo, canal)` | | Sostiene el `upsert(on_conflict="usuario_id,tipo,canal")` de `repository.py:69` |

Comentario de tabla (`:1049`), citado completo: "Qué notificaciones quiere recibir
cada usuario y por qué canal. Sin fila = default del backend."

## RLS (`rls_final.sql:544-585`)

Las tres tablas tienen RLS habilitado. Policies citadas completas:

**`notificaciones`** (comentario de sección, `:544`: "cada uno ve LAS SUYAS.
admin/gerencia ven las de su droguería."):

```sql
CREATE POLICY no_sel ON notificaciones FOR SELECT USING (
    destinatario_id = (select auth.uid())
    OR ((select get_rol()) IN ('admin','gerencia') AND (select mismo_tenant(drogueria_id)))
    OR (select es_superadmin())
);
CREATE POLICY no_ins ON notificaciones FOR INSERT WITH CHECK ((select mismo_tenant(drogueria_id)));
CREATE POLICY no_upd ON notificaciones FOR UPDATE
USING (destinatario_id = (select auth.uid()) OR (select es_superadmin()))
WITH CHECK (destinatario_id = (select auth.uid()) OR (select es_superadmin()));
CREATE POLICY no_del ON notificaciones FOR DELETE USING ((select es_superadmin()));
```

**`notificacion_entregas`**: `ne_sel` filtra por `EXISTS` contra el `destinatario_id`
de la notificación asociada (no denormalizado), con nota explícita en el propio SQL
(`:566-568`), citada completa: "Nota: acá el EXISTS SÍ se mantiene a propósito —
filtra por DESTINATARIO de la notificación, no por tenant. No se puede denormalizar
sin duplicar el destinatario_id en cada fila de entrega." `ne_upd` está restringido a
`admin`/`gerencia` — coherente con que ningún código de aplicación actualiza esta
tabla hoy (ver arriba); si alguna vez se implementa el worker de envío real
(`ROADMAP.md:64-72`), tendría que correr con un rol que pase esa policy (`service_role`
la bypasea, como ya hace `crear_entrega`).

**`notificacion_preferencias`**: `np_sel`/`np_ins`/`np_upd`/`np_del` — todas con la
rama base `usuario_id = auth.uid()`, más `admin` (solo lectura en `np_sel`) y
`es_superadmin()`.

## CRUD real ejercido por el módulo

| Tabla | Operación | Función | Archivo:línea |
|---|---|---|---|
| `notificaciones` | INSERT | `repo.crear_notificacion` | `repository.py:7-8` |
| `notificaciones` | SELECT por id | `repo.obtener_notificacion` | `repository.py:26-30` |
| `notificaciones` | SELECT no leídas ni archivadas, orden `created_at desc` | `repo.listar_no_leidas` | `repository.py:33-43` |
| `notificaciones` | UPDATE `leida_at` | `repo.marcar_leida` | `repository.py:46-53` |
| `notificaciones` | UPDATE `archivada_at` | `repo.marcar_archivada` | `repository.py:56-63` |
| `notificacion_entregas` | INSERT | `repo.crear_entrega` | `repository.py:11-12` |
| `notificacion_preferencias` | SELECT por `usuario_id`+`tipo` | `repo.preferencias_de_tipo` | `repository.py:15-23` |
| `notificacion_preferencias` | UPSERT (`on_conflict="usuario_id,tipo,canal"`) | `repo.upsert_preferencia` | `repository.py:66-72` |
| `notificacion_preferencias` | SELECT por `usuario_id` | `repo.listar_preferencias` | `repository.py:75-82` |

**No hay ningún `DELETE`** sobre ninguna de las 3 tablas en todo el módulo —
confirmado por `Grep` de `.delete()` sobre `services/presupuestacion/notificaciones/`,
sin resultados (los únicos `.delete()` del árbol están en
`tests/notificaciones/conftest.py:8-10`, teardown de tests). Ver
[`casos_de_uso.md`](./casos_de_uso.md).

**No hay ningún `UPDATE` sobre `notificacion_entregas`** en todo el módulo ni en el
resto del repositorio — confirmado por `Grep` de `notificacion_entregas` combinado con
`.update(` en todo `services/presupuestacion/` y `tests/`, sin resultados. Ver
[`estados.md`](./estados.md) y [`pendientes.md`](./pendientes.md).
