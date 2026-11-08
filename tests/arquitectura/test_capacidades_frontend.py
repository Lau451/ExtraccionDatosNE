"""Etapa 5 (X-ARQ-005, odd/tasks/roles-capacidades.md S7): el frontend nombra las
mismas capacidades que services/shared/permisos.py `MATRIZ`.

- `CAPACIDADES` en frontend/src/features/auth/capacidades.ts tiene exactamente las
  claves de la matriz.
- Todo `puede('...')` / `requireCapacidad('...')` bajo frontend/src usa una
  capacidad que existe en la matriz.
- La copia de la matriz que usan los tests del frontend (src/test/capacidades.ts)
  asigna los mismos roles que la matriz.
"""

import re
from pathlib import Path

from services.shared.permisos import MATRIZ

FRONTEND_SRC = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
CAPACIDADES_TS = FRONTEND_SRC / "features" / "auth" / "capacidades.ts"
ESPEJO_TS = FRONTEND_SRC / "test" / "capacidades.ts"

_LITERAL = re.compile(r"'([^']+)'")
_USO = re.compile(r"\b(?:puede|requireCapacidad)\(\s*'([^']+)'\s*\)")
_FILA_ESPEJO = re.compile(r"^\s*'([^']+)':\s*\[([^\]]*)\],", re.MULTILINE)


def _capacidades_declaradas() -> list[str]:
    texto = CAPACIDADES_TS.read_text(encoding="utf-8")
    cuerpo = re.search(r"export const CAPACIDADES = \[(.*?)\] as const", texto, re.DOTALL)
    assert cuerpo, "no se encontró `export const CAPACIDADES = [...] as const`"
    return _LITERAL.findall(cuerpo.group(1))


def test_capacidades_del_frontend_son_las_de_la_matriz():
    declaradas = _capacidades_declaradas()
    assert len(declaradas) == len(set(declaradas)), "capacidades repetidas en capacidades.ts"
    assert set(declaradas) == set(MATRIZ)


def test_usos_en_el_frontend_existen_en_la_matriz():
    desconocidas: list[str] = []
    usos = 0
    for archivo in sorted(FRONTEND_SRC.rglob("*.ts*")):
        for capacidad in _USO.findall(archivo.read_text(encoding="utf-8")):
            usos += 1
            if capacidad not in MATRIZ:
                desconocidas.append(f"{archivo.relative_to(FRONTEND_SRC).as_posix()}: {capacidad}")
    assert usos > 0, "no se encontró ningún puede()/requireCapacidad() (¿cambió el patrón?)"
    assert desconocidas == []


def test_espejo_de_tests_asigna_los_mismos_roles_que_la_matriz():
    espejo = {
        capacidad: frozenset(_LITERAL.findall(roles))
        for capacidad, roles in _FILA_ESPEJO.findall(ESPEJO_TS.read_text(encoding="utf-8"))
    }
    assert espejo == dict(MATRIZ)
