# Roadmap — Backend de Presupuestación

El backend quedó cerrado y auditado (ver auditoría de seguridad de 2026-07-14, 7 commits
sobre `dev` entre `7cb0aad` y `ab4a8da`). Este documento consolida lo que quedó pospuesto
**a propósito** durante el desarrollo — no es una lista de bugs ni de tareas urgentes, es
documentación de intención para quien retome el proyecto sin el contexto de las sesiones
donde se decidió cada corte de alcance. Nada de esto bloquea el uso actual del backend.

## Del schema / modelo

### `orden_compra` en `extraccion/`

`POST /extracciones/{id}/validar` materializa `licitacion` y `comparativa`, pero
`orden_compra` levanta `ValidationError` ("todavía no tiene materialización
implementada"). Se pospuso porque el módulo de extracción de `app/` que generaría estos
`extraction_results` no existe todavía — no había pipeline real contra el cual construir
ni probar. Cuando exista, construir `materializar_orden_compra` contra datos reales de
ese pipeline, **no contra la lectura original del spec**: la materialización de
licitación/comparativa terminó divergiendo del spec una vez que hubo CSVs reales para
probar (columnas que no estaban, formatos distintos), y no hay razón para pensar que
orden_compra sea diferente.

### Versionado de reglas de automatización

El spec sugiere versionado para `reglas_automatizacion` (mismo patrón
`version_numero`/`es_vigente`/`reemplaza_id` que sí se implementó para `comparativas`).
Se descartó para esta ronda porque no había ninguna regla real en producción que lo
justificara. Es barato de agregar después: `acciones_ejecutadas.regla_id` ya apunta a la
fila exacta que disparó cada acción, así que el historial de ejecución no se pierde
aunque la regla se edite sin versionar; solo faltaría agregar las columnas y la lógica de
"no editar, versionar" el día que haga falta auditar cambios de la regla en sí.

### `workflow_transiciones`

Pospuesto — los estados (`eventos`, `procesos_comerciales`, `presupuestos`,
`comparativas`, `ordenes_compra`) usan columnas `estado` con transiciones validadas a
mano en cada `service.py`, no una tabla de transiciones configurable. El diseño quedó
deliberadamente extensible: agregar una tabla de transiciones para hacer el workflow
configurable por tipo de proceso no debería requerir rediseñar las tablas de estado
existentes, solo una capa de validación que las consulte antes de los `UPDATE
estado=...` que ya existen.

### `proveedor_producto_alias`

Tabla y columnas ya existen en el schema (espejo por proveedor de
`cliente_producto_alias`, pensada para el matching proveedor→producto del §2 del spec),
pero no tiene ningún código propio — ni lectura ni escritura, confirmado explícitamente
durante la auditoría de seguridad. No bloquea el matching cliente→producto que sí está
implementado; el matching proveedor→producto nunca se pidió construir en esta ronda.

## De funcionalidad

### Motor de automatizaciones y scheduler de eventos recurrentes

`disparar_reglas()`/`procesar_acciones_pendientes()` (`automatizaciones/service.py`) y
`generar_instancias_recurrentes()` (`eventos/service.py`) están completos y con tests de
integración, pero ninguno está conectado a un disparador real: no hay cron/worker
corriendo `procesar_acciones_pendientes()`/`generar_instancias_recurrentes()`
periódicamente, y ningún flujo de negocio (confirmar una OC, adjudicar una licitación)
llama a `disparar_reglas()` todavía. Es el "motor mínimo, sin conectar" que pedía el spec
para esta ronda — conectarlo (agregar el cron/worker, identificar en qué puntos del
código debería dispararse cada `evento_disparador`) es la próxima ronda.

### Envíos reales de notificaciones (email/WhatsApp/push)

El modelo está completo: `notificaciones`, `notificacion_entregas` (una fila por canal),
`notificacion_preferencias` (opt-in por usuario×tipo×canal). Falta la integración con un
proveedor real de envío — toda entrega queda en `notificacion_entregas.estado='pendiente'`
para siempre; el canal se calcula bien pero nada lo despacha. Necesita elegir
proveedor(es) por canal (ej. Resend/SendGrid para email, alguna API de WhatsApp Business)
y un worker que tome las entregas pendientes y las procese, análogo al de
automatizaciones.

## De la transición al frontend nuevo

### Identificación opcional en `extraccion/` — pasa a obligatoria cuando se retire el HTML viejo

`services/extraccion/auth.py` (`get_usuario_id_actual`) identifica al usuario real
cuando `POST /procesar` recibe un JWT válido (para `processing_sessions.subido_por`),
pero es **opcional**, no un gate: sin header `Authorization`, la request sigue
funcionando exactamente igual que antes (sin atribución), porque el HTML viejo
(`templates/`, `static/main.js`) nunca mandó ni va a mandar un token — no tiene ningún
concepto de sesión, y corre en un servidor interno sin exposición a internet, sin
cuentas creadas todavía para nadie. El resto de `extraccion/` (`licitaciones.py`,
`extraction_results.py`, `clientes.py`, `/api/documentos*`) sigue sin ningún tipo de
identificación, por la misma razón.

Cuando el frontend nuevo reemplace al HTML viejo (y con él, el onboarding real de
cuentas para la droguería), esto debería pasar a ser obligatorio en todos esos
endpoints — no antes, porque exigirlo ahora requeriría enseñarle a usar login a gente
que va a usar un sistema que está por descontinuarse, para repetir el mismo onboarding
después en el sistema que lo reemplaza.

## De seguridad / testing

### Allowlist de campos en `historial_cambios`

`core/audit.py:registrar_cambio` no valida qué `campo` puede auditarse por entidad — hoy
es seguro porque ningún call site pasa un campo sensible de `presupuesto` (costo,
márgenes) al historial, pero nada a nivel de código lo impediría si un futuro cambio lo
hiciera, y `GET /historial/{entidad}/{id}` es legible por roles (`comercial`,
`lider_comercial`) a los que el resto del sistema les oculta esos mismos datos
explícitamente. Detectado en la auditoría de seguridad de esta sesión y documentado como
comentario en el propio `core/audit.py`.

### Tests de aislamiento cross-tenant real

Esta sesión agregó `crear_usuario_autenticado` (`tests/conftest.py`) — el primer fixture
del proyecto que arma un `Client` autenticado con un JWT real en vez de `service_client`
(que bypasea RLS por completo). Se usó para 2 tests puntuales de notificaciones
(confirmar que RLS sola, sin el filtro de código, contiene el acceso a datos ajenos). Con
el fixture ya disponible, valdría la pena ampliar la cobertura a aislamiento cross-tenant
explícito: confirmar empíricamente que un `comercial` de una droguería no puede ver/tocar
datos de otra droguería, en vez de confiar en que las policies lo dicen en el papel. La
mayoría de los tests del proyecto siguen usando `service_client` y por lo tanto no
ejercitan RLS en absoluto.
