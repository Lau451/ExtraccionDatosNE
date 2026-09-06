# Decisiones de diseño — PCP

Numeración D-PCP-NNN, correspondiente 1:1 con D1-D12 de
`openspec/changes/gestor-pcp/design.md` (letra original entre paréntesis).
Resumidas en palabras propias — el texto completo de cada decisión, con sus
citas de código y de esquema, vive en `design.md`.

### D-PCP-001 (D1) — Módulo top-level, fachada unidireccional

**Decisión**: `services/pcp/` vive como hermano de `services/terceros/` y
`services/productos/`, no como submódulo de `services/presupuestacion/`.
`services/pcp/**` solo puede importar `services.presupuestacion.pricing.
service`, `services.presupuestacion.notificaciones.service`,
`services.terceros.api` y `services.productos` — nunca el `repository` de
otro módulo. `services/presupuestacion` solo importa `services.pcp` desde
`main.py` (el montaje del router).

**Motivo**: PCP es un dominio de Compras con tablas, roles y ciclo de vida
propios; enterrarlo bajo `presupuestacion/` convertiría una futura extracción
en un segundo refactor.

**Verificación**: `tests/pcp/test_dependencias.py` (`ast`, mismo criterio
que `tests/terceros/test_dependencias.py`) — re-confirmado en verde en cada
fase que agregó un import cross-módulo nuevo (PR6 catálogo, PR7 negociación,
PR9 consultas, PR11 mensajería/notificaciones).

### D-PCP-002 (D2) — Header + renglón, con snapshot inmune a la regeneración

**Decisión**: `pcp` es 1:1 con un `presupuesto` de origen (como máximo un PCP
abierto por presupuesto). `pcp_renglones` ancla en `item_proceso_id` — nunca
`presupuesto_items.id`, que se borra e inserta de nuevo en cada regeneración
de presupuesto (RN-PRICING-008) — y guarda `cantidad`/`precio_referencia`
como snapshots tomados al momento de la selección, sin FK a
`presupuesto_items`.

**Motivo**: un PCP que negocia contra un `presupuesto_items.id` quedaría
huérfano la próxima vez que Comercial regenere el presupuesto.

**Sin columna de costo en ninguna tabla del módulo**: el valor siempre se
deriva en lectura desde `precios_proveedor`/`costos_productos` — cachearlo
lo desincronizaría en cuanto esas tablas cambien, ya que las filas de PCP no
se recalculan en vivo.

### D-PCP-003 (D3) — Catálogo real, no derivado del historial de precios

**Decisión**: `producto_proveedores` es una asociación explícita, con alta
ad-hoc durante la gestión de un PCP. Arranca vacío.

**Motivo**: derivar el catálogo de `precios_proveedor` confundiría "quién
cotizó alguna vez" con "quién puede cotizar" — un proveedor nuevo, que nunca
cotizó, nunca podría aparecer como opción.

### D-PCP-004 (D4) — `no_cotiza` como resultado de primera clase, sin tocar `precios_proveedor`

**Decisión**: `pcp_renglon_resultados` guarda el *resultado* de la
negociación (`precio_obtenido | no_cotiza | sin_respuesta`), separado de
`precios_proveedor`, que sigue siendo el registro de precio. Invariante:
`precio_obtenido` ⟺ `precio_proveedor_id NOT NULL`. Solo `precio_obtenido`
escribe una fila real en `precios_proveedor`.

**Motivo**: un sentinel de precio (`0` o `NULL`) para `no_cotiza` rompería el
`CHECK (>= 0)` de `precios_proveedor` o le entregaría al motor de pricing un
producto gratis. Modelar el resultado como su propia tabla evita fabricar
nunca un precio falso.

**Reuso**: la misma fila de `pcp_renglon_resultados` sirve tres veces —
`seleccionar_proveedores` (PR5) la crea en `sin_respuesta`, `registrar_
resultado` (PR7) la transiciona, `agrupar_renglones` (PR9) la usa como
prueba de "renglón asignado al proveedor P" — ver `base_de_datos.md`.

### D-PCP-005 (D5) — `plazo_pago_dias` migra a FK, con rollback de un release

**Decisión**: `precios_proveedor` gana `condicion_pago_id`/`forma_pago_id`
(FK compuesta a `condiciones_pago`/`formas_pago`), backfilleadas desde el
`plazo_pago_dias INTEGER` legado. Ese entero sobrevive nullable y sin uso por
código nuevo durante al menos un release.

