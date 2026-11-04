"""Endpoints de integracion_progress (odd/tasks/integracion-progress.md S3, S4, S5).

- POST /integracion-progress/presupuestos: carga manual del archivo de presupuestos
  tal como lo exporta Progress (multipart). Corre el mismo pipeline que la recepción
  automática desde la carpeta. Solo admin, mismo rol-set que
  POST /pcp/imports/presupuestos-legacy (ROLES_IMPORT_PRESUPUESTOS_LEGACY de PCP).
- GET /integracion-progress/archivos: registro de archivos del tenant. Lee con el
  user client para que aplique la política parch_sel (0043).
"""

import ntpath

from fastapi import APIRouter, Depends, File, Query, UploadFile
from supabase import Client

from services.integracion_progress.models import RecepcionPresupuestosOut
from services.integracion_progress.recepcion import service as recepcion
from services.integracion_progress.registro import service as registro
from services.integracion_progress.registro.models import (
    EstadoArchivo,
    RegistroArchivo,
    Sentido,
)
from services.pcp.api import ROLES_IMPORT_PRESUPUESTOS_LEGACY
from services.shared.auth import UsuarioPerfil, require_roles
from services.shared.database import get_service_client, get_user_client
from services.shared.exceptions import ForbiddenError

router = APIRouter()

# Mismos roles que la política de lectura parch_sel de progress_archivos (0043, L7).
_ROLES_LECTURA = ("superadmin", "admin", "gerencia", "compras", "lider_comercial", "comercial")


def _drogueria(usuario: UsuarioPerfil) -> str:
    if usuario.drogueria_id is None:
        raise ForbiddenError("El usuario no tiene una droguería asignada")
    return usuario.drogueria_id


@router.post("/integracion-progress/presupuestos", response_model=RecepcionPresupuestosOut)
def recibir_presupuestos_endpoint(
    archivo: UploadFile = File(...),
    usuario: UsuarioPerfil = Depends(require_roles(*ROLES_IMPORT_PRESUPUESTOS_LEGACY)),
) -> RecepcionPresupuestosOut:
    resultado = recepcion.recibir_archivo(
        get_service_client(),
        drogueria_id=_drogueria(usuario),
        tipo="presupuestos",
        # Algunos navegadores mandan la ruta completa (C:\fakepath\...).
        nombre_archivo=ntpath.basename(archivo.filename or ""),
        contenido=archivo.file.read(),
        origen="manual",
        usuario_id=usuario.id,
    )
    return RecepcionPresupuestosOut(
        estado=resultado.estado,
        registro_id=resultado.registro.id,
        nombre_archivo=resultado.registro.nombre_archivo,
        procesado_at=resultado.registro.procesado_at,
        errores=resultado.errores,
        resultados=resultado.resultados,
    )


@router.get("/integracion-progress/archivos", response_model=list[RegistroArchivo])
def listar_archivos_endpoint(
    sentido: Sentido | None = None,
    estado: EstadoArchivo | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    usuario: UsuarioPerfil = Depends(require_roles(*_ROLES_LECTURA)),
    user_client: Client = Depends(get_user_client),
) -> list[RegistroArchivo]:
    return registro.listar(
        user_client,
        drogueria_id=_drogueria(usuario),
        sentido=sentido,
        estado=estado,
        limit=limit,
        offset=offset,
    )
