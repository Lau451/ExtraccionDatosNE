# Layered extraction instructions

Backlog feature (not started). Extraction prompt instructions in layers: general per document type, per client type, and per client. All applicable layers are combined. Recorded during presupuestador-v1; the user chose to do it after that feature.

## Specs

- S1 Layers (L1): "en vez de hacer las intrucciones por cliente podemos hacerlas por tipo de clietnes, o que se pueda poner reglas generales para directas o licitaciones o por cliente"
- S2 Combination (L2): "Se suman todas" — the general layer, then the client-type layer, then the client layer, in that order. The most specific layer goes last and may clarify or correct the earlier ones.

## Tasks

- [ ] T1 (S1, S2) Data model for the general and client-type layers (today `cliente_formato_documentos` requires `cliente_id`, UNIQUE (cliente_id, doc_type)) and prompt assembly in `/procesar`. Route: TBD. Commit: —
- [ ] T2 (S1) Screen to manage instructions per layer (none exists today; only `services/presupuestacion/clientes/router.py:148,161`). Route: TBD. Commit: —
- [ ] T3 (S2) Revisit the presupuestador-v1 T1b fallback (directa uses the client's licitación format plus an `aviso`): decide whether it stays once general layers exist. Route: TBD. Commit: —

## Log

- L1 (user, original request): "BIEN SI, ESTABIEN PERO EN VEZ DE HACER LAS INTRUCCIONES POR CLIENTE PODEMOS HACERLAS POR TIPO DE CLIETNES, O QUE SE PUEDA PONER REGLAS GENERALES PARA DIRECTAS O LICITACIONES O POR CLIENTE"
- L2 (user decisions): combination -> "Se suman todas (recomendado)"; timing -> "Feature aparte, después".
- L3 (parent exploration): the client type already exists as `clientes.tipo` IN ('hospital', 'obra_social', 'municipio', 'provincia', 'nacional', 'otro') (`docs/schema/extractor_final.sql`). Instructions are read in `services/extraccion/main.py` (`_resolver_formato_prompt`, `_buscar_formato`). There is no frontend screen for formats.
