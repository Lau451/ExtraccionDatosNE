# Decisiones de diseño — Carga de documentos

Numeración D-CARGADOCUMENTOS-NNN, verificada contra el código y el proposal activo
(`openspec/changes/carga-documentos/proposal.md`, `tasks.md`).

### D-CARGADOCUMENTOS-001 — `NuevaLiciCotiDialog.tsx` se mantiene sin caller en vez de eliminarse

- **Decisión**: al sacar la vinculación a `proceso_comercial` de esta pantalla, `NuevaLiciCotiDialog.tsx`
  quedó sin ningún import en `frontend/src/` (confirmado por grep en esta sesión), pero el archivo
  no se borró.
- **Motivo**: explícito en `openspec/changes/carga-documentos/proposal.md:45-50` — cita textual:
  > "`NuevaLiciCotiDialog.tsx` (parte del change ya archivado
  > [`archive/procesos-comerciales`](../../../openspec/changes/archive/procesos-comerciales/))
  > queda SIN ningún caller en el árbol actual — no se borra, porque la próxima pantalla
  > (`validar-extraccion`) va a necesitar la misma capacidad de 'crear/vincular proceso comercial'
  > y es razonable reutilizarlo o adaptarlo ahí en vez de reescribirlo desde cero."

  Como parte de la misma revisión, se ajustó su firma para ese reuso futuro: pasó a recibir `clase`
  como prop controlada en vez de gestionar su propio estado interno (`tasks.md:55-57`).
- **Ventajas**: si `validar-extraccion` efectivamente reusa el componente, se evita reescribir un
  formulario+mutación ya probado en aislamiento; el ajuste de firma (`clase` como prop) ya lo deja
  más cerca de la forma que necesitaría esa pantalla.
- **Desventajas**: es código sin ningún caller, sin test, que puede divergir silenciosamente de
  `procesosComerciales.ts`/`ProcesoComercialCreatePayload` sin que nada lo detecte hasta el día en
  que alguien intente montarlo — mismo patrón de riesgo que `requireRole` en
  [`../frontend_login/decisiones.md`](../frontend_login/decisiones.md) D-LOGIN-003, con una
  diferencia relevante: `requireRole` tiene un destino de reuso ya definido por el sistema de rutas
  actual (cualquier ruta futura que necesite guard por rol), mientras que el destino de
  `NuevaLiciCotiDialog.tsx` (`validar-extraccion`) todavía no tiene `spec.md` ni `tasks.md` —
  `openspec/changes/validar-extraccion/proposal.md:28-31` deja explícitamente abierto si el
  componente "se reubica... tal cual, o se adapta", es decir, ni siquiera está confirmado que la
  forma actual del componente sobreviva sin cambios. Ver
  [`pendientes.md`](./pendientes.md) P2(1) para el detalle de riesgo.

### D-CARGADOCUMENTOS-002 — La vinculación a `proceso_comercial` se saca de esta pantalla y se traslada a "Validar extracción"

