# Fix: parser de PDF dedicado para orden de compra

## Objetivo

Separar la extracción de texto de PDF de `orden_compra` del parser genérico compartido
(`_extract_native_pdf` en `services/extraccion/parsers.py`, usado hoy por licitación Y
comparativa Y orden_compra por igual), para no arrastrar comportamiento pensado para
comparativas/licitación a documentos de orden de compra, que tienen una forma distinta
(texto libre de cabecera + tabla chica de renglones en la misma página).

## Problema real, reproducido con un documento real (no hipotético)

Se subió una OC real de un hospital (`SAMCo Rafaela Hospital Dr. Jaime Ferré`, impresa
desde un sistema web — sin bordes de tabla visibles) y el extractor no detectó ningún
renglón. Diagnóstico, corriendo el parser directo:

```python
from services.extraccion.parsers import parse_document
parse_document(Path(".../OC 104857 Nueva Era.pdf"))
# -> '| Cod. | Artículo | Cantidad | P.Unitario | Total |\n| --- | --- | --- | --- | --- |'
```

Solo el encabezado de la tabla llegó a Gemini — nada del texto libre (cliente, CUIT,
número de orden, fecha) ni las 2 filas de datos reales.

**Causa raíz, verificada leyendo `_extract_native_pdf` (parsers.py:370-434)**:

1. **Línea 391-418**: por cada página, `if tables: [procesa SOLO la tabla] else:
   [extrae texto libre]`. Si una página tiene una tabla, el texto libre de esa MISMA
   página se descarta por completo — nunca se extrae. En una OC real, el texto de
   cabecera (cliente, CUIT, número, fecha) está en la misma página que la tabla de
   renglones, así que se pierde entero.
2. **Detección de tabla en sí falla**: `pdfplumber` con su estrategia por defecto
   (basada en líneas/reglas visibles) no reconoce las filas de datos en un PDF impreso
   desde una web sin bordes de tabla dibujados — solo detecta la fila de encabezado.

Ninguno de los dos problemas es hipotético: ambos se reprodujeron con el archivo real
de prueba (ver fixture nuevo, abajo).

**Por qué esto no rompió comparativa/licitación hasta ahora**: esas páginas son,
en la práctica, tabla-completas (el precedente que motivó este diseño en primer lugar
era distribuir marcas de proveedores en comparativas — `_distribute_brands`, línea 262,
ya es lógica específica de comparativas metida sin condicionar en la función
"genérica"). Una orden de compra de cliente real casi siempre mezcla cabecera de texto
libre + tabla chica en la misma página — un patrón que este parser nunca contempló.

## Alcance

**No tocar** `_extract_native_pdf`, `_distribute_brands`, ni nada que use licitación o
comparativa — cero riesgo de regresión ahí, verificar con su suite de tests existente
sin cambios.

Crear una función de extracción de PDF **dedicada a orden_compra** (nombre a criterio
del implementador, ej. `_extract_native_pdf_orden_compra` + una entrada pública nueva,
ej. `parse_document_orden_compra(filepath)`, en el mismo `parsers.py` o en un módulo
nuevo si se prefiere mantener `parsers.py` más chico — decisión del implementador) con
estas reglas:

1. **Nunca descartar el texto libre de una página por tener una tabla.** Extraer
   `page.extract_text()` de TODAS las páginas, siempre — la tabla (si la hay) se agrega
   como enriquecimiento, no como reemplazo.
2. **Detección de tabla más permisiva.** Si la estrategia por defecto de
   `pdfplumber.extract_tables()` devuelve una tabla con 1 sola fila (o ninguna), probar
   una estrategia alternativa antes de rendirse (ej. `table_settings` con
   `vertical_strategy`/`horizontal_strategy` en `"text"` en vez de `"lines"` — pdfplumber
   soporta esto nativamente). Si ninguna estrategia encuentra filas de datos reales, no
   es un error — el texto libre ya capturado (punto 1) sigue teniendo toda la
   información, la tabla es soporte extra.
3. **Sin `_distribute_brands` ni ninguna lógica específica de comparativas.**
4. Mantener el mismo pipeline de fallback que ya existe (`_parse_pdf`: native →
   Docling → Vision) para el caso de que `pdfplumber` no esté disponible o falle por
   completo — no reinventar eso, solo el paso "native" cambia para `orden_compra`.

Actualizar `services/extraccion/robot_orden_compra.py` (línea 335, `markdown =
parse_document(ruta_archivo)`) para que use la función nueva en vez de la genérica.
`robot_comparativas.py` y el robot de licitación (verificar su nombre real) **no se
tocan**.

## Fixture nueva (dato real, no sintético)

