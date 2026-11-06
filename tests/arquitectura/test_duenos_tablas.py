"""Only the owner module writes its tables (docs/arquitectura/README.md P1, stage 2).

The comercial tables are written only from `services/presupuestacion/` (the future
`comercial` module, D-ARQ-006). Other modules may read them; a write through the
Supabase client (`.table("<tabla>")` followed by insert/update/upsert/delete in the
same call chain) anywhere else in `services/` fails this test. `scripts/` and `tests/`
seed TEST data on purpose and are not modules."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

_TABLAS_COMERCIAL = (
    "procesos_comerciales",
    "items_proceso",
    "presupuestos",
    "presupuesto_items",
    "presupuesto_legacy_map",
)
_DUENO_COMERCIAL = RAIZ / "services" / "presupuestacion"

# `.table("x")` / `.from_("x")` up to the end of its call chain (`.execute()`), across lines.
_CADENA = re.compile(r"\.(?:table|from_)\(\s*[\"']([a-z_]+)[\"']\s*\)(.*?)\.execute\(\)", re.DOTALL)
_ESCRITURA = re.compile(r"\.(insert|update|upsert|delete)\(")


def _escrituras(archivo: Path, tablas: tuple[str, ...], raiz: Path = RAIZ) -> list[str]:
    texto = archivo.read_text(encoding="utf-8")
    encontradas = []
    for cadena in _CADENA.finditer(texto):
        tabla, resto = cadena.group(1), cadena.group(2)
        if tabla in tablas and _ESCRITURA.search(resto):
            linea = texto.count("\n", 0, cadena.start()) + 1
            encontradas.append(f"{archivo.relative_to(raiz).as_posix()}:{linea} {tabla}")
    return encontradas


def _archivos_fuera_del_dueno(dueno: Path) -> list[Path]:
    return [
        archivo
        for archivo in (RAIZ / "services").rglob("*.py")
        if dueno not in archivo.parents
    ]


def test_detects_a_write_split_across_lines_and_ignores_reads(tmp_path):
    archivo = tmp_path / "modulo.py"
    archivo.write_text(
        "\n".join(
            [
                'client.table("presupuestos")',
                '    .update({"estado": "x"})',
                '    .eq("id", 1).execute()',
                'client.table("presupuestos").select("id").execute()',
                'client.table("pcp").insert({}).execute()',
            ]
        ),
        encoding="utf-8",
    )

    assert _escrituras(archivo, _TABLAS_COMERCIAL, raiz=tmp_path) == ["modulo.py:1 presupuestos"]


def test_only_comercial_writes_its_tables():
    escrituras = [
        escritura
        for archivo in _archivos_fuera_del_dueno(_DUENO_COMERCIAL)
        for escritura in _escrituras(archivo, _TABLAS_COMERCIAL)
    ]

    assert escrituras == []


def test_detects_a_write_on_a_stored_query_and_through_from_(tmp_path):
    archivo = tmp_path / "m.py"
    archivo.write_text(
        't = client.table("items_proceso")\n'
        't.delete().eq("id", 1).execute()\n'
        'client.from_("presupuestos").insert({}).execute()\n',
        encoding="utf-8",
    )

    assert _escrituras(archivo, _TABLAS_COMERCIAL, raiz=tmp_path) == [
        "m.py:1 items_proceso",
        "m.py:3 presupuestos",
    ]


def test_ignores_reads_of_comercial_tables_and_writes_to_other_tables(tmp_path):
    archivo = tmp_path / "m.py"
    archivo.write_text(
        'client.table("presupuestos").select("*").execute()\n'
        'client.table("pcp").delete().execute()\n',
        encoding="utf-8",
    )

    assert _escrituras(archivo, _TABLAS_COMERCIAL, raiz=tmp_path) == []
