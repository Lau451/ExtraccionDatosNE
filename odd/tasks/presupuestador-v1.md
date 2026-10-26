# Presupuestador v1

First in-house version of the presupuestador: upload a file, verify the extraction, match against the product catalog, and build a presupuesto with the same columns as the Progress presupuestador. Real pricing rules come later; v1 uses a fixed margin.

## Specs

- S1 Flow (L2): "el usuario procese el archivo, luego pase por una verificacion coo la de Oc para ver que se haya extraido correctamente, una vez validado sigue la etapa de maching con el catalogo"
- S2 Class at upload (L2): "al procesar el archivo se debe elegir 1 si es directa y 2 si es licitacion porque las directas trabajan con stock y las licitaciones no"
- S3 Verification (L2): "una verificacion coo la de Oc para ver que se haya extraido correctamente"
- S4 Catalog matching (L2): "una vez validado sigue la etapa de maching con el catalogo"
- S5 Progress matches (L2): "puedo ver la posibilidad de exportar los macheos que ya se hicieron en progress para no empezar de 0"
- S6 Presupuesto columns (L2): "se crea el presupuesto en el cual va a aparecer numero de renglon,descripcion del producto, cantidad solicitada, precio unitario, precio total unitarioxcantidad, rentabilidad, costo." / "la idea por ahora es tener lo que se tiene en el presupuestador de progress."
- S7 Fixed margin (L3, L4): "vaos a utilixar un margen fijo hasta hacer el otor de reglas" / "puede ser un 30%"

## Tasks

- [x] T1 (S2) Upload asks for class 1 Directa / 2 Licitación and sends `cotizacion` / `licitacion` so the proceso comercial gets the right `clase`. Route: inline (backend `/procesar` + `persistent_output` + FormCard). Commit: 7d15aa6 (backend 1316 passed, frontend 653 passed, tsc -b and oxlint clean).
- [ ] T2 (S1, S3) Verify the existing `validar-extraccion` flow end to end with a real file of each class; fix gaps. Route: TBD. Commit: —
- [ ] T3 (S4) Matching screen per proceso: renglones, `estado_matching`, candidates, confirm / sin match (backend exists; likely needs a "renglones with candidates" endpoint). Route: TBD. Commit: —
- [ ] T4 (S7) Pricing fixed margin 30%: "margin only" mode on `reglas_pricing` that skips market price (additive migration) + default 30% rule per droguería. Route: TBD. Commit: —
- [ ] T5 (S6) Presupuesto screen: generate button + table with renglón, descripción, cantidad, precio unitario, total, rentabilidad, costo; stock check for directas. Route: TBD. Commit: —
- [ ] T6 (S5) Import Progress matches into `cliente_producto_alias`. BLOCKED: needs a sample Progress export; check whether matches are per client or global. Route: TBD. Commit: —

## Log

- L1 (user, original request): "quiero empezar con el presupuestador, me decis que hay sobre esto en el proyeccto?"
- L2 (user): "bien te explico que pretendo en esta primera version: mi idea es que el usuario procese el archivo, luego pase por una verificacion coo la de Oc para ver que se haya extraido correctamente, una vez validado sigue la etapa de maching con el catalogo en este punto puedo ver la posibilidad de exportar los macheos que ya se hicieron en progress para no empezar de 0, luego se crea el presupuesto en el cual va a aparecer numero de renglon,descripcion del producto, cantidad solicitada, precio unitario, precio total unitarioxcantidad, rentabilidad, costo. En un principio luego puede llegar a modificarse, la idea por ahora es tener lo que se tiene en el presupuestador de progress. esa es la idea general luego vamos a trabajar en coo calcular el precing, tambien hay que acordarse que al procesar el archivo se debe elegir 1 si es directa y 2 si es licitacion porque las directas trabajan con stock y las licitaciones no"
- L3 (user): "vaos a utilixar un margen fijo hasta hacer el otor de reglas"
- L4 (user): "puede ser un 30%" — same 30% for both classes (parent assumption; `reglas_pricing.clase_proceso` allows splitting later).
- L5 (user): "me parece biel el plan, arranca con el documento de seguimiento pero no hagas t1"
- L6 (parent exploration, evidence):
  - Upload offers a single "Licitación / Directa" type (`frontend/src/features/carga-documentos/components/FormCard.tsx:16`); `ProcesoComercialSelector.tsx:19` derives `clase` from `document_type`, so a directa ends up as licitación. `DocType` already includes `cotizacion`; the robot extracts it like licitación (`services/extraccion/persistent_output.py:37`).
  - Validation materializes `items_proceso` and runs `procesar_matching_item` automatically (`services/presupuestacion/extraccion/service.py:1074`); matching = client alias by normalized description, else rapidfuzz WRatio → `automatico` / `sugerido` / `pendiente` (`services/presupuestacion/matching/service.py:39`). No matching UI exists.
  - `calcular_precio` (`services/presupuestacion/pricing/service.py:53`) prefers market median (`v_precio_mercado_producto`) when present and only falls back to `margen_objetivo_pct`; a plain default rule is therefore NOT a fixed margin.
  - Stock: verified at generation and committed at `presentar` only for `clase = cotizacion` (`pricing/service.py:160`, `presupuestos/service.py:195`).
  - Products without cost in `costos_productos` stay without price (`items_sin_precio`).
  - No presupuesto UI exists; `presupuesto_items` already holds `precio_unitario`, `cantidad_ofertada`, `monto_total`, `costo_usado`, `margen_resultante_pct`.
  - Hard rule: any FK anchors on `item_proceso_id`, never `presupuesto_items.id` (RN-PRICING-008).
- L7 (user): "arranquemos con t1"
- L8 (parent exploration, T1): live schema already allows `cotizacion` in `extraction_results.document_type`, `processing_sessions.doc_type` and `cliente_formato_documentos.doc_type` (`docs/schema/extractor_final.sql:559,584,301`), so no migration. Gaps: `/procesar` maps every non comparativa/orden tipo to `licitacion` (`services/extraccion/main.py:542`); `persistir_output_final` rejects `cotizacion` (`services/extraccion/persistent_output.py:39`); `/api/documentos` filter ignores it (`main.py:651`). Validation already handles `cotizacion` (`services/presupuestacion/extraccion/service.py:41`, listado label "Directa"). Client prompt formats are looked up by exact doc_type, so a directa only uses a format stored as `cotizacion`.
