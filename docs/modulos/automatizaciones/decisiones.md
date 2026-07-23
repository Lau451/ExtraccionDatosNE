# Decisiones de diseño — Automatizaciones

Numeración D-AUTOMATIZACIONES-NNN, verificada contra el código en esta sesión.

### D-AUTOMATIZACIONES-001 — Modelo genérico de 8 `tipo_accion`, con solo 2 implementados

- **Decisión**: `TipoAccion` (`models.py:10-13`) y el `CHECK ck_ra_tipo_accion`
  (`extractor_final.sql:893-896`) declaran 8 valores posibles, pero `_ejecutar_accion`
  (`service.py:87-131`) solo implementa 2 (`crear_evento`, `enviar_notificacion`); los
  otros 6 caen en un fallback genérico `(False, "... no implementado aún")`.
- **Motivo**: no hay ningún comentario explícito en `models.py`, `service.py` ni en el
  `COMMENT ON` del `CHECK` de BD que declare por qué se modelaron 8 tipos de acción de
  entrada si la implementación cubre 2. [SUPOSICIÓN, no confirmada por comentario
  explícito]: es consistente con el mismo patrón que `services/presupuestacion/
  ROADMAP.md:53-62` describe para el módulo completo — "motor mínimo" diseñado con la
  superficie completa del vocabulario de negocio (los 8 tipos de acción que el spec
  contempla a futuro: crear OC, enviar email/WhatsApp, ejecutar agente de IA, cambiar
  estado, webhook) pero implementado incrementalmente, empezando por los 2 casos que ya
  tenían un módulo de negocio (`eventos`, `notificaciones`) listo para consumir. "Motivo
  pendiente de definición funcional" en cuanto a por qué esos 2 primero y no otros.
- **Ventajas**: el `Literal`/`CHECK` no necesita una migración de schema cada vez que se
  implemente un nuevo tipo de acción — la superficie de datos ya está declarada; un
  administrador puede crear hoy una regla con `tipo_accion="webhook"` sin que la BD la
  rechace, aunque no vaya a ejecutarse hasta que se implemente.
- **Desventajas**: una regla creada con uno de los 6 tipos no implementados **parece**
  válida (pasa la validación de Pydantic y el `CHECK` de BD) pero nunca produce ningún
  efecto — el error solo se descubre en tiempo de ejecución (o nunca, dado que no hay
  disparador real, RN-AUTOMATIZACIONES-006), no en tiempo de creación. No hay ningún
  aviso en `POST /automatizaciones/reglas` que le diga al usuario "este tipo de acción
  todavía no está implementado". Ver [`pendientes.md`](./pendientes.md).

### D-AUTOMATIZACIONES-002 — `reglas_automatizacion` no tiene versionado

- **Decisión**: no existe tabla de versiones ni columna de versión para las reglas —
  `PATCH` sobre una regla la modifica in-place.
- **Motivo**: documentado con comentario explícito en el propio DDL
  (`extractor_final.sql:902`, `COMMENT ON TABLE reglas_automatizacion`), citado textual:

  > "Reglas 'cuando ocurre X → ejecutar Y'. Sin versionado (deliberado: no hay reglas en
  > producción para justificarlo — acciones_ejecutadas.regla_id ya apunta a la FILA de
  > la regla, así que agregar versionado después no requiere migrar datos)."

  Decisión explícitamente condicionada al estado actual: "no hay reglas en producción"
  es coherente con RN-AUTOMATIZACIONES-006 (nadie dispara el motor todavía).
- **Ventajas**: modelo de datos más simple mientras no hay uso real; el propio comentario
  deja una ruta de migración clara si se necesitara versionado más adelante, sin
  necesidad de migrar datos históricos porque `acciones_ejecutadas.regla_id` ya referencia
  la fila concreta.
- **Desventajas**: si una regla se edita (`PATCH`) mientras tiene acciones `pendiente` en
  la cola, `procesar_acciones_pendientes` ejecutará la acción con los parámetros
  **actuales** de la regla (`obtener_regla` trae la fila viva, `service.py:217`), no los
  vigentes al momento en que se disparó — un cambio de `parametros_accion` entre el
  encolado y el procesamiento afecta retroactivamente acciones ya pendientes. No
  verificado con un test específico en esta sesión.

### D-AUTOMATIZACIONES-003 — Backoff exponencial en minutos (`2 ** intentos`), no en segundos ni con techo configurable

- **Decisión**: `procesar_acciones_pendientes` calcula `proximo_intento_at = fin +
  timedelta(minutes=2 ** intentos)` (`service.py:249`) — la unidad es minutos, la base
  es 2, y no hay ningún límite superior al valor de `2 ** intentos` más allá del que
  impone indirectamente `ck_ra_reintentos` (`max_reintentos <= 10`, lo que acota
  `intentos` a como máximo 10, y por lo tanto el backoff máximo posible a `2**10 = 1024`
  minutos ≈ 17 horas).
