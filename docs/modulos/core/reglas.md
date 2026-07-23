# Reglas — Core

Todas las reglas fueron verificadas contra el código real en esta sesión. La numeración
sigue exactamente la definida en el descubrimiento previo; no existe una RN-CORE-015 —
no se identificó en el código una regla adicional que ameritara ese número, por lo que
el hueco se preserva en vez de renumerar.

Las reglas se separan en dos grupos: **técnicas** (mecanismo de infraestructura —
locking, reintentos, formato de datos, cacheo) y **de negocio** (decisiones sobre cómo
se reparte stock, quién puede hacer qué, y qué se considera correcto para el dominio de
Drogueria Nueva Era).

## Reglas técnicas

### RN-CORE-001 — Optimistic locking en las actualizaciones de stock

- **Descripción**: cada UPDATE sobre `cantidad_comprometida` o `cantidad_disponible`
  incluye en el `WHERE` el valor que se leyó momentos antes; si otra transacción ya
  modificó la fila, el UPDATE afecta 0 filas y no hay overwrite silencioso.
- **Condición**: cualquier intento de comprometer, liberar o descontar stock.
- **Resultado**: `actualizar_comprometida_si_no_cambio` / `actualizar_disponible_si_no_cambio`
  devuelven `None` cuando el `WHERE` no matchea ninguna fila, señal de carrera concurrente.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/stock.py:31-41` (comprometida),
  `:44-54` (disponible); condición documentada en `:61-64`; consumido desde
  `_comprometer_hasta` (`:81-87`).
- **Observaciones**: [IMPLEMENTADO]. Es la base sobre la que se apoyan las reglas de
  negocio RN-CORE-003 a RN-CORE-008.

### RN-CORE-002 — Reintentos acotados con backoff ante carrera concurrente

- **Descripción**: cada operación de ajuste de stock (comprometer, liberar por dos
  variantes, descontar disponible) reintenta hasta `_MAX_REINTENTOS = 5` veces si el
  UPDATE condicional falla por carrera, esperando `0.05 * (intento + 1)` segundos entre
  intentos.
- **Condición**: el UPDATE condicional de RN-CORE-001 devuelve `None` (0 filas
  afectadas).
- **Resultado**: si los 5 intentos fallan, se levanta `ConflictError`.
- **Prioridad**: Alta.
- **Archivo**: constantes en `services/presupuestacion/core/stock.py:9-10`; aplicado en
  los cuatro helpers con el mismo patrón: `_comprometer_hasta` (`:68`, backoff `:90`,
  excepción `:92`), `_liberar_monto` (`:101`, `:117`, `:119-121`), `_liberar_hasta`
  (`:215`, `:235`, `:237-239`), `_descontar_disponible_hasta` (`:246`, `:266`,
  `:268-270`).
- **Observaciones**: [IMPLEMENTADO]. Verificado con test de mock de carrera forzada
  (`tests/core/test_stock.py:77-128`) y con tests de concurrencia real con hilos
  (`tests/core/test_stock.py:214-300`).

### RN-CORE-009 — Mapeo de excepciones de dominio a status HTTP

- **Descripción**: cada subclase de `DomainError` se mapea a un código HTTP fijo:
  `AuthenticationError`→401, `ForbiddenError`→403, `NotFoundError`→404,
  `ConflictError`→409, `ValidationError`→422.
- **Condición**: se levanta cualquiera de estas excepciones durante el manejo de una
  request.
- **Resultado**: FastAPI responde con el status y el `detail` (`exc.message`)
  correspondiente vía `JSONResponse`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/exceptions.py:31-37` (`STATUS_MAP`),
  `:40-46` (`register_exception_handlers`).
- **Observaciones**: [IMPLEMENTADO]. Una excepción de dominio no listada en
  `STATUS_MAP` cae al default `500` (`exceptions.py:42`), no a un error específico —
  ver D-CORE-007.

### RN-CORE-010 — Formato exacto del header `Authorization`

- **Descripción**: el header debe tener la forma exacta `Bearer <token>`; cualquier otra
  cosa (header ausente, esquema distinto, sin token) levanta `AuthenticationError`.
- **Condición**: request a un endpoint que depende de `get_bearer_token` (directo o vía
  `get_current_claims`/`get_current_user`/`require_roles`/`get_user_client`).