El PDF real ya existe en `C:\Users\LAUREANO\OneDrive\Escritorio\Pruebas\OC 104857 Nueva
Era.pdf` — copiarlo a `tests/fixtures/orden_compra/04_pdf_real_sin_bordes/documento.pdf`
(mismo patrón que los otros 3 fixtures) junto con su `esperado.csv` según la gramática
D6. Contenido real del documento (verificado leyendo el PDF):

- Cliente: SAMCo Rafaela Hospital Dr. Jaime Ferré, CUIT 30-67428388-8
- Orden de Compra Nro 00104857, Fecha 10/9/2026
- Renglón 1: Hidroclorotiazida 50 mg comp., cantidad 3000, precio unitario $109,75
- Renglón 2: Gemfibrozil 600 mg comp., cantidad 4000, precio unitario $187,00

Este fixture es la prueba de regresión real del bug — antes del fix, el extractor no
debe detectar ningún renglón (`OrdenCompraSinRenglonesError` o vacío); después del fix,
debe detectar los 2 renglones reales con cliente/CUIT/número de OC correctos.

## Verificación

- `pytest tests/test_robot_orden_compra.py -q` (0 regresiones + el nuevo fixture en
  verde, con llamada real a Gemini para el fixture nuevo — igual que los otros 3).
- `pytest tests/ -q -m "not integration"` completo — confirmar 0 regresiones en
  cualquier test de licitación/comparativa que dependa de `_extract_native_pdf`.
- Prueba manual: re-subir el PDF real original (no la copia de fixture) por la UI
  (`http://localhost:5173`, tipo "Orden de compra") y confirmar que ahora detecta los 2
  renglones — el orquestador puede hacer esto directo con el navegador, no hace falta
  que lo haga el batch de implementación.

## Contexto de tooling

- Strict TDD Mode activo. Test runner: `pytest tests/` (venv, `asyncio_mode=auto`).
- Llamadas reales a Gemini para el fixture nuevo consumen créditos reales — mismo
  criterio que los otros 3 fixtures existentes de este mismo directorio.
- No agregar línea de atribución de IA a ningún commit.
- Commit directo en `dev`, sin branch/PR nuevo — no pushear, el orquestador revisa y
  pushea.

## Tareas

- [x] 1 Copiar el PDF real a `tests/fixtures/orden_compra/04_pdf_real_sin_bordes/documento.pdf`
  y escribir su `esperado.csv` (gramática D6, con los datos reales de arriba).
  - Evidencia: PDF copiado (`cp`), 78020 bytes. Contenido verificado leyendo el PDF
    directo con pdfplumber (`extract_text()`), no solo confiando en el resumen de
    este archivo: coincide exactamente (cliente, CUIT, Nro de OC 00104857, fecha
    10/9/2026, 2 renglones con cantidades/precios). `esperado.csv` escrito con la
    gramática D6; `direccion_entrega` y el glyph roto de "Ferré" se ajustaron
    después de la corrida real de Gemini (tarea 5) para reflejar el resultado
    real observado — ver nota de deviation abajo.
- [x] 2 [RED] Confirmar que el fixture nuevo falla con el parser actual (correr
  `procesar_orden_compra` sin el fix — 0 renglones detectados o error, documentar el
  resultado exacto).
  - Comando: `python -c "from pathlib import Path; from services.extraccion.parsers
    import parse_document; print(repr(parse_document(Path('.../OC 104857 Nueva
    Era.pdf'))))"` (parser SIN modificar, contra el PDF real).
  - Resultado exacto obtenido: `'| Cod. | Art�culo | Cantidad | P.Unitario | Total
    |\n| --- | --- | --- | --- | --- |'` — 0 filas de datos, 0 texto de cabecera.
    Confirma exactamente el diagnóstico de este archivo.
- [x] 3 [GREEN] Implementar la función de extracción dedicada (sección "Alcance" arriba)
  y cablearla en `robot_orden_compra.py`.
  - `_extract_native_pdf_orden_compra` + `_parse_pdf_orden_compra` +
    `parse_document_orden_compra` agregadas a `services/extraccion/parsers.py`
    (sin tocar `_extract_native_pdf`/`_distribute_brands`/`_parse_pdf`/
    `parse_document`/`_EXTENSION_ROUTER`). `robot_orden_compra.py` actualizado
    para importar y llamar `parse_document_orden_compra` en vez de
    `parse_document` (línea ~335, y el import de línea ~37). Mocks de
    `tests/test_robot_orden_compra.py` actualizados al nuevo nombre (3 sites) —
    8/8 tests de ese archivo en verde tras el cambio.
