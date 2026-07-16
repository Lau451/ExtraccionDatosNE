# Proposal: Validar extracción

**Estado: sin empezar.** Stub creado el 2026-07-15 durante el trabajo de `carga-documentos`,
únicamente para dejar registrado el scope que se le transfirió — no hay `spec.md` ni `tasks.md`
todavía. Se completa cuando arranque el trabajo real de esta pantalla (pantalla #3 del MVP, ver
`frontend/PROGRESS.md`).

## Por qué existe este stub ahora

Durante el change [`carga-documentos`](../carga-documentos/proposal.md) se descubrió (verificado
contra `docs/schema/extractor_final.sql`) que `comparativas.proceso_comercial_id` y
`ordenes_compra.proceso_comercial_id` son `UUID NOT NULL`. La primera implementación intentó
capturar esa vinculación en la pantalla de carga de documentos. Se revisó esa decisión el mismo
día: `proceso_comercial_id` es una decisión de negocio pura, sin impacto en la calidad de la
extracción — a diferencia de `Cliente`, que sí inyecta instrucciones al prompt de Gemini y por eso
no se puede diferir. El momento correcto para resolver la vinculación es acá, en "Validar
extracción", que el usuario siempre visita antes de que se cree cualquier dato de negocio real (la
fila efectiva en `comparativas`/`ordenes_compra` se crea recién en este paso).

## Scope heredado de carga-documentos (a incorporar cuando arranque este change)

- **Vinculación a `proceso_comercial`**: selector para elegir un proceso comercial existente, con
  variante "crear uno nuevo" para el caso Licitación/Directa (que sí puede fundar un proceso) y
  variante "solo selección" para Comparativa/Orden de Compra (que solo se vinculan a uno
  existente, nunca fundan uno). El diseño completo de esta interacción (incluida la razón por la
  que Comparativa/OC no tienen botón "+ Nueva") está documentado en el historial de
  `carga-documentos/proposal.md` y puede reusarse casi tal cual acá.
- **Componente de UI reusable**: `frontend/src/features/carga-documentos/components/NuevaLiciCotiDialog.tsx`
  quedó sin ningún caller tras sacarse de `carga-documentos` — ya recibe `clase` como prop
  controlada (no gestiona su propio estado de clase). Evaluar si se reubica a
  `features/validar-extraccion/` tal cual, o se adapta.
- **Backend ya construido y reusable sin cambios**: `services/extraccion/procesos_comerciales_client.py`
  (`validar_proceso_comercial_id()`, `listar_nombres_procesos_comerciales()`), ambas con el filtro
  `.eq("drogueria_id", drogueria_id)` obligatorio (client es service_role, bypasea RLS). También
  `services/extraccion/persistent_output.py` ya persiste `proceso_comercial_id` en
  `extraction_results` cuando se le pasa.
- **Decisión de arquitectura ya resuelta, no volver a discutir**: `services/extraccion` consulta
  `procesos_comerciales` directo (no vía HTTP a `services/presupuestacion`, no resuelto del lado
  del frontend). Razonamiento completo en `carga-documentos/proposal.md`, sección "Decisión de
  arquitectura".
- **Probablemente el mecanismo real sea `PATCH /api/extraction-results/{id}`**: el router
  `services/extraccion/routers/extraction_results.py` ya tiene un endpoint PATCH que acepta
  `licitacion_id` en el body (ver `tests/test_extraction_results_api.py`) — evaluar si la
  vinculación de esta pantalla pasa por ahí en vez de por un endpoint nuevo. Ese router NO fue
  tocado ni auditado durante `carga-documentos` — verificar su estado real antes de asumir que
  funciona tal cual.

## Siguiente paso

Cuando se arranque este change formalmente: `sdd-explore` o exploración manual del flujo real de
"validar extracción" (qué pantalla/mockup existe, si existe), y recién ahí escribir
`proposal.md` completo (reemplazando este stub), `spec.md`, `design.md` si aplica, y `tasks.md`.
