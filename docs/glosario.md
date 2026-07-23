# Glosario — Drogueria Nueva Era

Glosario conceptual de términos de negocio y técnicos usados en el sistema, pensado
para cualquier persona que se sume al equipo (técnica o no). Cada entrada indica una
definición breve y el/los módulo(s) donde aparece el concepto, con referencia a
`docs/modulos/<módulo>/`. No es una auditoría de comportamiento línea por línea — para
eso están los documentos de cada módulo (`reglas.md`, `estados.md`, `pendientes.md`,
etc.); acá se prioriza que el término se entienda.

Convención de referencia: "módulo X" siempre remite a `docs/modulos/X/README.md` salvo
que se indique un documento distinto.

---

## A

**Activar / desactivar usuario**
Mecanismo para bloquear el acceso de un usuario sin borrar su cuenta ni su historial:
`PATCH /usuarios/{id}/activo` marca `usuarios.activo = false`, y el bloqueo real ocurre
en cada request posterior — `get_current_user` rechaza con 401 a cualquier usuario con
`activo = False`, aunque su JWT de Supabase siga técnicamente vigente (son dos sistemas
distintos: desactivar en `usuarios` no invalida el token ya emitido). Solo
`superadmin`/`admin` pueden activar/desactivar, nadie puede hacerlo sobre su propia
cuenta, y `superadmin`/`sistema` están protegidos de esta vía. No existe un mecanismo
equivalente para el registro de la empresa (`droguerias.activa` no tiene ningún efecto
funcional confirmado todavía). Ver módulos `usuarios` y `core`.

**Adjudicación / Adjudicada**
Marca que indica que una oferta de un proveedor (`ofertas_items`) fue la elegida para
comprarse dentro de una comparativa. Puede ser una estimación automática
(`adjudicacion_estimada`, calculada al validar una comparativa) o una confirmación
oficial (`adjudicada = true`, escrita al confirmar una orden de compra). Ver módulos
`comparativas`, `compras`, `extraccion_validacion`.

**Alias de cliente**
Relación guardada (`cliente_producto_alias`) que asocia la descripción textual libre
que un cliente usó en una licitación/cotización con un producto exacto del catálogo,
una vez que un humano confirmó esa asociación. Si el mismo cliente vuelve a usar la
misma descripción, el sistema la matchea automáticamente sin volver a puntuar
candidatos. Ver módulo `matching`.

**Alias de proveedor**
Concepto espejo de "alias de cliente" pero para proveedores (`proveedor_producto_alias`).
Existe como tabla en el esquema de base de datos pero **no tiene código propio todavía**
— es una funcionalidad pendiente. Ver módulo `matching`.

**Auditoría (`historial_cambios`)**
Registro centralizado de cambios de campo y eventos de ciclo de vida sobre entidades de
negocio, escrito por `core/audit.py` y expuesto de solo lectura por el endpoint
`GET /historial/{entidad}/{entidad_id}`. No todos los módulos lo usan de forma
consistente: `eventos` y `presupuestos` auditan sistemáticamente; `clientes`,
`catalogo` e `imports` no auditan ninguna de sus mutaciones. Ver módulo `core`.

## B

**Bearer token / JWT**
Token de autenticación que el frontend envía en el header `Authorization: Bearer <token>`
en cada llamada HTTP. El backend lo verifica contra el JWKS de Supabase
(`shared/auth_jwt.py`) para identificar al usuario y resolver su rol. Ver módulo `core`
y módulo `frontend_login`.

## C

**Catálogo**
El maestro de productos, categorías, proveedores, costos y stock por depósito de la
droguería. Es dueño de las tablas `productos`, `categorias`, `proveedores`,
`costos_productos` y `stock_productos`. Es el módulo con más acoplamiento indirecto del
sistema: 5 módulos distintos (`matching`, `comparativas`, `pricing`, `core`, `imports`)
leen o escriben esas tablas sin pasar por el código de `catalogo/`. Ver módulo
`catalogo`.