- [x] 4 Tests unitarios de la función nueva de extracción de PDF (sin depender de
  Gemini): confirmar que texto libre + tabla en la misma página se capturan los dos, con
  al menos un caso que reproduzca el patrón exacto del PDF real (tabla sin bordes,
  detección con estrategia alternativa).
  - `tests/test_parsers_orden_compra.py` (nuevo, 3 tests, 0 mocks — pdfplumber real):
    1) PDF sintético con tabla CON bordes (GRID) + texto libre de cabecera en la
       misma página → ambos capturados. 2) Fixture PDF real (04) → reproduce el
       patrón exacto (tabla sin bordes) y confirma que la función dedicada
       recupera cabecera + los 2 renglones. 3) No-regresión: `_extract_native_pdf`
       (compartido, sin tocar) sigue devolviendo 0 renglones para el mismo PDF real
       — documenta que el bug original sigue ahí para licitación/comparativa (no
       hay riesgo de que el fix "se filtrara" sin querer al código compartido).
    `pytest tests/test_parsers_orden_compra.py -q` → `3 passed`.
- [x] 5 Correr el fixture 04 completo (extracción real vía Gemini) y confirmar que
  ahora sí detecta los 2 renglones con los datos correctos.
  - Corrida real vía `procesar_orden_compra()` (Gemini real, sin mocks) sobre una
    copia del fixture 04. CSV generado con 2 filas correctas — ver reporte final
    para el contenido completo. Consumió créditos reales de Gemini (mismo criterio
    que los fixtures 01-03).
- [x] 6 [REFACTOR] Verificación completa (arriba) — confirmar especialmente 0
  regresiones en licitación/comparativa.
  - `pytest tests/test_robot_orden_compra.py -q` → `8 passed`.
  - `pytest tests/test_parsers_orden_compra.py -q` → `3 passed`.
  - `pytest tests/ -q -m "not integration"` → `387 passed, 450 deselected` (0 fails).
  - `pytest tests/test_robot_comparativas.py tests/test_brand_distribution.py -q`
    → `82 passed` (los únicos tests que ejercitan `_extract_native_pdf`/
    `_distribute_brands`/`parse_document` directamente — confirmado por grep, sin
    cambios de comportamiento).

## Deviaciones respecto al diagnóstico original de este archivo

1. **Licitación NO usa el parser compartido.** El diagnóstico (línea 6) decía que
   `_extract_native_pdf` es "usado hoy por licitación Y comparativa Y orden_compra
   por igual". Verificado leyendo `services/extraccion/robot.py::procesar_archivo`
   (la función que atiende licitación desde `main.py`, tipo default en el branch
   `if/elif tipo==...`): NO llama a `parsers.parse_document` en ningún punto — sube
   el PDF directo a Gemini Vision (`client.files.upload` + `generate_with_fallback`).
   `parse_document` está importado en `main.py` pero sin ningún call site ahí
   tampoco. En la práctica solo comparativa (`robot_comparativas.py:644/975`) y,
   hasta este fix, orden_compra compartían `_extract_native_pdf`. Esto no cambia
   el alcance del fix (igual no se tocó el parser compartido), pero corrige la
   justificación de por qué es seguro no tocarlo.
2. **No existe (ni existía) un test pytest que corra los fixtures 01-03 con Gemini
   real.** La sección de Verificación de este archivo asume "el nuevo fixture en
   verde, con llamada real a Gemini — igual que los otros 3 fixtures ya
   existentes". Grep completo de `tests/` confirma que los fixtures 01-03 de
   `tests/fixtures/orden_compra/` NO están referenciados por ningún test — solo
   por `_generar_fixtures.py` (script de generación, no de test). No hay
   infraestructura pytest que compare contra `esperado.csv` con Gemini real para
   ningún fixture de esta carpeta. Por eso la tarea 5 se ejecutó como corrida
   directa de verificación (script ad-hoc contra `procesar_orden_compra()`, real,
   sin mocks) en vez de un nuevo test pytest permanente — construir esa
   infraestructura de comparación automática (que gastaría créditos de Gemini en
   cada corrida de CI) está fuera del alcance de las 6 tareas listadas y no se
   inventó sin pedirlo.
3. **`direccion_entrega` y el glyph roto en `razon_social_cliente`** se decidieron
   empíricamente con la corrida real de la tarea 5, no adivinados de antemano:
   Gemini infirió `direccion_entrega = "Lisandro de la Torre 737"` del contexto
   (aunque el documento no la etiqueta explícitamente como "dirección de entrega"),
   y `razon_social_cliente` conserva el carácter de reemplazo "�" en vez de "é" —
   artefacto de decodificación de fuente preexistente en el PDF (pdfplumber
   `extract_text()` ya lo devuelve así con el parser SIN modificar; no lo introduce
   este fix, y arreglarlo está fuera de alcance de esta tarea).
