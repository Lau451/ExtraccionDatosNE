# Reglas técnicas globales — ExtraccionDatosNE

Este documento consolida reglas técnicas **transversales**: comportamiento que aplica al
sistema completo o a varios módulos a la vez, no a un módulo en particular. Las reglas de
negocio propias de cada módulo viven en `docs/modulos/<modulo>/reglas.md`; este archivo
no las repite salvo cuando ilustran un patrón repetido que amerita consolidarse acá.

Metodología: toda afirmación de comportamiento real está marcada [IMPLEMENTADO] con cita
`archivo:línea` verificada releyendo el código fuente en esta sesión (no se copió
ciegamente lo que ya decía la documentación de módulo). Donde el código no permite
determinar una regla de negocio, se deja explícito "Pendiente de definición funcional".

El repo tiene 2 backends — `services/extraccion` (legacy) y `services/presupuestacion`
(nuevo, 19 módulos de dominio bajo `services/presupuestacion/<dominio>/`) — más
`services/shared` (JWT compartido) y `frontend/`. La mayoría de las reglas de este
documento describen `services/presupuestacion/`, que es donde vive casi toda la lógica de
negocio nueva; se señala explícitamente cuándo `services/extraccion` diverge.

**Multi-tenant**: la tabla `droguerias` (código) es la unidad de tenant del sistema —
"empresa" en el vocabulario de negocio/UI es sinónimo de una fila de `droguerias`, nunca
una entidad de código separada (ver `docs/glosario.md` "Drogueria" y "Empresa"). Las
funciones SQL `get_drogueria_id()`, `es_superadmin()` y `mismo_tenant(p_drogueria)`
(`docs/schema/rls_final.sql:55-70`) son la base de la mayoría de las policies RLS citadas
en este documento: `get_drogueria_id()` resuelve el tenant del usuario autenticado desde
su propia fila en `usuarios`, `es_superadmin()` sortea el aislamiento de tenant, y
`mismo_tenant()` combina ambas para el caso general "es superadmin o pertenece a esta
droguería". [IMPLEMENTADO].

---

## 1. Autenticación

### 1.1 Kernel JWT compartido

`services/shared/auth_jwt.py` es el único código compartido entre los dos backends del
monorepo. No contiene lógica de negocio de ningún dominio — solo verifica firma y
vigencia de un JWT de Supabase Auth y devuelve el payload crudo. [IMPLEMENTADO] —
docstring del módulo (`services/shared/auth_jwt.py:1-5`).

- **Quién lo emite**: Supabase Auth (fuera de este repositorio). El token se verifica
  contra el JWKS publicado en `{supabase_url}/auth/v1/.well-known/jwks.json`
  (`services/shared/auth_jwt.py:18`).
- **Algoritmos aceptados**: `ES256` y `HS256`, con `audience="authenticated"`
  (`services/shared/auth_jwt.py:31-32`).
- **Cliente JWKS cacheado**: `_jwk_client` está decorado con `@lru_cache`
  (`services/shared/auth_jwt.py:16-17`) — un `PyJWKClient` por proceso y por
  `supabase_url`.
- **Expiración**: el claim `exp` viene del propio JWT; `jwt.decode` la valida
  internamente (parte de `jwt.PyJWTError` si venció) — no hay lógica de expiración
  propia del repositorio, se delega enteramente en la librería `PyJWT`.
  [IMPLEMENTADO] (`services/shared/auth_jwt.py:22-36`, sin manejo especial de `exp`
  fuera del `try/except` genérico).
- **Fallo de verificación**: cualquier `jwt.PyJWTError` (firma inválida, vencido,
  malformado) se traduce a `TokenInvalidoError("Token inválido o vencido")`
  (`services/shared/auth_jwt.py:34-35`). `TokenInvalidoError` es una excepción propia de
  este archivo — no conoce `DomainError` de `presupuestacion` ni `HTTPException` de
  `extraccion`; cada backend la traduce a su propio tipo de error (ver 1.2, 1.3).

### 1.2 Consumo en `services/presupuestacion` — identificación OBLIGATORIA

`core/auth.py` es el único consumidor de `auth_jwt.py` dentro de `presupuestacion/`
(`services/presupuestacion/core/auth.py:10`). Flujo:

1. `get_bearer_token` exige el header exacto `Authorization: Bearer <token>` (comparación
   de esquema case-insensitive); si falta o está malformado, `AuthenticationError`
   (`services/presupuestacion/core/database.py:10-16`).
2. `get_current_claims` llama a `verificar_token`; si `TokenInvalidoError`, lo traduce a
   `AuthenticationError("Token inválido o vencido")`
   (`services/presupuestacion/core/auth.py:24-29`).
3. `get_current_user` toma el `sub` del token y busca la fila en `usuarios`
   (`SELECT id, drogueria_id, rol WHERE id = claims.sub`,
   `services/presupuestacion/core/auth.py:36-42`); si no hay fila, `NotFoundError` — token
   válido pero sin perfil (`core/auth.py:43-44`).

