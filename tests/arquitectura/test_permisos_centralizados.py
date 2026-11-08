"""Etapa 5 (X-ARQ-005, odd/tasks/roles-capacidades.md S6): los módulos autorizan
por capacidad (`require_capacidad`, services/shared/permisos.py), nunca con su
propia tupla de roles.

- Ningún archivo fuera de `services/shared/` usa `require_roles`.
- Ningún archivo fuera de `services/shared/` define a nivel de módulo una tupla,
  lista o set de nombres de rol, salvo las reglas que no son permisos por acción
  (`_FUERA_DE_LA_MATRIZ`).
"""

import ast
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parent.parent.parent / "services"

_ROLES = {"superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras", "sistema"}

# Reglas con roles que no son "quién puede hacer esta acción" (S5).
_FUERA_DE_LA_MATRIZ = {
    # Jerarquía de usuarios: a qué roles puede asignar gerencia (roles-permisos-matriz S7).
    ("presupuestacion/usuarios/service.py", "ROLES_GESTIONABLES_POR_GERENCIA"),
    # Destinatarios de una notificación, no un permiso.
    ("presupuestacion/extraccion/service.py", "_ROLES_NOTIFICACION_REEMPLAZO"),
}


def _es_coleccion_de_roles(valor: ast.expr) -> bool:
    if isinstance(valor, ast.Call) and getattr(valor.func, "id", None) in {"frozenset", "set", "tuple"} and valor.args:
        valor = valor.args[0]
    if not isinstance(valor, (ast.Tuple, ast.List, ast.Set)) or not valor.elts:
        return False
    return all(isinstance(e, ast.Constant) and e.value in _ROLES for e in valor.elts)


def ofensores(raiz: Path) -> list[str]:
    encontrados: list[str] = []
    for archivo in sorted(raiz.rglob("*.py")):
        relativo = archivo.relative_to(raiz).as_posix()
        if relativo.startswith("shared/"):
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Name) and nodo.id == "require_roles":
                encontrados.append(f"{relativo}:{nodo.lineno} usa require_roles")
            elif isinstance(nodo, ast.alias) and nodo.name == "require_roles":
                encontrados.append(f"{relativo} importa require_roles")
        for nodo in arbol.body:
            if isinstance(nodo, (ast.Assign, ast.AnnAssign)) and nodo.value is not None:
                destinos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                for destino in destinos:
                    if (
                        isinstance(destino, ast.Name)
                        and _es_coleccion_de_roles(nodo.value)
                        and (relativo, destino.id) not in _FUERA_DE_LA_MATRIZ
                    ):
                        encontrados.append(f"{relativo}:{nodo.lineno} define la tupla de roles {destino.id}")
    return encontrados


def test_ningun_modulo_autoriza_con_tuplas_de_roles():
    assert ofensores(SERVICES_ROOT) == []


def test_el_guard_detecta_tuplas_y_require_roles(tmp_path):
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "auth.py").write_text("def require_roles(*roles): ...\n", encoding="utf-8")
    (tmp_path / "pcp").mkdir()
    (tmp_path / "pcp" / "router.py").write_text(
        "from services.shared.auth import require_roles\n"
        "_ROLES = ('admin', 'gerencia')\n"
        "OTROS = frozenset({'compras'})\n"
        "NO_ROLES = ('a', 'b')\n"
        "dep = require_roles('admin')\n",
        encoding="utf-8",
    )
    assert ofensores(tmp_path) == [
        "pcp/router.py importa require_roles",
        "pcp/router.py:5 usa require_roles",
        "pcp/router.py:2 define la tupla de roles _ROLES",
        "pcp/router.py:3 define la tupla de roles OTROS",
    ]
