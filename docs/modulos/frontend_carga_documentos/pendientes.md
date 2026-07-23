# Pendientes — Auditoría técnica de Carga de documentos

Clasificación P1 (crítico/bloqueante) / P2 (deuda técnica relevante) / P3 (menor), verificada
contra el código real en esta sesión.

## P1 — Crítico

1. **No hay ningún test de frontend en todo el repositorio, incluido este módulo.** Ya documentado
   como hallazgo transversal en [`../frontend_login/pendientes.md`](../frontend_login/pendientes.md)
   P1(1); se confirma que sigue aplicando sin cambios: `frontend/package.json` (releído en esta
   sesión) no tiene script `test` ni `vitest` en `dependencies`/`devDependencies`; no se encontró
   ningún archivo `*.test.ts(x)`/`*.spec.ts(x)` en `frontend/src`. Esto aplica en particular a
   `FormCard.tsx` (la lógica más densa del módulo: mutación, invalidación de cache, reglas de tipo
   de documento) y a `NuevaLiciCotiDialog.tsx` (que ni siquiera se ejercita en la app real, así que
   un test sería hoy la única forma de verificar que sigue funcionando). No se repite el análisis
   completo acá — ver el documento enlazado para el detalle y la recomendación.

2. **Falta verificación end-to-end de subida real de archivo (tarea sin cerrar en el change activo).**
   `openspec/changes/carga-documentos/tasks.md:76-81` deja sin marcar (`[ ]`) "Subir un archivo real
   end-to-end y confirmar que aparece en 'Cargas recientes'", con la nota explícita de que no fue
   testeable con las herramientas de automatización de browser disponibles en esa sesión (no
   permiten adjuntar un archivo por path del filesystem a un `<input type="file">` fuera de
   adjuntos compartidos por el usuario). Consistente con esto, el change sigue **activo** — no
   archivado — en `openspec/changes/carga-documentos/` (confirmado: el directorio existe fuera de
   `openspec/changes/archive/` en esta sesión), y `frontend/PROGRESS.md:10` sigue marcando la
   pantalla "🔶 En progreso", no "✅ Hecho". Las tareas de cierre del change
   (`tasks.md:87-89`: actualizar `PROGRESS.md` y mover a `archive/`) también siguen sin marcar.
   [RECOMENDACIÓN]: ejercitar la subida de un archivo real (PDF/Excel válido) contra un backend
   `services/extraccion` corriendo, confirmar que aparece en `RecentCard` sin refrescar la página
   manualmente (validando la invalidación de cache documentada en `flujo.md`), antes de cerrar el
   change.

## P2 — Deuda técnica relevante

