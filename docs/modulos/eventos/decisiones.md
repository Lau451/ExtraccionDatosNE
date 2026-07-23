# Decisiones de diseño — Eventos

Numeración D-EVENTOS-NNN, verificada contra el código en esta sesión.

### D-EVENTOS-001 — El mapeo `OrigenEvento → OrigenCambio` se tipa como `dict[OrigenEvento, str]`, no `dict[str, str]`

- **Decisión**: `_ORIGEN_EVENTO_A_ORIGEN_CAMBIO` (`service.py:24-29`) se declara con
  clave tipada `OrigenEvento` (el `Literal` de 4 valores de `eventos.origen`), en vez de
  `str` genérico.
- **Motivo**: documentado con comentario explícito, citado completo en RN-EVENTOS-004
  (`service.py:20-23`) — forzar que agregar un quinto valor a `OrigenEvento` sin
  agregar su entrada correspondiente en el diccionario rompa el chequeo de tipos
  estático, en vez de fallar recién en producción con un `KeyError` la primera vez que
  alguien cree un evento con ese origen nuevo.
- **Ventajas**: el error de "vocabulario no mapeado" se detecta en tiempo de desarrollo
  (si el repositorio corre `mypy`/`pyright` en CI — no verificado en esta sesión) en vez
  de en runtime; documenta en el propio tipo la intención de que el diccionario debe
  cubrir el 100% del `Literal`.
- **Desventajas**: la protección depende enteramente de que exista un chequeo de tipos
  estático corriendo sobre este archivo — en Python puro sin ese chequeo, un `Literal`
  ampliado sin actualizar el diccionario sigue fallando recién en runtime, igual que con
  `dict[str, str]`. La ventaja es exclusivamente de "shift-left" del error, no de
  eliminarlo.

### D-EVENTOS-002 — La dependencia entre eventos es lineal (`depende_de_id: str | None`), no un grafo de múltiples dependencias

- **Decisión**: un evento puede depender como máximo de **un** evento anterior — no
  existe una tabla intermedia `evento_dependencias` ni un array de IDs.
- **Motivo**: documentado con comentario explícito en el propio DDL
  (`extractor_final.sql:776`, `COMMENT ON COLUMN eventos.depende_de_id`), citado
  textual:

  > "Evento que debe completarse ANTES que este. NULL = no depende de nadie. Flujos
  > reales son lineales; si algún día se necesita esperar a VARIOS, se migra a una
  > tabla evento_dependencias sin tocar el resto."

  Es una decisión documentada como deliberadamente mínima para el caso de uso actual,
  con una ruta de migración ya prevista si se necesitara un grafo completo.
- **Ventajas**: `RN-EVENTOS-001`/`RN-EVENTOS-002` (bloqueo y desbloqueo en cascada) se
  implementan con un `SELECT`/`UPDATE` directo por `depende_de_id`
  (`repository.py:52-60`), sin necesidad de resolver un grafo de dependencias ni
  detectar ciclos más allá del `CHECK ck_eventos_no_self` (un evento no puede depender
  de sí mismo, `extractor_final.sql:770`). `v_eventos_bloqueo` es un `LEFT JOIN`
  autoreferencial de una sola línea (`extractor_final.sql:1658-1674`).
- **Desventajas**: no se puede modelar "el evento B espera a que A **y** C estén
  completados" sin una migración de esquema. Tampoco existe protección contra un **ciclo
  indirecto** de más de 2 eventos (A depende de B, B depende de A, vía dos `UPDATE`
  separados) — el `CHECK ck_eventos_no_self` solo evita la autorreferencia directa; no
  se encontró en esta sesión ningún `CHECK` ni validación de aplicación que impida un
  ciclo de longitud 2 o más. [SUPOSICIÓN de riesgo, no confirmada con un test que
  reproduzca el ciclo] — ver [`pendientes.md`](./pendientes.md).

### D-EVENTOS-003 — `DELETE /eventos/{id}` exige roles más restrictivos que el resto de las operaciones de escritura

- **Decisión**: `eliminar_evento_endpoint` usa `require_roles("admin", "gerencia")`
  (`router.py:89`) en vez de `_ROLES_ESCRITURA` (`("admin", "gerencia",
  "lider_comercial", "comercial", "compras")`, `router.py:33`), usado por
  `crear`/`actualizar`/`completar`. Es el único endpoint de `eventos/` con un tuple de
  roles distinto al de las constantes del módulo.
- **Motivo**: no documentado con comentario en el código — "Motivo pendiente de
  definición funcional". Hipótesis razonable **no confirmada** [SUPOSICIÓN]: borrar un
  evento (aunque sea soft-delete) es una operación más sensible que crearlo o marcarlo
  completado, y se restringe a los 2 roles de mayor jerarquía.
- **Ventajas**: reduce la superficie de quién puede hacer desaparecer un evento del
  calendario/listados, sin restringir la creación ni el avance normal del flujo (crear,
  actualizar, completar) a esos mismos 2 roles.
- **Desventajas**: introduce una asimetría de roles sin documentar dentro del mismo
  archivo — alguien que lea solo `_ROLES_ESCRITURA` y no revise cada `@router.delete`
  individualmente puede asumir incorrectamente que todos los roles de escritura pueden
  borrar. No hay ningún test en `tests/eventos/test_service.py` que ejercite la
  autorización HTTP (los tests llaman a las funciones de `service.py` directamente, sin
  pasar por `router.py`/`require_roles`) — esta asimetría de roles no tiene cobertura
  de test en el alcance leído.

### D-EVENTOS-004 — `generar_instancias_recurrentes` no filtra por `drogueria_id` y no tiene wrapper `_para_endpoint`

- **Decisión**: a diferencia de las demás funciones de negocio del módulo, que siempre
  reciben o resuelven un `drogueria_id` de tenant,
  `repo.listar_recurrentes_a_ejecutar` (`repository.py:119-128`) trae plantillas de
  **todas** las droguerías en una sola corrida, y `generar_instancias_recurrentes` no
  tiene un wrapper `_para_endpoint` que resuelva `get_service_client()` (a diferencia de
  las 6 funciones de `eventos`/`eventos_recurrentes` que sí lo tienen).
- **Motivo**: coherente con estar pensada como un job de sistema global (RN-EVENTOS-006)
  en vez de una operación por request de un usuario de una droguería puntual — no hay un
  comentario explícito que lo confirme, así que el "por qué" concreto queda como
  "Motivo pendiente de definición funcional".
- **Ventajas**: un único job puede procesar todas las droguerías en una corrida, sin
  necesidad de invocarlo N veces (una por tenant).
- **Desventajas**: quien la invoque debe pasar explícitamente un `client` con privilegio
  de `service_role` (sin RLS) armado a mano — no hay ningún `Depends` ni wrapper que lo
  fuerce ni lo documente en la propia firma de la función (`client: Client` genérico,
  `service.py:316`). Si alguna vez se conecta un disparador real (cron/worker,
  RN-EVENTOS-006), quien lo implemente deberá asegurarse manualmente de resolver el
  cliente correcto — no hay ningún error explícito si se le pasa un `user_client` con
  RLS activo (fallaría silenciosamente con menos filas de las esperadas, filtradas por
  la política RLS del usuario que lo invoque, en vez de un error claro).
