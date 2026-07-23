# Arquitectura — Notificaciones

## Modelo de datos: notificación + entregas por canal + preferencias

Tres tablas, cada una con un rol distinto:

```
notificaciones               notificacion_entregas          notificacion_preferencias
────────────────             ──────────────────────         ──────────────────────────
el AVISO en sí               UNA fila por canal              qué quiere recibir cada
(qué pasó, para quién,       intentado para ese aviso        usuario, por tipo y canal
prioridad, leído/archivado)  (estado de ENVÍO, no de         (opt-in, sin fila = default
                              lectura)                        del backend)

id                            id                              id
drogueria_id                  notificacion_id ──FK CASCADE──▶ (n/a, independiente)
destinatario_id                drogueria_id                   usuario_id
tipo                           canal                          drogueria_id
titulo / mensaje               estado='pendiente' (fijo)      tipo
prioridad                      destino / proveedor_externo /  canal
url_destino                    referencia_externa (sin usar)  habilitada
origen                         intentos / enviado_at /
proceso_comercial_id / ...     error_msg (sin usar)
  (5 FK polimórficas +
  accion_ejecutada_id, todas
  sin leer por el código Python)
leida_at / archivada_at
metadata
```

`crear_notificacion` (`service.py:11-62`) es la única función que escribe en las tres
tablas en una sola operación: inserta la notificación, resuelve las preferencias del
destinatario para ese `tipo`, e inserta una fila de entrega por cada canal habilitado
(o el default `("web",)` si no hay preferencia cargada). Ver
[`flujo.md`](./flujo.md) para el detalle paso a paso y
[`base_de_datos.md`](./base_de_datos.md) para columnas y `CHECK`s completos.

## `crear_notificacion` es de uso interno, no un endpoint público

Cita textual completa del docstring (`service.py:25-28`):

> "Crea una notificación y una fila en notificacion_entregas por cada canal habilitado
> del destinatario para ese tipo. Sin preferencia cargada → default del backend (solo
> 'web'). Función de uso interno: la llaman otros módulos como efecto secundario
> (eventos, automatizaciones), no un endpoint público."

Confirmado por `router.py` completo: ninguno de los 4 endpoints monta
`crear_notificacion` — el único camino HTTP para crear una notificación en este módulo
no existe; toda notificación nace desde código Python de otro módulo (ver
"corrección" abajo) o desde el bypass de `extraccion/repository.py:101-102`
(documentado en [`../extraccion_validacion/pendientes.md`](../extraccion_validacion/pendientes.md)).

**Corrección al docstring**: aunque menciona "eventos" como llamador, `eventos/
service.py` no importa `notificaciones` en ningún punto (`eventos/service.py:1-12`,
imports completos, y `Grep` de `notif` case-insensitive sobre todo `eventos/` sin
resultados). El único consumidor Python real es `automatizaciones/service.py:16,115`.
Ver [`decisiones.md`](./decisiones.md) D-NOTIFICACIONES-005.

## Patrón de decisión caso por caso: `user_client` vs `service_client` en el router

A diferencia de otros módulos donde la elección de cliente sigue un patrón uniforme
(p. ej. "lectura=`user_client`, escritura=`service_client`" en `automatizaciones/`),
`notificaciones/router.py` decide caso por caso, con comentarios explícitos que citan
las policies RLS reales verificadas antes de decidir:

- `GET /notificaciones/no-leidas` → `user_client` (`router.py:23-30`), con comentario
  citado completo:

  > "user_client (no service_role): la policy no_sel de RLS ya permite
  > destinatario_id = auth.uid() -- RLS queda como red de contención real si el
  > filtro de destinatario_id del repository alguna vez se rompe."

- `GET /notificacion-preferencias` → `user_client` (`router.py:47-53`), con comentario:

  > "user_client: la policy np_sel tiene la misma rama usuario_id = auth.uid()."

- `PUT /notificacion-preferencias` → `user_client` (`router.py:56-66`), con comentario:

  > "user_client: np_ins y np_upd permiten ambas usuario_id = auth.uid() (confirmado
  > contra las policies reales antes de migrar este endpoint puntual)."

- `PATCH /notificaciones/{id}/leer` y `PATCH /notificaciones/{id}/archivar`
  (`router.py:33-44`) **no inyectan ningún cliente en el router** — llaman a
  `marcar_leida_para_endpoint`/`marcar_archivada_para_endpoint`
  (`service.py:106-111`), que resuelven `get_service_client()` internamente, **sin
  ningún comentario que justifique por qué estos dos no siguen el mismo patrón** de
  verificar la policy `no_upd` (que también permite `destinatario_id = auth.uid()`,
  ver [`base_de_datos.md`](./base_de_datos.md)) y usar `user_client` como los otros
  tres. Ver [`decisiones.md`](./decisiones.md) D-NOTIFICACIONES-003 y
  [`pendientes.md`](./pendientes.md).

Este patrón de "verificar la policy real antes de decidir, y dejar la evidencia en un
comentario" es, hasta donde se auditó en esta sesión, específico de este módulo — no
se encontró un comentario equivalente en `automatizaciones/router.py` ni en
`eventos/router.py`, que siguen la regla fija "lectura=`user_client`,
escritura=`service_client`" sin cuestionarla endpoint por endpoint.
