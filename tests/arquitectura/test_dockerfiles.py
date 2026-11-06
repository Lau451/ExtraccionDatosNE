"""Every `services.<package>` a service imports is copied into its Docker image.
The images copy only the packages listed in their Dockerfile, so a missing COPY makes
the container fail at startup with ModuleNotFoundError."""
import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
_COPY = re.compile(r"^COPY\s+services/([A-Za-z0-9_]+)\s", re.MULTILINE)


def _paquetes_copiados(dockerfile: Path) -> set[str]:
    return set(_COPY.findall(dockerfile.read_text(encoding="utf-8")))


def _paquetes_importados(paquete: str) -> set[str]:
    importados: set[str] = set()
    for archivo in (RAIZ / "services" / paquete).rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                nombres = [nodo.module]
            else:
                continue
            for nombre in nombres:
                partes = nombre.split(".")
                if partes[0] == "services" and len(partes) > 1:
                    importados.add(partes[1])
    return importados


@pytest.mark.parametrize("servicio", ["presupuestacion", "extraccion"])
def test_image_copies_every_imported_services_package(servicio):
    copiados = _paquetes_copiados(RAIZ / "services" / servicio / "Dockerfile")
    pendientes = set(copiados)
    alcanzados: set[str] = set()
    while pendientes:
        paquete = pendientes.pop()
        alcanzados.add(paquete)
        pendientes |= _paquetes_importados(paquete) - alcanzados

    assert alcanzados - copiados == set()
