# Pendientes — Auditoría técnica de Clientes

Clasificación P1 (ausencia de una capacidad esperada) / P2 (deuda técnica relevante) /
P3 (menor), verificada contra el código y los tests reales en esta sesión.

## P1 — Ausencia de auditoría

1. **Ninguna mutación de este módulo queda registrada en `historial_cambios`.**
   Confirmado por grep exhaustivo en esta sesión: 0 referencias a `core.audit`,
   `registrar_cambio`, `registrar_cambios` o `registrar_evento_ciclo_vida` en los 4
   archivos fuente (`models.py`, `repository.py`, `service.py`, `router.py`).
   [IMPLEMENTADO] el hecho. Esto significa que el alta y la baja de un cliente, el
   upsert de `instrucciones_prompt` (el texto que se inyecta al prompt de Gemini vía
   `services/extraccion/main.py`), el alta/edición de un contacto y el alta de una
   observación no dejan ningún rastro auditable — a diferencia de módulos que sí
   integran auditoría, ver `docs/modulos/core/` para el mecanismo (`core/audit.py`) que
   otros módulos consumen. Particularmente relevante para
   `cliente_formato_documentos`: un cambio en las instrucciones que recibe la IA no
   queda trazado a quién lo hizo ni cuándo, más allá del campo `actualizado_por` (sin
   historial de versiones anteriores).

## P2 — Deuda técnica relevante

1. **Validación de tenant duplicada e independiente en dos capas, sin compartir
   resultado.** Para los 3 sub-recursos, `router.py` valida pertenencia con
   `user_client` (RN-CLIENTES-007, `router.py:123-139`) y `service.py` la revalida con
   `service_client` (RN-CLIENTES-002, `service.py:18-26`) — dos queries distintas
   contra la misma tabla, con distinta excepción cada una (`ForbiddenError` vs
   `ValidationError`). [IMPLEMENTADO]. Riesgo concreto: si en el futuro se agrega un
   call site que invoque una función `*_para_endpoint` de `service.py` sin pasar antes
   por `_validar_cliente_y_obtener_drogueria_id` del router (por ejemplo, un script
   interno o un nuevo endpoint que reutilice el wrapper), la protección de
   RN-CLIENTES-007 (incluida la excepción explícita para `superadmin`) desaparece sin
   que nada lo señale estructuralmente — solo queda la validación de `service.py`, más
   estricta y sin la excepción de rol.

2. **Duplicación de mantenimiento: tres implementaciones distintas para la misma regla
   de negocio.** RN-CLIENTES-001, RN-CLIENTES-002 y RN-CLIENTES-007 resuelven el mismo
   problema (¿el cliente pertenece a la droguería del solicitante?) con tres consultas
   y tres tipos de excepción distintos (`NotFoundError`, `ValidationError`,
   `ForbiddenError` — ver D-CLIENTES-004 en [`decisiones.md`](./decisiones.md)). Si la
   regla de negocio cambiara (por ejemplo, agregar una excepción para otro rol además
   de `superadmin`), habría que tocar los tres lugares de forma consistente, sin que
   exista un punto único de verdad. [IMPLEMENTADO].

## P3 — Menor

1. **Inconsistencia de excepciones dentro del mismo `service.py` para el mismo
   escenario.** `obtener_cliente` (RN-CLIENTES-001, `service.py:126-130`) usa
   `NotFoundError` para "el cliente es de otra droguería" — oculta la existencia del
   recurso. `_validar_cliente_de_la_drogueria` (RN-CLIENTES-002, `service.py:18-26`)
   usa `ValidationError` para el mismo escenario exacto — revela que el recurso existe,
   solo que no es accesible. Ambas funciones conviven en el mismo archivo sin que haya
   un comentario que explique la diferencia. [IMPLEMENTADO]. Ver D-CLIENTES-004.

2. **`cliente_contactos.activo` es escribible pero no tiene ningún efecto funcional.**
   `ClienteContactoUpdate.activo` (`models.py:67`) permite pisar el campo vía `PATCH
   /clientes/{id}/contactos/{contacto_id}`, y `ClienteContactoOut.activo`
   (`models.py:79`) lo expone en la respuesta, pero ningún query de `repository.py`
   (`listar_contactos`, `repository.py:66-74`; `buscar_contacto`, `repository.py:81-85`)
   lo usa como filtro. [IMPLEMENTADO] — confirmado por lectura completa de
   `repository.py` en esta sesión. Mismo patrón de deuda ya documentado para
   `usuarios.activo` en [`../usuarios/README.md`](../usuarios/README.md): una API que
   sugiere "desactivar contacto" sin que esa desactivación tenga ningún efecto
   observable.

3. **Sin paginación en los 4 listados del módulo.** `listar_clientes`
   (`repository.py:30-41`), `listar_contactos` (`repository.py:66-74`),
   `listar_formato_documentos` (`repository.py:118-126`) y `listar_observaciones`
   (`repository.py:133-141`) devuelven siempre el conjunto completo de filas que
   matchea el filtro, sin `limit`/`offset` ni cursor. [IMPLEMENTADO] el hecho de que no
   existe paginación. No es posible confirmar si esto constituye un problema real sin
   datos de volumen de producción — pendiente de definición funcional.

4. **`codigo_interno` no se escribe en el alta de cliente de este módulo.** `crear_cliente`
   (`service.py:99-117`) no incluye `codigo_interno` en el dict insertado
   (`service.py:104-116`), aunque la columna existe en `ClienteOut.codigo_interno`
   (`models.py:39`) y en la tabla (ver [`base_de_datos.md`](./base_de_datos.md)). No se
   pudo confirmar en esta sesión si `codigo_interno` se autogenera por un trigger de
   base de datos no versionado en este repositorio, si se completa después vía
   `services/presupuestacion/imports/repository.py` (que sí lo usa para matching por
   lote, `imports/repository.py:141-185`), o si simplemente queda `None` para clientes
   creados por esta API — pendiente de definición funcional.
