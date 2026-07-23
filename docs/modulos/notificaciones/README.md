# Módulo Notificaciones — `services/presupuestacion/notificaciones/`

## Qué es

Notificaciones es el "centro de notificaciones" de `presupuestacion/`: un modelo de
avisos internos multi-canal, separado deliberadamente del concepto de evento. El
comentario de la propia tabla lo resume (`docs/schema/extractor_final.sql:977`,
sección "CENTRO DE NOTIFICACIONES"):

> "CENTRO DE NOTIFICACIONES (separado de eventos: evento=trabajo, notificación=aviso)"

Cada notificación (`notificaciones`) puede generar una fila de **entrega** por cada
canal habilitado del destinatario (`notificacion_entregas` — `web`, `email`,
`whatsapp`, `sms`, `push`, `webhook`), y cada usuario puede configurar sus
**preferencias** de qué tipo de notificación quiere recibir por qué canal
(`notificacion_preferencias`). Con solo 45+82+66+111 líneas repartidas en 4 archivos
(`__init__.py` 0, `models.py` 45, `repository.py` 82, `router.py` 66, `service.py`
111 — contadas con `wc -l` en esta sesión) y `tests/notificaciones/` con 214 líneas
(`test_service.py`) y 10 líneas (`conftest.py`), es el módulo más chico documentado
hasta ahora en líneas de producción, pero con la suite de tests más rigurosa en
materia de RLS (ver más abajo).

## Qué NO hace HOY (crítico)

**Ninguna notificación se envía realmente por ningún canal.** Toda fila de
`notificacion_entregas` nace con `estado='pendiente'` (`repository.py:12`,
`service.py:58`) y ningún código del repositorio la vuelve a tocar — confirmado por
`Grep` exhaustivo de librerías/SDKs de envío (`smtp`, `sendgrid`, `twilio`, `resend`,
`requests`/`httpx`/`urllib` hacia APIs externas, `whatsapp`, `firebase`/`fcm`/`apns`,
`boto3`/`ses`, `mailgun`) sobre `services/presupuestacion/` completo en esta sesión:
sin resultados fuera de los propios `Literal` de vocabulario (`Canal` en
`models.py:14`, `CHECK ck_ne_canal`) y una mención en `ROADMAP.md`. Confirmado también
por `Grep` de `.update(` sobre `notificacion_entregas` en todo el repositorio: sin
resultados — ninguna fila de entrega transiciona jamás de `pendiente` a otro estado.

El propio `ROADMAP.md` del backend lo documenta como pendiente deliberado
(`services/presupuestacion/ROADMAP.md:64-72`, sección "Envíos reales de
notificaciones"), citado completo:

> "El modelo está completo: `notificaciones`, `notificacion_entregas` (una fila por
> canal), `notificacion_preferencias` (opt-in por usuario×tipo×canal). Falta la
> integración con un proveedor real de envío — toda entrega queda en
> `notificacion_entregas.estado='pendiente'` para siempre; el canal se calcula bien
> pero nada lo despacha. Necesita elegir proveedor(es) por canal (ej. Resend/SendGrid
> para email, alguna API de WhatsApp Business) y un worker que tome las entregas
> pendientes y las procese, análogo al de automatizaciones."

