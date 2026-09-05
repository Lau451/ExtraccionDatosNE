"""Guard D5 (openspec/changes/terceros-modelo/design.md): services/terceros/
es una fachada unidireccional. services/presupuestacion/** puede importar
services.terceros.api, pero ningún módulo bajo services/terceros/** puede
importar services.presupuestacion.**, o se formaría un ciclo.

Este test es intencionalmente RED hasta que la Fase 3 cree services/terceros/
(tarea 2.8 de tasks.md): sin ese paquete, el guard no tiene nada que
recorrer, así que en vez de pasar en falso (0 archivos = 0 ofensores), la
aserción exige que el directorio exista. Se re-verifica en GREEN en la
Fase 7.5, una vez que todos los subdominios existen.
"""

import ast
from pathlib import Path

TERCEROS_ROOT = Path(__file__).resolve().parent.parent.parent / "services" / "terceros"

_PREFIJO_PROHIBIDO = "services.presupuestacion"


def _importa_presupuestacion(archivo: Path) -> bool:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            if any(alias.name.startswith(_PREFIJO_PROHIBIDO) for alias in nodo.names):
                return True
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module and nodo.module.startswith(_PREFIJO_PROHIBIDO):
                return True
    return False


def test_terceros_nunca_importa_presupuestacion():
    assert TERCEROS_ROOT.is_dir(), (
        "services/terceros/ todavia no existe (lo crea la Fase 3 de "
        "terceros-modelo); este guard queda RED hasta entonces por diseno (D5)."
    )
    ofensores = [
        str(archivo.relative_to(TERCEROS_ROOT.parent.parent))
        for archivo in TERCEROS_ROOT.rglob("*.py")
        if _importa_presupuestacion(archivo)
    ]
    assert not ofensores, (
        f"Import prohibido de services.presupuestacion en: {ofensores} "
        "(D5: services/terceros/ nunca importa services.presupuestacion, "
        "solo al reves)."
    )