**Motivo**: mismo patrón de `terceros-modelo` para `clientes`/`proveedores`
— unificar la representación de condiciones de pago sin una migración
disruptiva de un solo paso.

**Verificado, no un bug**: `tasks.md` 7.5 confirma explícitamente por test
que registrar un resultado de negociación (1) nunca modifica
`costos_productos` y (2) nunca afecta `precios_proveedor` de otro renglón —
dos renglones sobre el mismo producto, con `item_proceso_id` distintos,
mantienen su aislamiento total. Esto no fue un defecto a corregir: fue una
propiedad de diseño (el aislamiento por `item_proceso_id`) que se verificó
empíricamente en vez de asumirse.

### D-PCP-006 (D6) — Historial dedicado y append-only

**Decisión**: `pcp_historial` no extiende el `EntidadAuditable` de 5 valores
de `auditoria/models.py`. Append-only por ausencia total de políticas RLS de
UPDATE/DELETE.

**Motivo**: extender el Literal cerrado arrastraría PCP al router de
auditoría Comercial y a su matriz de visibilidad, sin necesidad.

**Hallazgo real**: el GRANT explícito (`SELECT, INSERT` a `authenticated`) no
es lo que impide el UPDATE/DELETE — Supabase ya otorga `ALL` a
`authenticated` en toda tabla nueva vía `ALTER DEFAULT PRIVILEGES` a nivel de
proyecto, sin importar lo que declare la migración. RLS es la única barrera
real (acá y en cualquier tabla del proyecto). El comentario original del
código asumía una defensa en profundidad GRANT+RLS que no existe; corregido
en `services/pcp/historial/service.py`.

### D-PCP-007 (D7) — `reglas_pcp`, seam sin motor

**Decisión**: tabla + FKs referentes únicamente. Sin filas, sin código de
servicio, sin motor de reglas.

**Motivo**: dejar el schema listo para cuando `origen='regla'` se escriba
por primera vez, sin construir un motor que el proposal explícitamente dejó
fuera de alcance (`reglas_pricing` tiene la forma correcta a imitar más
adelante — Compras-owned, no el motor genérico de `automatizaciones`).

### D-PCP-008 (D8) — Import legado idempotente por `codigo_legacy`

**Decisión**: `pcp_legacy_map` + RPC `upsert_pcp_legacy`, mirror de
`upsert_terceros_legacy` — mismo `#variable_conflict use_column` desde el
primer intento, para no repetir el bug de columna ambigua que
`terceros-modelo` corrigió después en su `0009`.

**Estado real**: la RPC y la tabla ya viven en el schema
(`0012_pcp_extras.sql`), pero **`services/pcp/imports/` no existe** — Fase 8
de `tasks.md` (tareas 8.1-8.8) quedó deliberadamente sin implementar. Bloqueo
real, no negligencia: se necesita el nombre exacto del campo de renglón en
el export legado y su regla de matching contra `item_proceso_id`, y ese
archivo real todavía no fue provisto. Nada del resto del módulo asume que el
import existe.

### D-PCP-009 (D9) — Consulta agrupada, PDF sin dependencia AGPL, puerto de envío

**Decisión**: `pcp_consultas` sin `pcp_id` — el agrupamiento many-to-many
real vive en `pcp_consulta_renglones`. PDF generado con `reportlab` (BSD),
no `pymupdf` (dual-licenciado AGPL/comercial, descartado explícitamente por
el usuario para este caso de uso más central), driven desde plantillas
Jinja2, detrás de un puerto `PdfRenderer` para poder cambiar de librería sin
tocar el resto del módulo. Envío saliente detrás de `MensajeriaPort`
(`enviar_email`/`enviar_whatsapp`); el adaptador por defecto
(`LoggingMensajeriaAdapter`) no envía nada real. Ningún proveedor de
mensajería se nombra en código ni en el valor por defecto de configuración.

**Motivo**: aislar la integración externa (proveedor de email/WhatsApp,
todavía sin decidir) del resto del módulo, que debe poder enviarse y
probarse sin esa decisión resuelta.

### D-PCP-010 (D10) — Feedback loop de dos fases, ambas ya implementadas

**Decisión**: cerrar un PCP dispara Fase A (email del resultado al
solicitante, siempre) y, si `PCP_REPRICING_AUTOMATICO` está activo, Fase B
(notificación interna + repricing automático si el presupuesto sigue
abierto).