Es decir: en `presupuestacion/`, un JWT sin perfil en `usuarios` **bloquea** la request
(404 vía `NotFoundError`); no hay modo anónimo. [IMPLEMENTADO].

### 1.3 Consumo en `services/extraccion` — identificación OPCIONAL

`services/extraccion/auth.py` usa el mismo `verificar_token`, pero con semántica
distinta: si no hay header `Authorization`, la request sigue como anónima
(`subido_por=NULL`); si el header está pero es inválido/vencido, sí es un error real
(`HTTPException(401)`). [IMPLEMENTADO], explícito en el docstring del archivo
(`services/extraccion/auth.py:1-11`): conviven un HTML viejo sin concepto de sesión y un
frontend nuevo con login real, y la identificación pasa a ser obligatoria recién cuando
se retire el HTML viejo. Además, si el `sub` del token no tiene fila en `usuarios`,
`extraccion/auth.py` **no** bloquea — solo loguea un warning y devuelve `None`
(`services/extraccion/auth.py:59-65`), a diferencia de `presupuestacion/core/auth.py`
que sí levanta `NotFoundError` en ese mismo caso. Esta es una divergencia de
comportamiento deliberada y documentada entre los dos backends, no un descuido.

### 1.4 Formato del header

Ambos backends exigen la misma forma exacta `Bearer <token>` (esquema case-insensitive),
implementada dos veces de forma independiente pero idéntica:
`services/presupuestacion/core/database.py:10-16` y
`services/extraccion/auth.py:23-34`. No hay una función compartida para esto — solo la
verificación del token en sí (`auth_jwt.py`) está compartida; el parseo del header está
duplicado. [IMPLEMENTADO].

---

## 2. Autorización / permisos

### 2.1 Modelo de roles

6 roles, definidos en un único `Literal` en `services/presupuestacion/usuarios/models.py:5`:
`superadmin`, `admin`, `gerencia`, `lider_comercial`, `comercial`, `compras`.
[IMPLEMENTADO]. `services/extraccion` no tiene roles propios — su docstring lo dice
explícitamente ("este servicio no tiene roles ni RLS propios",
`services/extraccion/auth.py:3`).

### 2.2 Enforcement en el router — `require_roles`

`require_roles(*roles)` (`services/presupuestacion/core/auth.py:48-54`) construye una
dependencia de FastAPI que exige `usuario.rol in roles`; si no, `ForbiddenError`. Es la
base de autorización por rol de 14 de los 16 routers de negocio de `presupuestacion/`.
Dos routers (`usuarios/router.py`, `notificaciones/router.py`) usan `get_current_user`
directo, sin whitelist de rol — solo exigen estar autenticado, delegando el resto del
control de acceso en RLS y en validaciones internas del `service.py`
(`docs/modulos/core/pendientes.md` P3(3), verificado contra
`services/presupuestacion/usuarios/router.py:4,15,24` y
`services/presupuestacion/notificaciones/router.py:4,24,35,42,49,59`). [IMPLEMENTADO] el
hecho; si es deliberado o un descuido queda "Pendiente de definición funcional" — no hay
comentario en el código que lo aclare.

### 2.3 Enforcement en RLS — y la inconsistencia real rol-router vs rol-RLS

`presupuestacion/` usa dos clientes de Supabase con propósito distinto
(`services/presupuestacion/core/database.py:19-29`):

- `get_service_client()` — `service_role`, **bypasea RLS por completo**. Reservado por
  convención a `service.py`, nunca a `router.py`.
- `get_user_client(token)` — `anon_key` autenticado con el JWT del request; Supabase
  aplica RLS normalmente.

Esa convención ("ningún `router.py` debe importar `get_service_client`") se verifica
**solo** con un test de grep de substring
(`tests/core/test_database.py:8-25`), no con análisis estático real — un alias de import
o un re-export indirecto lo evadiría sin que el test lo note
(`docs/modulos/core/decisiones.md` D-CORE-006).

**Inconsistencia real confirmada entre rol-router y rol-RLS**: en varios módulos, las
políticas de RLS de `UPDATE`/`INSERT` sobre una tabla **no incluyen todos los roles**
que `require_roles` sí autoriza a nivel de router. Cuando esto pasa, el `service.py`
resuelve el problema bypaseando RLS con `get_service_client()`, en vez de que el
`router.py` use `user_client`. Ejemplos verificados contra `docs/schema/rls_final.sql`:

- **Presupuestos** — `aprobar_presupuesto_para_endpoint` y `ajustar_item_para_endpoint`
  corren con `service_client` porque las políticas `pre_upd`/`pi_upd` de
  `docs/schema/rls_final.sql:254,264` son
  `(select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')` — **sin
  `superadmin`**, pese a que `superadmin` sí puede aprobar/ajustar vía `require_roles`.
  [IMPLEMENTADO] (`services/presupuestacion/presupuestos/service.py:258-261,264-281`,
  docstring citado textual: *"la RLS de presupuestos no incluye 'superadmin' en UPDATE"*).
