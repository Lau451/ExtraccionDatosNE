# Casos de uso — Automatizaciones

Los 4 endpoints montados en `services/presupuestacion/main.py:8`, `:55`
(`app.include_router(automatizaciones_router, tags=["automatizaciones"])`), sin prefijo
adicional — cada path ya incluye `/automatizaciones` en su propia declaración
(`router.py`).

Roles: `_ROLES = ("admin", "gerencia")` (`router.py:21`) — un único tuple de roles para
**los 4 endpoints**, sin distinción entre lectura y escritura (a diferencia de
`eventos/`, que separa `_ROLES_LECTURA`/`_ROLES_ESCRITURA`).

## `reglas_automatizacion`

| Método | Path | Roles | Función | Archivo:línea |
|---|---|---|---|---|
| GET | `/automatizaciones/reglas` | `_ROLES`, `activa` como filtro opcional de query | `listar_reglas_endpoint` | `router.py:24-30` |
| POST | `/automatizaciones/reglas` | `_ROLES` | `crear_regla_endpoint` | `router.py:33-37` |
| PATCH | `/automatizaciones/reglas/{regla_id}` | `_ROLES` | `actualizar_regla_endpoint` — solo campos enviados (RN-AUTOMATIZACIONES-007) | `router.py:40-46` |

**No existe `DELETE /automatizaciones/reglas/{id}`** — confirmado leyendo `router.py`
completo (54 líneas, 4 endpoints exactos, sin ningún `@router.delete`). La única forma
de desactivar una regla es `PATCH activa=false`; no hay borrado físico ni lógico
adicional (`activa=false` no es un soft-delete con timestamp, es simplemente el mismo
booleano que controla si la regla participa de `reglas_activas_para`). Ver
[`base_de_datos.md`](./base_de_datos.md) y [`decisiones.md`](./decisiones.md).

## Métricas

| Método | Path | Roles | Función | Archivo:línea |
|---|---|---|---|---|
| GET | `/automatizaciones/metricas` | `_ROLES` | `metricas_endpoint`, expone `v_metricas_automatizacion` | `router.py:49-54` |

## Cliente Supabase por endpoint

Los 2 endpoints de **escritura** (`POST`/`PATCH`) resuelven `get_service_client()`
internamente a través de un wrapper `_para_endpoint`
(`crear_regla_para_endpoint` `:63-64`, `actualizar_regla_para_endpoint` `:67-72`) — el
router no inyecta ningún cliente en esos casos. Los 2 endpoints de **lectura**
(`GET /automatizaciones/reglas`, `GET /automatizaciones/metricas`) inyectan
`user_client` con `Depends(get_user_client)` (`router.py:17`, `:28`, `:52`). Mismo
patrón documentado como D-PROCESOS-001 en Procesos Comerciales y repetido en
`eventos/` — ver [`../eventos/decisiones.md`](../eventos/decisiones.md).

## Quién consume el módulo — nadie dispara el motor en producción

El único uso real hoy es **administrativo**: un usuario con rol `admin` o `gerencia`
puede crear, listar, actualizar (activar/desactivar, cambiar prioridad, condición,
parámetros) y ver métricas de reglas vía HTTP. **No existe ningún flujo de negocio que
dispare `disparar_reglas()`**, y **no existe ningún worker/cron que corra
`procesar_acciones_pendientes()`** (RN-AUTOMATIZACIONES-006) — confirmado por `Grep`
exhaustivo de ambos nombres en todo el repositorio, sin call sites fuera de
`tests/automatizaciones/test_service.py`. En la práctica, una regla creada hoy vía
`POST /automatizaciones/reglas` puede quedar `activa=True` indefinidamente sin que
nunca se evalúe contra ningún evento real, y ninguna acción llegaría a encolarse ni
mucho menos a procesarse, salvo que alguien invoque el motor manualmente (por ejemplo,
desde una consola de administración fuera del alcance leído, o desde un test).

## Consumidores cruzados (con evidencia)

`automatizaciones/service.py:14-16` importa código Python de otros 2 módulos de
negocio:

- `eventos.models.EventoCreate` / `eventos.service.crear_evento` — usado en
  `_ejecutar_accion` (`:99-110`) cuando `tipo_accion == "crear_evento"`. Confirmado
  también del lado de `eventos/` (`docs/modulos/eventos/README.md:78-84`,
  `casos_de_uso.md:45-59`), que identifica a `automatizaciones/` como su **único**
  consumidor de negocio.
- `notificaciones.service.crear_notificacion` — usado en `_ejecutar_accion`
  (`:112-129`) cuando `tipo_accion == "enviar_notificacion"`.
  `notificaciones/service.py:25-28` documenta esta función como de uso interno para
  "otros módulos como efecto secundario (eventos, automatizaciones)" — comentario
  impreciso: `docs/modulos/notificaciones/decisiones.md` (D-NOTIFICACIONES-005) confirmó
  que `eventos/` no la llama; `automatizaciones/` es el único consumidor real. Ver
  [`../notificaciones/`](../notificaciones/) para la documentación completa.

No se encontró ningún otro consumidor de `automatizaciones/` — ni HTML/template legacy,
ni otro backend, ni `services/extraccion/` — confirmado por `Grep` de
`from services.presupuestacion.automatizaciones` en todo el repositorio en esta sesión.
