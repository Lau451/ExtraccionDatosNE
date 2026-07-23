# Pendientes — Comparativas

Auditoría técnica P1 (bloqueante/riesgo alto) / P2 (riesgo medio, corregir pronto) /
P3 (mejora, sin urgencia).

## P1 — `asignar_proveedor` no setea `es_drogueria_propia`, pese a que `compras/` da por sentado que existe un "PATCH manual" que lo hace

`compras/service.py:127-129` comenta explícitamente: "es_drogueria_propia hoy no se
auto-detecta ... así que en la práctica esto no dispara hasta que exista el PATCH
manual de asignación — comportamiento esperado." `asignar_proveedor`
(`service.py:23-25`, este módulo) es el único caso de escritura sobre `ofertas_items`
fuera de `extraccion/`, y su propósito (vincular manualmente un proveedor a una
oferta) coincide con lo que ese comentario describe — pero solo escribe
`{"proveedor_id": proveedor_id}`, nunca `es_drogueria_propia`.

**Impacto real**: sin importar cuántas ofertas se asignen manualmente vía este
endpoint, `es_drogueria_propia` permanece en `False` para siempre (ver
[`decisiones.md`](./decisiones.md) D-COMPARATIVAS-002). Consecuencias en cadena:

1. `v_renglones_ganados` (`extractor_final.sql:1576-1595`) nunca mostrará esas ofertas,
   aunque hayan ganado (`WHERE oi.es_drogueria_propia = TRUE`, RN-COMPARATIVAS-004) —
   el insumo de "anticipar compras" queda incompleto para toda oferta que dependía de
   una asignación manual.
2. `compras/confirmar_orden_compra` (`compras/service.py:130-131`) nunca marcará esas
   ofertas como `adjudicada = True` — la condición `oferta.get("es_drogueria_propia")`
   nunca es verdadera para una oferta que pasó por este módulo.
3. Es decir: **la única función del repositorio auditada en esta sesión cuyo nombre
   sugiere resolver este gap (`asignar_proveedor`) no lo resuelve**, y no hay ningún
   otro candidato conocido — se buscó `es_drogueria_propia = True` (o equivalente) en
   todo `services/` y no aparece en ningún `INSERT`/`UPDATE` de código de producción.

**Evidencia de que sería técnicamente viable, no solo deseable**: `proveedores` tiene
`es_competidor` (`BOOLEAN NOT NULL DEFAULT TRUE`, `extractor_final.sql:137`) y `tipo`
(incluye `'drogueria'` como valor válido del `CHECK`, `extractor_final.sql:146-147`) —
columnas que, a diferencia del texto libre que bloqueó la auto-detección en
`extraccion/` (D-EXTRACCIONVALIDACION-001), sí identifican de forma confiable si un
`proveedor_id` concreto representa a la propia droguería. Ninguna de las dos se lee en
este módulo.

**Prioridad**: Alta — es un gap funcional con impacto directo en el insumo de compras,
no solo un hallazgo de documentación.

**Recomendación** [RECOMENDACIÓN]: extender `asignar_proveedor` para que, tras
resolver el `proveedor` (`service.py:17`), derive `es_drogueria_propia` a partir de
`proveedor["es_competidor"] is False` y/o `proveedor["tipo"] == "drogueria"`, y lo
incluya en `campos` del `UPDATE` (`service.py:23-25`) junto a `proveedor_id`. Requiere
antes confirmar con negocio si `es_competidor=False` y `tipo='drogueria'` son
condiciones equivalentes, redundantes o independientes — no verificado en esta sesión
si existe una fila de `proveedores` que represente a la propia droguería en la base de
datos real.

## P2 — Sin auditoría (`core.audit`) en todo el módulo

`Grep` de `core.audit`/`registrar_cambio`/`registrar_evento_ciclo_vida` en los 4
archivos de `comparativas/`: cero resultados. `asignar_proveedor` cambia
`proveedor_id` de una oferta sin dejar ningún rastro en `historial_cambios` — a
diferencia de `_materializar_comparativa` (`extraccion/service.py`), que sí audita la
creación de la comparativa y el reemplazo de versión (ver
[`../extraccion_validacion/pendientes.md`](../extraccion_validacion/pendientes.md)).

