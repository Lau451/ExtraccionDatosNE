# Pendientes — Auditoría técnica de Procesos Comerciales

Clasificación P1 (ausencia de una capacidad esperada / riesgo estructural) / P2 (deuda
técnica relevante) / P3 (menor), verificada contra el código y los tests reales en
esta sesión.

## P1 — Riesgo estructural

1. **Responsabilidad del ciclo de vida de `estado` partida entre dos módulos, sin
   contrato explícito ni import compartido.** `procesos_comerciales/` define la
   máquina de estados nominal (`Estado`, `models.py:9-18`) y el vocabulario de
   estados terminales (`_ESTADOS_TERMINALES`, `repository.py:9`), pero el único write
   real de `estado` vive en `presupuestos/repository.py:actualizar_proceso_comercial`
   (`:68-71`), invocado desde `presupuestos/service.py:239-241`. [IMPLEMENTADO].
   Cualquier guarda de transición que se agregue en el futuro dentro de
   `procesos_comerciales/service.py` **no protegería** ese `UPDATE`, porque
   `presupuestos/repository.py` no importa ni pasa por ningún archivo de
   `procesos_comerciales/`. Ver [`estados.md`](./estados.md) y D-PROCESOS-002 en
   [`decisiones.md`](./decisiones.md).

2. **El constraint de negocio `ck_proc_cotizacion_sin_seguimiento` no tiene migración
   versionada en el repositorio.** Confirmado por el propio comentario de
   `service.py:13-16` (RN-PROCESOS-001, [`reglas.md`](./reglas.md)) y por D-PROCESOS-003
   en [`decisiones.md`](./decisiones.md). [IMPLEMENTADO] el hecho de que no se
   encontró la migración en esta sesión. Si alguien reconstruyera el schema desde las
   migraciones versionadas de este repositorio, el `CHECK` de base de datos no se
   recrearía — la validación de `_validar_campos_de_seguimiento` en Python quedaría
   como única barrera. Esa barrera además **no protege** los 2 `INSERT` inline que
   otros módulos podrían llegar a hacer sobre esta tabla en el futuro (hoy no existe
   ninguno fuera de `procesos_comerciales/repository.py:crear_proceso_comercial`, ver
   [`base_de_datos.md`](./base_de_datos.md)), porque la validación vive únicamente en
   `service.py`, no en la base de datos ni en ningún otro punto compartido.

## P2 — Deuda técnica relevante

1. **Ausencia total de guarda de transición de estado en todo el repositorio.**
   `presupuestos/repository.py:actualizar_proceso_comercial` (`:68-71`) es un `UPDATE`
   genérico sin ninguna condición sobre el `estado` anterior del proceso comercial.
   [IMPLEMENTADO], confirmado por lectura completa de
   `presupuestos/service.py:180-255` y `presupuestos/repository.py:68-71` en esta
   sesión. Nada impide forzar `estado="presentado"` sobre un proceso que ya esté en
   `cerrado`, `cancelado` o `adjudicado` — los mismos estados que
   `_ESTADOS_TERMINALES` (`repository.py:9`) considera "fuera de curso" para el
   listado. Ver [`estados.md`](./estados.md).

2. **7+ implementaciones distintas de "buscar proceso comercial por id", repartidas en
   5 módulos más 1 servicio externo, cada una con su propio subconjunto de columnas.**
   `matching/repository.py:14-22`, `extraccion/repository.py:13-21` (dentro de
   `presupuestacion/`), `pricing/repository.py:135-143`, `pricing/router.py:22-28`
   (inline), `compras/repository.py:6-14`, `compras/router.py:50-56` (inline) y
   `presupuestos/repository.py:18-26` seleccionan columnas ligeramente distintas
   (`id, drogueria_id, cliente_id`; `id, drogueria_id, cliente_id, clase`; `id,
   drogueria_id`; `id, drogueria_id, clase, estado`) para el mismo propósito, sin una
   función central reusable. [IMPLEMENTADO]. Ver [`arquitectura.md`](./arquitectura.md)
   para el detalle completo por archivo.

## P3 — Menor

1. **Estado incierto de la tabla legacy `licitaciones`.**
   `services/extraccion/procesos_comerciales_client.py:7-11` afirma en su docstring
   que la tabla `licitaciones` "ya no existe", pero
   `services/extraccion/routers/licitaciones.py` sigue vivo y consultando esa misma
   tabla (`listar_activas`, `:119-130`, confirmado leído en esta sesión). No es
   verificable sin acceso a la base de datos real si la tabla efectivamente ya no
   existe o si ambas afirmaciones coexisten (por ejemplo, la tabla vacía pero presente)
   — "Pendiente de definición funcional". El propio código explica que
   `routers/licitaciones.py` se deja intacto deliberadamente mientras el HTML legacy
   (`templates/licitaciones.html`, `calendario.html`) lo siga usando
   (`procesos_comerciales_client.py:7-11`, con referencia a
   `openspec/changes/carga-documentos/proposal.md`, no verificada en esta sesión).

2. **Mensaje de error con vocabulario legacy mezclado.**
   `services/extraccion/procesos_comerciales_client.py:47` devuelve el mensaje
   `"licitacion_id no es un UUID válido: {proceso_comercial_id}"` para un parámetro que
   se llama `proceso_comercial_id` en toda la firma de la función
   (`validar_proceso_comercial_id`, `:30`). [IMPLEMENTADO], cosmético: mezcla el
   vocabulario de la tabla vieja (`licitacion_id`) con el de la tabla nueva
   (`proceso_comercial_id`) en un mensaje que ve el usuario final de
   `services/extraccion`.
