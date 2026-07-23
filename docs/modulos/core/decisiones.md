# Decisiones de diseño — Core

Numeración D-CORE-NNN según el descubrimiento previo, verificada contra el código.

### D-CORE-001 — Optimistic locking en vez de locking pesimista para stock

- **Decisión**: los ajustes de `stock_productos` (comprometer, liberar, descontar) usan
  optimistic locking (UPDATE condicionado al valor leído) en vez de un lock pesimista
  explícito de la base de datos (`services/presupuestacion/core/stock.py:61-64`,
  docstring de `_comprometer_hasta`).
- **Motivo**: explícito en el código — evita overwrite silencioso; Postgres garantiza 0
  filas afectadas si hubo una escritura concurrente entre la lectura y el UPDATE
  (`core/stock.py:61-64`).
- **Ventajas**: no requiere locks explícitos de base de datos (`SELECT ... FOR UPDATE`
  o equivalentes), lo que simplifica el código y evita mantener transacciones abiertas
  mientras se espera una respuesta de red.
- **Desventajas**: bajo alta contención, agota reintentos (RN-CORE-002) y traslada la
  responsabilidad de reintentar al llamador (vía `ConflictError`); no hay garantía de
  que un pedido eventualmente se sirva bajo contención sostenida.

### D-CORE-002 — Stock como pool agregado entre depósitos, sin registro por fila

- **Decisión**: `core/stock.py` trata el stock de un producto como un pool agregado
  entre depósitos (reparto greedy al comprometer, RN-CORE-003), sin registrar en qué
  fila específica se comprometió cada unidad.