**Chunk / Chunking**
División de un documento grande (por ejemplo, una comparativa de precios con muchos
renglones) en partes más chicas para que la IA (Gemini) las procese en paralelo y sin
truncar la respuesta por límite de tokens. Si Gemini trunca una respuesta, el sistema
reintenta partiendo el chunk a la mitad. Ver módulo `extraccion_ia`.

**Cliente**
Entidad del maestro de clientes de la droguería: hospitales, obras sociales,
municipios, etc. Tiene contactos, formato de documentos propio (instrucciones para el
prompt de extracción IA) y observaciones asociadas. Distinto del concepto de "cliente
HTTP" (`service_client`/`user_client`, ver más abajo). Ver módulo `clientes`.

**Comparativa**
Documento con ofertas de **varios proveedores** para el mismo conjunto de renglones,
usado para elegir a quién comprarle cada ítem. Se diferencia de una licitación/cotización
(que trae un solo proveedor por renglón). Las comparativas tienen versionado: al cargar
una nueva comparativa vigente para el mismo alcance, la anterior deja de ser vigente
(`es_vigente`). Ver módulos `extraccion_validacion` (quien las crea) y `comparativas`
(quien las lee y permite asignar proveedor manualmente).

**Confianza (matching)**
Puntaje numérico (0-100) que indica qué tan seguro está el algoritmo de fuzzy matching
de que una descripción libre corresponde a un producto candidato. Confianza ≥ 70 marca
el matching como `sugerido`; por debajo, como `pendiente`. Ver módulo `matching`.

**Core**
Módulo de infraestructura transversal (no es una entidad de negocio) que resuelve
errores de dominio, autenticación/autorización, acceso a Supabase, compromiso de stock,
normalización de texto y auditoría. Es consumido, en mayor o menor medida, por
prácticamente todos los módulos de negocio de `services/presupuestacion/`. Ver módulo
`core`.

**Costo (estándar / especial)**
Precio al que la droguería compra un producto. Un **costo estándar** es el costo
histórico versionado por fecha (`costos_productos`); un **costo especial** es un precio
puntual negociado con un proveedor para un cliente o proceso comercial concreto
(`precios_proveedor`), que tiene prioridad sobre el costo estándar al calcular el precio
de venta. Ver módulos `catalogo` y `pricing`.

**Cotización**
Uno de los dos tipos (`Clase`) de proceso comercial, junto con "licitación": el pedido
de precio que un cliente hace a la droguería fuera de un proceso licitatorio formal. Ver
módulo `procesos_comerciales`.

**CUIT / CUIL**
Identificador tributario argentino de una droguería (empresa), validado al crear o
editar una droguería solo por **formato** (`NN-NNNNNNNN-N`, vía regexp) — no se calcula
ni valida el dígito verificador real. Un CUIT con formato correcto pero checksum
inválido (por ejemplo `20-00000000-0`) pasa la validación sin error. Ver módulo
`droguerias`.

## D

**Depósito**
Ubicación física donde se guarda stock de productos. El stock se lleva por producto y
por depósito (`stock_productos`), con cantidad disponible y cantidad comprometida
separadas. Ver módulos `catalogo` y `core` (motor de stock).

**`DomainError`**
Clase base de la jerarquía de excepciones de dominio del backend de presupuestación
(`core/exceptions.py`), con subclases como `NotFoundError`, `ConflictError`,
`ValidationError` y `ForbiddenError`. Se registran centralizadamente como handlers HTTP
de FastAPI, así que cualquier módulo que las levanta obtiene automáticamente el código
de estado HTTP correcto. Ver módulo `core`.

**Drogueria (multi-tenant / `drogueria_id`)**
El sistema está diseñado para dar servicio a más de una droguería (multi-tenant); casi
todas las tablas de negocio tienen una columna `drogueria_id` que aísla los datos de
cada droguería entre sí. Ver módulo `core` y `RLS` más abajo.

## E

