from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class LoginUsuario(BaseModel):
    id: str


class LoginOut(BaseModel):
    """Campos de la sesión de Supabase que el frontend pasa a `supabase.auth.setSession`."""

    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int | None
    token_type: str
    user: LoginUsuario


class CambiarPasswordIn(BaseModel):
    password_actual: str
    password_nueva: str
