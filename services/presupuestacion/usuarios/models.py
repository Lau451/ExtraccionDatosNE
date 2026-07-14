from typing import Literal

from pydantic import BaseModel

Rol = Literal["superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras"]


class UsuarioCreate(BaseModel):
    email: str
    password: str
    nombre: str
    rol: Rol
    drogueria_id: str | None = None


class UsuarioRolUpdate(BaseModel):
    rol: Rol


class UsuarioOut(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    nombre: str
    es_sistema: bool
    activo: bool
