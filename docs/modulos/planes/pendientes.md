# Pendientes — Auditoría técnica de Planes

Clasificación P1 (ausencia de una capacidad esperada) / P2 (deuda técnica relevante) /
P3 (menor), verificada contra el código, la migración y la ausencia de tests en esta
sesión.

## P1 — Ausencias esperadas, ya reconocidas como tales por el propio proyecto

1. **No hay CRUD de planes.** Solo `GET /planes` existe. Crear, editar o desactivar un
   plan requiere SQL directo contra la base, fuera de la aplicación. [IMPLEMENTADO] el
   hecho (confirmado por lectura completa de `router.py`, ausencia de
   `repository.py`/`service.py`). A diferencia de otros pendientes de este proyecto,
   esta ausencia está documentada como decisión explícita en el propio código — ver
   D-PLANES-001 en [`decisiones.md`](./decisiones.md) — por lo que no es un
   descubrimiento sino una confirmación de una limitación ya conocida.

2. **No hay ningún enforcement de los límites del plan.** `max_usuarios`,
   `max_documentos_mes`, `almacenamiento_mb` y `funcionalidades` son columnas sin
   ningún código que las lea para bloquear una operación — confirmado por grep en esta
   sesión sobre `services/presupuestacion/` y `services/extraccion/` (0 matches de
   estos 4 nombres de columna fuera de `planes/models.py` y la migración). Esto
   significa que, aunque una droguería tenga `plan_id` asignado y ese plan tenga
   `max_usuarios=5`, hoy nada impide crear un sexto usuario para esa droguería vía
   `POST /usuarios` — el módulo de Usuarios no consulta `planes` en ningún punto (no
   verificado exhaustivamente en este módulo, pero consistente con el grep de 0
   matches). [IMPLEMENTADO] el hecho de la ausencia. Mismo criterio de "estructura sin
   lógica" que D-PLANES-001 — pendiente de definición funcional si/cuándo se
   implementa.

## P2 — Deuda técnica relevante

1. **Sin ningún test.** No existe `tests/planes/` (confirmado con Glob en esta
   sesión) — ni de la única regla (RN-PLANES-001, filtro `activo=True`) ni de que el
   endpoint responda 401 sin autenticación. Para un módulo de 18 líneas de router el
   impacto es acotado, pero es la única ausencia total de cobertura entre los módulos
   nuevos de esta sesión (compárese con [`../droguerias/`](../droguerias/), que sí tiene
   `tests/droguerias/test_service.py`).

## P3 — Menor

1. **Las policies de escritura (`planes_ins`/`upd`/`del`) ya están definidas en RLS
   pero no las usa ningún código.** No es un riesgo de seguridad (nadie puede
   escribir sin pasar por ellas, porque no hay endpoint que lo intente), pero es
   superficie de base de datos sin código de aplicación correspondiente — quedará así
   hasta que se implemente el CRUD mencionado en P1(1).

2. **Sin paginación en `GET /planes`.** Devuelve siempre el catálogo completo de
   planes activos, sin `limit`/`offset`. Impacto previsiblemente mínimo dado que el
   número de planes de un sistema de suscripción suele ser pequeño (a diferencia de
   `clientes` o `productos`) — no verificable sin datos reales de producción.
