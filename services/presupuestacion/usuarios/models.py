from typing import Literal

from pydantic import BaseModel

Rol = Literal["superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras"]


class UsuarioCreate(BaseModel):
    email: str
    nombre: str
    apellido: str
    rol: Rol
    drogueria_id: str | None = None


class UsuarioRolUpdate(BaseModel):
    rol: Rol


class UsuarioActivoUpdate(BaseModel):
    activo: bool


class UsuarioPerfilUpdate(BaseModel):
    nombre: str | None = None
    apellido: str | None = None


class UsuarioOut(BaseModel):
    id: str
    drogueria_id: str | None
    rol: str
    nombre: str
    apellido: str | None
    es_sistema: bool
    activo: bool