**Hallazgo real y corregido — orden transición/validación en `cerrar_pcp`
(PR11)**: la primera implementación de `negociacion/service.py::cerrar_pcp`
corría las validaciones que pueden lanzar `ValidationError` (¿tiene
`solicitante_id`? ¿se puede resolver su email?) *después* de invocar
`gestion_service.cambiar_estado`. Como esa función persiste su `UPDATE` de
inmediato — sin una transacción de aplicación que envuelva el resto de
`cerrar_pcp` — y `'cerrada'` no tiene transiciones salientes
(`_TRANSICIONES_PERMITIDAS`), un PCP sin solicitante habría quedado
**cerrado para siempre sin completar nunca el feedback loop**, sin ninguna
forma de reabrirlo ni reintentar. El orquestador encontró y corrigió esto
después de la implementación del sub-agente: ahora `cerrar_pcp` lee el PCP
(sin mutarlo, vía `gestion_service.obtener_pcp`) y corre todas las
validaciones *antes* de invocar `cambiar_estado` — documentado explícitamente
en el docstring de la función. Cubierto por
`tests/pcp/negociacion/test_cerrar_pcp.py::test_cerrar_pcp_sin_solicitante_lanza_validation_error`
(triangulación: cero llamadas a mensajería, PCP nunca cerrado).

**Hallazgo real — el `CHECK` de `notificaciones.tipo` en base no es
"aditivo" solo por editar el `Literal` de Pydantic**: agregar
`'pcp_cerrada'` al `Literal` de `TipoNotificacion`
(`services/presupuestacion/notificaciones/models.py`) pasa la validación de
FastAPI, pero `notificaciones` tiene su propio `ck_notif_tipo CHECK (tipo IN
(...))` en la base real que no incluía ese valor — una escritura real habría
fallado con `23514` en tiempo de ejecución pese a que el código "ya estaba
implementado". Se descubrió por una corrida real de test de integración
contra el proyecto de test (no un chequeo en tiempo de import), y requirió
una migración no planeada: `0013_pcp_notificacion_tipo.sql`, que ensancha el
`CHECK` (aditivo, ningún valor existente se toca). Aprendizaje: un `Literal`
de Pydantic y un `CHECK` de Postgres son dos contratos independientes que
hay que ensanchar juntos — uno no implica el otro.

### D-PCP-011 (D11) — RLS y roles

**Decisión**: lectura restringida a `compras`/`gerencia`/`admin`
(+`superadmin`, convención estándar); escritura a `admin`/`gerencia`/
`compras` (idéntica a la política de `precios_proveedor`).
`comercial`/`lider_comercial` no ven pantallas de PCP en absoluto.

**Motivo**: confirmado explícitamente por el usuario — más angosto que el
borrador inicial de lectura tenant-wide.

**Verificación end-to-end**: `tests/pcp/test_matriz_roles.py` (`tasks.md`
12.2) cubre los 6 routers reales de `services/pcp/` montados en la app real,
confirmando que un rol fuera de `ROLES_LECTURA_PCP` es rechazado en los 10
endpoints GET y que un rol fuera de `ROLES_ESCRITURA_PCP` (incluido
`superadmin`, que lee pero no escribe) es rechazado en los 9 endpoints
POST/PATCH sin crear ni modificar ninguna fila. Esa misma suite encontró,
como efecto colateral, un defecto preexistente (no introducido por esta
fase): `listar_pcp`/`listar_renglones`/`listar_proveedores_producto` filtran
incondicionalmente por `usuario.drogueria_id` sin el bypass `es_superadmin`
que sí tienen `obtener_pcp`/`cambiar_estado`/`cerrar_pcp` — para
`superadmin` (`drogueria_id` NULL por diseño), eso produce un error de
Postgres (`invalid input syntax for type uuid: "None"`) en vez de una lista
vacía o completa. Documentado con `xfail(strict=True)` en la suite en vez de
corregido silenciosamente (fuera del alcance de esta fase de documentación);
queda como seguimiento para un change posterior.

### D-PCP-012 (D12) — Sugerencias como consultas, no tablas

**Decisión**: `pcp-sugerencias` no agrega schema. Agrupación por cantidad:
agregación de `pcp_renglones` por `producto_id` con más de un `pcp_id`
distinto dentro de una ventana de días a la fecha de entrega. Reutilización
de precio reciente: lectura directa de `v_precios_especiales_vigentes`
(ya filtra vigencia), sin reimplementación en Python.

**Motivo**: una heurística que no funciona se corrige con un cambio de
query, no con una migración.
