"""Códigos de error de Postgres compartidos por `services/pcp/**` (design.md
D1, File Changes).

Cada submódulo de PCP sigue definiendo su propia copia local de estos
códigos cuando los necesita (p.ej. `gestion/service.py::_UNIQUE_VIOLATION`)
porque D1 evita que un submódulo importe un helper interno de otro --mismo
criterio que ya documenta `gestion/service.py`. Este módulo es el lugar para
las constantes que sí son seguras de compartir, porque no cruzan la
frontera de un submódulo a otro: solo nombran un código estándar de
Postgres, igual que `services/terceros/errors.py::UNIQUE_VIOLATION`.
"""

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
