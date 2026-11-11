# Tasks: Agente de interpretación de formatos para Comparativas

> Nada de esto está implementado. Cada etapa es entregable por separado y se acepta solo si mejora
> la medición de la etapa 0 sin empeorar ningún documento del set de referencia.
> `strict_tdd: true` (ver `openspec/config.yaml`): cada tarea de código empieza por su test, con
> Gemini simulado.

## Antes de empezar

- [ ] 0.0 Reunir 15 a 20 comparativas reales que hoy fallan (largas y de estructura compleja) y sus
      resultados correctos. Sin esto no se puede arrancar.
- [ ] 0.0b Resolver los puntos abiertos PA-1 (límite de 500 filas editables) y PA-3 (dónde se
      guarda el set de referencia) de `design.md`.

## Etapa 0 — Base

- [ ] 0.1 Armar `tests/fixtures/comparativas_referencia/` (o la ubicación que resulte de PA-3) con
      cada archivo y su resultado esperado completo.
- [ ] 0.2 Escribir `scripts/medir_comparativas.py`: renglones recuperados, ofertas correctas, marcas
      correctas, ofertas inventadas. Guardar la línea de base.
- [ ] 0.3 Agregar la variable `COMPARATIVAS_AGENTE` en `services/extraccion/config.py` (default
      `off`).
- [ ] 0.4 Test + cambio: un chunk fallido deja de reemplazarse por vacío; se registra como problema
      y la extracción termina en `partial`.
- [ ] 0.5 Test + cambio: división recursiva ante truncamiento, también en el flujo por páginas
      (`_procesar_chunk_pdf`), conservando el contexto en ambas mitades.
- [ ] 0.6 Test + cambio: salida compacta del modelo (proveedores por índice, solo los que cotizan),
      `response_schema`, `temperature=0`. Verificar PA-4.
- [ ] 0.7 Migración: `extraction_results.resultado_path` (+ `.down.sql`, esquema y RLS en `docs/schema/`).
- [ ] 0.8 Test + cambio: guardar el JSON de resultado completo con advertencias
      (`persistent_output.py`).
- [ ] 0.9 Test + cambio: sacar `_filtrar_top_3_por_renglon` del extractor; el CSV lleva todas las
      ofertas ordenadas por renglón y precio (DEC-3).
- [ ] 0.10 Test + cambio en `presupuestacion/extraccion`: materializar todas las ofertas; confirmar
       que `_computar_posiciones` sigue correcto.
- [ ] 0.11 Frontend: `validar-extraccion` muestra todas las ofertas agrupadas por renglón, según lo
       resuelto en PA-1.
- [ ] 0.12 Correr la medición y comparar contra la línea de base.

## Etapa 1 — Estructura y prompt por capas

- [ ] 1.1 Crear `services/extraccion/comparativas_agente/` con `modelos.py` (`PerfilEstructura`,
      `Bloque`, `ResultadoBloque`, `Problema`, `Traza`).
- [ ] 1.2 `tests/extraccion_agente/test_dependencias.py`: el paquete no importa
      `services.presupuestacion`.
- [ ] 1.3 Test + cambio en `parsers.py`: devolver bloques con procedencia (páginas, hoja), sin romper
      `parse_document` para los otros pipelines.
- [ ] 1.4 Test + cambio en `parsers.py`: conservar el texto fuera de las tablas en páginas con tablas.
- [ ] 1.5 Test + cambio en `parsers.py`: leer todas las hojas de Excel/ODS.
- [ ] 1.6 Test + cambio en `parsers.py`: `is_scanned_pdf` muestrea páginas repartidas, no solo las 3
      primeras.
- [ ] 1.7 Test + `analizador.py`: muestra del documento, llamada con `response_schema`, cálculo de
      huella.
- [ ] 1.8 Test + corte en bloques según `patron_renglon`, con `contexto` repetido en cada bloque.
- [ ] 1.9 Test + `prompt_builder.py`: capas 1, 2, 3 y 6, con tope de tokens por capa.
- [ ] 1.10 Test + `extractor.py` y unión entre bloques (normalización de proveedor y de renglón,
       secciones con numeración reiniciada).