- **Resultado**: `AuthenticationError("Falta el header Authorization")` si no hay
  header; `AuthenticationError("El header Authorization debe ser 'Bearer <token>'")` si
  el esquema no es `bearer` o falta el token.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/database.py:10-16`.
- **Observaciones**: [IMPLEMENTADO]. Comparación de esquema case-insensitive
  (`scheme.lower() != "bearer"`, línea 14).

### RN-CORE-011 — Verificación de JWT contra JWKS de Supabase

- **Descripción**: el token se verifica contra el JWKS publicado por Supabase Auth,
  aceptando los algoritmos `ES256` y `HS256`, con `audience="authenticated"`.
- **Condición**: llamada a `verificar_token(token, supabase_url=...)`.
- **Resultado**: devuelve el payload crudo (`dict`, con al menos `sub` y `exp`) si es
  válido; levanta `TokenInvalidoError` ante cualquier `jwt.PyJWTError` (firma inválida,
  vencido, malformado).
- **Prioridad**: Alta.
- **Archivo**: `services/shared/auth_jwt.py:16-19` (`_jwk_client`, cacheado con
  `@lru_cache`), `:22-36` (`verificar_token`), algoritmos y audience en `:31-32`.
- **Observaciones**: [IMPLEMENTADO]. `TokenInvalidoError` se traduce a
  `AuthenticationError` del lado de cada consumidor
  (`services/presupuestacion/core/auth.py:27-28`), no dentro de `auth_jwt.py` — este
  archivo no conoce `DomainError`.

### RN-CORE-013 — Sin fila en `usuarios` para el `sub` del token → `NotFoundError`

- **Descripción**: si el JWT es válido pero no existe una fila en `usuarios` con
  `id = claims.sub`, se considera que el usuario no tiene perfil.
- **Condición**: `get_current_user` no encuentra resultados en el `SELECT`.
- **Resultado**: `NotFoundError("No se encontró el perfil de usuario")`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/core/auth.py:44-45`.
- **Observaciones**: [IMPLEMENTADO]. Distingue explícitamente "token inválido"
  (`AuthenticationError`, RN-CORE-011) de "token válido pero sin perfil"
  (`NotFoundError`) de "token válido, perfil existe, pero está desactivado"
  (`AuthenticationError`, RN-CORE-026).

### RN-CORE-014 — `get_service_client` es un singleton cacheado por proceso

- **Descripción**: `get_service_client()` está decorado con `@lru_cache`, por lo que la
  primera llamada crea el cliente y las siguientes devuelven la misma instancia.
- **Condición**: cualquier llamada a `get_service_client()` dentro del mismo proceso.
- **Resultado**: un único objeto `Client` reutilizado en todas las llamadas.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/core/database.py:19-22`.
- **Observaciones**: [IMPLEMENTADO].

### RN-CORE-016 — `get_service_client` no debe importarse en ningún `router.py` (enforced por test, no por lint)

- **Descripción**: convención de arquitectura — el cliente sin RLS solo debe usarse en
  `service.py` de jobs de sistema, nunca en un `router.py` expuesto a requests de
  usuario.
- **Condición**: existencia de la cadena de texto `"get_service_client"` en el contenido
  de algún archivo `router.py` bajo `services/presupuestacion/`.
- **Resultado**: si se detecta, el test falla — pero esto **no** es un chequeo de
  análisis estático (no verifica imports reales ni uso efectivo), es una búsqueda de
  substring sobre el texto del archivo.
- **Prioridad**: Alta.
- **Archivo**: verificado exclusivamente por `tests/core/test_database.py:8-25`; no hay
  ningún enforcement en el código de `core/` mismo.
- **Observaciones**: [IMPLEMENTADO] el test; [SUPOSICIÓN] que sea suficiente como
  enforcement — ver `pendientes.md` P2(3). Confirmado por grep: los 15 archivos que
  importan `get_service_client` son 14 `service.py` más `core/database.py` (su propia
  definición); ninguno es un `router.py`.

### RN-CORE-017 — Clasificación de `tipo_cambio` para cambios de campo

- **Descripción**: al registrar un cambio de campo, `tipo_cambio` es `"estado"` si el
  campo auditado se llama `"estado"`, y `"campo"` en cualquier otro caso.
- **Condición**: llamada a `registrar_cambio` con cualquier `campo`.
- **Resultado**: valor de `tipo_cambio` insertado en `historial_cambios`.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/core/audit.py:55`.
- **Observaciones**: [IMPLEMENTADO]. No aplica a `registrar_evento_ciclo_vida`, que
  recibe `tipo_cambio` como parámetro explícito (`"creacion"`, `"eliminacion"`,
  `"restauracion"`, `core/audit.py:99`).

### RN-CORE-018 — Agrupación de cambios bajo un `batch_id` común

