"""Guard de dueño único de la integración con Progress
(docs/arquitectura/integracion-progress.md; odd/tasks/integracion-progress.md, S2).

- `services/integracion_progress/**` solo importa `services.shared` y las fachadas
  públicas a las que entrega lotes (`_FACHADAS_DESTINO`).
- Fuera de `services/integracion_progress/`, nadie importa sus internos: solo
  `services.integracion_progress.api`. La única excepción es el montaje del router
  en `services/presupuestacion/main.py`.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROOT = REPO_ROOT / "services" / "integracion_progress"
# Los propios tests del módulo pueden probar sus internos.
TESTS_ROOT = REPO_ROOT / "tests" / "integracion_progress"
_RAICES_CONSUMIDORAS = ("services", "tests", "scripts")

_PREFIJO = "services.integracion_progress"
_FACHADA = f"{_PREFIJO}.api"
_ROUTER = f"{_PREFIJO}.router"
_MAIN_PRESUPUESTACION = REPO_ROOT / "services" / "presupuestacion" / "main.py"

# Fachadas públicas de los módulos dueños a los que integracion_progress entrega
# lotes. `services.presupuestacion.presupuestos.api` (`comercial`) recibe el archivo
# de presupuestos (S5; odd/tasks/procesos-comerciales-dueno.md S1).
_FACHADAS_DESTINO: set[str] = {"services.presupuestacion.presupuestos.api"}


def _paquete(archivo: Path) -> str:
    """Paquete al que pertenece `archivo` (contra el que se resuelven sus imports
    relativos), a partir de su ruta en el repo."""
    partes = archivo.relative_to(REPO_ROOT).with_suffix("").parts
    return ".".join(partes[:-1])


def _absoluto(nodo: ast.ImportFrom, paquete: str) -> str:
    if nodo.level == 0:
        return nodo.module or ""
    base = paquete.split(".")
    base = base[: len(base) - (nodo.level - 1)]
    return ".".join(base + ([nodo.module] if nodo.module else []))


def _modulos_importados(archivo: Path, paquete: str | None = None) -> list[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    paquete = _paquete(archivo) if paquete is None else paquete
    modulos: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            modulo = _absoluto(nodo, paquete)
            if modulo == _PREFIJO or (nodo.level and not nodo.module):
                # `from services.integracion_progress import api` o `from . import api`
                # importan el submódulo `api`.
                modulos.extend(f"{modulo}.{alias.name}" for alias in nodo.names)
            elif modulo:
                modulos.append(modulo)
    return modulos


def _pertenece(modulo: str, prefijo: str) -> bool:
    return modulo == prefijo or modulo.startswith(prefijo + ".")


def _permitido_desde_adentro(modulo: str) -> bool:
    if not _pertenece(modulo, "services"):
        return True
    return (
        _pertenece(modulo, "services.shared")
        or _pertenece(modulo, _PREFIJO)
        or modulo in _FACHADAS_DESTINO
    )


def _permitido_desde_afuera(archivo: Path, modulo: str) -> bool:
    if not _pertenece(modulo, _PREFIJO) or modulo == _FACHADA:
        return True
    return archivo == _MAIN_PRESUPUESTACION and modulo == _ROUTER


def _archivos_de_afuera():
    for raiz in _RAICES_CONSUMIDORAS:
        for archivo in (REPO_ROOT / raiz).rglob("*.py"):
            if archivo.is_relative_to(ROOT) or archivo.is_relative_to(TESTS_ROOT):
                continue
            yield archivo


def test_integracion_progress_solo_importa_shared_y_fachadas_destino():
    assert ROOT.is_dir(), "services/integracion_progress/ no existe"
    ofensores = [
        f"{archivo.relative_to(REPO_ROOT)} -> {modulo}"
        for archivo in ROOT.rglob("*.py")
        for modulo in _modulos_importados(archivo)
        if not _permitido_desde_adentro(modulo)
    ]
    assert not ofensores, (
        "services/integracion_progress/** solo puede importar services.shared y "
        f"las fachadas destino {sorted(_FACHADAS_DESTINO)}: {ofensores}"
    )


def test_los_imports_relativos_se_resuelven_contra_el_paquete(tmp_path):
    # R3-001 (T1): `from ..pcp import x` y `from . import y` no se veían como
    # `services.*` y pasaban el guard sin control.
    archivo = tmp_path / "modulo.py"
    archivo.write_text(
        "from . import service\n"
        "from .carpeta import escanear_carpeta\n"
        "from ...pcp.imports import service as pcp_service\n"
        "from services.shared import config\n",
        encoding="utf-8",
    )

    modulos = _modulos_importados(archivo, paquete=f"{_PREFIJO}.recepcion")

    assert modulos == [
        f"{_PREFIJO}.recepcion.service",
        f"{_PREFIJO}.recepcion.carpeta",
        "services.pcp.imports",
        "services.shared",
    ]
    assert not _permitido_desde_adentro("services.pcp.imports")


def test_de_los_destinos_solo_se_permite_la_fachada():
    assert _permitido_desde_adentro("services.presupuestacion.presupuestos.api")
    for interno in (
        "services.presupuestacion.presupuestos.importacion_legacy",
        "services.presupuestacion.presupuestos.importacion_legacy_models",
        "services.pcp.api",
    ):
        assert not _permitido_desde_adentro(interno), interno


def test_el_paquete_de_un_archivo_sale_de_su_ruta():
    assert _paquete(ROOT / "recepcion" / "carpeta.py") == f"{_PREFIJO}.recepcion"
    assert _paquete(ROOT / "recepcion" / "__init__.py") == f"{_PREFIJO}.recepcion"


def test_afuera_solo_se_importa_la_fachada():
    assert ROOT.is_dir(), "services/integracion_progress/ no existe"
    ofensores = [
        f"{archivo.relative_to(REPO_ROOT)} -> {modulo}"
        for archivo in _archivos_de_afuera()
        for modulo in _modulos_importados(archivo)
        if not _permitido_desde_afuera(archivo, modulo)
    ]
    assert not ofensores, (
        f"Fuera de services/integracion_progress/ solo se importa {_FACHADA} "
        f"(y {_ROUTER} desde services/presupuestacion/main.py): {ofensores}"
    )