- **Presupuestos (stock)** — `presentar_presupuesto_para_endpoint` corre con
  `service_client` porque la política `stock_upd`
  (`docs/schema/rls_final.sql:190`) es
  `(select get_rol()) IN ('admin','gerencia','compras')` — ni `comercial` ni
  `lider_comercial` (que sí pueden presentar) ni `superadmin` podrían comprometer stock
  vía `user_client`. [IMPLEMENTADO]
  (`services/presupuestacion/presupuestos/service.py:284-290`).
- **Clientes** — `upsert_formato_documento_para_endpoint` corre con `service_client`
  porque la RLS de `cliente_formato_documentos` no incluye `superadmin` en
  `INSERT`/`UPDATE`, cita textual del propio código: *"mismo criterio que el resto de
  los módulos"* (`services/presupuestacion/clientes/service.py:211-212`,
  `docs/modulos/clientes/decisiones.md` D-CLIENTES-002). El mismo patrón se repite sin
  comentario explícito para los otros 3 sub-recursos de `clientes/`
  (`docs/modulos/clientes/decisiones.md` D-CLIENTES-001).
- **Comparativas** — `asignar_proveedor_para_endpoint` corre con `service_role`
  (`docs/modulos/comparativas/reglas.md:30`).
- **Matching / Extracción_validación** — servicios de resolución de ítems corren con
  `service_role`, sin RLS (`docs/modulos/matching/reglas.md:132`,
  `docs/modulos/extraccion_validacion/reglas.md:131`).
- **Procesos comerciales** — operaciones batch corren con `service_role`
  (`docs/modulos/procesos_comerciales/README.md:62`).
