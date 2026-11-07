# Arquitectura objetivo — Plataforma Nueva Era

Este directorio define hacia dónde evoluciona el repositorio: de un conjunto de
funcionalidades construidas para necesidades puntuales a una **plataforma de
soluciones modulares, integradas entre sí y conectadas con Progress 9.1D**.

Es un documento de dirección, no de estado: describe la arquitectura objetivo y
los principios que guían cada cambio. El estado actual de cada módulo sigue
documentado en [`../modulos/`](../modulos/).

> Convención de etiquetas (igual que el resto de `docs/`):
> **[IMPLEMENTADO]** describe el código actual, con evidencia `archivo:línea`.
> **[RECOMENDACIÓN]** describe la dirección objetivo acordada, todavía no construida.

## En una frase

**Un monolito modular sobre una sola base de datos, con módulos dueños de sus datos,
una capa de plataforma común debajo, Progress como fuente de verdad detrás de una
capa de integración propia, y una única aplicación para el usuario.**

## Problema que resuelve

Hasta ahora, cada mejora que involucra datos o procesos de la empresa depende de
cambios en Progress 9.1D y de los tiempos de su proveedor. Con desarrollo asistido
por IA podemos construir soluciones mucho más rápido, pero esa velocidad se pierde
si cada herramienta nueva necesita una modificación en el sistema central.

El objetivo es que Nueva Era pueda **incorporar soluciones propias con autonomía**,
sin reemplazar Progress, sin duplicar lo que ya resuelve y sin terminar en un
conjunto de aplicaciones aisladas.

## Vista general

```
                 ┌──────────────── Frontend unificado (shell) ────────────────┐
                 │ Login · Menú por permisos · Rutas por módulo · Diseño común │
                 └──────────────────────────┬─────────────────────────────────┘
                                            │ HTTP (un solo origen)
┌───────────────────────────────────────────┴───────────────────────────────────┐
│ CAPACIDADES        extracción IA (proceso aparte) · agentes · automatizaciones │
├───────────────────────────────────────────────────────────────────────────────┤
│ MÓDULOS DE NEGOCIO comercial · compras/PCP · órdenes de compra · analítica     │
├───────────────────────────────────────────────────────────────────────────────┤
│ DATOS MAESTROS     productos (+ stock) · terceros (clientes/proveedores)       │
├───────────────────────────────────────────────────────────────────────────────┤
│ PLATAFORMA         identidad · capacidades · tenant · auditoría · eventos ·    │
│                    notificaciones · archivos · errores · configuración         │
├───────────────────────────────────────────────────────────────────────────────┤
│ INTEGRACIÓN PROGRESS  capa anticorrupción · adaptador de archivos (hoy)        │
└───────────────────────────────────────────────────────────────────────────────┘
                 Supabase / PostgreSQL (una base, tablas con dueño)
```

Las dependencias de código van **siempre hacia abajo**. `integracion_progress` es
consumida por los módulos de negocio y de maestros a través de su fachada; nunca
escribe tablas de otro módulo.

## Principios

| # | Principio | Qué significa en la práctica |
|---|-----------|------------------------------|
| P1 | **Un dueño por dato** | Cada tabla pertenece a un módulo; solo ese módulo escribe en ella. Los demás leen por su fachada o por vistas publicadas. |
| P2 | **Se entra a un módulo solo por su fachada** | Nadie importa el `service` o `repository` interno de otro módulo; se usa su `api.py`. Se hace cumplir con tests de dependencias. |
| P3 | **Dependencias hacia abajo, sin ciclos** | Negocio → maestros → plataforma. La plataforma no conoce a ningún módulo de negocio. |
| P4 | **Progress es la fuente de verdad de lo que ya administra** | No reimplementamos sus reglas: consumimos sus resultados. Lo que guardamos de Progress es una réplica con origen y fecha, nunca una segunda verdad. |
| P5 | **Un único punto de contacto con Progress** | Ningún módulo de negocio sabe si Progress se comunica por archivo, SQL o API. |
| P6 | **El contrato asume el canal más restrictivo** | Las operaciones con Progress son asincrónicas y los datos leídos tienen antigüedad, aunque mañana el canal sea más rápido. |
| P7 | **Permisos por capacidad, no por rol en el código** | Se verifica `pcp.escribir`, no `("admin", "gerencia", "compras")`. Los roles son datos que agrupan capacidades. |
| P8 | **Se despliega aparte solo por necesidad de ejecución** | Carga, dependencias pesadas, ritmo de release o aislamiento de fallas. No por prolijidad. |
| P9 | **Una sola aplicación para el usuario** | Un login, un menú, un diseño, una forma de mostrar errores, sin importar cuántos módulos haya detrás. |
| P10 | **Evolución gradual** | Cada paso es un PR revisable y reversible, mantiene las rutas HTTP actuales y se hace cuando el módulo se toca por otro motivo o cuando el problema duele. |

## Decisiones de arquitectura