- **Decisión**: el formulario de carga (`FormCard.tsx`) no captura ningún `proceso_comercial_id`
  (ni `licitacion_id` en la práctica, aunque el campo sigue existiendo como opcional en
  `ProcesarPayload`/`procesarDocumento`, ver `api.md`). La responsabilidad de vincular (o crear) un
  proceso comercial se difiere a la pantalla "Validar extracción" (#3 del MVP).
- **Motivo**: explícito en `openspec/changes/carga-documentos/proposal.md:29-36` — se determinó que
  `proceso_comercial_id` es una decisión de negocio pura sin impacto en la calidad de la extracción
  (a diferencia de `Cliente`, que sí afecta el prompt de Gemini vía `_resolver_formato_prompt`), y
  que "Validar extracción" es la pantalla que el usuario siempre visita antes de que se cree
  cualquier dato de negocio real (la fila efectiva en `comparativas`, con su `NOT NULL` en
  `proceso_comercial_id`, se crea recién ahí).
- **Ventajas**: separa una decisión de negocio (a qué proceso comercial pertenece este documento) de
  una decisión que afecta la calidad técnica de la extracción (qué cliente, para el prompt);
  evita bloquear la carga de un documento con un 422 por falta de vinculación cuando el usuario
  todavía no decidió a qué proceso pertenece.
- **Desventajas**: implica que "Cargas recientes" (`RecentCard.tsx`) muestra, por diseño, la
  mayoría de los documentos con `proceso_comercial: null` ("Sin vincular",
  `RecentCard.tsx:34`) hasta que el flujo de "Validar extracción" exista y se use — hoy eso es
  permanente, porque esa pantalla no tiene código real (ver `README.md`).

### D-CARGADOCUMENTOS-003 — Dos implementaciones independientes de `ApiError`

- **Decisión**: `lib/api/client.ts:3-11` y `lib/api/presupuestacion.ts:5-13` declaran cada uno su
  propia clase `ApiError extends Error`, estructuralmente idénticas, sin herencia ni tipo compartido
  entre ambas.
- **Motivo**: no hay ningún comentario en el código ni mención en el proposal que explique
  explícitamente por qué no se comparte una sola implementación — **Motivo pendiente de definición
  funcional**. Sí se observan diferencias objetivas entre ambos wrappers que son consistentes con
  (aunque no prueban) una decisión deliberada de mantenerlos separados: `extraccionFetch` no
  inyecta JWT y lee el mensaje de error de `body?.error` (formato propio de `services/extraccion`,
  `client.ts:29`), mientras que `presupuestacionFetch` sí inyecta JWT desde `supabase-js` en cada
  llamada y lee el mensaje de `body?.detail` (formato default de `HTTPException` de FastAPI,
  `presupuestacion.ts:36`) — es decir, aunque la clase de error es idéntica, los dos wrappers que la
  usan no lo son. [SUPOSICIÓN] razonada a partir de esas diferencias; no confirmada como el motivo
  real por ningún comentario o documento del proyecto.
- **Ventajas**: cada wrapper puede evolucionar de forma independiente (por ejemplo, si
  `services/presupuestacion` cambiara su formato de error a algo distinto de `detail`) sin tocar el
  otro archivo.
- **Desventajas**: cualquier código que necesite manejar errores de ambos backends de forma
  uniforme (por ejemplo, un `catch` genérico en un componente que llame a ambas APIs) no puede usar
  un único `instanceof ApiError` — tendría que importar y comprobar contra las dos clases por
  separado. Hoy ningún componente de este módulo necesita eso (`FormCard`/`RecentCard` solo usan
  `client.ts`; `NuevaLiciCotiDialog` solo usa `presupuestacion.ts`), así que el problema es
  latente, no observado. Ver [`pendientes.md`](./pendientes.md).

### D-CARGADOCUMENTOS-004 — "Orden de compra" se muestra deshabilitada, no oculta

- **Decisión**: la tercera opción del toggle de tipo de documento se renderiza siempre visible, con
  `disabled` y un badge "Próximamente" (`FormCard.tsx:9`, `:52-53`, `:65-69`), en vez de omitirse de
  `TIPO_OPTIONS` hasta que el pipeline exista.
- **Motivo**: explícito como requisito (`MUST`) en `openspec/changes/carga-documentos/spec.md:28-29`:
  "MUST deshabilitar la opción 'Orden de compra' (no clickeable) y mostrar badge 'Próximamente'.
  Verificado en Chrome real: el click no cambia el tipo seleccionado."
- **Ventajas**: comunica al usuario que la funcionalidad existe en el roadmap sin necesidad de
  documentación externa; evita que el usuario intente subir una orden de compra y reciba un error
  genérico sin contexto (el backend igual la rechazaría con 422 como defensa en profundidad, ver
  RN-CARGADOCUMENTOS-001).
- **Desventajas**: ninguna identificada — es una decisión de UX de bajo riesgo, consistente con el
  patrón ya usado en el Sidebar para los ítems deshabilitados (`Sidebar.tsx:36-42`).
