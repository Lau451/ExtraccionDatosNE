# Base de datos — Automatizaciones

Tablas y vista definidas en `docs/schema/extractor_final.sql:866-949` (sección "MOTOR DE
REGLAS DE AUTOMATIZACIÓN") y `:1678-1697` (vista de métricas). Todas las columnas y
`CHECK`s citados fueron leídos directamente del `CREATE TABLE` en esta sesión.

## `reglas_automatizacion` (`extractor_final.sql:870-900`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `drogueria_id` | UUID NOT NULL | FK `fk_ra_drog` → `droguerias` (`:1160`) |
| `nombre` | TEXT NOT NULL | |
| `descripcion` | TEXT NULL | |
| `evento_disparador` | TEXT NOT NULL | Texto libre, sin `CHECK` de vocabulario |
| `entidad_objetivo` | TEXT NOT NULL | `CHECK ck_ra_entidad`: `proceso_comercial, comparativa, orden_compra, presupuesto, evento, extraction_result, entrega` (7 valores, `:889-892`) |
| `condicion` | JSONB NULL | Formato libre a nivel de BD; la app solo soporta `{"campo","valor"}` (ver [`arquitectura.md`](./arquitectura.md)) |
| `tipo_accion` | TEXT NOT NULL | `CHECK ck_ra_tipo_accion`: 8 valores (`:893-896`) |
| `parametros_accion` | JSONB NULL | |
| `modo_ejecucion` | TEXT NOT NULL DEFAULT `'cola'` | `CHECK ck_ra_modo`: `inmediato, cola` (`:897`) |
| `max_reintentos` | INTEGER NOT NULL DEFAULT 3 | `CHECK ck_ra_reintentos`: `0 <= x <= 10` (`:898`) |
| `activa` | BOOLEAN NOT NULL DEFAULT TRUE | Nace activa; no hay campo de aprobación previa |
| `prioridad` | INTEGER NOT NULL DEFAULT 0 | `CHECK ck_ra_prioridad`: `>= 0` (`:899`); usada para ordenar `reglas_activas_para` |
| `created_by` / `updated_by` | UUID NULL | Sin FK declarada a `usuarios` en el bloque leído |
| `created_at` / `updated_at` | TIMESTAMPTZ | `updated_at` mantenido por trigger `t_u_ra` (`:1460`) |

Comentario de tabla (`:902`), citado completo: "Reglas 'cuando ocurre X → ejecutar Y'.
Sin versionado (deliberado: no hay reglas en producción para justificarlo —
`acciones_ejecutadas.regla_id` ya apunta a la FILA de la regla, así que agregar
versionado después no requiere migrar datos)." Ver
[`decisiones.md`](./decisiones.md) D-AUTOMATIZACIONES-002.

**Nota sobre validación de rango**: `ReglaAutomatizacionCreate.max_reintentos: int = 3`
(`models.py:26`) no tiene ningún `Field(ge=0, le=10)` de Pydantic — el rango `0-10` solo
se aplica a nivel de `CHECK` de BD (`ck_ra_reintentos`). Un `POST` con
`max_reintentos=999` pasa la validación de FastAPI/Pydantic y falla recién en el
`INSERT` a Supabase con un error de constraint, no con un `422` claro de la app. Mismo
patrón para `prioridad` (`ck_ra_prioridad >= 0`, sin `Field(ge=0)` en `models.py:27`).
Ver [`pendientes.md`](./pendientes.md).

## `acciones_ejecutadas` (`extractor_final.sql:910-945`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `drogueria_id` | UUID NOT NULL | FK `fk_ae_drog` (`:1162`) |
| `regla_id` | UUID NULL | FK `fk_ae_regla` → `reglas_automatizacion` (`:1163`); sin `ON DELETE CASCADE` (ver `test_procesar_acciones_pendientes...`, ninguno explícito en el `ALTER TABLE` leído) |
| `proceso_comercial_id`, `comparativa_id`, `orden_compra_id`, `presupuesto_id`, `evento_id` | UUID NULL c/u | Las **5 únicas** columnas FK polimórficas — FKs `fk_ae_proc`, `fk_ae_comp`, `fk_ae_oc`, `fk_ae_pre`, `fk_ae_ev` (`:1164-1168`) |
| `tipo_accion` | TEXT NOT NULL | Copiado de la regla al momento de ejecutar/encolar |
| `estado` | TEXT NOT NULL DEFAULT `'pendiente'` | `CHECK ck_ae_estado`: `pendiente, ejecutando, completada, fallida, cancelada` (5 valores, `:932`) — ver [`estados.md`](./estados.md) |
| `resultado` | JSONB NULL | Payload de éxito (`{"evento_id":...}` / `{"notificacion_id":...}`) |
| `error_msg` | TEXT NULL | Mensaje de error si `exito=False` |
| `intentos` | INTEGER NOT NULL DEFAULT 0 | `CHECK ck_ae_intentos >= 0` |
| `iniciado_at`, `finalizado_at`, `duracion_ms`, `proximo_intento_at`, `ejecutado_at` | Métricas de ejecución | `CHECK ck_ae_fechas`: `finalizado_at >= iniciado_at` cuando ambas no son NULL (`:942-944`) |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### `CHECK ck_ae_una_entidad` — la cobertura incompleta confirmada (`:933-939`)

```sql
CONSTRAINT ck_ae_una_entidad CHECK (
    (proceso_comercial_id IS NOT NULL)::int +
    (comparativa_id IS NOT NULL)::int +
    (orden_compra_id IS NOT NULL)::int +
    (presupuesto_id IS NOT NULL)::int +
    (evento_id IS NOT NULL)::int = 1
)
```

Exige que **exactamente una** de las 5 columnas FK esté seteada — nunca cero, nunca dos
o más. Pero `reglas_automatizacion.entidad_objetivo` (`ck_ra_entidad`, sección anterior)
admite **7** valores, incluyendo `extraction_result` y `entrega`, que no tienen columna
equivalente en `acciones_ejecutadas`. `COLUMNA_FK_POR_ENTIDAD` (`repository.py:9-15`)
refleja exactamente esta limitación de schema — mapea solo las 5 entidades cubiertas por
el `CHECK`, con un comentario explícito en el propio código (`repository.py:6-8`) citado
completo:

> "# columnas FK soportadas por acciones_ejecutadas / historial_cambios (ck_ae_una_entidad
> solo cubre estas 5 -- reglas_automatizacion.entidad_objetivo admite además
> 'extraction_result' y 'entrega', que NO tienen columna equivalente en esta tabla)."

