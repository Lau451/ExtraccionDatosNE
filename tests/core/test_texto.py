from services.presupuestacion.core.texto import normalizar_descripcion


def test_normalizar_descripcion_pasa_a_mayusculas():
    assert normalizar_descripcion("ibuprofeno") == "IBUPROFENO"


def test_normalizar_descripcion_saca_tildes():
    assert normalizar_descripcion("solución fisiológica") == "SOLUCION FISIOLOGICA"


def test_normalizar_descripcion_colapsa_espacios():
    assert normalizar_descripcion("gasa   estéril   x10") == "GASA ESTERIL X10"


def test_normalizar_descripcion_saca_puntuacion():
    assert normalizar_descripcion("ibuprofeno 600mg. x30, (blister)") == "IBUPROFENO 600MG X30 BLISTER"


def test_normalizar_descripcion_recorta_bordes():
    assert normalizar_descripcion("  gasa  ") == "GASA"