- [ ] 1.11 Test + `orquestador.py` mínimo y fachada en `robot_comparativas.py` detrás de
       `COMPARATIVAS_AGENTE`.
- [ ] 1.12 Medición contra la etapa 0.

## Etapa 2 — Validación y reproceso

- [ ] 2.1 Test + `validadores.py`: cobertura, duplicados y esquema (errores).
- [ ] 2.2 Test + `validadores.py`: anclaje, proveedor fuera de lista, escala de precio y
      desplazamiento (advertencias).
- [ ] 2.3 Test + orquestador: reproceso solo de bloques con problemas, máximo 2 rondas, problema
      incluido en la capa 6.
- [ ] 2.4 Migración: `processing_sessions.formato_documento_id` y `processing_sessions.traza`.
- [ ] 2.5 Test + cambio: persistir la traza por sesión.
- [ ] 2.6 Test + cambio en `presupuestacion/extraccion`: `GET /extracciones/{id}/filas` devuelve
      advertencias por renglón.
- [ ] 2.7 Frontend: advertencias visibles por renglón en `validar-extraccion`.
- [ ] 2.8 Medición. Revisar falsos positivos del anclaje sobre el set de referencia y ajustar.

## Etapa 3 — Memoria de formatos

- [ ] 3.1 Migración: `formatos_documento`, `formato_lecciones`, `formato_ejemplos` con RLS por
      droguería (sin la columna `embedding`).
- [ ] 3.2 Test + `memoria.py`: guardar formato nuevo, recuperar por cliente y por huella.
- [ ] 3.3 Test + orquestador: omitir el análisis cuando la huella es conocida.
- [ ] 3.4 Test + `prompt_builder.py`: capas 4 y 5; solo lecciones `validada`.
- [ ] 3.5 Test de aislamiento: una droguería no recupera formatos ni lecciones de otra.
- [ ] 3.6 Verificar PA-2 y PA-5. Migración: `CREATE EXTENSION vector`, columna `embedding` e índice.
- [ ] 3.7 Test + `memoria.py`: recuperación por similitud con umbral; vacío por debajo del umbral.
- [ ] 3.8 Medición: procesar dos veces el set y comparar la segunda pasada.

## Etapa 4 — Aprendizaje

- [ ] 4.1 Migración: `extraccion_correcciones` con RLS.
- [ ] 4.2 Test + cambio en `presupuestacion/extraccion/service.py`: guardar la diferencia al validar,
      también sin cambios.
- [ ] 4.3 Capacidades `formatos.lecciones.ver` y `formatos.lecciones.aprobar` en
      `services/shared/permisos.py` (admin y líder comercial).
- [ ] 4.4 Test + `aprendizaje.py`: tarea periódica que agrupa correcciones por formato y propone
      lecciones `candidata`.
- [ ] 4.5 Test + filtro de instrucciones: rechazar las que contengan precios o nombres de
      proveedores o clientes.
- [ ] 4.6 Test + generación de ejemplos con valores sintéticos a partir de extracciones validadas.
- [ ] 4.7 Endpoints para listar, aprobar y rechazar lecciones.
- [ ] 4.8 Frontend: pantalla de aprobación con el antes y después de la re-ejecución.
- [ ] 4.9 Test + retiro automático de lecciones que empeoran la tasa de corrección.
- [ ] 4.10 Medición final y decisión de dejar `COMPARATIVAS_AGENTE=on` por defecto.

## Cierre

- [ ] 5.1 Actualizar `docs/modulos/extraccion_ia/`, `docs/modulos/extraccion_validacion/`,
      `docs/modulos/comparativas/` y `docs/ia/README.md`.
- [ ] 5.2 Archivar `openspec/changes/parser-router-comparatives-refactor` como reemplazado.
- [ ] 5.3 Quitar el flujo anterior y la variable cuando el agente lleve un período estable.
