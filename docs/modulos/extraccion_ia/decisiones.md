# Decisiones de diseño — Extracción IA (legacy)

Numeración D-EXTRACCIONIA-NNN, verificada contra el código en esta sesión.

### D-EXTRACCIONIA-001 — Pipeline híbrido de PDF con 3 niveles de fallback (pdfplumber → Docling → Vision)

- **Decisión**: `_parse_pdf` prueba primero extracción nativa con pdfplumber (sin
  llamada a IA), reserva Docling (parsing ML local, más costoso en RAM) para PDFs
  escaneados o cuando pdfplumber falla/devuelve vacío, y usa Gemini Vision (llamada a
  API paga) solo como último recurso — ver [`arquitectura.md`](./arquitectura.md) para
  el diagrama completo.
- **Motivo**: no hay un comentario explícito en el código que declare "usamos
  pdfplumber primero porque es gratis y local". [SUPOSICIÓN], inferida del propio orden
  de la cadena y de comentarios parciales: el modo *lightweight* de Docling
  explícitamente busca "reducir uso de RAM" (`parsers.py:174`, docstring de
  `_docling_convert`), y Vision es la única rama que hace una llamada de red a Gemini
  por página/chunk — el orden observado (más barato/rápido primero, más caro/lento como
  último recurso) es consistente con optimizar costo y latencia, pero esa motivación no
  está escrita en ningún comentario del archivo. "Motivo pendiente de definición
  funcional" en su forma explícita.
- **Ventajas**: evita llamadas a Gemini (con costo y latencia de red) para la mayoría de
  los PDFs nativos, que son la mayoría de los casos esperables en documentos
  comerciales generados digitalmente.
- **Desventajas**: 3 rutas de código distintas para el mismo resultado final (un string
  Markdown/texto) implican 3 comportamientos a mantener, y — como documenta
  RN-EXTRACCIONIA-014 — casi ninguna tiene test directo. Ver
  [`pendientes.md`](./pendientes.md) P1.

### D-EXTRACCIONIA-002 — Chunking de comparativas para evitar truncamiento de Gemini

- **Decisión**: dividir documentos grandes de comparativas (por ítems de Markdown o por
  páginas de PDF) en vez de enviar todo el documento en una sola llamada a Gemini.
- **Motivo**: [IMPLEMENTADO], explícito en el propio código: `_JSON_CONFIG` fija
  `max_output_tokens=65_536` con el comentario "gemini-2.5-flash max; prevents mid-JSON
  truncation" (`robot_comparativas.py:49`), y el docstring de módulo declara
  explícitamente que el propósito del chunking es evitar el límite de salida de Gemini
  (`robot_comparativas.py:1-16`). El comentario junto a `_CHUNK_SIZE=15` — "reduce to 10
  if truncation persists in Phase 3" (`robot_comparativas.py:53`) — muestra que el valor
  fue calibrado empíricamente contra truncamientos observados en una fase de desarrollo
  previa ("Phase 3"), no derivado analíticamente de un cálculo de tokens.
- **Ventajas**: permite procesar comparativas de cualquier tamaño sin que la respuesta
  de Gemini se corte a mitad de un JSON; el split-in-half adicional
  (RN-EXTRACCIONIA-006) da una segunda capa de resiliencia si el tamaño de chunk fijo
  no alcanza para un documento particularmente denso.
- **Desventajas**: más llamadas a Gemini por documento (una por chunk, en vez de una
  sola), con el costo y la latencia agregada correspondientes; el paralelismo
  (`_MAX_PARALLEL_CHUNKS=3`) mitiga la latencia pero no el costo. El comentario "reduce
  to 10 if truncation persists" sugiere que 15 no es un valor definitivo, sino una
  aproximación sujeta a ajuste manual futuro.

### D-EXTRACCIONIA-003 — Reintentos con backoff largo (`max_retries=4, backoff_factor=40.0`)

- **Decisión**: tanto `procesar_archivo` (`robot.py:267`) como `_llamar_gemini_json`
  (`robot_comparativas.py:122`) usan `handle_gemini_errors(max_retries=4,
  backoff_factor=40.0)` — muy por encima de los defaults del decorador
  (`max_retries=3, backoff_factor=2.0`, `gemini_errors.py:69`).
- **Motivo**: no hay ningún comentario en `robot.py` ni en `robot_comparativas.py` que
  justifique por qué se eligieron exactamente esos valores. "Motivo pendiente de
  definición funcional". [SUPOSICIÓN]: con `backoff_factor=40.0`, un error de rate-limit
  persistente espera `40s, 80s, 160s` en los reintentos 1-3 (RN-EXTRACCIONIA-008) —
  tiempos consistentes con ventanas típicas de reseteo de cuota de la API de Gemini
  (medidas en minutos), lo que sugiere una intención de "esperar a que la cuota se
  libere" más que "reintentar rápido ante un error transitorio de red". No se encontró
  evidencia textual que confirme esta intención.
