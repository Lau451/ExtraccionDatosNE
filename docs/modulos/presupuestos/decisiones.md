# Decisiones de diseño — Presupuestos

Numeración D-PRESUPUESTOS-NNN, verificada contra el código en esta sesión.

### D-PRESUPUESTOS-001 — Guardar `precio_original_motor` solo en el primer ajuste manual, para no perder el precio calculado por el motor

- **Decisión**: `ajustar_item` copia `precio_unitario` a `precio_original_motor`
  únicamente si este último es `NULL` (`service.py:147-148`) — ajustes
  manuales posteriores no lo vuelven a tocar.
- **Motivo**: pendiente de definición funcional en el sentido de que no hay
  comentario textual en el código que lo explique, pero la intención es
  directamente inferible del nombre del campo y del comportamiento verificado
  (RN-PRESUPUESTOS-008,
  `tests/presupuestos/test_service.py:152-193`): conservar el precio que
  produjo el motor de `pricing/` **antes** de cualquier intervención humana,
  para poder comparar "lo que calculó el sistema" contra "lo que terminó
  cobrándose" incluso después de varios ajustes sucesivos.
- **Ventajas**: si `precio_original_motor` se sobrescribiera en cada ajuste, se
  perdería la referencia al cálculo original apenas hubiera un segundo ajuste
  — el campo dejaría de responder "¿cuánto había calculado el motor?" y pasaría
  a responder "¿cuál fue el ajuste anterior?", una pregunta distinta y menos
  útil para auditar decisiones comerciales. La regla del primer ajuste
  garantiza que el campo sea estable una vez fijado.
- **Desventajas**: si el motor de `pricing/` regenera el presupuesto
  (RN-PRICING-008, [`../pricing/reglas.md`](../pricing/reglas.md)) mientras el
  presupuesto sigue en `"generado"`/`"en_revision"`, el `DELETE + INSERT` de
  `presupuesto_items` borra la fila entera — incluyendo `precio_original_motor`
  — sin ningún mecanismo que la preserve o la traslade a la fila nueva. La
  garantía de "primer ajuste" solo protege contra ajustes repetidos de
  `presupuestos/`, no contra una regeneración de `pricing/`. Ver
  [`../pricing/arquitectura.md`](../pricing/arquitectura.md) (ya documentado
  desde ese lado) y [`pendientes.md`](./pendientes.md).

### D-PRESUPUESTOS-002 — Dos vistas SQL distintas por rol, en vez de un solo endpoint con serialización condicional en Python

- **Decisión**: la visibilidad de costo por rol (RN-PRESUPUESTOS-013) se
  implementa con dos vistas SQL completas (`v_presupuesto_comercial`,
  `v_presupuesto_revision`), seleccionadas por el router, en vez de un único
  `SELECT` sobre `presupuesto_items` con un `response_model` de Pydantic que
  omita campos según el rol del solicitante.
- **Motivo**: documentado textualmente en el propio schema
  (`docs/schema/rls_final.sql:15-18`): *"RLS filtra filas, no columnas. [...]
  Usan la vista v_presupuesto_comercial (definida al final, sin costo). La app
  dirige cada rol a la vista correcta"* — es decir, la limitación técnica de
  Postgres RLS (que no puede ocultar columnas, solo filas) es la que fuerza el
  patrón de dos vistas en vez de una política RLS por columna, que Postgres no
  soporta de forma nativa para `SELECT`.
- **Ventajas**: la garantía de que `comercial`/`lider_comercial` nunca reciben
  `costo_usado` vive en la base de datos (la vista, con `security_invoker`,
  `rls_final.sql:355`), no en la capa de serialización de FastAPI — un bug en
  `router.py` que enviara el rol equivocado a la vista equivocada seguiría sin
  poder filtrar columnas que la vista en sí no expone; a la inversa, no hay
  ningún riesgo de que un cambio en el modelo Pydantic de salida exponga
  accidentalmente un campo sensible, porque ambos endpoints devuelven `list[dict]`
  crudo sin pasar por un `response_model` (`router.py:65`).
- **Desventajas**: dos definiciones SQL a mantener en sincronía manualmente
  (`rls_final.sql:320-355` y `:454-501`) — cualquier columna nueva que deba
  verse en ambos roles hay que agregarla en los dos `CREATE VIEW`/`CREATE OR
  REPLACE VIEW` por separado; no hay una vista base común de la que ambas
  deriven. La responsabilidad de dirigir cada rol a la vista correcta recae
  enteramente en `router.py:69-73` — un error ahí (por ejemplo, invertir la
  condición) expondría costos a roles comerciales sin que ningún test de este
  módulo lo detecte hoy (RN-PRESUPUESTOS-013, cobertura de test parcial).

### D-PRESUPUESTOS-003 — `presupuestos/`, y no `procesos_comerciales/`, dispara la transición del proceso comercial a `"presentado"`

- **Decisión**: `presentar_presupuesto` hace el único `UPDATE` de
  `procesos_comerciales.estado` de todo el repositorio
  (RN-PRESUPUESTOS-007), en vez de que `presupuestos/` notifique el evento
  (por ejemplo, con una segunda llamada HTTP o un evento de dominio) a
  `procesos_comerciales/service.py` para que sea ese módulo el que decida si y
  cómo transicionar su propio campo.
- **Motivo**: pendiente de definición funcional — no hay comentario en el
  código que lo explique. Hipótesis razonable a partir de la estructura del
  repositorio (no confirmada): `procesos_comerciales/` no expone ningún
  `PATCH`/`PUT` (`procesos_comerciales/router.py`, según
  [`../procesos_comerciales/README.md`](../procesos_comerciales/README.md)) —
  es decir, la decisión de no tener un endpoint de transición de estado en ese
  módulo puede ser anterior a la necesidad de que `presupuestos/` transicione
  el proceso, y este `UPDATE` directo puede ser simplemente el camino de menor
  resistencia dentro de la misma transacción lógica de `presentar_presupuesto`
  (mismo `client`, mismo `usuario_id`, mismo evento de negocio), en vez de
  construir una segunda capa de eventos o un cliente HTTP interno entre
  módulos del mismo backend.
- **Ventajas**: una sola función controla ambos cambios de estado
  (presupuesto y proceso comercial) dentro de la misma llamada, sin necesidad
  de coordinar dos servicios ni de manejar fallos parciales entre una
  actualización y la otra (aunque tampoco hay ninguna transacción explícita que
  las una — ver [`pendientes.md`](./pendientes.md)). Es la implementación más
  simple posible del requisito "presentar el presupuesto también avanza el
  proceso comercial".
- **Desventajas**: exactamente el hallazgo ya documentado en detalle desde el
  otro lado, en
  [`../procesos_comerciales/arquitectura.md`](../procesos_comerciales/arquitectura.md)
  ("Ciclo de vida partido con `presupuestos/`") y
  [`../procesos_comerciales/pendientes.md`](../procesos_comerciales/pendientes.md)
  P1(1): cualquier guarda de transición que se agregue en el futuro dentro de
  `procesos_comerciales/service.py` **no protegería** este `UPDATE`, porque
  `presupuestos/repository.py:actualizar_proceso_comercial` no importa ni pasa
  por ningún archivo de `procesos_comerciales/`. Confirmado, con la misma
  cita, desde este lado: `presupuestos/repository.py:68-71` es un `UPDATE`
  genérico de propósito general (recibe `campos: dict[str, Any]`), reutilizado
  tal cual para el único caso de uso hoy existente (`estado="presentado"`), sin
  ninguna lógica específica de `procesos_comerciales` ni ninguna validación de
  que el proceso no esté ya en un estado terminal.
