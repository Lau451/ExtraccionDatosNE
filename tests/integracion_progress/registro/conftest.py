"""Repository falso en memoria para los tests del registro de archivos.

El service se prueba contra este doble: reproduce el UNIQUE (drogueria_id, sentido,
tipo, sha256), el filtro por droguería de las escrituras y los CAS por `estado`,
`intentos` y `updated_at`. El CAS real de `reclamar` contra Postgres lo prueba
test_repository.py (integración contra TEST).
"""

import uuid
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from postgrest.exceptions import APIError

from services.integracion_progress.registro import repository as repo


# Funciones de `repository` que reemplaza el doble (los fixtures las parchean todas).
METODOS_REPOSITORIO = (
    "buscar_por_contenido",
    "buscar_por_id",
    "insertar",
    "actualizar",
    "reclamar",
    "listar",
)


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

    def _fila_del_tenant(self, drogueria_id, registro_id):
        fila = self.filas.get(registro_id)
        return fila if fila is not None and fila["drogueria_id"] == drogueria_id else None

    def buscar_por_id(self, client, *, drogueria_id, registro_id):
        fila = self._fila_del_tenant(drogueria_id, registro_id)
        return deepcopy(fila) if fila else None

    def insertar(self, client, fila):
        if self.antes_de_insertar:
            hook, self.antes_de_insertar = self.antes_de_insertar, None
            hook()
        if any(self._clave(f) == self._clave(fila) for f in self.filas.values()):
            raise APIError({"code": "23505", "message": "duplicate key uq_parch_contenido"})
        self.inserts.append(deepcopy(fila))
        return self.sembrar(**fila)

    def actualizar(
        self,
        client,
        *,
        drogueria_id,
        registro_id,
        campos,
        estado_esperado=None,
        intentos_esperados=None,
    ):
        if self.antes_de_actualizar:
            hook, self.antes_de_actualizar = self.antes_de_actualizar, None
            hook()
        fila = self._fila_del_tenant(drogueria_id, registro_id)
        if fila is None:
            return None
        if estado_esperado is not None and fila["estado"] != estado_esperado:
            return None
        if intentos_esperados is not None and fila["intentos"] != intentos_esperados:
            return None
        self.updates.append((registro_id, deepcopy(campos)))
        fila.update(deepcopy(campos))
        return deepcopy(fila)

    def reclamar(
        self, client, *, drogueria_id, registro_id, estado_esperado, updated_at_esperado
    ):
        if self.antes_de_actualizar:
            hook, self.antes_de_actualizar = self.antes_de_actualizar, None
            hook()
        fila = self._fila_del_tenant(drogueria_id, registro_id)
        if (
            fila is None
            or fila["estado"] != estado_esperado
            or datetime.fromisoformat(fila["updated_at"]) != updated_at_esperado
        ):
            return None
        campos = {"estado": "recibido"}
        self.updates.append((registro_id, deepcopy(campos)))
        # El trigger trg_progress_archivos_updated_at renueva updated_at.
        fila.update(campos, updated_at=datetime.now(timezone.utc).isoformat())
        return deepcopy(fila)

    def listar(self, client, **kwargs):
        self.listar_kwargs = kwargs
        return [deepcopy(f) for f in self.filas.values()]


@pytest.fixture
def repo_falso(monkeypatch):
    falso = RepositorioFalso()
    for nombre in METODOS_REPOSITORIO:
        monkeypatch.setattr(repo, nombre, getattr(falso, nombre))
    return falso
