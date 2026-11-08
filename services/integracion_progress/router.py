"""Endpoints de integracion_progress (odd/tasks/integracion-progress.md S3, S4, S5).

- POST /integracion-progress/presupuestos: carga manual del archivo de presupuestos
  tal como lo exporta Progress (multipart). Corre el mismo pipeline que la recepción
  automática desde la carpeta. Solo admin, mismo rol-set que
  POST /pcp/imports/presupuestos-legacy (capacidad `presupuestos.importar_legacy`,
  services/shared/permisos.py).
  Un archivo de más de `TAMANO_MAXIMO_BYTES` se rechaza con 413 sin procesarlo.
  Un duplicado cuyo original terminó en `error` trae en `errores` los del original,
  para que la pantalla no lo confunda con uno que sigue en curso.
- GET /integracion-progress/archivos: registro de archivos del tenant. Lee con el
  user client para que aplique la política parch_sel (0043).
"""

import ntpath

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from supabase import Client

from services.integracion_progress.models import RecepcionPresupuestosOut
from services.integracion_progress.recepcion import service as recepcion
from services.integracion_progress.registro import service as registro
from services.integracion_progress.registro.models import (
    EstadoArchivo,
    RegistroArchivo,
    Sentido,
)
from services.shared.auth import UsuarioPerfil, require_capacidad
from services.shared.database import get_service_client, get_user_client
from services.shared.exceptions import ForbiddenError

router = APIRouter()


# Tope de la carga manual. Un export de presupuestos pesa unos pocos cientos de KB;
# el tope evita leer a memoria un archivo arbitrariamente grande.
TAMANO_MAXIMO_BYTES = 10 * 1024 * 1024
_MENSAJE_DEMASIADO_GRANDE = "El archivo supera el tamaño máximo de 10 MB"


def _leer_con_tope(archivo: UploadFile) -> bytes:
    """Lee a lo sumo un byte más que el tope; si lo supera, 413."""
    contenido = archivo.file.read(TAMANO_MAXIMO_BYTES + 1)
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise HTTPException(status_code=413, detail=_MENSAJE_DEMASIADO_GRANDE)
    return contenido


def _drogueria(usuario: UsuarioPerfil) -> str:
    if usuario.drogueria_id is None:
        raise ForbiddenError("El usuario no tiene una droguería asignada")
    return usuario.drogueria_id


@router.post("/integracion-progress/presupuestos", response_model=RecepcionPresupuestosOut)
def recibir_presupuestos_endpoint(
    archivo: UploadFile = File(...),
    usuario: UsuarioPerfil = Depends(require_capacidad("presupuestos.importar_legacy")),
) -> RecepcionPresupuestosOut:
    drogueria_id = _drogueria(usuario)
    contenido = _leer_con_tope(archivo)
    resultado = recepcion.recibir_archivo(
        get_service_client(),
        drogueria_id=drogueria_id,
        tipo="presupuestos",
        # Algunos navegadores mandan la ruta completa (C:\fakepath\...).
        nombre_archivo=ntpath.basename(archivo.filename or ""),
        contenido=contenido,
        origen="manual",
        usuario_id=usuario.id,
    )
    errores = resultado.errores
    if resultado.estado == "duplicado" and resultado.registro.estado == "error":
        errores = resultado.registro.errores or []
    return RecepcionPresupuestosOut(
        estado=resultado.estado,
        registro_id=resultado.registro.id,
        nombre_archivo=resultado.registro.nombre_archivo,
        procesado_at=resultado.registro.procesado_at,
        errores=errores,
        resultados=resultado.resultados,
    )


@router.get("/integracion-progress/archivos", response_model=list[RegistroArchivo])
def listar_archivos_endpoint(
    sentido: Sentido | None = None,
    estado: EstadoArchivo | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    usuario: UsuarioPerfil = Depends(require_capacidad("integracion_progress.leer")),
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
