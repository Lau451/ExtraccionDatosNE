-- =============================================================================
-- 0038: login con nombre de usuario y alta por el admin
-- (odd/tasks/login-usuario-alta-admin.md S1/S3/S5).
--
-- Cambios:
--   1. usuarios.debe_cambiar_password: TRUE en cuentas creadas o blanqueadas por
--      un admin; el backend bloquea casi todo hasta que el usuario la cambie.
--      Los usuarios existentes quedan en FALSE (conservan su contraseña).
--   2. usuarios.username: 3-30 caracteres de a-z 0-9 . _ -, en minúsculas,
--      único sin distinguir mayúsculas. Backfill desde la parte local de
--      auth.users.email (S5): minúsculas, se descarta todo carácter fuera del
--      formato, se recorta a 27 para dejar lugar al sufijo y, si choca, se
--      agrega un sufijo numérico desde 2 (jperez, jperez2, ...). Si queda vacío
--      se usa 'usuario'; si queda con 1-2 caracteres se completa con '0'.
--   3. DEFAULT de username: un valor aleatorio válido ('u' + 12 hex) para filas
--      insertadas por fuera del backend (seeds, fixtures de test, SQL manual),
--      que no conocen la columna. El backend siempre manda el username
--      explícito; el admin puede corregirlo después (PATCH /usuarios/{id}/username).
--
-- El email de auth.users no cambia: sigue siendo la identidad interna.
-- Re-ejecutable: el backfill solo toca filas con username NULL.
-- =============================================================================

ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN usuarios.debe_cambiar_password IS
  'TRUE cuando la contraseña la puso un admin (alta o blanqueo): el usuario debe cambiarla antes de usar el sistema.';

ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS username TEXT;

DO $$
DECLARE
  fila      RECORD;
  base      TEXT;
  candidato TEXT;
  sufijo    INT;
BEGIN
  FOR fila IN
    SELECT u.id, au.email
    FROM usuarios u
    LEFT JOIN auth.users au ON au.id = u.id
    WHERE u.username IS NULL
    ORDER BY u.created_at, u.id
  LOOP
    base := regexp_replace(lower(split_part(coalesce(fila.email, ''), '@', 1)), '[^a-z0-9._-]', '', 'g');
    base := left(base, 27);
    IF base = '' THEN
      base := 'usuario';
    ELSIF length(base) < 3 THEN
      base := rpad(base, 3, '0');
    END IF;

    candidato := base;
    sufijo := 2;
    WHILE EXISTS (SELECT 1 FROM usuarios WHERE lower(username) = candidato) LOOP
      candidato := base || sufijo::text;
      sufijo := sufijo + 1;
    END LOOP;

    UPDATE usuarios SET username = candidato WHERE id = fila.id;
  END LOOP;
END
$$;

ALTER TABLE usuarios
  ALTER COLUMN username SET DEFAULT ('u' || left(replace(gen_random_uuid()::text, '-', ''), 12));

ALTER TABLE usuarios
  ALTER COLUMN username SET NOT NULL;

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS ck_usuarios_username_formato;
ALTER TABLE usuarios
  ADD CONSTRAINT ck_usuarios_username_formato CHECK (username ~ '^[a-z0-9._-]{3,30}$');

CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_username_lower ON usuarios (lower(username));

COMMENT ON COLUMN usuarios.username IS
  'Nombre de usuario para el login (S1): 3-30 caracteres de a-z 0-9 . _ -, en minúsculas, único. Lo resuelve el backend al email interno de auth.users.';
