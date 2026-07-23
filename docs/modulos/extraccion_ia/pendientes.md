# Pendientes — Auditoría técnica de Extracción IA (legacy)

Clasificación P1 (ausencia de una capacidad esperada / riesgo estructural) / P2 (deuda
técnica relevante) / P3 (menor), verificada contra el código y los tests reales en esta
sesión.

## P1 — Riesgo estructural

1. **Gran parte del pipeline de parseo de PDF no tiene test directo.** `_parse_pdf`,
   `_parse_excel`, `_parse_html`, `_parse_image`, `is_scanned_pdf` y
   `_extract_native_pdf` (`parsers.py`) no aparecen en ningún `import` ni `patch(...)`
   de `tests/` — confirmado por grep en esta sesión sobre todo el directorio `tests/`,
   sin resultados para esos 6 nombres. La única cobertura de `parsers.py` es
   `tests/test_brand_distribution.py`, que prueba `_clean_brand` y `_distribute_brands`
   — dos helpers internos de `_extract_native_pdf`, no la función completa ni la cadena
   de fallback pdfplumber → Docling → Vision (RN-EXTRACCIONIA-014). Ningún test verifica
   el comportamiento cuando Docling no está instalado, cuando pdfplumber levanta una
   excepción, cuando un chunk de Docling falla individualmente, ni la detección de PDF
   escaneado (`is_scanned_pdf`). [IMPLEMENTADO] la ausencia, confirmada por grep. Riesgo:
   un cambio que rompa cualquiera de estas 6 funciones no sería detectado por la
   suite de tests actual.

2. **`generate_with_fallback` reintenta con el modelo fallback ante cualquier
   excepción, incluida una API key inválida/revocada.** `config.py:100-105` usa
   `except Exception as exc` genérico, sin clasificar el error. Confirmado además por
   `tests/test_fallback.py`, que prueba explícitamente 3 tipos de excepción distintos
   (`Exception("503...")`, `Exception("429...")`, `TimeoutError(...)`) y verifica el
   mismo comportamiento de fallback para los 3 — sin ningún test que cubra un error de
   autenticación. [IMPLEMENTADO]. Consecuencia: si la key resuelta por
   `get_next_client()` está vencida/revocada, la primera llamada falla, se reintenta con
   el modelo fallback usando el **mismo cliente** (misma key rota) y también falla — el
   mensaje de error final que ve el caller es sobre el modelo fallback, ocultando que la
   causa raíz es la key, no el modelo. Ver D-EXTRACCIONIA-004 en
   [`decisiones.md`](./decisiones.md).

3. **`_distribute_brands` está acoplado a un layout de columnas hardcodeado
   (`ITEM_COL=1, DESC_COL=3, PRICE_COL=5`), sin validación de que ese layout se cumpla.**
   `parsers.py:262-348` (RN-EXTRACCIONIA-015). El guard de entrada solo verifica que
   exista alguna fila con más columnas que `PRICE_COL` (`parsers.py:284-285`) — no
   verifica que las columnas 1, 3 y 5 sean efectivamente "Item", "Descripción" y "PU".
   Si un cliente sube una comparativa cuya tabla extraída por pdfplumber tiene un orden
   de columnas distinto (por ejemplo, una columna adicional al inicio), la función
   distribuiría marcas a la columna equivocada — o directamente a datos que no son
   Descripción — sin ningún error visible, produciendo un CSV final con marcas
   incorrectas silenciosamente. [IMPLEMENTADO] el acoplamiento, confirmado leyendo la
   función completa; los 6 tests de `tests/test_brand_distribution.py` usan
   consistentemente el mismo layout de 7 columnas y no ejercitan ningún layout
   alternativo.

## P2 — Deuda técnica relevante

1. **Doble capa de reintento (`generate_with_fallback` + `handle_gemini_errors`) sin
   documentación de cómo interactúan.** Una llamada a `_llamar_gemini_json` puede, en
   el peor caso, disparar: intento con modelo primario → falla → intento con modelo
   fallback (dentro de `generate_with_fallback`, sin backoff) → si también falla,
   propaga la excepción → `handle_gemini_errors` la clasifica y decide si reintentar
   **todo el ciclo anterior** con backoff (hasta 4 veces). El resultado es hasta 8
   llamadas de red por chunk en el peor caso (4 reintentos × 2 modelos), sin que ningún
   comentario en el código documente esta interacción ni el número total de llamadas
   posibles. [IMPLEMENTADO], deducido leyendo `config.py:96-105` junto con
   `gemini_errors.py:69-140` y sus puntos de aplicación en `robot.py:267` y
   `robot_comparativas.py:122`.

