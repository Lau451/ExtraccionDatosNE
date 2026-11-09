"""`presupuestacion/main.py` mounts one router per target module (X-ARQ-006,
odd/tasks/routers-por-modulo.md S3).

The routers of each module are grouped in `services/presupuestacion/modulos.py`, the
composition root: `main.py` imports no `*.router` module and calls `include_router`
once per entry of `MODULOS`.
"""
import ast
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
_MAIN = RAIZ / "services" / "presupuestacion" / "main.py"

_MODULOS_OBJETIVO = [
    "plataforma",
    "productos",
    "terceros",
    "comercial",
    "compras",
    "ordenes_compra",
    "integracion_progress",
    "automatizaciones",
]


def _arbol_main() -> ast.Module:
    return ast.parse(_MAIN.read_text(encoding="utf-8"), filename=str(_MAIN))


def test_main_imports_no_router_module():
    routers = [
        nodo.module
        for nodo in ast.walk(_arbol_main())
        if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.split(".")[-1] == "router"
    ]
    assert routers == [], f"main.py mounts loose routers instead of services/presupuestacion/modulos.py: {routers}"


def test_main_mounts_only_the_module_routers():
    llamadas = [
        nodo
        for nodo in ast.walk(_arbol_main())
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr == "include_router"
    ]
    assert len(llamadas) == 1, f"main.py has {len(llamadas)} include_router calls; expected one loop over MODULOS"


def test_modulos_are_the_target_modules_in_order():
    from services.presupuestacion.modulos import MODULOS

    assert [modulo.nombre for modulo in MODULOS] == _MODULOS_OBJETIVO


def test_no_route_is_registered_twice():
    from services.presupuestacion.main import app

    rutas = Counter(
        (ruta.path, metodo)
        for ruta in app.routes
        for metodo in sorted(getattr(ruta, "methods", None) or {"*"})
    )
    repetidas = [clave for clave, veces in rutas.items() if veces > 1]
    assert repetidas == [], f"routes mounted twice: {repetidas}"
