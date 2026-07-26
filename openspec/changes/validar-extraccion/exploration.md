# Exploration: Validar extracción

**Change:** validar-extraccion
**Fecha:** 2026-07-25
**Fase:** sdd-explore (previa a proposal.md real)

---

## Qué se confirmó del stub original

El stub (`proposal.md`, sección "Scope heredado de carga-documentos") acertó en:

- `services/extraccion/procesos_comerciales_client.py` — `validar_proceso_comercial_id()` y
  `listar_nombres_procesos_comerciales()` siguen existiendo y filtran `.eq("drogueria_id",
  drogueria_id)` como se documentó.
- `services/extraccion/persistent_output.py` sigue persistiendo `proceso_comercial_id` en
  `extraction_results` cuando se le pasa.
- `frontend/src/features/carga-documentos/components/NuevaLiciCotiDialog.tsx` está intacto,
  reusable tal cual, ya llama a `presupuestacionFetch` (backend con JWT), sin caller todavía.
- No existe ninguna ruta/feature de frontend para "Validar extracción" — confirmado por glob. Sin
  entrada en el sidebar tampoco.

## Qué se descubrió distinto (esto es lo importante)

**El mecanismo real NO es el que el stub suponía.** El stub apostaba a que la vinculación pasaría
por `PATCH /api/extraction-results/{id}` en `services/extraccion` — ese router está **roto/stale**:
referencia columnas (`licitacion_id`, `client_id`) que no existen en el schema actual de
`extraction_results` (`docs/schema/extractor_final.sql:387-408`). El único consumidor de ese
endpoint es su propio test. Candidato a borrar.

El mecanismo real, ya construido y probado, es **`POST /extracciones/{extraction_id}/validar`** en
`services/presupuestacion/extraccion/` (`router.py`, `service.py`, `repository.py`, `models.py`),
con 12 tests en `tests/extraccion/test_service.py` y documentación en
`docs/modulos/extraccion_validacion/`. Este endpoint no solo vincula — **materializa** filas reales:

- Para `licitacion`/`cotizacion`: crea `items_proceso` (dispara el matching).
- Para `comparativa`: crea `comparativas` + `ofertas_items`, con versionado.
- Para `orden_compra`: explícitamente no implementado todavía.
- Marca `extraction_results.validado = TRUE`, `validado_por`, `validado_at` — flag de un solo
  sentido, irreversible.

**"Validar extracción" no es solo una pantalla de vinculación** — el comentario del propio schema
de `comparativas` dice literalmente "se crea al validar la extracción". El scope real es donde la
extracción cruda de la IA se convierte en filas de negocio de verdad.

## Otros hallazgos

- `services/extraccion/main.py` — `GET /api/documentos/{doc_id}` también está roto (mismo patrón:
  `client_id`, tablas muertas `comparativas_results`/`licitaciones_results`).
- Ningún endpoint de listado filtra `extraction_results` por `validado` — `GET /api/documentos` no
  devuelve ese campo.
- No existe ninguna capacidad de edición de filas en ningún lado — `validar_extraccion` lee el CSV
  tal cual quedó en disco.

## Riesgo de infraestructura confirmado (no solo "sin verificar")

`services/extraccion` (puerto 8000) y `services/presupuestacion` (puerto 8001) son dos contenedores
Docker separados (`services/extraccion/Dockerfile`, `services/presupuestacion/Dockerfile`).
Verificado contra `docker-compose.yml`: **no hay sección `volumes:` en ningún servicio.**
`validar_extraccion` (en presupuestacion) lee `extraction_results.csv_disk_path` del disco local —
un path que escribió el OTRO contenedor. En producción (Docker real) esto no puede funcionar sin un
volumen compartido. Funciona hoy en desarrollo local solo porque ambos servicios corren directo
sobre el filesystem del host, sin containerización — no es una garantía real.

## Decisiones tomadas con el usuario (2026-07-25, post-exploración)

1. **Edición de filas antes de confirmar: SÍ entra en el scope.** El backend hoy solo soporta
   confirmar+vincular tal cual viene de Gemini — hay que agregar capacidad de edición antes de que
   se materialicen las filas reales.
2. **Gap de volumen compartido: se resuelve en este mismo change.** Agregar `volumes:` a
   `docker-compose.yml` para que ambos contenedores compartan `OUTPUT_BASE_DIR`. Cambio chico y
   contenido, no toca lógica de negocio.

## Recomendación de enfoque para la proposal real

- Reusar `services/presupuestacion/extraccion/` como base — la vinculación y materialización no
  necesitan reescribirse, solo extenderse para soportar edición de filas antes de `validar`.
- Borrar/deprecar el router stale `PATCH /api/extraction-results/{id}` en `services/extraccion` —
  no tiene caller real, está roto, y genera confusión sobre cuál es el mecanismo verdadero.
- Decidir dónde vive el listado "pendientes de validar" — presupuestacion parece más consistente
  para RBAC (ya exige JWT + rol).
- Reubicar `NuevaLiciCotiDialog.tsx` a `features/validar-extraccion/` tal cual, ya es reusable.
- Agregar volumen compartido en `docker-compose.yml` como parte de este change.

## Preguntas que quedaban abiertas (ya resueltas arriba)

1. ~~¿Edición de filas en scope, o validar == confirmar+vincular tal cual?~~ → Resuelto: sí, en scope.
2. ~~¿Cómo se resuelve el filesystem compartido entre contenedores?~~ → Resuelto: volumen compartido en este change.