- **Descripción**: `registrar_cambios` inserta una fila por campo modificado, todas con
  el mismo `batch_id`; si no se pasa uno explícito, se genera con `uuid.uuid4()`.
- **Condición**: llamada a `registrar_cambios` con un diccionario de `cambios` de más de
  un campo.
- **Resultado**: N filas en `historial_cambios` comparten `batch_id`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/core/audit.py:65-90`, generación en `:76`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/core/test_audit.py:48-84`.

### RN-CORE-019 — Serialización de valores para auditoría (`_a_texto`)

- **Descripción**: `None` se serializa como `None`; booleanos como `"true"`/`"false"`
  en minúscula; `datetime`/`date` con `.isoformat()`; el resto con `str()`.
- **Condición**: cualquier `valor_anterior`/`valor_nuevo` pasado a `registrar_cambio`.
- **Resultado**: valor de texto (o `None`) insertado en `historial_cambios`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/core/audit.py:21-28`.
- **Observaciones**: [IMPLEMENTADO]. Verificado exhaustivamente en
  `tests/core/test_audit.py:13-35`.

### RN-CORE-022 — Algoritmo de `normalizar_descripcion`

- **Descripción**: normaliza texto en 5 pasos: descomposición Unicode NFKD, eliminación
  de tildes (encode/decode ascii), eliminación de puntuación (reemplazo por espacio),
  colapso de espacios múltiples, y conversión a mayúsculas con recorte de bordes.
- **Condición**: cualquier llamada a `normalizar_descripcion(texto)`.
- **Resultado**: string normalizado en mayúsculas, sin tildes ni puntuación, con
  espacios simples.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/core/texto.py:5-8`.
- **Observaciones**: [IMPLEMENTADO]. Verificado exhaustivamente en
  `tests/core/test_texto.py`.

### RN-CORE-023 — Resolución de `.env` cuatro niveles arriba de `config.py`

- **Descripción**: `_ENV_FILE` se calcula subiendo 4 niveles de directorio (`.parent`
  x4) desde la ubicación de `core/config.py`.
- **Condición**: se instancia `Settings()` (directa o vía `get_settings()`).
- **Resultado**: pydantic-settings busca el `.env` en esa ruta absoluta calculada.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/core/config.py:6`.
- **Observaciones**: [IMPLEMENTADO]. Ver riesgo P2(5) en `pendientes.md`: un movimiento
  de `core/config.py` a otra profundidad de carpetas rompe esta resolución en silencio
  (no hay validación de que el archivo exista en esa ruta).

### RN-CORE-024 — Valor por defecto de `cors_origins`

- **Descripción**: si no se define `CORS_ORIGINS` en el entorno, el default es
  `"http://localhost:3000,http://localhost:5173"`.
- **Condición**: variable de entorno `cors_origins` ausente.
- **Resultado**: `Settings.cors_origins` toma ese valor; `cors_origins_list` lo separa
  por comas y descarta entradas vacías.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/core/config.py:16` (default), `:18-20`
  (`cors_origins_list`).
- **Observaciones**: [IMPLEMENTADO].

### RN-CORE-025 — `get_settings()` cacheado

- **Descripción**: `get_settings()` está decorado con `@lru_cache`, por lo que
  `Settings()` se instancia (y el `.env` se lee) una sola vez por proceso.
- **Condición**: cualquier llamada a `get_settings()`.
- **Resultado**: se devuelve siempre la misma instancia de `Settings`.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/core/config.py:23-25`.
- **Observaciones**: [IMPLEMENTADO].

## Reglas de negocio

### RN-CORE-003 — Reparto de compromiso entre depósitos, mayor libre primero

- **Descripción**: al comprometer stock de un producto, si un solo depósito no alcanza,
  se reparte entre todos los depósitos disponibles de esa droguería, ordenados
  descendentemente por cantidad libre (`disponible - comprometida`).
- **Condición**: `comprometer_stock_producto` recibe una `cantidad` a comprometer para
  un producto con más de una fila en `stock_productos`.
- **Resultado**: se recorren los depósitos en ese orden, comprometiendo lo que cada uno
  permita, hasta cubrir la cantidad pedida o agotar los depósitos.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/stock.py:138-142` (orden), `:147-153`
  (recorrido).
- **Observaciones**: [IMPLEMENTADO]. El criterio "mayor libre primero" es una decisión
  de negocio de reparto, no una necesidad técnica de la base de datos. Verificado en
  `tests/core/test_stock.py:34-50`.

