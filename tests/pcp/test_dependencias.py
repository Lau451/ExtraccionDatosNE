"""Guard D1 (openspec/changes/gestor-pcp/design.md): services/pcp/ es una
fachada unidireccional restringida. services/pcp/** solo puede importar capas
de servicio publicas de otros modulos -- nunca un repository ajeno -- y
services/presupuestacion/** solo puede importar services.pcp desde main.py
(el montaje del router).

Este test es intencionalmente RED hasta que la Fase 5 cree services/pcp/
(tasks.md 1.12, 5.7): sin ese paquete el primer guard no tiene nada que
recorrer, asi que en vez de pasar en falso (0 archivos = 0 ofensores), la
asercion exige que el directorio exista. Se re-verifica en GREEN en la
Fase 5.8, una vez que services/pcp/router.py existe y esta montado.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PCP_ROOT = REPO_ROOT / "services" / "pcp"
PRESUPUESTACION_ROOT = REPO_ROOT / "services" / "presupuestacion"

# D1: capas de servicio publicas que services/pcp/** puede importar. Nunca un
# `repository` ajeno, y nunca ningun otro submodulo de presupuestacion/terceros.
_PERMITIDOS_EXACTOS = {
    "services.presupuestacion.pricing.service",
    "services.presupuestacion.notificaciones.service",
    "services.terceros.api",
}
_PERMITIDOS_PREFIJO = ("services.productos",)

# Prefijos de otros modulos cuyo uso desde services/pcp/** esta vigilado.
# Cualquier import fuera de estos tres arboles (stdlib, pydantic, fastapi,
# services.shared, etc.) no es asunto de este guard.
_PREFIJOS_VIGILADOS = ("services.presupuestacion", "services.terceros", "services.productos")

_PREFIJO_PCP = "services.pcp"


def _modulos_importados(archivo: Path) -> list[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    modulos: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos.append(nodo.module)
    return modulos


def _es_prefijo_vigilado(modulo: str) -> bool:
    return any(modulo == p or modulo.startswith(p + ".") for p in _PREFIJOS_VIGILADOS)


def _modulo_permitido_desde_pcp(modulo: str) -> bool:
    if modulo in _PERMITIDOS_EXACTOS:
        return True
    if any(modulo == p or modulo.startswith(p + ".") for p in _PERMITIDOS_PREFIJO):
        # "nunca un repository ajeno" aplica incluso dentro de un prefijo
        # amplio como services.productos.
        return ".repository" not in modulo
    return False


def _ofensores_import_desde_pcp() -> list[str]:
    ofensores = []
    for archivo in PCP_ROOT.rglob("*.py"):
        for modulo in _modulos_importados(archivo):
            if _es_prefijo_vigilado(modulo) and not _modulo_permitido_desde_pcp(modulo):
                ofensores.append(f"{archivo.relative_to(REPO_ROOT)} -> {modulo}")
    return ofensores


def _ofensores_import_hacia_pcp() -> list[str]:
    ofensores = []
    for archivo in PRESUPUESTACION_ROOT.rglob("*.py"):
        if archivo.name == "main.py":
            continue
        for modulo in _modulos_importados(archivo):
            if modulo == _PREFIJO_PCP or modulo.startswith(_PREFIJO_PCP + "."):
                ofensores.append(f"{archivo.relative_to(REPO_ROOT)} -> {modulo}")
    return ofensores


def test_pcp_solo_importa_capas_publicas_permitidas():
    assert PCP_ROOT.is_dir(), (
        "services/pcp/ todavia no existe (lo crea la Fase 5 de gestor-pcp, "
        "tasks.md 5.7); este guard queda RED hasta entonces por diseno (D1)."
    )
    ofensores = _ofensores_import_desde_pcp()
    assert not ofensores, (
        f"Import prohibido desde services/pcp/**: {ofensores} "
        "(D1: services/pcp/** solo puede importar "
        "services.presupuestacion.pricing.service, "
        "services.presupuestacion.notificaciones.service, services.terceros.api "
        "y services.productos -- nunca un repository ajeno)."
    )


def test_presupuestacion_solo_importa_pcp_desde_main():
    assert PCP_ROOT.is_dir(), (
        "services/pcp/ todavia no existe (lo crea la Fase 5 de gestor-pcp, "
        "tasks.md 5.7); este guard queda RED hasta entonces por diseno (D1)."
    )
    ofensores = _ofensores_import_hacia_pcp()
    assert not ofensores, (
        f"Import prohibido de services.pcp fuera de main.py: {ofensores} "
        "(D1: services/presupuestacion/** solo importa services.pcp en "
        "main.py, para montar el router)."
    )
