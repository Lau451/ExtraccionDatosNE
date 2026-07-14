"""
Tests para _limpiar_cantidad: la columna 'cantidad' debe ser entero,
ignorando todo lo que va después de la coma.
"""

import pytest
from services.extraccion.robot import _limpiar_cantidad


def csv(*filas: str) -> str:
    return "\n".join(["item;cantidad;descripcion;origen", *filas])


@pytest.mark.parametrize("entrada,esperado", [
    # Casos con coma decimal
    ("1;1,5;Producto A;CLI",   "1;1;Producto A;CLI"),
    ("2;10,00;Producto B;CLI", "2;10;Producto B;CLI"),
    ("3;100,75;Producto C;CLI","3;100;Producto C;CLI"),
    # Punto de miles — se elimina
    ("1;1.500;Producto A;CLI",    "1;1500;Producto A;CLI"),
    ("2;2.000.000;Producto B;CLI","2;2000000;Producto B;CLI"),
    # Punto de miles + coma decimal — eliminar punto y truncar en coma
    ("3;1.500,75;Producto C;CLI", "3;1500;Producto C;CLI"),
    # Sin coma ni punto — no debe tocarse
    ("4;5;Producto D;CLI",     "4;5;Producto D;CLI"),
    ("5;0;Producto E;CLI",     "5;0;Producto E;CLI"),
    # Vacío — no debe romperse
    ("6;;Producto F;CLI",      "6;;Producto F;CLI"),
])
def test_limpia_cantidad_individual(entrada: str, esperado: str):
    resultado = _limpiar_cantidad(csv(entrada))
    lineas = resultado.split("\n")
    assert lineas[1] == esperado


def test_limpia_multiples_filas():
    entrada = csv(
        "1;2,5;Prod A;CLI",
        "2;10;Prod B;CLI",
        "3;1,999;Prod C;CLI",
    )
    resultado = _limpiar_cantidad(entrada)
    lineas = resultado.split("\n")
    assert lineas[1] == "1;2;Prod A;CLI"
    assert lineas[2] == "2;10;Prod B;CLI"
    assert lineas[3] == "3;1;Prod C;CLI"


def test_sin_columna_cantidad_no_falla():
    sin_cantidad = "item;descripcion;origen\n1;Producto;CLI\n"
    resultado = _limpiar_cantidad(sin_cantidad)
    assert resultado == sin_cantidad


def test_csv_vacio_no_falla():
    assert _limpiar_cantidad("") == ""