En la práctica, funcionalmente este módulo es hoy **un inbox interno**: guarda avisos,
los muestra al destinatario correcto (con RLS real detrás), y permite marcarlos
leídos/archivados. El resto del modelo multi-canal (canales, preferencias, entregas)
está completo a nivel de dato y de lógica de cálculo de canales, pero no tiene ningún
efecto observable fuera de la base de datos. Ver [`estados.md`](./estados.md) y
[`pendientes.md`](./pendientes.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `notificaciones/__init__.py` | Vacío. |
| `notificaciones/models.py` | 4 `Literal` (`TipoNotificacion` 13 valores, `Prioridad` 4, `OrigenNotificacion` 6, `Canal` 6) + `CANALES_DEFAULT` + 4 modelos Pydantic. |
| `notificaciones/repository.py` | Acceso a datos puro sobre `notificaciones`, `notificacion_entregas` y `notificacion_preferencias`. |
| `notificaciones/service.py` | `crear_notificacion` (uso interno, con resolución de canales), lectura/marcado de notificaciones, CRUD de preferencias, wrappers `_para_endpoint`. |
| `notificaciones/router.py` | 5 endpoints HTTP, todos scopeados al usuario autenticado. |

## Dependencias

Depende de Core (`core/database.py` — `get_service_client`/`get_user_client`,
`core/exceptions.py` — `ForbiddenError`/`NotFoundError`, `core/auth.py` —
`UsuarioPerfil`/`get_current_user`). No importa código Python de ningún otro módulo de
negocio — es, junto con `eventos/`, uno de los módulos "hoja" de los que otros dependen,
no al revés.

## Quién lo consume

- **`automatizaciones/service.py:16`** importa `notificaciones.service.crear_notificacion`
  y lo usa en `_ejecutar_accion` cuando `regla["tipo_accion"] == "enviar_notificacion"`
  (`automatizaciones/service.py:112-129`). Es el **único** consumidor Python confirmado
  del módulo — confirmado por `Grep` de `from services.presupuestacion.notificaciones`
  en todo el repositorio en esta sesión.
- **Corrección a un hallazgo previo**: `crear_notificacion` documenta en su propio
  docstring (`service.py:25-28`) que la llaman "otros módulos como efecto secundario
  (eventos, automatizaciones)", pero `eventos/service.py` **no** importa ni llama a
  `crear_notificacion` — confirmado por lectura completa de sus imports
  (`eventos/service.py:1-12`) y por `Grep` de `notif` (case-insensitive) sobre todo
  `eventos/`, sin resultados. El docstring está desactualizado respecto del código
  real: solo `automatizaciones/` es consumidor de negocio hoy. Ver
  [`decisiones.md`](./decisiones.md) y [`pendientes.md`](./pendientes.md).
- **Bypass confirmado desde `extraccion_validacion/`**: `services/presupuestacion/
  extraccion/repository.py:101-102` define su propia función `crear_notificacion` que
  inserta directo contra la tabla `notificaciones`, sin pasar por
  `notificaciones.service.crear_notificacion` — no genera ninguna fila en
  `notificacion_entregas` ni respeta `notificacion_preferencias`. Ya documentado en
  detalle desde el otro lado en
  [`../extraccion_validacion/pendientes.md`](../extraccion_validacion/pendientes.md)
  (P2, "Bypass de `notificaciones/`"); confirmado desde esta sesión que sigue así
  (`extraccion/repository.py:101-102`, `extraccion/service.py:119-134`
  `_notificar_reemplazo_comparativa`). Ver [`casos_de_uso.md`](./casos_de_uso.md).
- `services/presupuestacion/main.py:19`, `:54` monta `notificaciones_router` sin
  prefijo adicional (`tags=["notificaciones"]`).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — modelo de datos multi-canal (notificación +
  entregas por canal + preferencias) y el patrón de decisión caso por caso de
  `user_client`/`service_client` en el router.
- [`base_de_datos.md`](./base_de_datos.md) — tablas `notificaciones`,
  `notificacion_entregas`, `notificacion_preferencias`, columnas, `CHECK`s, RLS, CRUD.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-NOTIFICACIONES-NNN).
- [`flujo.md`](./flujo.md) — flujo de `crear_notificacion` con generación de entregas
  multi-canal, flujo de marcado leída/archivada, flujo de preferencias.
- [`estados.md`](./estados.md) — estados de notificación (leída/no leída/archivada) y
  de entrega (`pendiente` y los 4 valores del `CHECK` que ningún código escribe jamás).
- [`casos_de_uso.md`](./casos_de_uso.md) — los 5 endpoints (todos scopeados al
  usuario), quién consume `crear_notificacion` internamente, el bypass de
  `extraccion_validacion/`.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-NOTIFICACIONES-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3, con foco en la
  ausencia total de envío real y la fortaleza de los 2 tests con RLS real.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client`, ver
[`../core/`](../core/) — no se repite esa documentación acá. Para el motor que hoy es
el único consumidor de negocio de este módulo, ver
[`../automatizaciones/`](../automatizaciones/).