**Impacto**: `GET /historial/{entidad}/{entidad_id}` (módulo `auditoria/`, ver
[`../core/`](../core/README.md)) no puede mostrar "quién y cuándo reasignó el
proveedor de esta oferta" — un cambio con impacto en decisiones de compra
(RN-COMPARATIVAS-004/005) queda sin traza.

**Consistencia con el resto del repositorio**: igual que en `extraccion_validacion/`,
`EntidadAuditable` (`core/audit.py:7-9`) no incluye `"oferta_item"` como valor válido
— el `_COLUMNA_FK_POR_ENTIDAD` de `core/audit.py:12-18` solo mapea
`proceso_comercial`, `comparativa`, `orden_compra`, `presupuesto`, `evento`. Extender
la auditoría a este módulo requeriría primero extender esa infraestructura (fuera de
este alcance).

**Recomendación** [RECOMENDACIÓN]: si se decide auditar `asignar_proveedor`, extender
`EntidadAuditable`/`_COLUMNA_FK_POR_ENTIDAD` en `core/audit.py` (fuera del alcance de
este módulo) para soportar `"oferta_item"`, y llamar a `registrar_cambio` en
`service.py:23-25` con el valor anterior/nuevo de `proveedor_id`.

## P2 — Ningún test cubre `router.py` directamente

Los 5 tests de `tests/comparativas/test_service.py` llaman a `asignar_proveedor`
(el service) o `listar_renglones_ganados` (el repository) directamente con
`service_client`, nunca al endpoint HTTP. No hay evidencia en esta sesión de un test
que ejercite:

- `router.py:38-59` completo — en particular RN-COMPARATIVAS-002 (el chequeo de
  pertenencia de droguería del **usuario**, distinto del chequeo de
  RN-COMPARATIVAS-001 que sí está cubierto por
  `test_asignar_proveedor_de_otra_drogueria_falla`).
- El ruteo por rol de los 3 endpoints (`_ROLES_LECTURA` vs. `_ROLES_ASIGNAR`,
  RN-COMPARATIVAS-003).
- `v_ofertas_sin_matchear` — solo `v_renglones_ganados` tiene test propio
  (`test_v_renglones_ganados_muestra_ofertas_propias_ganadoras`,
  `tests/comparativas/test_service.py:102-134`).

Mismo patrón de gap ya documentado en
[`../extraccion_validacion/pendientes.md`](../extraccion_validacion/pendientes.md)
("Ningún test cubre `router.py` directamente") — parece ser una convención del
proyecto (probar `service.py`/`repository.py` por integración, no `router.py` vía
`TestClient`), no un descuido aislado de este módulo.

## P3 — `response_model` inconsistente entre los 3 endpoints

Los 2 `GET` declaran `response_model=list[RenglonGanado]` /
`response_model=list[OfertaSinMatchear]` (`router.py:21,30`); el `POST` no declara
ningún `response_model` (`router.py:38-44`) y retorna `dict` a secas — la fila cruda
de `ofertas_items` tal como la devuelve Supabase, sin pasar por un modelo Pydantic que
documente su forma. No es un bug (FastAPI serializa el `dict` igual), pero rompe la
consistencia de tipado de las respuestas del módulo y no aparece documentado en el
schema OpenAPI generado. Motivo pendiente de definición funcional: no hay evidencia de
si fue intencional (evitar mantener un modelo que refleje 1:1 todas las columnas de
`ofertas_items`) u omisión.

**Recomendación** [RECOMENDACIÓN]: definir un modelo de respuesta explícito (aunque
sea un subconjunto de columnas relevantes: `id`, `proveedor_id`, `drogueria_id`) para
`POST /ofertas/{oferta_id}/asignar-proveedor`.