- **Motivo**: no hay comentario explícito que justifique la elección de minutos sobre
  segundos, ni de base 2 sobre otra progresión. "Motivo pendiente de definición
  funcional" para la unidad y la base concretas — el docstring de
  `procesar_acciones_pendientes` (`:212-214`) solo confirma la intención general
  ("backoff exponencial (2**intentos min)"), no el porqué de esos parámetros.
- **Ventajas**: fórmula simple, sin dependencias externas ni configuración adicional;
  el techo implícito de `max_reintentos<=10` evita que un backoff crezca sin límite
  hacia semanas/meses.
- **Desventajas**: la unidad de minutos (contra segundos) hace que el primer reintento
  ya tarde 2 minutos como mínimo — no hay un modo de "reintento casi inmediato" para
  fallos transitorios de baja latencia (p. ej. un timeout de red puntual). Tampoco hay
  jitter (aleatoriedad) en el cálculo, así que si muchas acciones fallan al mismo tiempo
  (por una caída momentánea de un servicio dependiente), todas se reprograman con
  exactamente el mismo delay y potencialmente vuelven a colisionar en la próxima corrida
  del worker — riesgo teórico, no observable hoy porque no hay worker real corriendo
  (RN-AUTOMATIZACIONES-006).

### D-AUTOMATIZACIONES-004 — `_ACCIONES_INMEDIATAS_SOPORTADAS` existe como constante pero no se usa

- **Decisión**: `service.py:20` declara `_ACCIONES_INMEDIATAS_SOPORTADAS = {"crear_evento",
  "enviar_notificacion"}`, con el mismo contenido exacto que las 2 ramas `if`/`elif`
  reales de `_ejecutar_accion`, pero la constante no se referencia en ningún otro punto
  del archivo ni del repositorio (confirmado por `Grep` exhaustivo en esta sesión).
- **Motivo**: no documentado — "Motivo pendiente de definición funcional".
  [SUPOSICIÓN, no confirmada]: hipótesis razonable es que la constante fue pensada
  originalmente como guarda explícita (`if tipo_accion not in
  _ACCIONES_INMEDIATAS_SOPORTADAS: return False, "..."` antes de las ramas `if`/`elif`
  específicas) y quedó sin conectar durante el desarrollo, o es un artefacto de un
  refactor previo a `_ejecutar_accion` en su forma actual.
- **Ventajas**: ninguna en el estado actual — es código muerto que no aporta
  comportamiento.
- **Desventajas**: quien lea el archivo y encuentre esta constante puede asumir
  incorrectamente que existe una validación temprana basada en ella antes de llegar a
  las ramas `if`/`elif`, cuando en realidad el control de flujo real es el `if`/`elif`/
  `return` final de `_ejecutar_accion` (`:99-131`). Riesgo de que un cambio futuro
  (agregar un tipo de acción a las ramas `if`/`elif` sin actualizar esta constante, o
  viceversa) genere una inconsistencia silenciosa entre ambos lugares. Ver
  [`pendientes.md`](./pendientes.md).

### D-AUTOMATIZACIONES-005 — Un único tuple de roles (`_ROLES`) para los 4 endpoints, sin distinguir lectura de escritura

- **Decisión**: `router.py:21` define `_ROLES = ("admin", "gerencia")` y lo reutiliza
  idéntico en los 4 `Depends(require_roles(*_ROLES))` — a diferencia de `eventos/`, que
  separa `_ROLES_LECTURA` (6 roles) de `_ROLES_ESCRITURA` (5 roles).
- **Motivo**: no documentado con comentario — "Motivo pendiente de definición
  funcional". [SUPOSICIÓN, no confirmada]: coherente con que administrar reglas de
  automatización (a diferencia de ver/crear eventos operativos) es una función más
  cercana a configuración del sistema que a operación diaria, restringida a los 2 roles
  de mayor jerarquía incluso para lectura.
- **Ventajas**: modelo de permisos más simple de auditar (una sola constante, sin
  asimetría entre endpoints del mismo router, a diferencia de D-EVENTOS-003).
- **Desventajas**: roles operativos que sí pueden crear/completar eventos en `eventos/`
  (`lider_comercial`, `comercial`, `compras`) no pueden ni siquiera **ver** qué reglas
  de automatización existen (`GET /automatizaciones/reglas` también requiere
  `_ROLES`), lo que podría dificultar el diagnóstico de "por qué no se generó tal
  evento/notificación automática" para esos roles — aunque hoy es un punto moot porque
  ningún evento automático real se genera sin disparador (RN-AUTOMATIZACIONES-006). No
  hay ningún test en `tests/automatizaciones/test_service.py` que ejercite la
  autorización HTTP (los tests llaman a `service.py` directamente).