**Consecuencia en tiempo de ejecución**: una regla con `entidad_objetivo` en
`extraction_result`/`entrega` que efectivamente matchea `evento_disparador` en
`disparar_reglas` se **descarta sin ejecutar**, con un `logger.warning` explícito
(`service.py:162-169`) — no se crea ninguna fila en `acciones_ejecutadas`, no hay
`resultado` fallido para inspeccionar, la única traza queda en el log de aplicación.
[IMPLEMENTADO], confirmado por lectura completa de `disparar_reglas` y por el mensaje de
log citado ahí mismo. No hay ningún test en `tests/automatizaciones/test_service.py`
que ejercite una regla con `entidad_objetivo="extraction_result"` o `"entrega"` — los 8
tests leídos usan `entidad_objetivo="proceso_comercial"` exclusivamente (`_regla()`,
`test_service.py:14-23`). Ver [`pendientes.md`](./pendientes.md), P1.

`procesar_acciones_pendientes` (`service.py:211-267`) tiene el mismo patrón de
resolución (`columna_fk = repo.COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)`,
`:227`), pero como solo procesa filas que **ya existen** en `acciones_ejecutadas`, y
esas filas solo pueden haberse creado para las 5 entidades cubiertas (por el motivo de
arriba), el gap no se vuelve a manifestar ahí — es exclusivamente un problema de
`disparar_reglas`.

## Vista `v_metricas_automatizacion` (`extractor_final.sql:1679-1697`)

