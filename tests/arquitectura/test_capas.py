"""Guards de capas de la arquitectura objetivo (docs/arquitectura/README.md,
principio P3: dependencias hacia abajo, sin ciclos).

- `services/shared/` es la capa plataforma: no importa ningún otro módulo de
  `services/`.
- `services/productos/` y `services/terceros/` son datos maestros: nunca
  importan un módulo de negocio (`services.presupuestacion`, `services.pcp`).

Las reglas propias de cada módulo (por ejemplo, qué capas públicas puede usar
`services/pcp/`) siguen en `tests/<modulo>/test_dependencias.py`.
"""

import ast
from pathlib import Path

import pytest

SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent / "services"

_MODULOS_DE_NEGOCIO = ("services.presupuestacion", "services.pcp")
_MAESTROS = ("productos", "terceros")


def _modulos_importados(archivo: Path) -> list[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    modulos: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos.append(nodo.module)
    return modulos


def _pertenece(modulo: str, prefijo: str) -> bool:
    return modulo == prefijo or modulo.startswith(prefijo + ".")


def _ofensores(raiz: Path, prohibido) -> list[str]:
    assert raiz.is_dir(), f"{raiz} no existe"
    return [
        f"{archivo.relative_to(SERVICES_ROOT.parent)} -> {modulo}"
        for archivo in raiz.rglob("*.py")
        for modulo in _modulos_importados(archivo)
        if prohibido(modulo)
    ]


def test_plataforma_no_importa_otros_modulos():
    ofensores = _ofensores(
        SERVICES_ROOT / "shared",
        lambda m: _pertenece(m, "services") and not _pertenece(m, "services.shared"),
    )
    assert not ofensores, f"services/shared/ solo puede importar services.shared: {ofensores}"


@pytest.mark.parametrize("maestro", _MAESTROS)
def test_maestros_no_importan_modulos_de_negocio(maestro):
    ofensores = _ofensores(
        SERVICES_ROOT / maestro,
        lambda m: any(_pertenece(m, p) for p in _MODULOS_DE_NEGOCIO),
    )
    assert not ofensores, (
        f"services/{maestro}/ es un dato maestro y no puede importar "
        f"{_MODULOS_DE_NEGOCIO}: {ofensores}"
    )