### RN-CORE-004 — Reversión total si queda remanente sin cubrir

- **Descripción**: si tras recorrer todos los depósitos del producto queda una cantidad
  sin comprometer, se revierte todo lo que sí se había comprometido en esa llamada y se
  levanta `ConflictError`.
- **Condición**: `restante > 0` después del loop de reparto de RN-CORE-003.
- **Resultado**: `liberar_o_reportar` revierte los compromisos parciales de esta
  llamada; se levanta `ConflictError` con el detalle de cuánto faltó.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/stock.py:162-168`.
- **Observaciones**: [IMPLEMENTADO]. Regla de negocio: "no dejar stock comprometido a
  medias si no se puede cubrir el pedido completo". Verificado en
  `tests/core/test_stock.py:53-75`.

### RN-CORE-005 — `liberar_compromisos` no aborta ante fallo parcial

- **Descripción**: al revertir una lista de compromisos, cada fila se procesa de forma
  independiente; si revertir una falla (agota sus propios reintentos), se continúa con
  el resto en vez de abortar todo el proceso de reversión.
- **Condición**: uno o más compromisos de la lista fallan al revertirse
  (`_liberar_monto` levanta `ConflictError`).
- **Resultado**: se acumulan los fallidos y, al final, se levanta `ConflictError` con el
  detalle de qué filas y montos quedaron sin revertir — requiere reconciliación manual.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/stock.py:189-208`.
- **Observaciones**: [IMPLEMENTADO]. No existe ningún mecanismo automatizado de
  reconciliación posterior en el código revisado — ver `pendientes.md`. Verificado en
  `tests/core/test_stock.py:131-186`.

### RN-CORE-006 — `entregar_stock_producto` libera por el total, descuenta solo lo aceptado

- **Descripción**: al confirmar una entrega, se libera `cantidad_comprometida` por el
  total entregado (`cantidad_entregada`), pero `cantidad_disponible` se descuenta solo
  por lo aceptado (`cantidad_entregada - cantidad_rechazada`).
- **Condición**: llamada a `entregar_stock_producto` con `cantidad_entregada` y,
  opcionalmente, `cantidad_rechazada > 0`.
