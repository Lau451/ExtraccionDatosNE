# Módulo Core — `services/presupuestacion/core/`

## Qué es

Core es el conjunto de utilidades base que usa el resto de `services/presupuestacion/`
para resolver problemas transversales: errores de dominio, autenticación/autorización,
acceso a Supabase, ajuste concurrente de stock, normalización de texto, auditoría de
cambios y configuración de la aplicación. No representa una entidad de negocio propia
(no tiene un "proceso comercial Core" ni un "presupuesto Core"): es infraestructura de
soporte consumida por los módulos de negocio (`presupuestos/`, `compras/`,
`procesos_comerciales/`, etc.).

Para efectos de esta documentación, el módulo Core fusiona tres ubicaciones de código
que en el repositorio están físicamente separadas pero funcionan como una sola unidad
conceptual:

- `services/presupuestacion/core/` — el núcleo propiamente dicho.
- `services/presupuestacion/auditoria/` — la única capa HTTP de este bloque: expone
  por lectura lo que `core/audit.py` escribe.
- `services/shared/auth_jwt.py` — el kernel de verificación JWT compartido con
  `services/extraccion/` (el otro backend del monorepo).

Ver [`arquitectura.md`](./arquitectura.md) para el detalle de por qué se fusionan estas
tres ubicaciones en una sola documentación.

## Qué NO es

- No es un módulo de negocio: no modela procesos comerciales, presupuestos, órdenes de
  compra ni ninguna entidad del dominio de Drogueria Nueva Era.
- No implementa una máquina de estados propia. `core/stock.py` opera sobre magnitudes
  numéricas (`cantidad_comprometida`, `cantidad_disponible`), no sobre un enum de
  estados; `core/audit.py` clasifica `tipo_cambio` como una etiqueta de log, no como el
  estado de una entidad. Por esta razón **este módulo no tiene `estados.md`** — omitido
  deliberadamente del set de documentos.
- No es dueño (`owner`) de la tabla `usuarios`: la lee para resolver el perfil del
  solicitante (`core/auth.py`), pero el modelo y las reglas de esa tabla pertenecen al
  módulo `usuarios/`. Ver [`base_de_datos.md`](./base_de_datos.md).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `core/__init__.py` | Vacío; Core no expone una superficie pública unificada, cada consumidor importa directamente del submódulo que necesita. |
| `core/exceptions.py` | Jerarquía de excepciones de dominio (`DomainError` y subclases) y su registro centralizado como handlers HTTP de FastAPI. |
| `core/texto.py` | `normalizar_descripcion`: normaliza texto libre a mayúsculas sin tildes/puntuación para comparación/matching. |
| `core/database.py` | Resolución del token `Bearer` y construcción de los dos clientes de Supabase (`service_client` sin RLS, `user_client` con RLS). |
| `core/stock.py` | Compromiso, liberación y descuento de stock entre depósitos con optimistic locking; el archivo más largo y con más reglas de negocio del módulo. |
| `core/config.py` | `Settings` (pydantic-settings) leído desde `.env`, y `get_settings()` cacheado. |
| `core/audit.py` | Inserción de filas en `historial_cambios` (cambios de campo y eventos de ciclo de vida). |
| `core/auth.py` | Resolución de claims JWT a perfil de usuario (`UsuarioPerfil`) y `require_roles(*roles)` para autorización por rol. |
| `auditoria/models.py` | Modelo de salida `HistorialCambioOut` y una copia duplicada del mapeo entidad→FK de `core/audit.py` (ver [`pendientes.md`](./pendientes.md)). |
| `auditoria/router.py` | Único endpoint HTTP de este bloque: `GET /historial/{entidad}/{entidad_id}`. |
| `shared/auth_jwt.py` | Verificación de firma/vigencia de JWT contra el JWKS de Supabase; sin lógica de negocio de ningún dominio, compartido entre `extraccion` y `presupuestacion`. |

## Quién lo consume

Prácticamente todos los módulos de negocio de `presupuestacion/` dependen de Core en
mayor o menor medida: 14 módulos usan `core/database.py` para obtener clientes de
Supabase, casi todos los `router.py` usan `require_roles` de `core/auth.py`, y la
mayoría de los `service.py` usan `core/exceptions.py`. `core/stock.py` tiene solo 2
consumidores (`compras/` y `presupuestos/`) y `core/texto.py` solo 2
(`extraccion/service.py` y `matching/service.py`). El detalle completo, con evidencia
de call sites, está en [`casos_de_uso.md`](./casos_de_uso.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias, decisión de fusión de las 3
  ubicaciones, patrón `service_client` vs `user_client`.
- [`base_de_datos.md`](./base_de_datos.md) — tablas tocadas y qué operación hace Core
  sobre cada una.
- [`reglas.md`](./reglas.md) — reglas técnicas y de negocio (RN-CORE-NNN).
- [`flujo.md`](./flujo.md) — los 4 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — consumidores reales de Core con evidencia.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-CORE-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.
