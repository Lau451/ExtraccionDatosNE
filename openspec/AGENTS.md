# Convención de openspec/ para frontend/

Adoptado el 2026-07-15. Alcance: las 8 pantallas del MVP de `frontend/` (ver `frontend/PROGRESS.md`
para el estado de cada una).

## Por qué existe este documento

`openspec/changes/parser-router-comparatives-refactor/` quedó completamente implementado
(commit del 2026-04-02) y nunca se archivó. No hay manera de saber, mirando `openspec/changes/`,
qué está vivo y qué ya se cerró. Las dos reglas de abajo existen para que eso no se repita en
`frontend/`.

## Regla 1 — Un change por pantalla, no por decisión de diseño

Cada una de las 8 pantallas del MVP (login, carga de documentos, validar extracción, procesos
comerciales, matching, presupuestos, comparativas, compras) tiene **un** change en
`openspec/changes/<nombre-pantalla>/`. No se abre un change nuevo por cada decisión chica dentro
de esa pantalla (un endpoint adicional, un ajuste de UI, un fix de wiring) — eso va como una
revisión del `proposal.md`/`spec.md`/`tasks.md` existente del change de la pantalla, o directo en
el commit si no cambia el contrato observable.

Umbral práctico: si la decisión cambia lo que la pantalla hace o expone (nuevo endpoint, nuevo
flujo, cambio de contrato), se refleja en el change existente. Si es implementación interna sin
impacto observable, no toca openspec en absoluto.

## Regla 2 — Archivar es parte de terminar la pantalla, no un paso aparte

Una pantalla **no está terminada** hasta que su change está en `openspec/changes/archive/`. El
commit que cierra la pantalla (el último commit funcional de esa pantalla) tiene que incluir el
`git mv openspec/changes/<nombre>/ openspec/changes/archive/<nombre>/` en el mismo commit o en uno
inmediatamente siguiente antes de pasar a la próxima pantalla.

Consecuencia directa: si `frontend/PROGRESS.md` marca una pantalla como "hecho" pero su change
sigue en `openspec/changes/<nombre>/` (no en `archive/`), la pantalla NO está cerrada — hay que
volver y archivarla antes de seguir.

## Estructura de cada change

```
openspec/changes/<nombre-pantalla>/       (mientras está activo)
openspec/changes/archive/<nombre-pantalla>/  (una vez cerrado)
  proposal.md   — intent, scope (qué se construye y qué no), riesgos si aplica
  spec.md       — comportamiento observable: endpoints, contratos, escenarios Given/When/Then
  tasks.md      — checklist de tareas, marcado [x] a medida que se completan
  design.md     — opcional; solo si hay una decisión de arquitectura no trivial que vale la pena
                  documentar para quien retome el código después
```

No hace falta `design.md` en la mayoría de las pantallas de `frontend/` — son CRUD + wiring contra
`services/extraccion` y `services/presupuestacion`, no arquitectura nueva. Se agrega solo cuando
hay algo genuinamente no obvio (p. ej. una decisión de cómo resolver una relación entre servicios).

## Estado y visibilidad

`frontend/PROGRESS.md` es la vista rápida: las 8 pantallas, su estado (pendiente / en progreso /
hecho) y el link al change correspondiente. Se actualiza en el mismo commit que cambia el estado
de una pantalla — no es un documento que se sincroniza "después".