- **Ventajas**: mayor probabilidad de que un pico de rate-limit se resuelva solo sin
  intervención manual, en un pipeline donde el usuario ya espera (subida de archivo +
  procesamiento asíncrono) y no hay una necesidad dura de respuesta en milisegundos.
- **Desventajas**: en el peor caso (4 intentos, backoff exponencial), la espera
  acumulada antes de fallar definitivamente ronda los 280 segundos solo en reintentos
  de rate-limit — sin ningún mecanismo de cancelación visible en este módulo. Ver
  [`pendientes.md`](./pendientes.md).

### D-EXTRACCIONIA-004 — `generate_with_fallback` no filtra por tipo de excepción

- **Decisión**: ante **cualquier** excepción del modelo primario, reintentar de
  inmediato con el modelo fallback, sin inspeccionar el tipo ni el mensaje de la
  excepción (`config.py:100-105`).
- **Motivo**: no documentado en el código — "Motivo pendiente de definición funcional".
  El diseño prioriza simplicidad (un único `try/except Exception` genérico) sobre
  precisión de manejo de errores.
- **Ventajas**: máxima resiliencia ante fallas transitorias del modelo primario
  (sobrecarga, timeout, error 503) sin necesidad de mantener una lista de excepciones
  "reintentables" — cualquier falla del modelo primario tiene una segunda oportunidad
  automática.
- **Desventajas** [IMPLEMENTADO, confirmado]: errores que **no** se resolverían
  cambiando de modelo — como una API key inválida o revocada, que afecta al `client`
  completo, no al modelo elegido — también disparan el reintento con el modelo
  fallback, usando el mismo `client` potencialmente roto. Esto puede enmascarar la
  causa raíz real del error (el mensaje final que ve el caller es el de la falla del
  modelo *fallback*, no el motivo original de la falla del primario) y desperdicia una
  llamada de red completa antes de fallar. Ver RN-EXTRACCIONIA-007 y
  [`pendientes.md`](./pendientes.md) P1.

### D-EXTRACCIONIA-005 — Múltiples API keys con round-robin, en vez de una sola key

- **Decisión**: `GEMINI_API_KEYS` acepta una lista separada por comas; se crea un
  `genai.Client` por key (`config.py:69-80`) y `get_next_client()` rota entre ellos con
  un contador protegido por `threading.Lock` (`config.py:86-94`).
- **Motivo**: [IMPLEMENTADO], explícito en el comentario que precede la implementación:
  "Round-robin counter para distribuir load entre clientes" (`config.py:85`).
- **Ventajas**: distribuye la carga de requests entre múltiples cuotas de API,
  reduciendo la probabilidad de agotar la cuota de una sola key bajo uso concurrente.
- **Desventajas**: no hay lógica de *health-check* ni de exclusión de una key que esté
  fallando sistemáticamente (por ejemplo, revocada) — `get_next_client()` sigue
  rotándola en el ciclo igual que a las keys sanas, y cada fallo de esa key dispara el
  fallback de modelo (D-EXTRACCIONIA-004) antes de, eventualmente, fallar la request
  completa.

### D-EXTRACCIONIA-006 — `robot.py` no implementa chunking; `robot_comparativas.py` sí

- **Decisión**: `procesar_archivo` (licitaciones/pedidos) hace siempre una única
  llamada a Gemini por documento — no existe ninguna función de chunking en `robot.py`
  (confirmado por lectura completa del archivo). `procesar_comparativa` sí implementa 2
  estrategias de chunking (RN-EXTRACCIONIA-003/004).
- **Motivo**: no documentado explícitamente con un comentario que compare ambos casos.
  "Motivo pendiente de definición funcional" en su forma explícita. [SUPOSICIÓN]
  razonable a partir de la naturaleza de los datos: una licitación/pedido típico lista
  los ítems de **un solo** proveedor/cliente, mientras que una comparativa cruza
  **múltiples** proveedores por ítem — estructuralmente más grande y más propensa a
  superar el límite de salida de Gemini en documentos con muchas páginas o muchos
  proveedores. No se encontró ningún comentario que confirme esta razón como la
  intención real de diseño.
- **Ventajas**: `robot.py` se mantiene simple para el caso común (documento chico, un
  proveedor).
- **Desventajas**: si un pedido/licitación real excediera el límite de salida de Gemini
  (documento muy largo, muchos ítems), `procesar_archivo` no tiene ningún mecanismo de
  chunking ni de split-in-half — a diferencia de `robot_comparativas.py`, quedaría
  expuesto directamente a un truncamiento sin remediación automática. No se encontró
  ningún test que ejercite ese escenario para `robot.py`. Ver
  [`pendientes.md`](./pendientes.md).
