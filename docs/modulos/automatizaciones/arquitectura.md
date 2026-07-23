# Arquitectura — Automatizaciones

## Modelo evento-condición-acción

El módulo implementa un motor de reglas clásico "if this then that", con tres piezas:

1. **Disparador (`evento_disparador` + `entidad_objetivo`)**: un string libre
   (`evento_disparador: str`, `models.py:20`) más un `Literal` cerrado de 7 valores
   (`entidad_objetivo: EntidadObjetivo`, `models.py:6-9, 21`). No hay validación de que
   `evento_disparador` pertenezca a un vocabulario cerrado — es texto libre que el
   llamador de `disparar_reglas` decide (p. ej. `"completado"` en los tests,
   `test_service.py:17`).
2. **Condición (`condicion: dict | None`)**: formato deliberadamente simple, un único
   par `{"campo": ..., "valor": ...}` evaluado como igualdad exacta contra un dict de
   datos arbitrario (`_evaluar_condicion`, `service.py:77-84`). `None` es comodín
   (siempre matchea, `:80-81`). No hay soporte para `AND`/`OR`, operadores de
   comparación (`>`, `<`, `in`), ni anidamiento — confirmado por lectura completa de la
   función (8 líneas).
3. **Acción (`tipo_accion` + `parametros_accion`)**: un `Literal` cerrado de 8 valores
   (`models.py:10-13`) del cual solo 2 tienen implementación real en
   `_ejecutar_accion` (`service.py:87-131`). Ver [`reglas.md`](./reglas.md).

## Dependencias hacia otros módulos de negocio

A diferencia de todos los módulos de soporte documentados hasta ahora (Eventos, Core),
Automatizaciones **sí** importa código Python de otros dos módulos de negocio
directamente, sin pasar por HTTP:

- **`eventos`** (`service.py:14-15`):
  ```python
  from services.presupuestacion.eventos.models import EventoCreate
  from services.presupuestacion.eventos.service import crear_evento
  ```
  Usado en `_ejecutar_accion` (`:99-110`) cuando `tipo_accion == "crear_evento"`: arma
  un `EventoCreate` a partir de `parametros_accion` más la columna FK de la entidad que
  disparó la regla, y llama a `crear_evento(client, drogueria_id=..., body=body,
  usuario_id=..., origen="automatico")` — el único punto de todo el repositorio que
  pasa `origen="automatico"` explícitamente (confirmado del lado de `eventos/` en
  `docs/modulos/eventos/casos_de_uso.md:53-58`, ya alineada con el nombre real de la
  función). La función se llama `_ejecutar_accion` (`service.py:87-131`, 267 líneas
  totales), sin sufijo `_inmediata`, y se usa tanto para el modo `inmediato` como para
  el modo `cola` (ver [`flujo.md`](./flujo.md)).
- **`notificaciones`** (`service.py:16`):
  ```python
  from services.presupuestacion.notificaciones.service import crear_notificacion
  ```
  Usado en `_ejecutar_accion` (`:112-129`) cuando `tipo_accion == "enviar_notificacion"`:
  llama a `crear_notificacion(client, drogueria_id=..., destinatario_id=parametros[
  "destinatario_id"], tipo=parametros["tipo"], titulo=parametros["titulo"], ...,
  origen="automatizacion", relaciones=relaciones)`. `notificaciones/service.py:25-28`
  documenta que es "función de uso interno: la llaman otros módulos como efecto
  secundario (eventos, automatizaciones), no un endpoint público" — pero ese comentario
  es impreciso: `docs/modulos/notificaciones/decisiones.md` (D-NOTIFICACIONES-005)
  confirmó por grep que `eventos/service.py` **no** llama a `crear_notificacion` en
  ningún punto; `automatizaciones/` es el único consumidor real hoy. Ver
  [`../notificaciones/`](../notificaciones/) para la documentación completa del módulo
  consumido.

Ambas dependencias son excepciones de KeyError/TypeError capturadas explícitamente en
`_ejecutar_accion` (`:105-106`, `:127-128`) para convertir parámetros mal formados en un
resultado `(False, mensaje)` en vez de dejar que la excepción se propague sin control.

## Por qué el motor está desconectado

El propio código responde esta pregunta de forma explícita — no es una omisión sin
documentar, sino una decisión de alcance declarada en el docstring de `disparar_reglas`
(`service.py:148-154`, cita completa en [`README.md`](./README.md)): es "el motor
mínimo, sin conectar a los eventos de negocio todavía" que pedía el spec para la ronda
en la que se construyó, y conectarlo a disparadores reales (confirmar una OC, adjudicar
una licitación) queda para una ronda posterior. `services/presupuestacion/ROADMAP.md:53-62`
confirma el mismo estado desde la perspectiva de planificación del equipo, agrupando
este módulo junto con `eventos.generar_instancias_recurrentes()` bajo el mismo pendiente
de "scheduler/worker real". [IMPLEMENTADO] — confirmado por lectura de ambos textos y
por `Grep` exhaustivo de callers (ver [`README.md`](./README.md) y
[`pendientes.md`](./pendientes.md)).

## Patrón `service_client` vs `user_client`

Igual que en otros módulos de `presupuestacion/`: los 3 wrappers `_para_endpoint`
(`crear_regla_para_endpoint` `:63-64`, `actualizar_regla_para_endpoint` `:67-72`)
resuelven `get_service_client()` internamente (sin RLS); los endpoints de **lectura**
(`GET /automatizaciones/reglas`, `GET /automatizaciones/metricas`) inyectan
`user_client` con `Depends(get_user_client)` (`router.py:17`, `:28`, `:52`). El motor
(`disparar_reglas`, `procesar_acciones_pendientes`) recibe un `client: Client` genérico
sin resolverlo internamente — quien lo invoque (hoy, solo los tests) debe pasar
explícitamente el cliente correcto. No hay ningún wrapper `_para_endpoint` para el
motor, coherente con que no está conectado a ningún endpoint ni disparador real. Ver
[`../core/`](../core/) para el detalle general del patrón.

## No depende de Core `audit.py`

A diferencia de `eventos/`, que audita sistemáticamente cada cambio vía
`core/audit.py` (`registrar_cambio`/`registrar_evento_ciclo_vida`), `automatizaciones/`
**no importa `core.audit` en ningún archivo** — confirmado por `Grep` de
`registrar_cambio|core\.audit` sobre `services/presupuestacion/automatizaciones/` en
esta sesión, sin resultados. Las únicas dos formas en que quedan rastros de una acción
ejecutada son la propia fila de `acciones_ejecutadas` (log estructurado del motor,
distinto de `historial_cambios`) y, si la acción crea un evento, la auditoría que
`eventos.crear_evento` haga por su cuenta (fuera del control de este módulo). Ver
[`base_de_datos.md`](./base_de_datos.md).
