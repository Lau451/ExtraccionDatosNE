# Tasks: Carga de documentos

**Change:** carga-documentos
**Estado:** verificación end-to-end completa — falta solo el archivado (ver sección final)

---

## Scaffold y wiring base (sesión 2026-07-14) — hecho

- [x] `CargaDocumentos.tsx`, `FormCard.tsx`, `RecentCard.tsx` — scaffold completo
- [x] Drag & drop + selección de archivo
- [x] Selector de cliente contra `GET /api/clientes`
- [x] `POST /procesar` funcional para el caso sin licitación vinculada
- [x] Verificado en Chrome real (toggle, selectores, upload básico)

## Backend — resolver procesos_comerciales sin tocar routers/licitaciones.py — hecho

- [x] `services/extraccion/procesos_comerciales_client.py`: `validar_proceso_comercial_id()` y
      `listar_nombres_procesos_comerciales()`, ambas con `.eq("drogueria_id", drogueria_id)`
      explícito (client es service_role, bypasea RLS)
- [x] `POST /procesar` usa el nuevo helper para validar `licitacion_id` SI viene seteado — ya NO
      es obligatorio para ningún tipo (revertido tras la revisión de scope, ver proposal.md)
- [x] `POST /procesar` rechaza (422) `tipo == "ordenes"` fail-fast
- [x] `persistent_output.py:persistir_output_final()` — gap encontrado y corregido: ahora persiste
      `proceso_comercial_id` cuando `licitacion_id` no es `None` (antes se descartaba silenciosamente)
- [x] `GET /api/documentos` reemplaza el embed roto `licitacion:licitaciones(...)` por
      `proceso_comercial_id` crudo + `listar_nombres_procesos_comerciales()`. Campo renombrado de
      `licitacion` a `proceso_comercial`
- [x] **Bug adicional encontrado al levantar el servidor real**: el select de `GET /api/documentos`
      incluía `client_id`, columna que NO existe en `extraction_results` (confirmado contra
      `docs/schema/extractor_final.sql`) — causaba 500 en todo pedido. Preexistía a este change
      (el select original roto ya lo tenía). Corregido: columna sacada del select y del tipo
      `DocumentoReciente` en el frontend.
- [x] Tests actualizados: `test_licitaciones_persistence.py`, `test_main_integration.py`
      (patch targets renombrados, tests de "comparativa sin vincular → 422" y el requisito
      correspondiente ELIMINADOS tras la revisión de scope — esa regla ya no existe en este
      endpoint). Suite completa corrida: **383 passed**.
- [x] Verificado contra servidor real (`curl http://localhost:8000/api/documentos` → 200, shape
      correcto, sin 500)

## Frontend — toggle de 3 opciones y copy — hecho

- [x] `FormCard.tsx`: tercera opción "Orden de compra" deshabilitada, badge "Próximamente"
- [x] Verificado en Chrome real: click en "Orden de compra" no cambia el tipo seleccionado

## Revertido tras la revisión de scope (2026-07-15, misma sesión)

Estas tareas se habían completado y después se revirtieron explícitamente — quedan documentadas
para que no se dupliquen por error en `validar-extraccion`, que es donde esta lógica pertenece
ahora:

- [x→revertido] Selector secundario de `clase` (Licitación/Directa) en el flujo principal
- [x→revertido] `VinculacionSelector.tsx` (componente nuevo, 2 variantes) — **archivo borrado**,
  nunca se shippeó fuera de esta sesión
- [x→revertido] `NuevaLiciCotiDialog.tsx` recibiendo `clase` como prop — el cambio de firma queda
  (ya no gestiona `clase` como estado propio), pero el componente se quedó sin ningún caller en
  este change. NO se borró — ver proposal.md, razón: reutilizable en `validar-extraccion`
- [x→revertido] `POST /procesar` rechazando comparativas sin vincular — revertido en `main.py`,
  tests correspondientes eliminados

## Limpieza relacionada — hecho

- [x] Borrado código muerto en `frontend/src/lib/api/extraccion.ts`: `listarLicitacionesActivas`,
      `crearLicitacion`, `LicitacionActiva`, `LicitacionCreatePayload`, `TipoLicitacion`
- [x] `DocumentoReciente.licitacion` renombrado a `proceso_comercial`, `client_id` eliminado
      (columna inexistente)

## Verificación end-to-end

- [x] Chrome real: rama Licitación/Directa — toggle, dropzone, Cliente, sin selector de
      vinculación, sin errores de consola
- [x] Chrome real: rama Comparativa — mismo layout reducido, sin selector de vinculación
- [x] Chrome real: "Orden de compra" deshabilitada, badge "Próximamente", no responde al click
- [x] `GET /api/documentos` verificado contra servidor real (`curl`) — 200, sin 500, shape
      `proceso_comercial: null` para los documentos existentes (ninguno vinculado, esperado)
- [x] Subir un archivo real end-to-end y confirmar que aparece en "Cargas recientes" —
      verificado en Chrome real (sesión 2026-07-25) con `c1002_compraagil.pdf` adjuntado por el
      usuario: `POST /procesar` → "Documento procesado correctamente" → fila `completed` visible en
      "Cargas recientes" en la misma vista, sin recargar. La limitación previa de adjuntar archivos
      por path ya no aplica: el tool de browser automation ahora lo soporta cuando el usuario
      comparte el archivo con la sesión.
- [x] Bug encontrado en esta misma verificación y corregido: `POST /procesar` responde 200 antes de
      que `schedule_persist_output` (BackgroundTask, `services/extraccion/main.py`) termine de
      escribir en `extraction_results` — el `invalidateQueries` único que corría en
      `FormCard.onSuccess` casi siempre perdía la carrera contra ese guardado async, dejando
      "Cargas recientes" desactualizado hasta el próximo refetch (foco de ventana o navegación).
      Fix: `FormCard.tsx` ahora reintenta `fetchQuery` sobre `documentos-recientes` (hasta 6 veces,
      600ms de por medio) hasta ver crecer el conteo de documentos, en vez de un solo invalidate.
      Reverificado en Chrome real: la fila aparece sin recargar.
- [x] NO se corrió `npm run build` en ningún momento (regla del usuario) — todo verificado vía
      `vite dev` + Chrome real

## Archivado (al cerrar)

- [x] `frontend/PROGRESS.md` actualizado a "✅ Hecho"
- [x] Change movido a `openspec/changes/archive/carga-documentos/` en el mismo commit (o
      inmediatamente siguiente) que cierra la última tarea pendiente — regla 2 de `openspec/AGENTS.md`
