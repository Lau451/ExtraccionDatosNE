"""Parser del CSV de presupuestos de Progress (odd/tasks/integracion-progress.md S5).

Port uno a uno de `frontend/src/features/presupuestos-import/parsearCsvPresupuestos.test.ts`
(el parser del frontend se elimina): mismas columnas, validaciones y mensajes por
línea. Se suman los casos de decodificación de bytes (UTF-8 con/sin BOM, cp1252).
"""

import re
from decimal import Decimal

import pytest

from services.integracion_progress.tipos.presupuestos.parser import (
    parsear,
    parsear_texto,
)

ENCABEZADO = (
    "codigo_cliente;razon_social_cliente;numero_presupuesto;proceso_comercial;"
    "fecha_generacion;renglon;codigo_producto;descripcion_producto;cantidad_producto;"
    "precio_producto;importe_total;subtotal_renglon"
)
ENCABEZADO_COMAS = (
    "codigo_cliente,razon_social_cliente,numero_presupuesto,renglon,"
    "descripcion_producto,cantidad_producto"
)


def _csv(*lineas: str, salto: str = "\n") -> str:
    return salto.join(lineas)


def _un_error(resultado, linea: int, patron: str) -> None:
    assert len(resultado.errores) == 1
    assert resultado.errores[0]["linea"] == linea
    assert re.search(patron, resultado.errores[0]["mensaje"], re.IGNORECASE)


def test_parsea_filas_validas_con_delimitador_punto_y_coma_y_valores_completos():
    resultado = parsear_texto(
        _csv(
            ENCABEZADO,
            "CLI-1;Farmacia Central;PRE-100;1;24/09/2026;1;PROD-1;Amoxicilina 500mg;10,5;125,50;1317,75;99",
        )
    )

    assert resultado.errores == []
    assert resultado.filas == [
        {
            "codigo_cliente": "CLI-1",
            "razon_social_cliente": "Farmacia Central",
            "numero_presupuesto": "PRE-100",
            "proceso_comercial": "1",
            "fecha_generacion": "2026-09-24",
            "renglon": 1,
            "codigo_producto": "PROD-1",
            "descripcion_producto": "Amoxicilina 500mg",
            "cantidad_producto": Decimal("10.5"),
            "precio_producto": Decimal("125.50"),
            "importe_total": Decimal("1317.75"),
        }
    ]


def test_ignora_columnas_desconocidas_como_subtotal_renglon():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;999")
    )

    assert resultado.errores == []
    assert "subtotal_renglon" not in resultado.filas[0]


def test_omite_valores_opcionales_vacios_en_vez_de_enviarlos_como_cadena_vacia():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;")
    )

    assert resultado.errores == []
    assert resultado.filas[0] == {
        "codigo_cliente": "CLI-1",
        "razon_social_cliente": "Farmacia Central",
        "numero_presupuesto": "PRE-100",
        "proceso_comercial": None,
        "fecha_generacion": None,
        "renglon": 1,
        "codigo_producto": None,
        "descripcion_producto": "Amoxicilina 500mg",
        "cantidad_producto": Decimal("10"),
        "precio_producto": None,
        "importe_total": None,
    }


def test_auto_detecta_el_delimitador_coma_cuando_el_encabezado_usa_comas():
    resultado = parsear_texto(
        _csv(ENCABEZADO_COMAS, "CLI-2,Farmacia del Sur,PRE-200,1,Ibuprofeno 400mg,5")
    )

    assert resultado.errores == []
    assert len(resultado.filas) == 1
    assert resultado.filas[0]["numero_presupuesto"] == "PRE-200"


def test_empate_de_delimitadores_usa_coma():
    resultado = parsear_texto(_csv("a;b,c", "1;2,3"))

    # Con `,` gana el empate: "a;b" es una columna, así que faltan las requeridas.
    assert [e["mensaje"] for e in resultado.errores][0] == (
        'Falta la columna requerida "codigo_cliente"'
    )


def test_soporta_campos_entre_comillas_con_el_delimitador_embebido():
    resultado = parsear_texto(
        _csv(
            ENCABEZADO_COMAS,
            'CLI-2,"Farmacia del Sur, Sucursal Norte",PRE-200,1,"Jarabe, sabor frutilla",5',
        )
    )

    assert resultado.errores == []
    assert resultado.filas[0]["razon_social_cliente"] == "Farmacia del Sur, Sucursal Norte"
    assert resultado.filas[0]["descripcion_producto"] == "Jarabe, sabor frutilla"


def test_comillas_dobles_escapadas_dentro_de_un_campo():
    resultado = parsear_texto(
        _csv(ENCABEZADO_COMAS, 'CLI-2,"Farmacia ""El Sol""",PRE-200,1,Jarabe,5')
    )

    assert resultado.errores == []
    assert resultado.filas[0]["razon_social_cliente"] == 'Farmacia "El Sol"'