2. **`CLIENT` se importa pero no se usa en `robot.py` ni en `robot_comparativas.py`.**
   Ambos archivos importan `CLIENT` de `config.py` (`robot.py:11`,
   `robot_comparativas.py:40`) pero ninguno lo referencia en su cuerpo — confirmado por
   grep dentro de cada archivo, sin más ocurrencias que la línea de import. Solo
   `parsers.py` usa efectivamente `CLIENT` (en `_parse_image`,
   `parsers.py:661-662`, `:681`). Import muerto, cosmético, sin impacto funcional.

3. **Valores de `max_retries=4, backoff_factor=40.0` sin justificación comentada,
   con espera acumulada de hasta ~280 segundos.** Ver D-EXTRACCIONIA-003 en
   [`decisiones.md`](./decisiones.md). No hay ningún mecanismo de cancelación ni de
   feedback incremental al usuario visible en estos 5 archivos durante esa espera —
   verificar si `main.py` (fuera de este módulo) expone algún timeout o indicador de
   progreso queda fuera del alcance de esta documentación.

4. **`robot.py` no implementa chunking ni split-in-half, a diferencia de
   `robot_comparativas.py`.** Ver D-EXTRACCIONIA-006 en [`decisiones.md`](./decisiones.md).
   Si un pedido/licitación individual excediera el límite de salida de Gemini
   (`max_output_tokens` no se fija explícitamente en `robot.py` — a diferencia de
   `robot_comparativas.py`, que sí usa `_JSON_CONFIG` con `max_output_tokens=65_536`;
   `robot.py` llama a `generate_with_fallback` sin `config`, `robot.py:333`/`:335`, por
   lo que usa el default del SDK), no hay ningún mecanismo de recuperación — solo la
   validación superficial de que la respuesta contenga `"item;"`
   (RN-EXTRACCIONIA-001), que no detecta un CSV truncado a mitad de fila.

## P3 — Menor

1. **El comentario "Lazy import to avoid circular dependency at module load time"
   (`robot_comparativas.py:930`) no corresponde a un ciclo verificable en el grafo de
   imports actual.** `parsers.py` no importa nada de `robot.py` ni de
   `robot_comparativas.py` — confirmado por grep en esta sesión, sin resultados. Con el
   grafo actual, un import top-level de `parsers.parse_document` al inicio de
   `robot_comparativas.py` no formaría ningún ciclo. [SUPOSICIÓN]: posible vestigio de
   un estado anterior del código (no verificable sin historial de git, fuera de
   alcance) o medida defensiva mantenida por precaución. Ver
   [`arquitectura.md`](./arquitectura.md).

2. **`MODEL_NAME = PRIMARY_MODEL` (`config.py:78`) parece no tener ningún consumidor en
   el repositorio.** Comentario propio: "compatibilidad hacia atrás". Confirmado por
   grep sobre todo el repositorio buscando `MODEL_NAME`, sin resultados fuera de esa
   misma línea de definición. Candidato a variable muerta, aunque no se puede descartar
   con certeza total que algún script fuera del árbol indexado por esta sesión la use.

3. **`test_concurrency.py`, `test_concurrency_pytest.py` y `run_concurrency_test.sh` no
   ejercitan ninguna función de este módulo** — mockean `procesar_archivo` por completo
   para probar la concurrencia del endpoint HTTP (`main.py`), no la concurrencia de
   llamadas a Gemini. Se documentan acá solo para dejar constancia explícita de por qué
   se excluyeron del alcance de esta documentación (ver
   [`casos_de_uso.md`](./casos_de_uso.md)), no como hallazgo de deuda técnica de este
   módulo.

4. **`tests/test_key_fix.py` prueba `get_next_client`/`procesar_archivo` pero no forma
   parte del set de tests asignado a este módulo.** Dos de sus tres tests
   (`test_mismo_cliente_para_upload_y_generate`,
   `test_round_robin_alterna_entre_requests`) ejercitan directamente comportamiento de
   `robot.py`/`config.py` de este módulo; el tercero
   (`test_dos_usuarios_simultaneos_no_cruzan_clientes`) depende de `main.py`/FastAPI y
   pertenece al otro módulo. Se cita como evidencia en
   [`casos_de_uso.md`](./casos_de_uso.md) pero no se documentó como test principal de
   este módulo por no haber sido parte del alcance explícito.
