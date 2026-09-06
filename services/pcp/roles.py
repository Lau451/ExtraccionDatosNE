"""Roles de lectura/escritura compartidos por todos los routers de
services/pcp/ (design.md D11, mismo criterio que la política de
`precios_proveedor`).

Definidos una sola vez acá -- a diferencia de `_ROLES_LECTURA`/`_ROLES_ESCRITURA`
en services/terceros/identidad/router.py, que son locales a ese router porque
son el único consumidor -- porque PR5 (renglones), PR6 (catalogo-proveedores)
y PR7 (negociacion) necesitan exactamente el mismo par. Sin nombre `_` inicial
a propósito: son un export público de este módulo, no un detalle interno de
un único router. No es `services/pcp/{router,api,errors}.py` (eso sigue
siendo tarea de PR5, 5.7): este archivo no agrega ni monta nada, solo declara
dos constantes.
"""

ROLES_LECTURA_PCP = ("superadmin", "admin", "gerencia", "compras")
ROLES_ESCRITURA_PCP = ("admin", "gerencia", "compras")
