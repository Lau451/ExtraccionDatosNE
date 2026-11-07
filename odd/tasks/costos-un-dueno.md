# Etapa 3 — un solo dueño del versionado de costos

Stage 3 of docs/arquitectura/README.md (deviation X-ARQ-004): the cost versioning rule lives only in `services/productos`; the Progress import calls its facade.
Branch `feat/costos-un-dueno` from `dev` (`eae6a3c`). No migrations. Context: Progress owns product and tercero altas (L3); restricting manual writes is a separate later stage (L4).

## Specs

- **S1** One owner (L4): "El versionado queda en `productos` como una función de su fachada que procesa en lote. La importación la llama en lugar de tener su propia copia, y se borran las funciones duplicadas de `imports/repository.py`."
  - Facade `services/productos/api.py`; `services/presupuestacion/imports/service.py` imports it; `imports/repository.py` no longer touches `costos_productos`.
  - The manual `crear_costo` and the batch use the same rule function.
- **S2** Same behavior (L4): "No cambia ningún comportamiento." — import keeps `origen="import_sistema"`, counts `nuevos/actualizados/sin_cambios/no_encontrados`, closes the vigente on `fecha_desde - 1 day`; manual keeps `origen="manual"`, returns the vigente when the value is equal, and checks the product belongs to the droguería. `POST /imports/costos` and `POST /productos/{id}/costos` keep path, roles, request and response.
- **S3** Guard: a test fails if code in `services/` outside `services/productos` writes `costos_productos` (same mechanism as `tests/arquitectura/test_duenos_tablas.py`).
- **S4** Docs: X-ARQ-004 resolved in `docs/arquitectura/{README,mapa-modulos}.md` and `docs/modulos/{imports,productos}`; README stage table gains the new stage "maestros de solo lectura" (L4) as pending.

Out of scope: `imports` still upserts `productos` and `stock_productos` directly (Progress-owned data, belongs to the "maestros de solo lectura" stage); restricting manual cost/stock/alta endpoints (L4).

## Tasks

| ID | Specs | Route | Commit |
|----|-------|-------|--------|
| T1 | S1, S2, S3 | inline: RED guard + batch facade test, move rule to productos, import uses facade | aee45d4 |
| T2 | S4 | inline: docs | this commit (`docs(arquitectura): resolve X-ARQ-004 ...`) |

## Log

- **L1** (user, 2026-11-07): "si vamos a arrancar con la etapa 3 pero tambien estoy viendo la posibidad de cambiar la estructura de las entidades y los productos"
- **L2** (user, 2026-11-07): "si lo que pasa con articulos y terceros es que nosotros quisimos cambiar la estructura por ende es diferente a como llos maneja progress, tengo miedo de que haya friccion. Por otro lado pensé en dejarlos como están e ir alimentandolo con los datos que le vayamos pidiendo a progress, no se que opinas. Estoy habllando de productos y terceros"
- **L3** (user, 2026-11-07): "bien creo que la mejor decision es que los amneje progress" (option a: altas only in Progress).
- **L4** (assistant proposal, accepted by user "vamos asi"): "Etapa 3 (X-ARQ-004), solo mover la regla. El versionado queda en `productos` como una función de su fachada que procesa en lote. La importación la llama en lugar de tener su propia copia, y se borran las funciones duplicadas de `imports/repository.py`. No cambia ningún comportamiento." / "Etapa nueva, maestros de solo lectura. Se escribe el contrato de propiedad por campo en `docs/arquitectura` y se cierran o restringen los endpoints de arriba, junto con sus pantallas en el frontend."
