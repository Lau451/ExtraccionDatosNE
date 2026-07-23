# Pendientes — Auditoría técnica de Core

Clasificación P1 (riesgo/impacto alto) / P2 (deuda técnica relevante) / P3 (menor),
verificada contra el código y los tests reales en esta sesión. Donde el insumo previo
de descubrimiento no coincidió con lo observado al releer el repositorio, se corrige
explícitamente.

## P1 — Riesgo alto

1. **Falta de allowlist de campos auditables.** `core/audit.py` no valida qué `campo`
   es válido auditar para cada entidad (D-CORE-008,
   `services/presupuestacion/core/audit.py:44-50`). Combinado con que
   `GET /historial/{entidad}/{entidad_id}` es legible por 6 roles sin filtro adicional
   (RN-CORE-021, `services/presupuestacion/auditoria/router.py:10`), un futuro call
   site que audite un campo sensible lo expondría sin control extra. [IMPLEMENTADO[el
   riesgo], RECOMENDACIÓN[la mitigación]: agregar un allowlist de campos permitidos por
   entidad en `core/audit.py`, o un filtro de campos sensibles en `auditoria/router.py`
   antes de exponer un campo nuevo.

2. **`auth.py`, `config.py` y `exceptions.py` sin test directo en `tests/core/`.**
   Verificado: `tests/core/` contiene únicamente `test_audit.py`, `test_stock.py`,
   `test_texto.py` y `test_database.py`; no existe `test_auth.py`, `test_config.py` ni
   `test_exceptions.py`. [IMPLEMENTADO]. Además, `test_database.py` en sí mismo no
   ejercita ninguna de las tres funciones de `core/database.py`
   (`get_bearer_token`, `get_service_client`, `get_user_client`) — su único test
   (`tests/core/test_database.py:8-25`) verifica exclusivamente la regla de
   arquitectura RN-CORE-016/D-CORE-006 (que `get_service_client` no aparezca en ningún
   `router.py`). En consecuencia, `database.py` tampoco tiene cobertura directa de su
   propio comportamiento (parseo del header `Bearer`, construcción de los clientes),
   más allá de lo que ejercitan indirectamente los tests de integración de otros
   módulos vía las fixtures de `tests/conftest.py`.

## P2 — Deuda técnica relevante

1. **Duplicación exacta de `EntidadAuditable`/`_COLUMNA_FK_POR_ENTIDAD`** entre
   `core/audit.py:7-9`, `:12-18` y `auditoria/models.py:6`, `:8-14`. Hoy ambos mapeos
   coinciden, pero no hay ninguna garantía estructural (import compartido, test de
   igualdad) de que sigan coincidiendo si uno se edita sin el otro. [IMPLEMENTADO]

2. **Corrección al insumo previo — el archivo mal nombrado no es
   `tests/shared/test_auth_jwt.py`, es otro.** El insumo de descubrimiento afirmaba que
   `tests/shared/test_auth_jwt.py` "no testea `auth_jwt.py`, testea la regla D-CORE-006
   vía grep de texto". Al releer ambos archivos, esto es incorrecto:
   - `tests/shared/test_auth_jwt.py:1-11` sí testea `auth_jwt.py` directamente
     (`verificar_token` levantando `TokenInvalidoError` ante un token malformado) — su
     nombre es correcto.
   - El test que verifica la regla D-CORE-006/RN-CORE-016 (grep de `"get_service_client"`
     sobre cada `router.py`) es en realidad
     `tests/core/test_database.py:8-25`
     (`test_service_client_no_se_importa_en_ningun_router`). Este sí es el caso de un
     archivo cuyo nombre sugiere que testea `database.py` en general, pero en la
     práctica solo contiene ese único test de arquitectura (ver P1(2) arriba) — el
     nombre no es "engañoso" respecto a qué prueba (`test_database.py` testeando algo
     de `database.py` es razonable), pero sí da una impresión de cobertura de
     `database.py` que no existe.

3. **Enforcement de "no `service_client` en routers" es un chequeo de substring, no
   análisis estático.** `tests/core/test_database.py:19` busca la cadena de texto
   `"get_service_client"` en el contenido crudo del archivo — no analiza el AST ni
   resuelve imports reales. Un alias de import o una reexportación indirecta podría
   evadir la detección sin que el test lo note. [IMPLEMENTADO], ver D-CORE-006.

4. **`_liberar_monto` y `_liberar_hasta` en `stock.py` tienen lógica y mensajes casi
   idénticos pero semántica distinta.** `_liberar_monto`
   (`services/presupuestacion/core/stock.py:95-121`) resta un monto fijo con piso en 0;
   `_liberar_hasta` (`core/stock.py:211-239`) libera hasta un monto deseado, acotado a
   lo comprometido en la fila. Ambas comparten casi el mismo cuerpo de reintentos y el
   mismo mensaje de error final ("No se pudo liberar el stock comprometido tras un
   error, reintentá la operación", `core/stock.py:119-121` y `:237-239`).
   [IMPLEMENTADO]. [RECOMENDACIÓN]: evaluar si `_liberar_monto` puede expresarse como
   un caso particular de `_liberar_hasta` (o viceversa) para reducir la duplicación.

5. **`config.py` resuelve `.env` con 4 `.parent` desde la ubicación del archivo**
   (`services/presupuestacion/core/config.py:6`). Un movimiento de `core/config.py` a
   otra profundidad de carpetas rompe esta resolución en silencio — no hay ninguna
   validación de que el `.env` calculado exista. [IMPLEMENTADO], RN-CORE-023.

6. **`core/__init__.py` vacío, sin superficie pública unificada**
   (`services/presupuestacion/core/__init__.py`). Cada consumidor debe conocer y
   escribir el path completo del submódulo que necesita; no hay un punto único desde
   el cual descubrir la API de Core. [IMPLEMENTADO].

## P3 — Menor

1. **`texto.py` es un archivo de 8 líneas con una sola función**
   (`services/presupuestacion/core/texto.py`). No representa un problema funcional,
   pero es notablemente pequeño en comparación con el resto del módulo.

2. **`exceptions.py` sin `__all__` ni docstring de módulo**
   (`services/presupuestacion/core/exceptions.py:1-4`, sin docstring tras los imports).
   No afecta el comportamiento, pero dificulta a un lector nuevo entender de un
   vistazo qué se espera importar de este archivo.

3. **`get_current_user` se usa directamente (sin `require_roles`) en
   `usuarios/router.py` y `notificaciones/router.py`.** No es un bug — ambos endpoints
   solo exigen estar autenticado, sin restricción de rol específico
   (`services/presupuestacion/usuarios/router.py:4`, `:15`, `:24`;
   `services/presupuestacion/notificaciones/router.py:4`, `:24`, `:35`, `:42`, `:49`,
   `:59`). Se señala porque, a diferencia de los otros 14 routers de
   `presupuestacion/` que sí usan `require_roles` con una whitelist explícita, estos
   dos dependen únicamente de RLS y de la lógica interna de cada `service.py` para
   acotar qué puede ver/hacer cada usuario. [IMPLEMENTADO] el hecho;
   "Pendiente de definición funcional" si esto es una decisión deliberada (ambos
   endpoints son de autoservicio, donde cualquier rol autenticado necesita acceso) o un
   descuido — no hay comentario en el código que lo aclare.