```sql
SELECT r.id AS regla_id, r.drogueria_id, r.nombre, r.tipo_accion, r.modo_ejecucion,
       COUNT(a.id) AS ejecuciones,
       COUNT(a.id) FILTER (WHERE a.estado = 'completada') AS exitosas,
       COUNT(a.id) FILTER (WHERE a.estado = 'fallida')    AS fallidas,
       ROUND(AVG(a.duracion_ms) FILTER (WHERE a.estado = 'completada'), 0) AS duracion_promedio_ms,
       MAX(a.duracion_ms) FILTER (WHERE a.estado = 'completada')           AS duracion_max_ms,
       ROUND(AVG(a.intentos), 2) AS intentos_promedio,
       MAX(a.finalizado_at)      AS ultima_ejecucion
FROM reglas_automatizacion r
LEFT JOIN acciones_ejecutadas a ON a.regla_id = r.id
GROUP BY r.id, r.drogueria_id, r.nombre, r.tipo_accion, r.modo_ejecucion;
```

`LEFT JOIN` explícito: una regla sin ejecuciones todavía aparece igual en `GET
/automatizaciones/metricas` con `ejecuciones=0` y el resto de las métricas en `NULL`
(vía `COUNT`/`AVG`/`MAX` sobre cero filas). `security_invoker = on`
(`extractor_final.sql:1716`) — la vista respeta RLS del `user_client` que la consulte,
coherente con que `GET /automatizaciones/metricas` inyecta `user_client`
(`router.py:52`). Comentario de vista (`:1697`): "Rendimiento por regla: cuánto tarda,
cuántas veces falla, cuántos reintentos necesita. Base para medir agentes de IA."

## CRUD real ejercido por el módulo

| Tabla | Operación | Función | Archivo:línea |
|---|---|---|---|
| `reglas_automatizacion` | INSERT | `repo.crear_regla` | `repository.py:18-19` |
| `reglas_automatizacion` | SELECT por id | `repo.obtener_regla` | `repository.py:22-26` |
| `reglas_automatizacion` | SELECT lista, filtro `activa` opcional, orden `prioridad desc` | `repo.listar_reglas` | `repository.py:29-33` |
| `reglas_automatizacion` | UPDATE parcial | `repo.actualizar_regla` | `repository.py:36-37` |
| `reglas_automatizacion` | SELECT filtrado (`drogueria_id`+`entidad_objetivo`+`evento_disparador`+`activa=True`, orden `prioridad desc`) | `repo.reglas_activas_para` | `repository.py:40-53` |
| `acciones_ejecutadas` | INSERT | `repo.crear_accion_ejecutada` | `repository.py:56-57` |
| `acciones_ejecutadas` | UPDATE parcial | `repo.actualizar_accion_ejecutada` | `repository.py:60-61` |
| `acciones_ejecutadas` | SELECT `estado='pendiente'` AND (`proximo_intento_at` NULL o vencido), **sin filtro `drogueria_id`** | `repo.listar_acciones_pendientes` | `repository.py:64-73` |
| `v_metricas_automatizacion` | SELECT filtrado por `drogueria_id` | `repo.metricas` | `repository.py:76-83` |

**No hay ningún `DELETE`** sobre `reglas_automatizacion` ni `acciones_ejecutadas` en todo
el módulo — confirmado por `Grep` de `.delete()` sobre
`services/presupuestacion/automatizaciones/`, sin resultados (los únicos `.delete()`
del árbol de `automatizaciones` están en `tests/automatizaciones/conftest.py:11-18`,
teardown de tests). Ver [`casos_de_uso.md`](./casos_de_uso.md).

**`listar_acciones_pendientes` sin filtro de tenant** (`repository.py:64-73`): a
diferencia de `reglas_activas_para`, que sí recibe y filtra por `drogueria_id`, esta
función trae pendientes de **todas** las droguerías en una sola llamada — mismo patrón
que `eventos.repository.listar_recurrentes_a_ejecutar` (documentado en
`docs/modulos/eventos/decisiones.md` D-EVENTOS-004), coherente con estar pensada como
un job de sistema global. Ver [`decisiones.md`](./decisiones.md).