**Empresa**
Nombre de negocio/UI para una fila de la tabla `droguerias` — es el mismo concepto, no
una entidad de código separada. El backend y las URLs usan siempre `droguerias`/
`drogueria_id` (incluida la ruta del frontend `/superadmin/empresas`, que gestiona esa
misma tabla); "empresa" es simplemente cómo se lo llama en el vocabulario de negocio y
en las pantallas dirigidas a `superadmin` — decisión consciente de nomenclatura, no una
inconsistencia. Ver módulo `droguerias`.

**Entrega (de orden de compra)**
Registro de mercadería físicamente recibida contra una orden de compra
(`entregas_oc`/`entregas_oc_items`), que ajusta el stock disponible del catálogo en el
mismo paso. Puede ser parcial (recibir menos de lo pedido). Ver módulo `compras`.

**Estado (de un evento)**
Situación en la que se encuentra una tarea operativa (`eventos.estado`): pendiente,
bloqueada (por depender de otro evento no completado), en progreso, completada o
vencida. Ver módulo `eventos`.

**Estado (de un presupuesto)**
Los presupuestos sí tienen una máquina de estados real, con guardas de transición:
`generado` (recién calculado por Pricing) → `en_revision` → `aprobado` → `presentado`
(al presentar, se compromete stock real) y estados terminales adicionales. Es distinto
del estado del proceso comercial (ver siguiente entrada). Ver módulo `presupuestos`.

**Estado (de un proceso comercial)** ⚠️ *ver nota de inconsistencia*
Campo nominal (`procesos_comerciales.estado`, 8 valores posibles) que en teoría
representa en qué etapa está una licitación o cotización. **A diferencia del estado de
presupuesto, este campo no tiene ninguna guarda de transición**: el único módulo que lo
escribe es `presupuestos` (al presentar un presupuesto, fuerza el proceso comercial a
`"presentado"` sin verificar cuál era el estado anterior). El propio módulo dueño de la
tabla (`procesos_comerciales`) nunca escribe este campo. Ver módulos
`procesos_comerciales` y `presupuestos`.

**Estado de entrega de notificación**
Cada notificación puede generar una fila de "entrega" por canal (web, email, whatsapp,
etc.), con un estado que hoy nace siempre en `pendiente` y **nunca cambia**, porque
todavía no hay integración real con ningún proveedor de envío (email, WhatsApp, etc.).
En la práctica, el sistema hoy funciona como un inbox interno, no como un despachador
multi-canal real. Ver módulo `notificaciones`.

**`estado_matching`**
Estado del proceso de matching de un renglón contra el catálogo: `pendiente` (sin
resolver), `sugerido` (candidato automático con confianza suficiente) o `confirmado`
(un humano lo validó, o vino de un alias ya confirmado). También existe `sin_match`
cuando no se pudo asociar a ningún producto. No hay forma de "reabrir" un matching ya
resuelto. Ver módulo `matching`.

**Evento**
Tarea u acción operativa concreta (llamar a un cliente, recibir mercadería, facturar,
hacer seguimiento) que puede depender de un proceso comercial, comparativa, orden de
compra, cliente o proveedor, y puede depender de otro evento anterior (bloqueo lineal).
No confundir con "notificación" (ver más abajo): el propio esquema de base de datos
distingue explícitamente "evento = trabajo, notificación = aviso". Ver módulo `eventos`.

**Extracción (IA)**
Proceso de convertir un documento (PDF, Excel, imagen) en datos estructurados usando
Gemini. Corre en el backend legacy `services/extraccion/` y devuelve un CSV en disco,
sin persistir las filas extraídas en base de datos directamente — solo su metadata
(`extraction_results`). Ver módulos `extraccion_ia` y `extraccion_api`.

**Extracción-Validación**
Módulo puente que toma una extracción IA ya procesada (una fila de `extraction_results`)
y la materializa en tablas de negocio reales: crea renglones (`items_proceso`) para
licitaciones/cotizaciones (disparando matching automático) o comparativas/ofertas para
comparativas de precios. Ver módulo `extraccion_validacion`.

