# Proposal: Carga de documentos

**Estado: en progreso.** Iniciado el 2026-07-15 al adoptar la convención de `openspec/`. Tuvo dos
revisiones el mismo día: primero se agregó vinculación a `procesos_comerciales` en esta pantalla
(por un bug de diseño real, ver "Hallazgo" abajo); después se sacó esa vinculación de acá y se
trasladó a la pantalla "Validar extracción" (ver "Revisión: la vinculación se saca de esta
pantalla" abajo). Este documento refleja el estado FINAL del scope — la sección de hallazgo se deja
como registro histórico de por qué se llegó hasta acá, no como spec vigente.

## Intent

Pantalla donde el usuario sube un documento (licitación/directa, comparativa, orden de compra —
esta última todavía sin pipeline) para que `services/extraccion` lo procese con Gemini. Incluye el
selector de cliente y la lista de "cargas recientes". Ya NO incluye vinculación a un
`proceso_comercial` — ver revisión abajo.

## Hallazgo (histórico): bug de diseño en el formulario, verificado contra schema

`comparativas.proceso_comercial_id` es `UUID NOT NULL` (`docs/schema/extractor_final.sql:561`).
Igual `ordenes_compra.proceso_comercial_id` (`:609`). El mockup original ocultaba el selector de
vinculación en la rama "Comparativa" cuando debía capturarse ese dato. Esto llevó a una primera
implementación (`VinculacionSelector` con dos variantes, selector de clase movido al flujo
principal, bloqueo de submit sin vinculación) que después se revirtió — ver la revisión siguiente.
El hallazgo del bug en sí sigue siendo válido: el dato es efectivamente obligatorio en la base. Lo
que cambió es EN QUÉ PANTALLA se captura.

## Revisión: la vinculación se saca de esta pantalla

**Decisión**: `proceso_comercial_id` es una decisión de negocio pura, sin ningún impacto en la
calidad de la extracción. La pantalla correcta para resolverla es "Validar extracción" (pantalla
#3 del MVP), que el usuario siempre visita antes de que se cree cualquier dato de negocio real
(la fila efectiva en `comparativas`, con su `NOT NULL`, se crea recién ahí, no en la carga cruda).

`Cliente`, en cambio, se queda tal cual en esta pantalla — ese campo SÍ afecta la extracción en sí:
inyecta instrucciones al prompt de Gemini en el momento de la llamada (`_resolver_formato_prompt`
en `main.py`), así que no se puede diferir a una pantalla posterior sin perder esa capacidad.

**Consecuencia en el código ya escrito**: se revirtió el requisito agregado en `POST /procesar`
que rechazaba (422) una comparativa sin `licitacion_id` — si la UI nunca va a mandar ese campo
desde esta pantalla, exigirlo acá hubiera roto toda carga de comparativas. El campo `licitacion_id`
sigue existiendo como parámetro opcional del endpoint (se valida si viene, por compatibilidad con
otros posibles callers), pero no es obligatorio para ningún tipo de documento en `/procesar`.

**Consecuencia en componentes de UI**: `VinculacionSelector.tsx` (creado en esta misma sesión) se
borró — nunca llegó a shippearse fuera de esta conversación. `NuevaLiciCotiDialog.tsx` (parte del
change ya archivado [`archive/procesos-comerciales`](../archive/procesos-comerciales/)) queda SIN
ningún caller en el árbol actual — no se borra, porque la próxima pantalla (`validar-extraccion`)
va a necesitar la misma capacidad de "crear/vincular proceso comercial" y es razonable reutilizarlo
o adaptarlo ahí en vez de reescribirlo desde cero. Queda documentado acá para que no se pierda el
rastro de por qué existe un componente sin imports.

**La decisión de arquitectura ya tomada sigue vigente, solo cambia quién la consume**: `extraccion`
sigue siendo quien va a consultar `procesos_comerciales` directo (opción a, ver razonamiento
completo abajo) — pero el caller pasa a ser la pantalla `validar-extraccion` en vez de esta. El
código de infraestructura ya escrito (`services/extraccion/procesos_comerciales_client.py`) no
cambia y se reutiliza tal cual desde ahí.

## Scope (final)

### Ya implementado (sesiones 2026-07-14 y 2026-07-15 — ver `archive/procesos-comerciales`)
- UI base: `CargaDocumentos.tsx`, `FormCard.tsx`, `RecentCard.tsx`.
- Drag & drop + selección de archivo, selector de cliente (`GET /api/clientes`), verificado en
  Chrome real.
- `POST /procesar` funciona para el caso base sin vincular.

### Flujo final de esta pantalla
1. **Toggle de tipo de documento, 3 opciones**: Licitación/Directa, Comparativa, Orden de Compra.
   La tercera queda **visible pero deshabilitada**, con badge "Próximamente" — no tiene pipeline
   de extracción implementado (confirmado leyendo `main.py`: no hay rama `tipo == "ordenes"`).
   Verificado en Chrome real: la opción no responde al click.
2. **Copy "Cotización" → "Directa"**: aplicado donde corresponda mostrar la clase (fuera de esta
   pantalla — acá no hay selector de clase, ver revisión arriba).
3. **Campo Cliente**: sin cambios.
4. **Sin vinculación a proceso comercial en esta pantalla** — ver revisión arriba.

### Explícitamente fuera de scope
- `services/extraccion/routers/licitaciones.py` como módulo completo — **no se toca**. Sigue
  activo porque `templates/licitaciones.html` y `calendario.html` (HTML legacy) llaman
  `/api/licitaciones/*` en producción real (confirmado en el commit `8de06b0`).
- Pipeline de extracción para Orden de Compra.
- Vinculación/creación de `procesos_comerciales` — pertenece a `validar-extraccion`
  (ver [`openspec/changes/validar-extraccion/proposal.md`](../validar-extraccion/proposal.md)).

## Decisión de arquitectura — RESUELTA (opción a), consumida desde validar-extraccion

**Decisión**: quien resuelve `procesos_comerciales` es `services/extraccion` directo, con su
cliente Supabase existente (`get_client()`, service-role key), escopeado por `drogueria_id` vía
`resolver_drogueria_id_unica()`. Mismo patrón que ya usa para escribir en
`extraction_results`/`processing_sessions`.

**Por qué**: el schema ya está diseñado así — `extraction_results.proceso_comercial_id` tiene FK
directa a `procesos_comerciales(id)` (`extractor_final.sql:1087`), sin tabla intermedia. RLS de
`procesos_comerciales` permite `SELECT` a cualquier usuario autenticado del mismo tenant
(`rls_final.sql:202`), aunque en la práctica `extraccion` bypassea RLS igual por usar
`SUPABASE_SERVICE_KEY`.

**Importante — NO tocar `routers/licitaciones.py`**: la consulta a `procesos_comerciales` vive en
código nuevo (`procesos_comerciales_client.py`), no reutiliza `validar_licitacion_id()` de ese
archivo, para no violar la decisión ya tomada en `8de06b0`.

## Riesgos

Bajo. El código de infraestructura (`procesos_comerciales_client.py`, la persistencia de
`proceso_comercial_id` en `extraction_results`) ya está construido y probado — queda a la espera de
que `validar-extraccion` lo consuma desde su propia UI.