- **Motivo**: explícito en el código — simplicidad (docstring de
  `entregar_stock_producto`, `services/presupuestacion/core/stock.py:287-292`: "no hay
  registro de en qué fila exacta se comprometió o tiene stock cada unidad").
- **Ventajas**: modelo de datos simple (solo dos columnas numéricas por fila de
  depósito, sin tabla de "reservas" individuales).
- **Desventajas**: liberar y descontar corren en pasadas independientes con distinto
  criterio de orden (RN-CORE-007), pudiendo tocar depósitos distintos a los
  originalmente comprometidos; no hay trazabilidad de "esta unidad específica vino de
  este depósito".

### D-CORE-003 — Reversión de compromisos sin abortar ante el primer fallo

- **Decisión**: `liberar_compromisos` revierte cada compromiso de la lista de forma
  independiente; si uno falla, no aborta el resto — acumula los fallidos
  (`services/presupuestacion/core/stock.py:189-208`).
- **Motivo**: explícito en el código — minimizar stock "colgado" (comentario en
  `core/stock.py:190-193`: "sigue con el resto en vez de abortar todo").
- **Ventajas**: maximiza la cantidad de stock efectivamente liberado aun cuando alguna
  fila individual tenga problemas.
- **Desventajas**: deja estado inconsistente pendiente de intervención humana; no existe
  en el código revisado ningún mecanismo automatizado de reconciliación posterior para
  los compromisos que quedaron sin revertir (ver `pendientes.md` P1).

### D-CORE-004 — Encadenamiento de errores con `raise ... from`

- **Decisión**: cuando la limpieza de un error (revertir compromisos) falla a su vez, el
  nuevo `ConflictError` se levanta con `raise ... from motivo_original`
  (`services/presupuestacion/core/stock.py:183-186`).
- **Motivo**: explícito en el código — trazabilidad completa (comentario en
  `core/stock.py:176-179`: "no deja que el error de limpieza reemplace en silencio el
  motivo original").
- **Ventajas**: el traceback final conserva ambos motivos (el error original y el error
  de limpieza), facilitando el diagnóstico y la reconciliación manual.
- **Desventajas**: ninguna documentada en el código; es un patrón estándar de Python sin
  costo aparente.

### D-CORE-005 — `auth_jwt.py` aislado en `services/shared/` sin lógica de negocio

- **Decisión**: la verificación de firma/vigencia del JWT vive en
  `services/shared/auth_jwt.py`, fuera de ambos backends, explícitamente sin lógica de
  negocio de ningún dominio (`services/shared/auth_jwt.py:1-5`, docstring del módulo).
- **Motivo**: explícito en el docstring — cada servicio decide qué hacer con las claims
  (resolver rol, droguería, exigir un `usuario_id`) del lado de su propio módulo de
  auth.
- **Ventajas**: evita duplicar la validación JWKS/firma entre `services/extraccion/` y
  `services/presupuestacion/` — es el único código compartido entre los dos backends
  del monorepo.
- **Desventajas**: "Motivo pendiente de definición funcional" para la ausencia de un
  test de contrato cross-servicio que garantice que ambos backends siguen consumiendo
  `auth_jwt.py` de forma compatible entre sí a medida que evolucionan por separado.

### D-CORE-006 — `get_service_client` restringido a jobs de sistema, enforced por grep de test

- **Decisión**: `get_service_client` (que bypasea RLS) está restringido por convención a
  `service.py` de jobs de sistema, nunca a `router.py`, y esa restricción se verifica
  con un test que busca la cadena `"get_service_client"` en el texto de cada
  `router.py` (`tests/core/test_database.py:8-25`), no con un lint estático.
- **Motivo**: explícito en el test — prevenir bypass de RLS desde endpoints de usuario
  (`tests/core/test_database.py:21-24`: "service_role no debe usarse en routers de
  usuario, solo en jobs de sistema").
- **Ventajas**: enforcement automático y simple de implementar, sin dependencias
  adicionales (ni AST, ni herramientas de lint específicas).
- **Desventajas**: frágil ante refactors de imports (p. ej. un alias o un re-export
  indirecto no contendría literalmente la cadena `"get_service_client"` y pasaría el
  test sin detectarse); es un chequeo de substring de texto, no de análisis estático
  real de imports/uso.

### D-CORE-007 — Manejo de excepciones de dominio centralizado en un único registro

- **Decisión**: el mapeo `DomainError → status HTTP` se centraliza en
  `register_exception_handlers(app)`, invocado una sola vez en `main.py:32`, en vez de
  try/except repetido en cada router.
- **Motivo**: "Motivo pendiente de definición" — no hay comentario explícito en el
  código que lo justifique; es inferible del patrón mismo (un único punto de mapeo
  error→status evita repetir la tabla `STATUS_MAP` en cada endpoint).
- **Ventajas**: evita repetir el mapeo de errores en cada router; agregar un nuevo tipo
  de `DomainError` solo requiere una entrada en `STATUS_MAP`.
- **Desventajas**: una excepción de dominio que no esté listada en `STATUS_MAP` no es
  interceptada con su semántica propia — cae al status `500` genérico
  (`core/exceptions.py:42`), sin distinción del tipo de error real.

### D-CORE-008 — `core/audit.py` sin allowlist de campos auditables por entidad

- **Decisión**: `registrar_cambio` no valida qué nombres de `campo` son válidos para
  auditar en cada entidad — cualquier string es aceptado.
- **Motivo**: riesgo documentado explícitamente por el propio autor en el código
  (`services/presupuestacion/core/audit.py:44-50`, comentario que describe el riesgo y
  aclara que hoy no está explotado porque ningún call site pasa un campo sensible).
- **Ventajas**: simplicidad de la API — `registrar_cambio`/`registrar_cambios` no
  necesitan conocer de antemano qué campos son válidos para cada una de las 5
  entidades.
- **Desventajas**: nada en `core/audit.py` impide que un futuro call site audite un
  campo sensible, que luego quedaría expuesto vía `GET /historial/{entidad}/{entidad_id}`
  a los 6 roles de `_ROLES_LECTURA` (RN-CORE-021) sin ningún control adicional. Ver
  `pendientes.md` P1.
