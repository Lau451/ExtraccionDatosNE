-- Down migration para 0039: quita el guard de debe_cambiar_password/username.

DROP TRIGGER IF EXISTS trg_usuarios_protege_credenciales ON usuarios;
DROP FUNCTION IF EXISTS trg_usuarios_protege_credenciales();