- **Droguerías** — mismo patrón, en sentido inverso: la policy `droguerias_upd`
  (`docs/schema/rls_final.sql:103`) es
  `es_superadmin() OR (get_rol() = 'admin' AND id = get_drogueria_id())` — más permisiva
  que la API, que exige `require_roles("superadmin")` en el único endpoint de escritura
  (`services/presupuestacion/droguerias/router.py:41,50,58`) y corre siempre con
  `service_client`. La policy más permisiva nunca llega a ejecutarse porque el router no
  usa `user_client`. Ya documentado en detalle como
  [D-DROGUERIAS-003](./modulos/droguerias/decisiones.md#d-droguerias-003--la-policy-rls-droguerias_upd-permite-más-que-lo-que-expone-la-api)
  — no se repite el detalle acá, solo se deja registrado como una instancia más del
  mismo patrón transversal.

**Consecuencia arquitectónica transversal** (no una regla de negocio de un módulo
puntual): en `presupuestacion/`, **RLS no es la fuente de verdad de la autorización de
escritura** — es una capa que cubre parcialmente los roles reales y que la aplicación
rodea sistemáticamente con `service_client` cuando no alcanza. La autorización real de
"quién puede escribir qué" queda en `require_roles` del router más las validaciones
explícitas de pertenencia a droguería que el propio router hace con `user_client` antes
de delegar (ejemplo: `services/presupuestacion/presupuestos/router.py:24-57`,
RN-PRESUPUESTOS-016). RLS sigue siendo la fuente de verdad real solo para **lecturas**
(`GET`), donde la mayoría de los routers sí usa `user_client` sin bypass. [IMPLEMENTADO]
el patrón descrito; [SUPOSICIÓN] que esta caracterización general ("RLS gobierna
lecturas, no escrituras, en la mayoría de los módulos de negocio") se cumpla en los 19
módulos sin excepción — no se releyó cada uno de los 19 `service.py` línea por línea en
esta sesión, se generalizó a partir de los 6 casos verificados arriba más lo ya relevado
en `docs/modulos/core/`.

### 2.4 Auditoría de lectura del historial

`GET /historial/{entidad}/{entidad_id}` es legible por los 6 roles completos
(`superadmin`, `admin`, `gerencia`, `lider_comercial`, `comercial`, `compras`), sin
restricción adicional por campo dentro de esos roles
(`services/presupuestacion/auditoria/router.py:10,17`, RN-CORE-021). No hay allowlist de
campos auditables — cualquier `campo` es aceptado por `registrar_cambio`
(`services/presupuestacion/core/audit.py:44-50`, D-CORE-008) — riesgo documentado
explícitamente en el propio código.

### 2.5 Protección de auto-modificación y roles protegidos por diseño

Patrón transversal agregado en la sesión de julio 2026 (módulo `usuarios`), verificado
releyendo `services/presupuestacion/usuarios/service.py` completo en esta sesión. No es
una regla local a una sola función — se repite **idéntica** en las tres operaciones
destructivas/sensibles sobre otro usuario:

| Función | Auto-modificación bloqueada | Roles protegidos (`superadmin`/`sistema`) |
|---|---|---|
| `cambiar_rol` | `usuario_id == creador.id` → `ForbiddenError` (`service.py:58-59`) | `objetivo["rol"] in ("superadmin", "sistema") or nuevo_rol in (...)` → `ForbiddenError` (`service.py:65-68`) |
| `cambiar_activo` | `usuario_id == creador.id` → `ForbiddenError` (`service.py:85-86`) | `objetivo["rol"] in ("superadmin", "sistema")` → `ForbiddenError` (`service.py:92-93`) |
| `eliminar_usuario` | `usuario_id == creador.id` → `ForbiddenError` (`service.py:105-106`) | `objetivo["rol"] in ("superadmin", "sistema")` → `ForbiddenError` (`service.py:112-113`) |

- **Auto-modificación**: ningún usuario puede cambiarse su propio rol, desactivarse ni
  eliminarse a sí mismo por estas tres vías, sin importar su rol (ni siquiera
  `superadmin` puede hacerlo consigo mismo). El chequeo `usuario_id == creador.id` se
  evalúa siempre **antes** de comprobar que el usuario objetivo existe — mismo orden en
  las tres funciones (`docs/modulos/usuarios/reglas.md` RN-USUARIOS-014/017/023, con
  `flujo.md` documentando el orden completo). Motivo verificado en el propio código y en
  los tests que reproducen el bug que esta regla corrige: sin ella, un único `admin`
  podía autodegradarse o autodesactivarse y quedar sin nadie que pudiera revertirlo.
- **Roles protegidos por diseño**: `superadmin` y `sistema` no pueden cambiarse de rol,
  desactivarse ni eliminarse por la vía normal de gestión de usuarios, en los tres casos
  simétricamente. Antes de esta sesión, `cambiar_rol` solo protegía a `superadmin` —
  `sistema` no tenía ninguna protección, y un `admin` podía en teoría degradar o
  reasignar el rol del usuario técnico real `SYSTEM` (identificado por
  `usuario_sistema_id` en `core/config.py`). El agregado de `sistema` a las tres
  protecciones está motivado por un incidente real de testing manual en esta sesión: un
  admin desactivó por error al usuario `SYSTEM` antes de que `cambiar_activo` tuviera
  esta protección (`docs/modulos/usuarios/reglas.md` RN-USUARIOS-019, con test explícito
  que reproduce el caso, `tests/usuarios/test_service.py:312-320`). La simetría es
  consistente con el CHECK `ck_usuarios_superadmin` de la base, que ya trata a
  `superadmin` y `sistema` igual (`docs/schema/rls_final.sql:39-42`). [IMPLEMENTADO] el
  patrón en `cambiar_activo`/`eliminar_usuario` con test explícito para la rama
  `sistema`; en `cambiar_rol` la rama `sistema` está implementada en el código pero **sin
  test dedicado** que la ejercite (gap anotado en
  `docs/modulos/usuarios/pendientes.md`, ver también `reglas.md` RN-USUARIOS-009).

---

## 3. Auditoría

### 3.1 Mecanismo

`core/audit.py` es el único mecanismo transversal de audit log de `presupuestacion/`:
inserta filas en `historial_cambios`, append-only (Core no hace `UPDATE` ni `DELETE`
sobre esa tabla, `docs/modulos/core/base_de_datos.md:47-48`). Dos funciones:

- `registrar_cambio`/`registrar_cambios` — una fila por campo modificado, con
  `tipo_cambio` = `"estado"` si el campo es `"estado"`, o `"campo"` en cualquier otro
  caso (`services/presupuestacion/core/audit.py:55`).
- `registrar_evento_ciclo_vida` — una única fila para creación/eliminación/restauración,
  sin `campo` ni valores anterior/nuevo (`core/audit.py:93-114`).

Todas las filas de una misma llamada a `registrar_cambios` comparten un `batch_id`
(generado con `uuid.uuid4()` si no se pasa uno explícito, `core/audit.py:76`).
[IMPLEMENTADO].

### 3.2 Qué se audita — limitado a 5 entidades

Solo se puede auditar una de 5 entidades con FK fija: `proceso_comercial`,
`comparativa`, `orden_compra`, `presupuesto`, `evento`
(`services/presupuestacion/core/audit.py:7-9,12-18`, `EntidadAuditable`). El mapeo
entidad→columna FK está **duplicado** (no importado, copiado) en
`services/presupuestacion/auditoria/models.py:6,8-14` — hoy coinciden, pero no hay
ninguna garantía estructural de que sigan coincidiendo si uno se edita sin el otro
(`docs/modulos/core/pendientes.md` P2(1)).

### 3.3 Qué NO se audita

Cualquier entidad fuera de esas 5 (por ejemplo: `usuarios`, `clientes`,
`stock_productos`, `notificaciones`, `reglas_pricing`) no tiene rastro en
`historial_cambios` — no existe mecanismo de auditoría transversal para ellas.
[IMPLEMENTADO] por ausencia: `EntidadAuditable` es un `Literal` cerrado de 5 valores; una
llamada con una sexta entidad falla el tipado. Si algún módulo de negocio necesita
trazabilidad para una entidad fuera de esas 5, no hay ningún mecanismo del repositorio
que la provea hoy — "Pendiente de definición funcional" si eso es una decisión
deliberada o una limitación no evaluada.

`services/extraccion` no tiene ningún mecanismo de auditoría equivalente — no importa ni
usa `core/audit.py` de `presupuestacion/` (son paquetes Python separados) ni tiene un
mecanismo propio de audit log encontrado en esta sesión. [IMPLEMENTADO] por ausencia de
referencias cruzadas entre ambos backends salvo `services/shared/auth_jwt.py`.

---

## 4. Manejo de fechas

- **Timezone**: `services/presupuestacion/` usa consistentemente
  `datetime.now(timezone.utc).isoformat()` para timestamps (`deleted_at`, `leida_at`,
  `archivada_at`, `ultima_generacion`, `fecha_real`, etc.). Verificado en al menos 10
  archivos: `catalogo/repository.py:49,117`, `clientes/repository.py:55`,
  `automatizaciones/service.py:172,177,230,235`, `automatizaciones/repository.py:65`,
  `matching/repository.py:56`, `presupuestos/service.py:110,221`,
  `extraccion/service.py:291`, `notificaciones/repository.py:49,59`,
  `eventos/repository.py:48,120`, `eventos/service.py:149,242,243,372`.
  [IMPLEMENTADO]. No se encontró ningún uso de `datetime.now()` sin timezone (naive) en
  `presupuestacion/` en esta búsqueda.
- **Inconsistencia real: `date.today()` sin timezone explícito** en `pricing/repository.py:24,40,99`
  y `compras/service.py:247` — usa la fecha local del proceso/servidor
  (`date.today()`), no `datetime.now(timezone.utc).date()`. A diferencia del resto del
  sistema, que ancla explícitamente a UTC, estas 4 líneas dependen de la zona horaria
  configurada en el proceso Python que ejecuta el backend. [IMPLEMENTADO] la
  divergencia de patrón; el impacto real (¿el servidor corre en UTC? ¿hay un caso de
  negocio cerca de medianoche donde esto cambie qué fila de `costos_productos` o
  `precios_proveedor` se lee como vigente?) queda "Pendiente de definición funcional" —
  no verificado en esta sesión.
- `services/extraccion` no fue auditado exhaustivamente para este punto — fuera del
  alcance principal de esta consolidación (módulo legacy).
- No hay una utilidad compartida (`core/fechas.py` o similar) para construir estos
  timestamps — cada archivo repite `datetime.now(timezone.utc).isoformat()` de forma
  literal. [IMPLEMENTADO] por ausencia — no existe tal archivo en
  `services/presupuestacion/core/` (ver mapa de archivos en
  `docs/modulos/core/README.md:41-53`, no lista ningún `fechas.py`/`dates.py`).

---

## 5. Logging

Diferencia marcada entre los dos backends:

- **`services/extraccion`** (legacy): logging extendido — 115 llamadas a
  `logger.info/warning/error/debug/exception` en 13 archivos distintos (`auth.py`,
  `config.py`, `persistent_output.py`, `parsers.py`, `persistent_chunking.py`,
  `background_tasks.py`, `main.py`, `gemini_errors.py`, `robot.py`,
  `supabase_client.py`, `procesos_comerciales_client.py`, `robot_comparativas.py`,
  `routers/clientes.py`). [IMPLEMENTADO] — conteo verificado por grep en esta sesión.
- **`services/presupuestacion`** (nuevo, 19 módulos + core): **una única** llamada de
  logging en todo el backend —
  `logger.warning(...)` en `automatizaciones/service.py:164`, dentro de una rama de
  ejecución de reglas de automatización. [IMPLEMENTADO] — verificado por el mismo grep,
  0 resultados en `core/`, `presupuestos/`, `compras/`, `pricing/`, `matching/`,
  `usuarios/`, `clientes/`, `catalogo/`, `procesos_comerciales/`, `comparativas/`,
  `imports/`, `notificaciones/`, `eventos/`, `extraccion/` (submódulo de
  presupuestacion), `auditoria/`.
- `services/presupuestacion/main.py:25-28` configura `logging.basicConfig(level=LOG_LEVEL
  env var, default "INFO", formato con timestamp/logger/nivel/mensaje)` — la
  infraestructura de logging está lista y configurada, pero prácticamente sin uso.
  [IMPLEMENTADO].

**Inconsistencia transversal real**: el backend nuevo, que concentra toda la lógica de
negocio crítica (compromiso de stock con reintentos, cálculo de pricing, aprobación de
presupuestos, auditoría), no deja rastro en logs de aplicación para diagnosticar fallos
en producción más allá de las excepciones HTTP que ve el cliente y las filas de
`historial_cambios` (que solo cubren las 5 entidades de la sección 3.2). Por ejemplo,
`core/stock.py` agota 5 reintentos con backoff y levanta `ConflictError`
(RN-CORE-002) sin loguear ni un intento fallido individual — el único rastro es la
excepción HTTP 409 final. [IMPLEMENTADO] por ausencia — releído `core/stock.py`
completo (ver `docs/modulos/core/api.md`), sin ninguna llamada a `logging`.

---

## 6. Manejo de errores

### 6.1 Patrón centralizado en `services/presupuestacion`

`core/exceptions.py` define una jerarquía `DomainError` con 5 subclases y un mapeo fijo
a status HTTP (`services/presupuestacion/core/exceptions.py:5-37`):

| Excepción | Status HTTP |
|---|---|
| `AuthenticationError` | 401 |
| `ForbiddenError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `ValidationError` | 422 |

El mapeo se registra **una única vez**, en el arranque de la app
(`register_exception_handlers(app)`, `services/presupuestacion/main.py:32`, que invoca
`core/exceptions.py:40-46`) — no hay `try/except` repetido por router. Una excepción de
dominio no listada en `STATUS_MAP` cae al `500` genérico
(`core/exceptions.py:42`, D-CORE-007). [IMPLEMENTADO].

Confirmado por grep en esta sesión: **ningún archivo de `services/presupuestacion/`
levanta `fastapi.HTTPException` directamente** — todos los 19 módulos de negocio pasan
exclusivamente por `DomainError`/sus subclases. [IMPLEMENTADO] (0 resultados de
`HTTPException` en `services/presupuestacion/`).

### 6.2 `services/extraccion` no usa este patrón

`services/extraccion` levanta `fastapi.HTTPException` directamente, con status codes
literales hardcodeados en cada punto (ejemplos verificados en
`services/extraccion/auth.py:31-33` → 401, `:47` → 503, `:52` → 401). No existe una
jerarquía de excepciones de dominio propia en este backend ni un registro centralizado
de handlers. [IMPLEMENTADO]. Esto es coherente con que son dos aplicaciones FastAPI
independientes (`services/extraccion/main.py` y `services/presupuestacion/main.py`, cada
una con su propio `app = FastAPI(...)`), no un monolito compartido — pero significa que
**no hay un contrato de error único para todo el sistema**: un cliente que consuma ambos
backends ve dos convenciones de error distintas (una vía `DomainError`→`STATUS_MAP`
centralizado, otra vía `HTTPException` ad hoc por endpoint).

### 6.3 Inconsistencia de tipo de excepción para el mismo problema (tenant isolation)

Dentro de `presupuestacion/`, el mismo escenario de negocio — "el recurso pertenece a
otra droguería" — se traduce a **tres status HTTP distintos** según qué capa lo
detecte, documentado explícitamente en `docs/modulos/clientes/decisiones.md`
D-CLIENTES-004: `service.py:obtener_cliente` usa `NotFoundError` (404),
`service.py:_validar_cliente_de_la_drogueria` usa `ValidationError` (422), y
`router.py:_validar_cliente_y_obtener_drogueria_id` usa `ForbiddenError` (403). No es un
caso aislado de un módulo: `presupuestos/router.py` sí es consistente y siempre usa
`ForbiddenError` para el mismo escenario (RN-PRESUPUESTOS-016), lo que confirma que no es
una limitación técnica del framework sino una inconsistencia real de criterio entre
módulos sobre qué excepción corresponde a "no es tuyo". [IMPLEMENTADO] — cita verificada
contra `docs/modulos/clientes/decisiones.md:57-73`.

### 6.4 `nuevo_rol` sin re-tipar como riesgo de excepción no mapeada

`usuarios/service.py:cambiar_rol` recibe `nuevo_rol: str` sin validarlo contra el
`Literal Rol` (`services/presupuestacion/usuarios/service.py:42-44,65-66`,
RN-USUARIOS-012). Si se llama fuera del router (que sí valida vía Pydantic) con un valor
fuera de los 6 roles válidos, el único guardarraíl es el `CHECK` de Postgres — cuya
excepción del driver de Supabase **no está mapeada a ningún `DomainError`**, por lo que
cae al handler genérico `500` en vez de a un `ValidationError` (422). [IMPLEMENTADO] el
hecho de que no está tipado; la consecuencia exacta sobre el status HTTP resultante no
fue verificada end-to-end en esta sesión (inferida del código, no de un test).

### 6.5 Recomendación transversal: mapear errores de servicios externos a `DomainError` en `repository.py`

Patrón nuevo introducido en esta sesión en los módulos `usuarios` y `droguerias`, que se
recomienda generalizar a cualquier integración futura con un servicio externo (hoy, solo
Supabase Auth vía `postgrest`/`gotrue`).

- **Qué se hace**: la capa `repository.py` de cada módulo atrapa la excepción concreta
  del SDK externo y la traduce a un `DomainError` ya mapeado por `STATUS_MAP` (§6.1), en
  vez de dejarla propagar cruda.
  - `usuarios/repository.py:20-32` (`invitar_usuario_auth`) atrapa `AuthApiError`: si
    `exc.status == 429` (rate limit de envío de emails), `ConflictError`; para cualquier
    otro código, `ValidationError` con el mensaje de Supabase
    (`docs/modulos/usuarios/reglas.md` RN-USUARIOS-013).
  - `usuarios/repository.py:57-66` (`eliminar_usuario_auth`) atrapa **cualquier**
    `AuthApiError` y lo traduce a `ConflictError` (actividad asociada) — sin distinguir
    por status, a diferencia del caso anterior (`docs/modulos/usuarios/reglas.md`
    RN-USUARIOS-027).
  - `droguerias/service.py:32-38` (`eliminar_drogueria`) atrapa
    `postgrest.exceptions.APIError` (violación de FK) y lo traduce a `ConflictError`
    (`docs/modulos/droguerias/reglas.md` RN-DROGUERIAS-004).
- **Por qué importa a nivel transversal, no solo local a estos dos módulos**: una
  excepción de un SDK externo que no hereda de `DomainError` no está registrada en
  `register_exception_handlers` (§6.1) y no es capturada por ningún handler de FastAPI —
  cae a `ServerErrorMiddleware`, la capa más externa que arma Starlette internamente,
  fuera de cualquier middleware agregado por la app (incluido `CORSMiddleware`,
  `services/presupuestacion/main.py:36-42`). El resultado es un `500` **sin headers
  CORS**, que el navegador nunca expone al código JavaScript que hizo la llamada —
  aparece como `Failed to fetch` sin ningún mensaje legible, en vez de un error de
  dominio con status y mensaje claros. [IMPLEMENTADO] el mecanismo de traducción en los
  dos módulos citados; [SUPOSICIÓN] el efecto exacto sobre CORS no fue reproducido con un
  test automatizado en esta sesión — el mapeo de errores de `usuarios/repository.py` fue
  verificado manualmente por el usuario contra Supabase Auth real (rate limit y email
  inválido), ver RN-USUARIOS-013.
- **Recomendación**: cualquier módulo nuevo que llame a un servicio externo (hoy sería
  solo Supabase Auth; a futuro, cualquier proveedor de email/WhatsApp si se implementa
  el envío real de `notificaciones`, ver `docs/glosario.md` "Estado de entrega de
  notificación") debería aplicar el mismo patrón: atrapar la excepción del SDK en la
  capa de `repository.py` (no en `router.py` ni en `service.py`) y traducirla al
  `DomainError` que mejor represente la semántica del fallo, en vez de confiar en el
  handler `500` default. No hay hoy ningún lint ni test que exija este patrón — es una
  convención por repetición de ejemplo, no un mecanismo enforced.

---

## 7. Convenciones de API

- **Rutas**: sustantivos en plural, kebab-case cuando son compuestos
  (`/ordenes-compra`, `/notificacion-preferencias`, `/entregas/pendientes`), con
  sub-acciones como verbo en la última porción de la ruta
  (`/ordenes-compra/{id}/confirmar`, `/ordenes-compra/{id}/entregas`). Verificado en
  `services/presupuestacion/compras/router.py:44,69,81,98,106` y
  `services/presupuestacion/usuarios/router.py:13,21,33,40`. [IMPLEMENTADO] el patrón
  observado en estos dos routers; no se relevaron los 16 routers restantes línea por
  línea para esta consolidación — [SUPOSICIÓN] que el patrón se sostiene en el resto,
  dado que es consistente con las rutas citadas en `docs/modulos/*/casos_de_uso.md` de
  los módulos ya documentados (auditoria, notificaciones, presupuestos).
- **Sin paginación**: no se encontró ningún endpoint `GET` de listado en
  `presupuestacion/` que acepte parámetros de paginación (`limit`/`offset`/`page`) en
  esta sesión — ni en `usuarios/router.py`, ni en `compras/router.py`, ni en
  `auditoria/router.py` (`GET /historial/{entidad}/{entidad_id}` devuelve toda la lista
  ordenada por `created_at desc`, `auditoria/router.py:25`, sin límite). [IMPLEMENTADO]
  por ausencia en los routers relevados; "Pendiente de definición funcional" si esto es
  una decisión deliberada (volumen de datos bajo, por ahora) o una limitación no
  evaluada — no hay comentario en el código que lo aclare.
- **`response_model` inconsistente en al menos un módulo**: `docs/modulos/comparativas/pendientes.md:101`
  documenta `response_model` inconsistente entre los 3 endpoints de ese router — no
  releído en el código fuente en esta sesión, se reporta tal como está relevado y
  clasificado en el módulo de origen.

---

## 8. Otras reglas técnicas transversales

### 8.1 Validación de UUID — ausente en formato, presente solo por tipo de columna

No hay ningún validador de formato UUID a nivel de aplicación (Pydantic) para los campos
`cliente_id`/`categoria_id` que después se usan en construcción de filtros de query.
Confirmado explícitamente en `services/presupuestacion/procesos_comerciales/models.py:24,45`
(`cliente_id: str | None`) y `services/presupuestacion/catalogo/models.py:16,27,42`
(`categoria_id: str | None`) — ambos tipados como `str` simple, sin `Field(pattern=...)`
ni validador custom. [IMPLEMENTADO].

Esto es explotable de forma concreta en
`services/presupuestacion/pricing/repository.py:67-70` (`_alcance_or`), la única función
de `pricing/repository.py` que construye un filtro PostgREST por interpolación directa
de f-string en vez de los métodos tipados de `postgrest-py`:

```python
def _alcance_or(columna: str, valor: str | None) -> str:
    if valor is None:
        return f"{columna}.is.null"
    return f"{columna}.is.null,{columna}.eq.{valor}"
```

Si `valor` contuviera `,` o `.`, podría alterar la estructura del filtro pasado a
`.or_()` (`repository.py:86-88`) — un patrón análogo a una inyección de filtro, aunque
contenido en el lenguaje de query de PostgREST. La única barrera real hoy es que las
columnas de Postgres sean de tipo `uuid` (no `text`), lo cual **no se pudo verificar en
esta sesión** porque no hay migraciones SQL de `presupuestacion/` versionadas en el
repositorio — el schema se administra directo en Supabase
(`docs/modulos/pricing/pendientes.md:47-56`). [IMPLEMENTADO] el patrón de código;
[SUPOSICIÓN] su explotabilidad real, condicionada al tipo de columna no verificado.

### 8.2 Validación general con Pydantic

Los modelos de entrada/salida de `presupuestacion/` usan Pydantic (`BaseModel`,
`Literal` para enums cerrados como `Rol`, `EntidadAuditable`, `OrigenCambio`,
`Clase`). Verificado en `core/auth.py:13-21`, `usuarios/models.py:5`,
`core/audit.py:7-10`. No se usa un framework de validación alternativo en
`presupuestacion/`. [IMPLEMENTADO].

### 8.3 `core/__init__.py` vacío — sin superficie pública unificada

`services/presupuestacion/core/__init__.py` está vacío; no hay un punto de entrada único
para importar de Core — cada consumidor escribe el path completo del submódulo que
necesita (`from services.presupuestacion.core.audit import registrar_cambio`, no `from
services.presupuestacion.core import ...`). [IMPLEMENTADO]
(`docs/modulos/core/README.md:43`, `docs/modulos/core/pendientes.md` P2(6)). Este mismo
patrón (sin `__init__.py` que reexporte) se repite en los módulos de negocio revisados —
no se verificó exhaustivamente en los 19 módulos, pero es consistente con las citas de
import completas (`from services.presupuestacion.<modulo>.service import ...`) usadas en
`docs/modulos/*/casos_de_uso.md`.

### 8.4 Optimistic locking como patrón único de concurrencia

El único mecanismo de control de concurrencia encontrado en el sistema es optimistic
locking vía `UPDATE ... WHERE columna = valor_leído`, usado exclusivamente en
`core/stock.py` para `cantidad_comprometida`/`cantidad_disponible`
(`services/presupuestacion/core/stock.py:31-54`, RN-CORE-001). No se encontró ningún uso
de `SELECT ... FOR UPDATE` ni de locks pesimistas explícitos en el código relevado de
`presupuestacion/` (D-CORE-001, decisión explícita en el código: evita mantener
transacciones abiertas mientras se espera respuesta de red). Bajo alta contención, el
llamador recibe `ConflictError` tras agotar 5 reintentos — no hay garantía de que un
pedido eventualmente se sirva bajo contención sostenida. [IMPLEMENTADO].

### 8.5 `service_client` como singleton cacheado, `user_client` no

`get_service_client()` está decorado con `@lru_cache` — un único objeto `Client`
reutilizado por proceso (`services/presupuestacion/core/database.py:19-22`,
RN-CORE-014). `get_user_client(token)` **no** está cacheado — construye un cliente nuevo
en cada llamada, autenticado con el token del request
(`core/database.py:25-29`). Asimetría esperada (el service client no depende de datos
por-request; el user client sí), pero vale dejarla explícita porque no está comentada en
el código. [IMPLEMENTADO].

---

## Resumen de fuentes

Este documento se construyó releyendo directamente: `services/shared/auth_jwt.py`,
`services/presupuestacion/core/{auth,database,exceptions,audit,stock}.py`,
`services/presupuestacion/main.py`, `services/extraccion/{auth,main}.py`,
`services/presupuestacion/usuarios/models.py`, y grep dirigido sobre
`services/presupuestacion/` y `services/extraccion/` para timestamps (`datetime.now`),
logging (`logger.*`) y manejo de errores (`HTTPException`). Se consolidó además evidencia
ya verificada en `docs/modulos/core/*.md`, `docs/modulos/{pricing,usuarios,clientes,
presupuestos,comparativas,matching,procesos_comerciales,extraccion_validacion,
notificaciones}/{reglas,decisiones,pendientes}.md`, contrastando contra
`docs/schema/rls_final.sql` para las políticas de RLS citadas en la sección 2.3.

**Actualización de esta sesión (§2.3 ítem droguerías, §2.5, §6.5, nota de multi-tenant)**:
releídos completos y reverificados contra el código real
`services/presupuestacion/usuarios/service.py`,
`docs/modulos/usuarios/reglas.md`, `docs/modulos/droguerias/{reglas,decisiones}.md`,
`docs/modulos/core/reglas.md`, `services/presupuestacion/core/exceptions.py`,
`services/presupuestacion/main.py` (orden de `register_exception_handlers` vs.
`CORSMiddleware`) y `docs/schema/rls_final.sql:50-89` (funciones auxiliares de tenant).
