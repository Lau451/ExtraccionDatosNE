"""Guard estructural de la migración 0043 (progress_archivos): el UNIQUE que impide
procesar dos veces el mismo contenido y los valores de los CHECK que el service
asume. Barato: lee el SQL, no toca la BD."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRACION = REPO_ROOT / "supabase" / "migrations" / "0043_progress_archivos.sql"
DOWN = REPO_ROOT / "supabase" / "migrations" / "0043_progress_archivos.down.sql"


@pytest.fixture(scope="module")
def sql():
    return re.sub(r"\s+", " ", MIGRACION.read_text(encoding="utf-8"))


def test_unique_por_contenido(sql):
    assert (
        "CONSTRAINT uq_parch_contenido UNIQUE (drogueria_id, sentido, tipo, sha256)" in sql
    )


@pytest.mark.parametrize(
    ("constraint", "fragmento"),
    [
        ("ck_parch_sentido", "CHECK (sentido IN ('entrada', 'salida'))"),
        ("ck_parch_origen", "origen IN ('carpeta', 'manual')"),
        ("ck_parch_estado", "CHECK (estado IN ('recibido', 'procesado', 'error'))"),
    ],
)
def test_checks(sql, constraint, fragmento):
    assert f"CONSTRAINT {constraint} " in sql
    inicio = sql.index(f"CONSTRAINT {constraint} ")
    assert fragmento in sql[inicio : inicio + 200]


def test_estado_por_defecto_y_rls(sql):
    assert "estado TEXT NOT NULL DEFAULT 'recibido'" in sql
    assert "ALTER TABLE progress_archivos ENABLE ROW LEVEL SECURITY" in sql
    assert "GRANT SELECT ON progress_archivos TO authenticated" in sql
    # Escritura solo vía service_role: sin políticas INSERT/UPDATE.
    assert "FOR INSERT" not in sql
    assert "FOR UPDATE" not in sql
    assert "NOTIFY pgrst, 'reload schema'" in sql


def test_down_borra_la_tabla():
    down = DOWN.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS progress_archivos" in down
