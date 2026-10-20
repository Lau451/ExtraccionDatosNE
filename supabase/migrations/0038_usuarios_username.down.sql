-- Down migration para 0038: quita usuarios.username (con su índice único y su
-- CHECK de formato) y usuarios.debe_cambiar_password.

DROP INDEX IF EXISTS ux_usuarios_username_lower;
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS ck_usuarios_username_formato;
ALTER TABLE usuarios DROP COLUMN IF EXISTS username;
ALTER TABLE usuarios DROP COLUMN IF EXISTS debe_cambiar_password;