1. **`NuevaLiciCotiDialog.tsx` sin ningún caller — código muerto de facto, con un destino de reuso
   todavía no confirmado.** Ver [`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-001: el
   proposal lo declara intencional (reservado para `validar-extraccion`), así que no es una omisión
   accidental — pero a diferencia de `requireRole` en
   [`../frontend_login/pendientes.md`](../frontend_login/pendientes.md) P2(1) (que tiene un destino
   de reuso genérico ya soportado por el sistema de rutas actual), el destino de este componente
   (`openspec/changes/validar-extraccion/`) es solo un stub de `proposal.md` sin `spec.md` ni
   `tasks.md` ("Estado: sin empezar", `validar-extraccion/proposal.md:3`), y el propio stub deja
   abierto si el componente se reubicará "tal cual" o se adaptará (`validar-extraccion/proposal.md:30-31`).
   El riesgo real es doble: (a) puede divergir silenciosamente de `procesosComerciales.ts`/
   `ProcesoComercialCreatePayload` sin que nada lo detecte (sin test, sin caller que lo ejercite);
   (b) existe la posibilidad de que, cuando arranque `validar-extraccion`, se determine que la forma
   actual no sirve tal cual y el componente termine reescrito de todos modos, en cuyo caso el código
   actual habrá quedado muerto sin haberse usado nunca. [IMPLEMENTADO] el hecho de la ausencia de
   caller; [RECOMENDACIÓN] revisar explícitamente este componente como primer paso al iniciar
   `validar-extraccion`, en vez de asumir que se puede montar tal cual.

2. **Manejo de errores de red mínimo en ambos wrappers de fetch.** `extraccionFetch` (`client.ts:17-34`)
   y `presupuestacionFetch` (`presupuestacion.ts:19-41`) comparten el mismo patrón: `const body =
   await response.json().catch(() => null)` — solo protege contra un body que no parsea como JSON.
   Si el propio `fetch()` rechaza (red caída, DNS, CORS, timeout del navegador), esa excepción
   original (p. ej. `TypeError: Failed to fetch`) se propaga sin envolver en `ApiError`, así que
   `mutation.error` en `FormCard.tsx:133` (cast `as Error`) termina mostrando el mensaje crudo del
   navegador en vez de un mensaje curado. No hay retry configurado en ninguna de las dos
   `useMutation` de este módulo (`FormCard.tsx:28-38`, `NuevaLiciCotiDialog.tsx:27-44` — TanStack
   Query no reintenta mutaciones por defecto, y ninguna de las dos pasa `retry`), y no hay
   diferenciación entre error de red, error HTTP y timeout en ningún punto de la cadena. Mismo
   hallazgo, en esencia, que RN-LOGIN-003 en el módulo de Login pero sin siquiera el mensaje curado
   fijo que tiene `LoginForm` — acá el usuario ve directamente `(mutation.error as Error).message`.
   [RECOMENDACIÓN]: envolver el `fetch()` en un `try/catch` dentro de ambos wrappers para
   distinguir al menos "error de red" de "error HTTP", y considerar un mensaje curado por defecto en
   la UI en vez de mostrar el mensaje crudo del error.

3. **Sidebar desalineado con las 8 pantallas del MVP real.** `NAV_ITEMS` (`Sidebar.tsx:12-19`) no
   corresponde a los nombres de `frontend/PROGRESS.md:8-16` — tiene "Licitaciones", "Calendario",
   "Historial", "Presupuestos", "Comparativas" (todas `disabled` salvo "Carga de documentos"), sin
   ningún ítem para "Procesos comerciales" (#4, ya "✅ Hecho" según `PROGRESS.md:12` pero sin
   pantalla propia — solo accesible hoy a través del modal huérfano de este módulo), "Validar
   extracción" (#3), "Matching" (#5) ni "Compras" (#8). El propio código lo reconoce como
   placeholder pendiente de mockup Figma — cita exacta, `Sidebar.tsx:10-11`:
   `// Placeholder: los 6 items y sus rutas finales vienen del mockup Figma`
   `// (SEjXiBEMxprppdgmlNHKO8), todavía sin validar por screenshot en esta sesión.`
   [IMPLEMENTADO] el hecho del desalineamiento; [RECOMENDACIÓN] actualizar `NAV_ITEMS` en el mismo
   change que le dé pantalla propia a "Procesos comerciales" o que arranque "Validar extracción",
   para no acumular más desalineamiento.

4. **`FormCard.tsx` mezcla responsabilidades sin separación.** Ver el detalle completo en
   [`arquitectura.md`](./arquitectura.md) "FormCard.tsx mezcla responsabilidades": estado de UI
   (drag&drop), fetch de clientes, mutación de subida y reglas de negocio del tipo de documento
   (`ACCEPT_POR_TIPO`, opciones deshabilitadas) conviven en un único componente de 149 líneas, sin
   separación entre contenedor y presentación ni extracción de las constantes de negocio a un
   archivo aparte. No genera un bug hoy, pero dificulta testear cada responsabilidad por separado
   (relevante en particular dado el hallazgo P1(1) de ausencia total de tests) y aumenta el costo de
   cualquier cambio futuro que solo toque una de las cuatro responsabilidades. [RECOMENDACIÓN]:
   extraer `ACCEPT_POR_TIPO`/`TIPO_OPTIONS` a un módulo de configuración, y considerar un hook
   `useCargaDocumento()` que encapsule `clientesQuery` + `mutation` para separar la lógica de la
   presentación.

5. **`ApiError` duplicado entre `client.ts` y `presupuestacion.ts` sin mecanismo de unificación.**
   Ver [`decisiones.md`](./decisiones.md) D-CARGADOCUMENTOS-003 para el detalle completo y el
   motivo (no documentado explícitamente, razonado por diferencia funcional entre wrappers). Se
   lista también acá como deuda técnica porque, a diferencia de una decisión cerrada, no hay
   evidencia de que sea definitiva — es simplemente el estado actual sin justificación registrada
   en el código. [RECOMENDACIÓN]: si en algún momento un componente necesita manejar errores de
   ambos backends de forma uniforme, evaluar extraer una única clase `ApiError` a un módulo
   compartido (`lib/api/errors.ts` o similar) e importarla desde ambos wrappers.

6. **`STATUS_STYLES` de `RecentCard.tsx` no coincide con los valores reales que escribe el backend.**
   `RecentCard.tsx:5-9` define estilos para las claves `'completado'`, `'procesando'`, `'error'`
   (español). Según [`../extraccion_api/estados.md`](../extraccion_api/estados.md) ("`extraction_results.status`
   y `chunk_results.status` — no son máquinas de estado en este módulo"), el código Python de
   `services/extraccion` que escribe esa columna lo hace siempre con el literal en inglés
   `"completed"` (`persistent_output.py:207`, citado en esa documentación) — no se encontró
   evidencia de que ese módulo escriba `"procesando"`, `"error"`, ni siquiera `"completado"` (con o
   sin acento) en ningún punto. Consecuencia: en el estado actual del backend, ninguna clave de
   `STATUS_STYLES` matchea nunca el valor real de `doc.status`, así que el badge de estado en
   `RecentCard.tsx:36-43` siempre cae al fallback `bg-slate-100 text-slate-600`
   (`STATUS_STYLES[doc.status] ?? 'bg-slate-100 text-slate-600'`, `RecentCard.tsx:39`) — el
   color-coding por estado, tal como está escrito, no se activa nunca contra el backend real de
   hoy. [IMPLEMENTADO] la definición de `STATUS_STYLES` con esas claves; [SUPOSICIÓN] razonada de
   que nunca matchea, a partir de cruzar ambos documentos — no se ejecutó el flujo end-to-end en
   esta sesión para confirmarlo empíricamente (ver P1(2) de este mismo documento, que ya señala que
   esa verificación end-to-end está pendiente). [RECOMENDACIÓN]: alinear las claves de
   `STATUS_STYLES` con los valores reales en inglés (`'completed'`, y los que corresponda si algún
   día `services/extraccion` escribe `'partial'`/`'failed'` como sugiere el comentario de
   `persistent_output.py:69` citado en `../extraccion_api/estados.md`), o normalizar el valor en el
   backend antes de exponerlo si se prefiere mantener el copy en español del lado del frontend.

## P3 — Menor

1. **`licitacionId` sigue existiendo en `ProcesarPayload`/`procesarDocumento` sin ningún caller que
   lo envíe.** `extraccion.ts:23` (`licitacionId?: string`) y `extraccion.ts:51`
   (`if (licitacionId) formData.append('licitacion_id', licitacionId)`) siguen implementados, pero
   `FormCard.tsx:31` nunca lo pasa en el objeto que arma para `procesarDocumento`. Es consistente
   con D-CARGADOCUMENTOS-002 (el campo sigue existiendo del lado del backend como opcional, "por
   compatibilidad con otros posibles callers", `openspec/changes/carga-documentos/proposal.md:41-42`)
   y no representa un bug — pero es una superficie de API frontend sin ningún uso real hoy, similar
   en espíritu a `NuevaLiciCotiDialog.tsx` aunque de menor riesgo (es un campo opcional de una
   función, no un componente completo).

2. **`listarProcesosComerciales` (`procesosComerciales.ts:21-23`) está exportado pero sin ningún
   caller.** `NuevaLiciCotiDialog.tsx` solo invalida la query `['procesos-comerciales']`
   (`:38`) tras crear un proceso — no la lee con esta función en ningún punto del alcance de esta
   documentación. Menor porque el propio componente que la acompañaría (`NuevaLiciCotiDialog.tsx`)
   ya está huérfano (P2(1)); si ese componente se reactiva, es esperable que también se agregue el
   componente que sí liste procesos comerciales existentes (el modal solo cubre "crear uno nuevo",
   no "elegir uno existente" — ver el diseño heredado descripto en
   `openspec/changes/validar-extraccion/proposal.md:22-27`).