def test_acepta_crlf_bom_inicial_y_descarta_lineas_finales_vacias():
    csv = "\ufeff" + _csv(
        ENCABEZADO_COMAS, "CLI-3,Farmacia Norte,PRE-300,1,Paracetamol 500mg,20", "", "", salto="\r\n"
    )

    resultado = parsear_texto(csv)

    assert resultado.errores == []
    assert len(resultado.filas) == 1
    assert resultado.filas[0]["codigo_cliente"] == "CLI-3"


def test_acepta_fecha_generacion_en_formato_iso_ademas_de_dd_mm_aaaa():
    resultado = parsear_texto(
        _csv(
            "codigo_cliente,razon_social_cliente,numero_presupuesto,fecha_generacion,renglon,"
            "descripcion_producto,cantidad_producto",
            "CLI-1,Farmacia Central,PRE-100,2026-09-24,1,Amoxicilina 500mg,10",
        )
    )

    assert resultado.errores == []
    assert resultado.filas[0]["fecha_generacion"] == "2026-09-24"


def test_encabezados_en_mayusculas_y_con_espacios_se_normalizan():
    resultado = parsear_texto(
        _csv(
            " CODIGO_CLIENTE ,Razon_Social_Cliente,NUMERO_PRESUPUESTO,Renglon,"
            "Descripcion_Producto,CANTIDAD_PRODUCTO",
            "CLI-1,Farmacia Central,PRE-100,1,Amoxicilina 500mg,10",
        )
    )

    assert resultado.errores == []
    assert resultado.filas[0]["codigo_cliente"] == "CLI-1"


def test_reporta_un_error_por_columna_requerida_faltante_en_el_encabezado_sin_parsear_filas():
    resultado = parsear_texto(
        _csv(
            "codigo_cliente,razon_social_cliente,renglon,descripcion_producto,cantidad_producto",
            "CLI-1,Farmacia Central,1,Amoxicilina 500mg,10",
        )
    )

    assert resultado.filas == []
    assert resultado.errores == [
        {"linea": 1, "mensaje": 'Falta la columna requerida "numero_presupuesto"'}
    ]


def test_reporta_renglon_no_entero_con_el_numero_de_linea_del_csv():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;;;abc;;Amoxicilina 500mg;10;;;")
    )

    assert resultado.filas == []
    assert resultado.errores == [{"linea": 2, "mensaje": "renglón no es un número entero"}]


def test_reporta_cantidad_producto_no_numerica():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;diez;;;")
    )

    assert resultado.filas == []
    assert resultado.errores == [
        {"linea": 2, "mensaje": "cantidad_producto no es numérica (formato esperado: 1250,50)"}
    ]


def _cantidad_de(valor: str):
    return parsear_texto(
        _csv(ENCABEZADO, f"CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;{valor};;;")
    )


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1250,50", Decimal("1250.5")),
        ("1250", Decimal("1250")),
        ("0,75", Decimal("0.75")),
        ("1234567,89", Decimal("1234567.89")),
        ("10", Decimal("10")),
        ("-3,5", Decimal("-3.5")),
    ],
)
def test_formato_numerico_progress_acepta(valor, esperado):
    resultado = _cantidad_de(valor)

    assert resultado.errores == []
    assert resultado.filas[0]["cantidad_producto"] == esperado


@pytest.mark.parametrize(
    "valor", ["1250.50", "1.250", "1.250,50", "1,250.50", "1,2,3", "12,", "١٢"]
)
def test_formato_numerico_progress_rechaza_sin_adivinar(valor):
    # "1,2,3" con `;` como delimitador llega entero a la columna; "١٢" son
    # dígitos arábigos: el formato solo acepta 0-9, igual que `\d` en JS.
    resultado = _cantidad_de(valor)

    assert resultado.filas == []
    _un_error(resultado, 2, "cantidad")


def test_precio_e_importe_invalidos_tienen_su_propio_mensaje():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;1.5;x;")
    )

    assert resultado.errores == [
        {
            "linea": 2,
            "mensaje": "precio_producto no es numérico (formato esperado: 1250,50); "
            "importe_total no es numérico (formato esperado: 1250,50)",
        }
    ]


def test_reporta_codigo_cliente_numero_presupuesto_y_descripcion_producto_faltantes():
    resultado = parsear_texto(_csv(ENCABEZADO, ";Farmacia Central;;;;1;;;10;;;"))

    assert resultado.filas == []
    assert resultado.errores == [
        {
            "linea": 2,
            "mensaje": "falta codigo_cliente; falta numero_presupuesto; falta descripcion_producto",
        }
    ]


def test_acumula_errores_de_varias_filas_conservando_la_numeracion_de_linea_original():
    resultado = parsear_texto(
        _csv(
            ENCABEZADO,
            "CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;",
            "CLI-2;Farmacia Sur;PRE-200;;;abc;;Ibuprofeno 400mg;5;;;",
            "CLI-3;Farmacia Norte;PRE-300;;;3;;Paracetamol 500mg;20;;;",
        )
    )

    assert len(resultado.filas) == 2
    assert [f["codigo_cliente"] for f in resultado.filas] == ["CLI-1", "CLI-3"]
    _un_error(resultado, 3, "renglón")


