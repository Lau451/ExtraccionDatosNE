# Casos de uso — Notificaciones

Los 5 endpoints montados en `services/presupuestacion/main.py:19`, `:54`
(`app.include_router(notificaciones_router, tags=["notificaciones"])`), sin prefijo
adicional — cada path ya incluye su segmento propio en `router.py`.

**Sin restricción de rol**: a diferencia de `automatizaciones/` (`_ROLES = ("admin",
"gerencia")` en sus 4 endpoints), ningún endpoint de `notificaciones/router.py` usa
`Depends(require_roles(...))` — el único `Depends` de autorización es
`get_current_user` (cualquier usuario autenticado). El scoping real ocurre por
identidad (`destinatario_id`/`usuario_id = auth.uid()` o el equivalente en código de
aplicación), no por rol — coherente con que cada usuario solo puede ver/tocar sus
propias notificaciones y preferencias sin importar su rol. Confirmado por lectura
completa de `router.py` (5 endpoints exactos, sin ningún import de `require_roles`).

## Notificaciones

| Método | Path | Cliente | Función | Archivo:línea |
|---|---|---|---|---|
| GET | `/notificaciones/no-leidas` | `user_client` (verificado contra policy `no_sel`) | `listar_no_leidas_endpoint` | `router.py:22-30` |
| PATCH | `/notificaciones/{notificacion_id}/leer` | `service_client` (vía wrapper, sin comentario de por qué no `user_client`) | `marcar_leida_endpoint` | `router.py:33-37` |
| PATCH | `/notificaciones/{notificacion_id}/archivar` | `service_client` (ídem) | `marcar_archivada_endpoint` | `router.py:40-44` |

**No existe `POST /notificaciones`** — no hay ningún endpoint HTTP para crear una
notificación manualmente. Confirmado leyendo `router.py` completo: 4 endpoints
exactos, ninguno con método `POST` sobre `/notificaciones`. La única forma de crear
una notificación es la función interna `crear_notificacion` (`service.py:11-62`),
llamada desde código Python de otro módulo — ver "Quién consume `crear_notificacion`"
abajo. Coherente con el docstring citado en [`arquitectura.md`](./arquitectura.md):
"Función de uso interno... no un endpoint público."

**No existe `DELETE`** sobre ninguna de las 3 tablas del módulo vía HTTP — ver
[`base_de_datos.md`](./base_de_datos.md).

## Preferencias

| Método | Path | Cliente | Función | Archivo:línea |
|---|---|---|---|---|
| GET | `/notificacion-preferencias` | `user_client` (verificado contra policy `np_sel`) | `listar_preferencias_endpoint` | `router.py:47-53` |
| PUT | `/notificacion-preferencias` | `user_client` (verificado contra `np_ins`/`np_upd`) | `upsert_preferencia_endpoint` | `router.py:56-66` |

`PUT` cubre tanto creación como actualización (upsert) — no existe un `POST` separado
para "crear preferencia por primera vez". El `body` (`NotificacionPreferenciaUpsert`)
solo acepta `tipo`, `canal`, `habilitada`; `usuario_id`/`drogueria_id` siempre se toman
del usuario autenticado (`service.py:87-99`), nunca del body.

## Quién consume `crear_notificacion` — solo `automatizaciones/`

`automatizaciones/service.py:16` importa `notificaciones.service.crear_notificacion` y
lo usa en `_ejecutar_accion` (`automatizaciones/service.py:112-129`) cuando
`regla["tipo_accion"] == "enviar_notificacion"`, pasando
`destinatario_id`/`tipo`/`titulo` desde `parametros_accion` de la regla. Es el
**único** consumidor Python confirmado en todo el repositorio — `Grep` de `from
services.presupuestacion.notificaciones` en esta sesión no encontró ningún otro
call site fuera de `automatizaciones/`, `notificaciones/` mismo, `main.py` (montaje
del router) y `tests/notificaciones/`.

**`eventos/service.py` no llama a `crear_notificacion`**, pese a que el docstring de la
función (`service.py:25-28`) la menciona como llamador ("otros módulos... eventos,
automatizaciones"). Confirmado por lectura completa de los imports de
`eventos/service.py:1-12` y por `Grep` de `notif` (case-insensitive) sobre todo
`eventos/`, sin resultados. Ver [`decisiones.md`](./decisiones.md)
D-NOTIFICACIONES-005 y [`pendientes.md`](./pendientes.md).

Recordar además que este consumo depende de que alguien dispare el motor de
`automatizaciones/` — `disparar_reglas()` no tiene ningún disparador real en
producción hoy (documentado en
[`../automatizaciones/README.md`](../automatizaciones/README.md)), así que en la
práctica **ninguna notificación se crea automáticamente hoy** por este camino; el
único camino que sí crea notificaciones reales en producción es el bypass descrito
abajo.

## Bypass confirmado: `extraccion_validacion/` no pasa por este módulo

`services/presupuestacion/extraccion/repository.py:101-102` define su propia función
homónima:

```python
def crear_notificacion(client: Client, fila: dict[str, Any]) -> None:
    client.table("notificaciones").insert(fila).execute()
```

Llamada desde `_notificar_reemplazo_comparativa`
(`extraccion/service.py:112-134`) para avisar a `admin`/`gerencia`/`lider_comercial`
cuando una nueva extracción reemplaza la comparativa vigente de un proceso. Esta
función **inserta directo contra `notificaciones`**, sin pasar por
`notificaciones.service.crear_notificacion` — no genera ninguna fila en
`notificacion_entregas` ni consulta `notificacion_preferencias`. Ya documentado en
detalle desde el otro lado en
[`../extraccion_validacion/pendientes.md`](../extraccion_validacion/pendientes.md)
(sección "P2 — Bypass de `notificaciones/`"); confirmado en esta sesión que el código
sigue exactamente igual (`extraccion/repository.py:101-102`,
`extraccion/service.py:112-134`).

**Consistencia con lo documentado allá**: dado que ninguna entrega real se envía por
ningún canal hoy (RN-NOTIFICACIONES-008), el impacto práctico de este bypass —"nunca
se genera una fila de entrega, aunque el usuario haya deshabilitado el tipo en sus
preferencias"— es hoy menos grave de lo que sería si el módulo tuviera envío real
activo: en ambos caminos (con o sin bypass) la notificación termina siendo visible
solo como fila en `notificaciones` (vía `GET /notificaciones/no-leidas`), sin ningún
canal externo despachando nada. El bypass sí importa igual para el respeto de
preferencias del usuario (`notificacion_preferencias`), que se ignora por completo en
ese camino.
