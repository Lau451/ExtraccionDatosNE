"""Repository falso en memoria para los tests del registro de archivos.

La tabla `progress_archivos` (migración 0043) todavía no está aplicada en la BD de
test, así que el service se prueba contra este doble: reproduce el UNIQUE
(drogueria_id, sentido, tipo, sha256) y el CAS por `intentos` de `actualizar`.
"""

import uuid
from copy import deepcopy

import pytest
from postgrest.exceptions import APIError

from services.integracion_progress.registro import repository as repo


class RepositorioFalso:
    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.inserts: list[dict] = []
        self.updates: list[tuple[str, dict]] = []
        # Hooks para simular carreras: se ejecutan una vez antes de la operación.
        self.antes_de_insertar = None
        self.antes_de_actualizar = None

    def _clave(self, fila):
        return (fila["drogueria_id"], fila["sentido"], fila["tipo"], fila["sha256"])

    def sembrar(self, **campos):
        fila = {
            "id": str(uuid.uuid4()),
            "drogueria_id": "drog-1",
            "sentido": "entrada",
            "tipo": "presupuestos",
            "nombre_archivo": "PRESUPUESTOS_20261104120000.csv",
            "sha256": "0" * 64,
            "origen": "carpeta",
            "estado": "recibido",
            "filas": None,
            "errores": None,
            "usuario_id": "usuario-sistema",
            "intentos": 0,
            "procesado_at": None,
            "created_at": "2026-11-04T12:00:00+00:00",
            "updated_at": "2026-11-04T12:00:00+00:00",
        }
        fila.update(campos)
        self.filas[fila["id"]] = fila
        return deepcopy(fila)

    def buscar_por_contenido(self, client, *, drogueria_id, sentido, tipo, sha256):
        for fila in self.filas.values():
            if self._clave(fila) == (drogueria_id, sentido, tipo, sha256):
                return deepcopy(fila)
        return None

    def buscar_por_id(self, client, *, registro_id):
        fila = self.filas.get(registro_id)
        return deepcopy(fila) if fila else None

    def insertar(self, client, fila):
        if self.antes_de_insertar:
            hook, self.antes_de_insertar = self.antes_de_insertar, None
            hook()
        if any(self._clave(f) == self._clave(fila) for f in self.filas.values()):
            raise APIError({"code": "23505", "message": "duplicate key uq_parch_contenido"})
        self.inserts.append(deepcopy(fila))
        return self.sembrar(**fila)

    def actualizar(self, client, *, registro_id, campos, intentos_esperados=None):
        if self.antes_de_actualizar:
            hook, self.antes_de_actualizar = self.antes_de_actualizar, None
            hook()
        fila = self.filas.get(registro_id)
        if fila is None:
            return None
        if intentos_esperados is not None and fila["intentos"] != intentos_esperados:
            return None
        self.updates.append((registro_id, deepcopy(campos)))
        fila.update(deepcopy(campos))
        return deepcopy(fila)

    def listar(self, client, **kwargs):
        self.listar_kwargs = kwargs
        return [deepcopy(f) for f in self.filas.values()]


@pytest.fixture
def repo_falso(monkeypatch):
    falso = RepositorioFalso()
    for nombre in ("buscar_por_contenido", "buscar_por_id", "insertar", "actualizar", "listar"):
        monkeypatch.setattr(repo, nombre, getattr(falso, nombre))
    return falso
