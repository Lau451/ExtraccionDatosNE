-- Down migration para 0040: quita el guard de INSERT en usuarios. El guard de
-- UPDATE de 0039 queda como está.

DROP TRIGGER IF EXISTS trg_usuarios_protege_alta ON usuarios;
DROP FUNCTION IF EXISTS trg_usuarios_protege_alta();