## F

**Fuzzy matching**
Técnica de comparación de texto aproximada (librería `rapidfuzz`, algoritmo `WRatio`)
usada para encontrar el producto del catálogo más parecido a una descripción libre,
cuando no existe un alias de cliente ya confirmado. Ver módulo `matching`.

## I

**Imports**
Módulo de ingesta masiva de maestros (productos, costos, stock, proveedores, clientes)
desde sistemas externos, vía carga en lote por HTTP. Hace upsert por código interno y
desactiva por lote lo que no vino en la carga más reciente. No reutiliza el código de
`catalogo/` ni `clientes/`: reimplementa sus propias queries y, en el caso del
versionado de costos, duplica el mismo algoritmo de `catalogo/` de forma independiente.
Ver módulo `imports`.

**Invitación (alta de usuario)**
Único mecanismo de alta de cuentas del sistema — no existe auto-registro (`signUp`) en
ningún punto del frontend. Un `superadmin`/`admin` crea el usuario desde
`POST /usuarios`, que dispara `client.auth.admin.invite_user_by_email` de Supabase Auth
(sin password asignada por el backend); el destinatario recibe un email y define su
propia contraseña al aceptar la invitación en `/accept-invite`. El mismo mecanismo de
sesión temporal por link se reusa para el reset de contraseña (`/reset-password`). Ver
módulos `usuarios` y `frontend_login`.

**Item de proceso (renglón)**
Cada línea/renglón de una licitación o cotización (`items_proceso`): una descripción de
producto pedida, con cantidad y, eventualmente, el producto de catálogo que le
corresponde una vez resuelto el matching. Ver módulos `procesos_comerciales`,
`matching`, `extraccion_validacion`.

## L

**Licitación**
Uno de los dos tipos (`Clase`) de proceso comercial, junto con "cotización": un proceso
formal de compra pública o privada al que la droguería se presenta con una oferta de
precios. Ver módulo `procesos_comerciales`.

## M

**Margen**
Porcentaje de ganancia que se aplica sobre el costo de un producto para calcular su
precio de venta. El motor de pricing usa una regla de margen (`reglas_pricing`) y decide
entre el precio de mercado (con descuento) o un piso de margen mínimo, con un margen
objetivo como respaldo si no hay dato de mercado. Ver módulo `pricing`.

**Matching**
Proceso de resolver a qué producto exacto del catálogo corresponde la descripción libre
de un renglón de licitación/cotización. Usa primero alias de cliente ya confirmados y,
si no hay, fuzzy matching contra productos activos. Se dispara automáticamente al
materializar una licitación/cotización, no tiene endpoint propio para "correr matching"
manualmente. Ver módulo `matching`.

**Matriz de visibilidad**
Patrón usado en el módulo Presupuestos: existen dos vistas SQL distintas
(`v_presupuesto_comercial`, `v_presupuesto_revision`) que exponen distintos campos según
el rol del usuario que consulta un presupuesto. Ver módulo `presupuestos`.

## N

