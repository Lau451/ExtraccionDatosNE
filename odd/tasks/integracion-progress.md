# Integración Progress — stage 1

Create `services/integracion_progress/`, the single owner of the Progress 9.1D file exchange (docs/arquitectura/integracion-progress.md), with a file registry and automatic + manual reception of the presupuestos file.
Branch `feat/integracion-progress`, stacked on `feat/plataforma-cimientos` (stage 0, `3c1989b`). Migrations: writers only write SQL; the user applies them in the TEST SQL Editor (Supabase MCP is read-only).

## Specs

- **S1** Agreed stage 1 scope (L2): "Crear `integracion_progress` y mover ahí la exportación de OC y la importación de presupuestos. El lector del CSV pasa del frontend al backend. Agregar el registro de archivos (duplicados, errores, reproceso), la recepción automática desde la carpeta y los primeros `contrato.md`".
- **S2** Single owner: everything that knows the Progress folder, encoding, file naming and atomic write lives in `services/integracion_progress/`; other modules use only `services/integracion_progress/api.py`. A dependency test enforces it: `integracion_progress` imports only `services.shared` plus the public facades it delivers to, and no module outside it imports its internals. The OC export keeps building its rows in `presupuestacion/oc_export` and hands the writing to the facade; endpoint, roles, file name, folder, encoding and CAS behaviour stay identical.
- **S3** File registry: every file received or written is recorded with tenant, direction (`entrada`/`salida`), type, file name, SHA-256, origin (`carpeta`/`manual`), state (`recibido` → `procesado` | `error`), row count, per-line errors, user and timestamps. The same file content (same SHA-256, tenant and type) is never processed twice: a second arrival is reported as a duplicate and changes nothing. A file in `error` can be reprocessed.
- **S4** Reception (L3, L4): "Progress lo deja en una carpeta"; "Automática + manual (Recomendado) — La plataforma revisa la carpeta de entrada sola cada pocos minutos, y la carga manual sigue existiendo. Las dos pasan por el mismo registro de archivos".
  - Automatic: the presupuestación backend scans a configured inbox folder every few minutes, skips files still being written (`.tmp`, hidden), processes each file through the registry, and moves it to `procesados/` or `errores/` afterwards. Disabled when the folder or tenant is not configured.
  - Manual: the import screen uploads the file itself (multipart) instead of parsed rows; the backend runs the same pipeline.
- **S5** Backend parser: the presupuestos CSV is decoded and parsed in the backend (UTF-8 with or without BOM, falling back to cp1252), with the same columns, validations and per-line error messages the frontend parser applies today (`frontend/src/features/presupuestos-import/parsearCsvPresupuestos.ts`). Rows are delivered to `services.pcp.api`; import results and idempotency (`presupuesto_legacy_map`) are unchanged. The frontend parser is removed.
- **S6** Contracts: `services/integracion_progress/tipos/<tipo>/contrato.md` for `oc` (outbound) and `presupuestos` (inbound), following the file standard in docs/arquitectura/integracion-progress.md.

## Tasks

| ID | Specs | Route | Commit |
|----|-------|-------|--------|
| T1 | S2 | worker: module skeleton, `api.py`, move the OC writer behind the facade, dependency test | `ad5d5cf` (110 passed: tests/oc_export, tests/integracion_progress, tests/arquitectura; app boots, 180 routes) |
| T2 | S3 | worker: migration 0043 registry table + down + snapshot, registry repository/service | `3254fae` (33 tests, fake repository; migration applied and verified in TEST, L7) |
| T3 | S5, S3, S4 (manual) | worker: backend parser, upload endpoint, frontend switch to file upload | |
| T4 | S4 (automatic) | worker: inbox scanner in presupuestación lifespan, config, docker-compose; independent verify (concurrency, delivery) | |
| T5 | S6, S1 | inline: `contrato.md` files, docs/arquitectura + docs/modulos update | |

## Log

- **L1** (user, 2026-11-04): "bien empecemos con etpa 0 y 1"
- **L2** (assistant proposal accepted in L1, stage 1 row): "Crear `integracion_progress` y mover ahí la exportación de OC y la importación de presupuestos. El lector del CSV pasa del frontend al backend. Agregar el registro de archivos (duplicados, errores, reproceso), la recepción automática desde la carpeta y los primeros `contrato.md`"
- **L3** (user answer, "¿Cómo llega hoy el archivo de presupuestos desde Progress?"): "Progress lo deja en una carpeta"
- **L4** (user answer, "¿Qué querés para esta etapa?"): "Automática + manual (Recomendado)" — option text: "La plataforma revisa la carpeta de entrada sola cada pocos minutos, y la carga manual sigue existiendo. Las dos pasan por el mismo registro de archivos"
- **L5** Exploration evidence: the presupuestos import receives JSON rows (`services/pcp/imports/router.py:41-55`); the frontend reads the file as UTF-8 (`ImportarPresupuestosLegacy.tsx:38`) while Progress exports cp1252; the PCP legacy import takes JSON, not a Progress CSV, so it stays out of scope; presupuestación has no background loop (the extracción lifespan sweep at `services/extraccion/main.py:53-108` is the pattern); next migration number is 0043.
- **L7** (user, 2026-11-04): "listo la migracion y por ahora dejemos que los archivos se vean por todos" — 0043 applied in TEST; read policy keeps the six roles (superadmin, admin, gerencia, compras, lider_comercial, comercial). Verified by read in TEST (`grnamollopxdlstcpxhc`): 15 columns, 13 constraints incl. `uq_parch_contenido`, RLS on with `parch_sel` (6 roles + `mismo_tenant`) and `parch_del` (superadmin), no INSERT/UPDATE policy, trigger `trg_progress_archivos_updated_at`, index `idx_parch_drog_created`, 0 rows.
- **L6** Decision: the inbox folder path and the tenant for automatic reception are settings (the exact Progress folder is not known yet); automatic reception stays off until both are set.
