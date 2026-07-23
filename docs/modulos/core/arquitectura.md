# Arquitectura — Core

## Posición de Core en el sistema

Core es la capa base de `services/presupuestacion/`: no importa de ningún otro módulo
de negocio (`presupuestos/`, `compras/`, `procesos_comerciales/`, etc.), y todos ellos
importan de Core en mayor o menor medida. [IMPLEMENTADO] — confirmado por inspección de
imports: ningún archivo de `core/`, `auditoria/` ni `shared/auth_jwt.py` importa desde
un paquete de negocio de `presupuestacion/`; la única dependencia interna cruzada
dentro del propio bloque es `core/auth.py` que importa de `core/config.py`,
`core/database.py`, `core/exceptions.py` y `shared/auth_jwt.py`
(`services/presupuestacion/core/auth.py:7-10`).

```
                         ┌─────────────────────────────┐
                         │   services/shared/auth_jwt.py │  ← kernel JWT compartido
                         │   (sin lógica de negocio)      │
                         └───────────────┬───────────────┘
                                         │ usado por
                       ┌─────────────────┴─────────────────┐
                       │                                     │
        ┌──────────────▼──────────────┐      ┌───────────────▼──────────────┐
        │ services/extraccion/auth.py │      │ services/presupuestacion/     │
        │ (identificación OPCIONAL)   │      │   core/auth.py                │
        └──────────────────────────────┘      │ (identificación OBLIGATORIA, │
                                                │  con roles y RLS)            │
                                                └───────────────┬───────────────┘
                                                                │
   ┌──────────────┬──────────────┬──────────────┬──────────────┼───────────────┐
   │              │              │              │              │               │
core/         core/          core/          core/          core/           core/
exceptions.py texto.py       database.py    stock.py       config.py       audit.py
   │              │              │              │              │               │
   └──────────────┴──────────────┴──────┬───────┴──────────────┴───────────────┘
                                         │ leído por (capa HTTP de solo lectura)
                                ┌────────▼────────┐
                                │ auditoria/       │
                                │ models.py+router.py │
                                └────────┬────────┘
                                         │
                     ┌───────────────────┴───────────────────────────────────┐
                     │   Todos los módulos de negocio de presupuestacion/     │
                     │   (presupuestos, compras, procesos_comerciales,        │
                     │    pricing, eventos, extraccion, matching, catalogo,   │
                     │    clientes, imports, usuarios, notificaciones,        │
                     │    automatizaciones, comparativas)                    │
                     └─────────────────────────────────────────────────────────┘
```

`core/__init__.py` está vacío (`services/presupuestacion/core/__init__.py`), por lo que
no existe un punto de entrada único: cada consumidor importa directamente del
submódulo puntual que necesita (p. ej. `from services.presupuestacion.core.audit import
registrar_cambio`), no de `services.presupuestacion.core`. [IMPLEMENTADO]

## Por qué se documentan juntos `auditoria/`, `shared/auth_jwt.py` y `core/`

- **`auditoria/`** no tiene lógica propia de negocio: `auditoria/router.py` es un único
  endpoint de lectura (`GET /historial/{entidad}/{entidad_id}`,
  `services/presupuestacion/auditoria/router.py:13-19`) que consulta la misma tabla
  (`historial_cambios`) que escribe `core/audit.py`, protegido con la misma
  dependencia de autorización (`require_roles`) que usa el resto de Core. Separarlo en
  su propia documentación de módulo obligaría a explicar dos veces la misma tabla y el
  mismo mecanismo de auth. [IMPLEMENTADO]
- **`services/shared/auth_jwt.py`** es el único código compartido entre los dos
  backends del monorepo (`services/extraccion/` y `services/presupuestacion/`,
  `services/shared/auth_jwt.py:1-5`, `services/extraccion/auth.py:18`,
  `services/presupuestacion/core/auth.py:10`). No pertenece conceptualmente a ninguno
  de los dos backends por separado, y `core/auth.py` es su único consumidor dentro de
  `presupuestacion/`; documentarlo aparte fragmentaría el flujo de autenticación que
  describe [`flujo.md`](./flujo.md) (Flujo B) en dos documentos distintos sin necesidad.
  [IMPLEMENTADO]

## Patrón `service_client` vs `user_client`

Este es el patrón de acceso a datos central de todo el backend de presupuestación, y se
documenta una única vez acá como referencia (los demás módulos lo enlazan en vez de
repetirlo).

`core/database.py` expone dos formas de construir un cliente de Supabase
(`services/presupuestacion/core/database.py`):

- **`get_service_client()`** (`core/database.py:19-22`): usa
  `settings.supabase_service_key` y está decorado con `@lru_cache` (línea 19), por lo
  que es un singleton por proceso — se crea una sola vez y se reutiliza en todas las
  llamadas posteriores (RN-CORE-014). Este cliente **bypasea Row Level Security
  (RLS)**: cualquier consulta hecha con él ve todos los datos de todas las droguerías,
  sin el filtro de RLS que aplica Supabase a las claves anónimas autenticadas. Por
  diseño, está reservado a jobs de sistema y procesos internos, nunca a un endpoint
  invocado directamente por un usuario — ver RN-CORE-016 y D-CORE-006.
- **`get_user_client(token)`** (`core/database.py:25-29`): usa
  `settings.supabase_anon_key` y autentica el cliente PostgREST con el JWT del request
  (`client.postgrest.auth(token)`, línea 28). Con este cliente, Supabase aplica RLS
  normalmente: cada consulta queda acotada a lo que las políticas de RLS permiten para
  ese usuario/droguería. Es el cliente que debe usar cualquier código que atienda una
  request de un usuario autenticado.

La regla no escrita en código (solo verificada por un test, ver RN-CORE-016) es: los
`router.py` de `presupuestacion/` no deben importar `get_service_client` — deben
depender de `get_user_client` (directo o vía `core/auth.py`) para que las respuestas
respeten RLS por droguería.