**Notificación**
Aviso interno dirigido a un usuario (por ejemplo, "se reemplazó la comparativa vigente
del proceso X"), separado del concepto de "evento" (que es una tarea operativa). Cada
notificación puede generar entregas por canal (web, email, whatsapp, sms, push,
webhook) y respeta preferencias configurables por usuario. Hoy, ningún canal envía
realmente nada fuera de la base de datos — ver "Estado de entrega de notificación". Ver
módulo `notificaciones`.

## O

**Oferta (`ofertas_items`)**
Precio propuesto por un proveedor concreto para un renglón dentro de una comparativa.
Puede tener el flag `adjudicada` (compra oficial confirmada) y `adjudicacion_estimada`
(cálculo automático de cuál sería la mejor oferta). Ver módulos `extraccion_validacion`,
`comparativas`, `compras`.

**Orden de compra (OC)**
Documento formal de compra a un proveedor, generado a partir de un proceso comercial ya
ganado. Tiene su propio ciclo: creación, confirmación (que adjudica condicionalmente la
oferta ganadora) y registro de entregas. El esquema tiene columnas preparadas para
versionado de OC (`version_numero`, `es_vigente`, `reemplaza_id`) pero **todavía no
están implementadas** en el código. Ver módulo `compras`.

## P

**Plan (de suscripción)**
Catálogo de solo lectura de planes por droguería (`planes`), con columnas de límites
declarados (`max_usuarios`, `max_documentos_mes`, `almacenamiento_mb`,
`funcionalidades`). Hoy es solo estructura: no tiene CRUD (se carga por SQL directo
contra la base) ni existe ningún código, en ningún backend, que lea esas columnas para
bloquear o limitar algo — cita textual de la migración que lo crea: "sin lógica de
facturación ni enforcement de límites todavía". Una droguería se asocia a un plan vía
`droguerias.plan_id`, gestionado desde el módulo `droguerias`, no desde `planes`. Ver
módulo `planes`.

**Presupuesto**
Documento con el precio de venta calculado para cada renglón de un proceso comercial,
generado por el motor de pricing. A partir de ahí, el módulo `presupuestos` gestiona su
ciclo de vida: revisión, ajuste manual de ítems, aprobación y presentación al cliente
(momento en el que se compromete stock real). Ver módulos `pricing` (lo genera) y
`presupuestos` (gestiona su ciclo de vida).

**Pricing**
Motor de cálculo de precio de venta por ítem de un proceso comercial: resuelve el costo
aplicable (especial o estándar), le aplica una regla de margen y decide el precio final.
También es quien genera (o regenera) el presupuesto asociado a un proceso comercial. Ver
módulo `pricing`.

**Proceso comercial**
Entidad raíz del pipeline comercial: una licitación o cotización dada de alta en el
sistema, de la que después cuelgan renglones (`items_proceso`), matching, presupuesto,
comparativas y órdenes de compra. Ver módulo `procesos_comerciales`.

**Proveedor**
Entidad del maestro de proveedores de la droguería, a quien se le compran productos.
Ver módulos `catalogo` y `compras`.

## R

**Regla de automatización**
Configuración tipo "si pasa X (evento disparador) y se cumple una condición, entonces
ejecutar una acción" (crear evento, enviar notificación, etc.), sobre la tabla
`reglas_automatizacion`. El motor está implementado y testeado, pero **hoy nada en el
código de producción lo dispara** — ni un flujo de negocio real ni un worker/cron. Ver
módulo `automatizaciones`.

**RLS (Row Level Security)**
Mecanismo de Supabase/PostgreSQL que restringe qué filas puede ver o modificar cada
usuario según políticas definidas a nivel de base de datos (por ejemplo, aislar los
datos de cada `drogueria_id`). El backend usa dos tipos de cliente Supabase, ver
`service_client` / `user_client` más abajo. Ver módulo `core`.

**Rol (de usuario)**
Etiqueta que determina qué puede hacer un usuario autenticado dentro del sistema (por
ejemplo, qué endpoints puede invocar vía `require_roles`). Los roles válidos están
definidos como un `Literal` de 6 valores en el módulo `usuarios`. Ver módulos `usuarios`
y `core` (mecanismo de autorización).

## S

**`service_client` / `user_client`**
Los dos tipos de cliente Supabase que usa el backend de presupuestación.
`service_client` opera **sin RLS** (rol de servicio, bypasea las políticas de seguridad
por fila — se usa para operaciones administrativas o de sistema). `user_client` opera
**con RLS**, respetando las políticas de seguridad según el usuario autenticado que hizo
la request. Ver módulo `core`.

**Stock (comprometido / disponible)**
`stock_productos` separa la cantidad físicamente disponible de un producto en un
depósito de la cantidad ya comprometida (reservada por un presupuesto presentado, por
ejemplo, pero todavía no descontada por una entrega real). El motor de stock de Core usa
optimistic locking para ajustar estas cantidades de forma concurrente seguridad. Ver
módulos `core` y `catalogo`.

## U

**Usuario**
Cuenta de una persona que usa el sistema, con un rol asociado. El alta se hace por
invitación por email (ver "Invitación"), nunca por auto-registro. El campo `activo`
**sí tiene efecto funcional implementado**: activar/desactivar (ver esa entrada más
arriba) bloquea el acceso en `get_current_user` con 401, incluso con un JWT vigente. Ver
módulo `usuarios`.

---

## Inconsistencias de nomenclatura detectadas entre módulos

Estas entradas señalan casos donde el mismo concepto de negocio tiene nombres, valores o
implementaciones distintas en distintas partes del sistema — vale la pena que cualquier
persona nueva las conozca antes de asumir que un término significa lo mismo en todos
lados.

- **Badge de estado de documento — español vs. inglés.** El frontend
  (`RecentCard.tsx`, módulo `frontend_carga_documentos`) define estilos de badge para
  las claves en español `'completado'`, `'procesando'`, `'error'`. El backend
  (`services/extraccion`, módulo `extraccion_api`) escribe siempre el valor en inglés
  `"completed"` sobre `extraction_results.status` y `chunk_results.status`. Como
  resultado, **ninguna clave del frontend matchea nunca el valor real que escribe el
  backend**, así que el badge de estado en pantalla queda siempre en el estilo por
  defecto — el color/etiqueta de "completado" nunca se aplica en la práctica. Ver
  `docs/modulos/frontend_carga_documentos/pendientes.md` y
  `docs/modulos/extraccion_api/estados.md`.

- **Dos módulos distintos llamados "extracción".** `services/extraccion/` (backend
  legacy, cubierto por los módulos `extraccion_ia` y `extraccion_api`) y
  `services/presupuestacion/extraccion/` (módulo `extraccion_validacion`) son paquetes
  de código completamente distintos que comparten el mismo nombre de carpeta
  (`extraccion/`). El primero hace el parseo con IA y expone HTTP; el segundo toma el
  resultado ya procesado y lo materializa en tablas de negocio de `presupuestacion`. Ver
  la nota explícita al inicio de `docs/modulos/extraccion_validacion/README.md`.

- **Dos módulos distintos llamados "comparativas".** El pipeline de extracción de
  comparativas de precios con IA (`services/extraccion/robot_comparativas.py`, dentro
  de `extraccion_ia`) genera el CSV crudo; el módulo `comparativas` de
  `presupuestacion` es una fachada de negocio, más chica, que solo lee y permite asignar
  proveedor manualmente sobre datos ya materializados por `extraccion_validacion`. Son
  tres capas distintas del mismo concepto de negocio con nombres parecidos. Ver la nota
  explícita al inicio de `docs/modulos/comparativas/README.md`.

- **`estado` de proceso comercial sin guardas vs. `estado` de presupuesto con
  guardas.** Ambos campos se llaman "estado" y modelan un concepto similar (en qué
  etapa está algo), pero se comportan de forma muy distinta: `presupuestos.estado`
  tiene transiciones validadas; `procesos_comerciales.estado` es un tipo nominal sin
  ninguna guarda de transición, y de hecho lo escribe un módulo que no es su dueño
  (`presupuestos`, no `procesos_comerciales`). Ver módulos `procesos_comerciales`
  (`estados.md`) y `presupuestos`.

- **"Evento" vs. "notificación".** Son conceptos deliberadamente separados en el
  diseño del sistema (comentario textual del propio esquema SQL: "evento=trabajo,
  notificación=aviso"), pero ambos módulos usan vocabulario y modelos de datos
  parecidos (estado, prioridad, origen), lo que puede generar confusión sobre cuál usar
  al construir una nueva funcionalidad. Ver módulos `eventos` y `notificaciones`.
