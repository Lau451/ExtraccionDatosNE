# Decisiones de diseño — Imports

Numeración D-IMPORTS-NNN, verificada contra el código en esta sesión.

### D-IMPORTS-001 — Reconciliación completa por lote en vez de upsert incremental

- **Decisión**: para productos, proveedores (con `codigo_interno`) y clientes, cada
  llamada recalcula el conjunto completo de filas activas en base de datos y desactiva
  todo lo que no vino en el lote recibido — en vez de limitarse a insertar/actualizar
  lo presente y dejar intacto lo ausente.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código que
  explique por qué se eligió este modelo de sincronización total ("el lote es la
  verdad completa del sistema origen") en vez de uno incremental ("el lote es un
  delta"). Es un diseño consistente con un sistema origen que exporta su maestro
  completo en cada corrida (por ejemplo, un ERP que vuelca la tabla entera), pero esa
  suposición no está documentada ni verificada — no se pudo confirmar contra ningún
  cliente real de estos endpoints (ver [`casos_de_uso.md`](./casos_de_uso.md)).
- **Ventajas**: garantiza que el maestro de la droguería siempre refleje exactamente el
  último estado reportado por el sistema origen, sin necesidad de que ese sistema
  informe explícitamente altas/bajas — basta con que reenvíe su tabla completa.
- **Desventajas**: un lote parcial o incompleto (por un bug de paginación en el sistema
  origen, un timeout que corta el envío a mitad, o un archivo mal generado) desactiva
  silenciosamente todo lo que faltó, sin ningún mecanismo de este módulo que distinga
  "no vino porque ya no existe" de "no vino por un error del envío". No hay un umbral
  de seguridad (por ejemplo, "no desactivar más del X% del total en una sola corrida")
  ni una confirmación previa. Ver [`pendientes.md`](./pendientes.md) P2.

### D-IMPORTS-002 — `usuario_id` fijo (`usuario_sistema_id`) en vez de atribuir al usuario real que dispara la importación

- **Decisión**: los 5 wrappers `*_para_endpoint` resuelven `usuario_id` con
  `_usuario_sistema_id()` — un UUID técnico fijo leído de `Settings.usuario_sistema_id`
  (`core/config.py:15`) — en vez de recibir el `usuario.id` del `UsuarioPerfil` que
  `router.py` ya tiene disponible vía `require_roles`.
- **Motivo**: pendiente de definición funcional — no hay comentario en el código.
  Comparando con `clientes/service.py` y `catalogo/service.py`, cuyos wrappers
  `*_para_endpoint` sí reciben `usuario_id` como parámetro explícito pasado desde
  `router.py`, el patrón de este módulo es una excepción deliberada, no un descuido de
  copia — el router de `imports/` ni siquiera pasa `usuario.id` a la función del
  servicio en ningún punto de los 5 endpoints. Una hipótesis razonable (no confirmada)
  es que las filas de `created_by`/`updated_by` buscan reflejar "esto lo escribió el
  proceso de import", análogo a `origen="import_sistema"` en costos, en vez de "esto lo
  escribió la persona que apretó el botón".
- **Ventajas**: uniformidad — todas las filas creadas por importación quedan
  identificables por un único `usuario_id` conocido, sin depender de qué cuenta
  humana tenía la sesión activa.
- **Desventajas**: se pierde la trazabilidad de **quién** disparó una importación
  puntual — si dos personas distintas con rol `admin`/`gerencia`/`compras` corren
  importaciones en momentos distintos, ambas dejan el mismo `created_by`/`updated_by`.
  Combinado con la ausencia total de auditoría (`core.audit`, ver
  [`pendientes.md`](./pendientes.md) P1), no queda ningún registro de quién ejecutó una
  importación masiva que, por ejemplo, desactivó cientos de productos.

### D-IMPORTS-003 — Reimplementar el algoritmo de versionado de costos en vez de reusar `catalogo.service.crear_costo`

- **Decisión**: `importar_costos` arma su propia lógica de cierre+alta de costo
  vigente en `imports/service.py:106-137`, en vez de importar y llamar a
  `catalogo.service.crear_costo` (`catalogo/service.py:195-218`) con
  `origen="import_sistema"` como parámetro.
- **Motivo**: pendiente de definición funcional — no hay comentario en ninguno de los
  dos archivos. Una hipótesis razonable (no confirmada) es evitar el acoplamiento
  imports→catalogo en la dirección "normal" (ya existe uno en la dirección inversa, ver
  D-IMPORTS-004) — pero de ser así, tampoco está documentado como decisión consciente.
  Otra hipótesis es que `catalogo.crear_costo` recibe un `CostoCreate` (Pydantic) y no
  expone el campo `origen` en su modelo (`catalogo/models.py:109-111`, sin campo
  `origen`, confirmado en [`../catalogo/reglas.md`](../catalogo/reglas.md)
  RN-CATALOGO-007) — reusarlo tal cual habría forzado siempre `origen="manual"`, y
  extenderlo para aceptar `origen` como parámetro habría sido un cambio a un archivo de
  otro módulo.
- **Ventajas**: cada módulo controla su propio algoritmo sin depender de cambios en el
  otro — un cambio en la firma de `catalogo.crear_costo` no rompe a `imports/` en
  tiempo de import (a diferencia de lo que sí ocurre con `DEPOSITO_SENTINEL`, ver
  D-IMPORTS-004).
- **Desventajas**: es la duplicación de lógica de negocio más grave del proyecto
  confirmada hasta ahora — dos implementaciones independientes del mismo algoritmo
  sobre la misma tabla, sin ningún punto único de verdad. Si la regla de negocio
  cambiara (el criterio de cierre de `fecha_hasta`, agregar una validación de fecha
  futura, cambiar el manejo de igualdad de valores), habría que modificar
  `catalogo/service.py:195-218` **y** `imports/service.py:106-137` de forma
  consistente, sin ningún mecanismo (test compartido, función común) que lo garantice.
  Ver [`pendientes.md`](./pendientes.md) P1 y
  [`../catalogo/pendientes.md`](../catalogo/pendientes.md) P2(1) para el mismo hallazgo
  documentado desde el otro lado.

### D-IMPORTS-004 — `DEPOSITO_SENTINEL` definido en Imports (soporte) en vez de en Catálogo (negocio, dueño de `stock_productos`)

- **Decisión**: la constante `DEPOSITO_SENTINEL = "unico"` vive en
  `imports/service.py:18`, y `catalogo/repository.py:6` la importa desde acá, en vez de
  que Catálogo defina su propia constante (siendo el módulo documentalmente dueño de
  `stock_productos`) y que Imports la importe de Catálogo.
- **Motivo**: pendiente de definición funcional — no hay comentario en ninguno de los
  dos archivos. Mismo hallazgo ya documentado desde el lado de Catálogo,
  [`../catalogo/decisiones.md`](../catalogo/decisiones.md) D-CATALOGO-004; esta entrada
  lo confirma desde el lado de origen de la constante.
- **Ventajas**: un único valor consistente entre la carga masiva de stock
  (`imports/repository.py:89-91`) y el ajuste manual de Catálogo
  (`catalogo/repository.py:185-191`) — un producto sin depósito específico cae siempre
  en la misma fila de `stock_productos`, sin importar qué flujo la escribió.
- **Desventajas**: acoplamiento negocio→soporte en la dirección menos intuitiva —
  `catalogo/` depende de `imports/` (un módulo de carga masiva) para una constante de
  su propio dominio. Si este archivo se elimina, se mueve, o se renombra la constante,
  `catalogo/repository.py` falla en tiempo de import con un error que no señala
  ninguna causa evidente dentro de `catalogo/`. Ver
  [`pendientes.md`](./pendientes.md) P1.

### D-IMPORTS-005 — La actualización de clientes no reactiva `activo` (posible gap, no una decisión documentada)

- **Decisión implícita**: a diferencia de productos y proveedores, la rama de
  actualización de `importar_clientes` no incluye `"activo": True` en el dict que
  actualiza (`service.py:284-291`, RN-IMPORTS-007).
- **Motivo**: no hay ningún comentario ni test que indique que esto sea intencional.
  Dado que el mismo desarrollador implementó los 3 flujos con reconciliación
  (productos, proveedores, clientes) con un patrón casi idéntico salvo por este detalle
  puntual, la ausencia de la clave `"activo"` en clientes tiene más forma de omisión
  que de decisión deliberada — pero no se puede afirmar con certeza sin el motivo
  documentado. Se incluye acá como decisión "implícita" en vez de en
  [`pendientes.md`](./pendientes.md) porque, a diferencia de un P1/P2/P3 típico, se
  trata de un comportamiento verificable con exactitud (no una ausencia genérica) que
  encaja mejor con el formato de esta página.
- **Ventajas**: ninguna identificada.
- **Desventajas**: un cliente desactivado por una importación queda desactivado para
  siempre, incluso si el sistema origen vuelve a reportarlo activo en importaciones
  futuras — a menos que alguien lo reactive manualmente vía
  `clientes/router.py` (`PATCH /clientes/{id}`, roles `_ROLES_ESCRITURA` de ese
  módulo). Ver [`pendientes.md`](./pendientes.md) P2.