def test_saltea_filas_intermedias_vacias_sin_error():
    resultado = parsear_texto(
        _csv(
            ENCABEZADO,
            "CLI-1;Farmacia Central;PRE-100;;;1;;Amoxicilina 500mg;10;;;",
            ";;;",
            "CLI-2;Farmacia Sur;PRE-200;;;abc;;Ibuprofeno 400mg;5;;;",
        )
    )

    assert len(resultado.filas) == 1
    _un_error(resultado, 4, "renglón")


def test_reporta_proceso_comercial_invalido_cuando_no_es_1_ni_2():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;9;;1;;Amoxicilina 500mg;10;;;")
    )

    assert resultado.filas == []
    assert resultado.errores == [{"linea": 2, "mensaje": "proceso_comercial debe ser 1 o 2"}]


def test_el_archivo_vacio_reporta_un_unico_error_de_encabezado():
    resultado = parsear_texto("")

    assert resultado.filas == []
    assert resultado.errores == [{"linea": 1, "mensaje": "El archivo está vacío"}]


def test_un_archivo_solo_con_lineas_vacias_tambien_esta_vacio():
    resultado = parsear_texto(";;\n;;\n")

    assert resultado.filas == []
    assert resultado.errores == [{"linea": 1, "mensaje": "El archivo está vacío"}]


@pytest.mark.parametrize("fecha", ["31/02/2026", "2026-13-45", "29/02/2027", "24-09-2026"])
def test_reporta_fecha_generacion_invalida(fecha):
    resultado = parsear_texto(
        _csv(ENCABEZADO, f"CLI-1;Farmacia Central;PRE-100;;{fecha};1;;Amoxicilina 500mg;10;;;")
    )

    assert resultado.filas == []
    assert resultado.errores == [
        {"linea": 2, "mensaje": "fecha_generacion inválida (use dd/mm/aaaa o aaaa-mm-dd)"}
    ]


def test_acepta_29_02_en_un_anio_bisiesto():
    resultado = parsear_texto(
        _csv(ENCABEZADO, "CLI-1;Farmacia Central;PRE-100;;29/02/2028;1;;Amoxicilina 500mg;10;;;")
    )

    assert resultado.errores == []
    assert resultado.filas[0]["fecha_generacion"] == "2028-02-29"


def test_reporta_comillas_sin_cerrar_y_no_parsea_el_resto_del_archivo():
    resultado = parsear_texto(
        _csv(
            ENCABEZADO,
            'CLI-1;Farmacia Central;PRE-100;;;1;;"Descripcion sin cerrar;10;;;',
            "CLI-2;Farmacia Sur;PRE-200;;;2;;Ibuprofeno 400mg;5;;;",
        )
    )

    assert resultado.filas == []
    assert resultado.errores == [
        {"linea": 2, "mensaje": "Comillas sin cerrar a partir de la línea 2"}
    ]


def test_reporta_el_numero_de_linea_fisico_considerando_saltos_de_linea_dentro_de_comillas():
    resultado = parsear_texto(
        _csv(
            ENCABEZADO,
            'CLI-1;Farmacia Central;PRE-100;;;1;;"Descripcion\ncon salto";10;;;',
            "CLI-2;Farmacia Sur;PRE-200;;;abc;;Ibuprofeno 400mg;5;;;",
        )
    )

    assert len(resultado.filas) == 1
    assert resultado.filas[0]["descripcion_producto"] == "Descripcion\ncon salto"
    _un_error(resultado, 4, "renglón")


# --- decodificación de los bytes crudos (S5) ----------------------------------

_FILA_ACENTOS = "CLI-1;Farmacia Pérez Ñandú;PRE-100;;;1;;Jarabe pediátrico;10;;;"


def test_decodifica_un_archivo_cp1252_con_acentos():
    resultado = parsear(_csv(ENCABEZADO, _FILA_ACENTOS).encode("cp1252"))

    assert resultado.errores == []
    assert resultado.filas[0]["razon_social_cliente"] == "Farmacia Pérez Ñandú"
    assert resultado.filas[0]["descripcion_producto"] == "Jarabe pediátrico"


def test_decodifica_un_archivo_utf8_con_bom():
    resultado = parsear(b"\xef\xbb\xbf" + _csv(ENCABEZADO, _FILA_ACENTOS).encode("utf-8"))

    assert resultado.errores == []
    assert resultado.filas[0]["codigo_cliente"] == "CLI-1"
    assert resultado.filas[0]["razon_social_cliente"] == "Farmacia Pérez Ñandú"


def test_decodifica_un_archivo_utf8_sin_bom():
    resultado = parsear(_csv(ENCABEZADO, _FILA_ACENTOS).encode("utf-8"))

    assert resultado.errores == []
    assert resultado.filas[0]["descripcion_producto"] == "Jarabe pediátrico"


def test_bytes_que_no_son_utf8_ni_cp1252_dan_un_error_de_linea_1():
    # 0x81 no está definido en cp1252 y no es UTF-8 válido.
    resultado = parsear(b"codigo_cliente\x81\n")

    assert resultado.filas == []
    assert resultado.errores == [
        {"linea": 1, "mensaje": "No se pudo leer el archivo: el encoding no es UTF-8 ni cp1252"}
    ]