| ID | Decisión | Motivo |
|----|----------|--------|
| D-ARQ-001 | **Monolito modular**, no microservicios. | Equipo chico, una sola base, desarrollo asistido por IA. Los microservicios suman red, versionado de contratos y transacciones distribuidas sin resolver un problema que hoy tengamos. |
| D-ARQ-002 | **Unidades desplegables solo por perfil de ejecución.** Hoy son dos: extracción IA y el resto. | `services/extraccion` ya corre aparte (Gemini, docling, mucha RAM; `docker-compose.yml`). Es el criterio a mantener. |
| D-ARQ-003 | **`services/shared/` se convierte en la capa `plataforma`** y absorbe lo que queda del núcleo en `presupuestacion/`. | La extracción ya empezó: `auth`, `database`, `config` y `exceptions` viven en `services/shared/` y `presupuestacion/core/` los reexporta por compatibilidad (`services/presupuestacion/core/auth.py:1-8`). Falta mover `audit`, `texto` y los módulos transversales, llevar `stock` a `productos`, y que los consumidores importen de `shared` y no del shim. |
| D-ARQ-004 | **Capa anticorrupción para Progress, con adaptador de archivos bidireccional.** | Hoy el único canal es el intercambio de CSV, y en el futuro podría haber otros. Ver [`integracion-progress.md`](./integracion-progress.md). |
| D-ARQ-005 | **Eventos de dominio con tabla outbox en Postgres**, sin bus de mensajes. | Alcanza para reacciones entre módulos (notificaciones, analítica, agentes) sin infraestructura nueva. |
| D-ARQ-006 | **El módulo `comercial` queda junto** (procesos, matching, pricing, presupuestos, comparativas). | Comparten ciclo de vida y se escriben entre sí. Separarlos hoy cortaría una transacción de negocio en dos. Ver [`mapa-modulos.md`](./mapa-modulos.md). |

## Lo que explícitamente no hacemos

- No reemplazamos Progress ni replicamos todos sus datos "por las dudas". Se sincroniza solo lo que un módulo concreto necesita.
- No usamos una base de datos por módulo ni un bus de mensajes externo (Kafka, RabbitMQ).
- No hacemos una reorganización masiva de carpetas en un solo cambio.
- No separamos en módulos por motivos puramente técnicos.

## Documentos de este directorio

| Documento | Contenido |
|-----------|-----------|
| [`mapa-modulos.md`](./mapa-modulos.md) | Módulos actuales → módulos objetivo, qué se separa, qué queda junto y desvíos conocidos. |
| [`plataforma-comun.md`](./plataforma-comun.md) | Usuarios, permisos, información compartida, eventos, evolución a distinta velocidad y experiencia unificada. |
| [`integracion-progress.md`](./integracion-progress.md) | Contrato con Progress, flujo de archivos en ambos sentidos y estándar de archivos para el proveedor. |
| [`propuesta-gerencia.html`](./propuesta-gerencia.html) | Versión para Gerencia: lenguaje no técnico, con ejemplos. Se abre en el navegador y se puede imprimir o guardar como PDF. |

## Etapas de implementación

Cada etapa es una feature ODD propia (`odd/tasks/<feature>.md`). El orden pone primero lo
que más riesgo tiene de romper datos sin que se note y deja al final lo que es orden.

| Etapa | Qué resuelve | Desvío | Estado |
|-------|--------------|--------|--------|
| 0 | Cimientos: capas y `services/shared` como plataforma (`tests/arquitectura/test_capas.py`). | X-ARQ-001 | **[IMPLEMENTADO]** (#96) |
| 1 | `integracion_progress`: fachada, registro de archivos, recepción manual y automática. | — | **[IMPLEMENTADO]** (#97, `odd/tasks/integracion-progress.md`) |
| 2 | Un solo dueño de `procesos_comerciales`: los demás módulos escriben a través de su fachada. | X-ARQ-003 | **[IMPLEMENTADO]** (`odd/tasks/procesos-comerciales-dueno.md`) |
| 3 | Versionado de costos en un solo lugar: `imports` llama a la fachada de `productos`. | X-ARQ-004 | **[IMPLEMENTADO]** (`odd/tasks/costos-un-dueno.md`) |
| 4 | `pcp` usa las fachadas de `notificaciones` y `pricing` en lugar de sus internos. | X-ARQ-002 | Pendiente |
| 5 | Roles y permisos centralizados en la plataforma. | X-ARQ-005 | Pendiente |
| 6 | `presupuestacion/main.py` deja de montar 25 routers sueltos; se agrupan por módulo. | X-ARQ-006 | Pendiente |
| 7 | Maestros de solo lectura: las altas de productos y terceros las hace Progress. Se escribe el contrato de propiedad por campo y se cierran o restringen los endpoints manuales de alta, costo y stock, junto con sus pantallas. | — | Pendiente |
| Después | Eventos con outbox en Postgres ([`plataforma-comun.md`](./plataforma-comun.md)) y nuevos tipos de archivo con Progress a medida que se acuerden con el proveedor. | — | Pendiente |