- **Resultado**: `cantidad_aceptada = cantidad_entregada - cantidad_rechazada`
  (`stock.py:298`); pasada 1 libera por `cantidad_entregada` (`:304-311`); pasada 2
  descuenta por `cantidad_aceptada` (`:316-323`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/stock.py:273-325`, especialmente `:298`,
  `:304`, `:316`.
- **Observaciones**: [IMPLEMENTADO]. Regla de negocio explícita en el docstring de la
  función (`:281-285`): "la promesa al cliente queda resuelta, sea aceptada o
  rechazada" / "lo rechazado nunca entró al stock vendible". Verificado en
  `tests/core/test_stock.py:329-357`.

### RN-CORE-007 — Liberar y descontar recorren depósitos en órdenes independientes

- **Descripción**: dentro de `entregar_stock_producto`, la pasada de liberación ordena
  los depósitos por mayor `cantidad_comprometida` primero, y la pasada de descuento por
  mayor `cantidad_disponible` primero — son dos órdenes distintos e independientes entre
  sí, no atados a la misma fila.
- **Condición**: el producto tiene más de un depósito con stock.
- **Resultado**: pueden liberarse y descontarse depósitos distintos entre sí (no hay
  correlación fila a fila entre lo que se liberó y lo que se descontó).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/core/stock.py:301-303` (orden liberación),
  `:313-315` (orden descuento).
- **Observaciones**: [IMPLEMENTADO]. Documentado explícitamente en el docstring
  (`:287-292`): "no hay registro de en qué fila exacta se comprometió o tiene stock
  cada unidad". Consecuencia directa de D-CORE-002. Verificado en
  `tests/core/test_stock.py:360-403`.

### RN-CORE-008 — `entregar_stock_producto` no revierte nada si no alcanza

- **Descripción**: si alguna de las dos pasadas (liberar o descontar) no logra cubrir el
  monto deseado en ningún depósito, no hay reversión — cada pasada simplemente topea en
  lo que haya disponible.
- **Condición**: la suma de lo comprometido (o lo disponible) entre depósitos es menor
  al monto que se intenta liberar (o descontar).
- **Resultado**: `entregar_stock_producto` devuelve `(liberado_total, descontado_total)`,
  que pueden ser menores a lo pedido; no se levanta excepción por esta causa ni se
  deshace la entrega ya registrada.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/stock.py:294-296` (docstring), `:306-311`
  y `:318-323` (loops sin manejo de remanente).
- **Observaciones**: [IMPLEMENTADO]. El propio `compras/service.py` documenta esta
  decisión de no revertir la entrega ya insertada
  (`services/presupuestacion/compras/service.py:211-217`). Verificado en
  `tests/core/test_stock.py:406-433`.

### RN-CORE-012 — `require_roles` exige pertenencia a una whitelist de roles

- **Descripción**: `require_roles(*roles)` construye una dependencia de FastAPI que
  exige `usuario.rol in roles`.
- **Condición**: el usuario autenticado (resuelto por `get_current_user`) tiene un
  `rol` que no está en la lista pasada a `require_roles`.
- **Resultado**: `ForbiddenError("No tenés permisos para esta acción")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/auth.py:48-54`.
- **Observaciones**: [IMPLEMENTADO]. Es la base de autorización por rol de
  prácticamente todos los routers de `presupuestacion/` (14 de ellos, ver
  `casos_de_uso.md`).

### RN-CORE-020 — `EntidadAuditable` limitada a 5 entidades con FK fija

- **Descripción**: solo se puede auditar una de 5 entidades
  (`proceso_comercial`, `comparativa`, `orden_compra`, `presupuesto`, `evento`), cada
  una con una columna FK fija predeterminada.
- **Condición**: cualquier llamada a `registrar_cambio`, `registrar_cambios` o
  `registrar_evento_ciclo_vida`.
- **Resultado**: la entidad determina qué columna de `historial_cambios` recibe el id
  (vía `_COLUMNA_FK_POR_ENTIDAD`); una entidad fuera de esas 5 no es válida para el
  tipo `Literal`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/core/audit.py:7-9` (tipo), `:12-18` (mapeo);
  duplicado (ver `pendientes.md` P2(1)) en
  `services/presupuestacion/auditoria/models.py:6`, `:8-14`.
- **Observaciones**: [IMPLEMENTADO]. Cualquier entidad nueva que se quiera auditar
  requiere modificar ambos archivos.

### RN-CORE-021 — Roles con acceso de lectura al historial de auditoría

- **Descripción**: `GET /historial/{entidad}/{entidad_id}` es accesible a los roles
  `superadmin`, `admin`, `gerencia`, `lider_comercial`, `comercial`, `compras`, sin
  ninguna restricción adicional por campo dentro de esos roles.
- **Condición**: request al endpoint con un usuario autenticado.
- **Resultado**: si el rol del usuario está en esa lista, se devuelve el historial
  completo de la entidad pedida (todos los campos auditados, sin filtrar); si no,
  `ForbiddenError` (RN-CORE-012).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/auditoria/router.py:10` (`_ROLES_LECTURA`),
  `:17` (aplicación vía `require_roles(*_ROLES_LECTURA)`).
- **Observaciones**: [IMPLEMENTADO]. Ver riesgo P1 en `pendientes.md`: sin allowlist de
  campos auditables (D-CORE-008), un campo sensible auditado a futuro quedaría expuesto
  a estos 6 roles sin control adicional.

### RN-CORE-026 — Usuario desactivado no puede seguir usando la app aunque su JWT siga vigente

- **Descripción**: `UsuarioPerfil` ahora incluye `activo: bool = True`, proyectado desde
  la columna `usuarios.activo`. `get_current_user` verifica ese valor después de
  resolver el perfil; si es `False`, no devuelve el perfil.
- **Condición**: el JWT de Supabase Auth es válido y existe una fila en `usuarios` para
  ese `sub`, pero `activo = False` en esa fila.
- **Resultado**: `AuthenticationError("Usuario desactivado")` (mapeada a HTTP 401 por
  RN-CORE-009), en vez de devolver el `UsuarioPerfil`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/auth.py:22` (campo `activo` en
  `UsuarioPerfil`), `:39` (`activo` agregado al `SELECT`), `:47-48` (chequeo y excepción).
- **Observaciones**: [IMPLEMENTADO]. Este es el gate real de "desactivar un usuario" a
  nivel de aplicación: Supabase Auth no invalida el JWT emitido cuando se desactiva un
  usuario en la tabla `usuarios` (son dos sistemas distintos — el JWT sigue siendo
  técnicamente válido hasta que expira por su cuenta). Sin esta verificación, un usuario
  desactivado podría seguir usando cualquier endpoint hasta que su token expirase. Se
  ejecuta en cada request autenticada (vía `get_current_user`, consumida directa o
  indirectamente por `require_roles`), no solo en el login.
