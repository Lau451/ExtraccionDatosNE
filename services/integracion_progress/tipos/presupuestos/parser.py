"""Parser del CSV de presupuestos que exporta Progress (odd/tasks/integracion-progress.md S5).

Port exacto de `frontend/src/features/presupuestos-import/parsearCsvPresupuestos.ts`
(que se elimina): mismas columnas, misma detección de delimitador, mismo tokenizador
RFC4180 y mismos mensajes de error por línea. Lo único nuevo es la decodificación de
los bytes crudos: UTF-8 (con o sin BOM) y, si no es UTF-8 válido, cp1252, que es el
encoding con el que exporta Progress.

Las filas salen como dicts compatibles con
`services.presupuestacion.presupuestos.api.FilaImportPresupuestoLegacy`
(los opcionales vacíos van como None) y los errores como `{"linea", "mensaje"}`.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# Columnas obligatorias del export: si falta alguna en el encabezado, el parseo se
# corta sin leer filas.
COLUMNAS_REQUERIDAS = (
    "codigo_cliente",
    "razon_social_cliente",
    "numero_presupuesto",
    "renglon",
    "descripcion_producto",
    "cantidad_producto",
)

COLUMNAS_OPCIONALES = (
    "proceso_comercial",
    "fecha_generacion",
    "codigo_producto",
    "precio_producto",
    "importe_total",
)

# Espacios que recortan `String.prototype.trim()` y `\s` en JS. `str.strip()` de
# Python difiere (no recorta U+FEFF y sí \x1c-\x1f, \x85), así que se fija el set.
_ESPACIOS_JS = (
    "\t\n\v\f\r \u00a0\u1680\u2028\u2029\u202f\u205f\u3000\ufeff"
    + "".join(chr(c) for c in range(0x2000, 0x200B))
)
_RE_ESPACIOS_JS = re.compile(f"[{re.escape(_ESPACIOS_JS)}]")

# `[0-9]` y no `\d`: en Python `\d` acepta dígitos Unicode y en JS no.
_FECHA_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_FECHA_DDMMYYYY = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})")
_ENTERO = re.compile(r"-?[0-9]+")
# Formato del export de Progress: coma decimal y SIN separador de miles (`1250,50`,
# `1250`). Cualquier otra forma (`1250.50`, `1.250`) es un error de fila, nunca una
# adivinanza: un separador mal interpretado cambia el valor 1000 veces.
_NUMERO_PROGRESS = re.compile(r"-?[0-9]+(,[0-9]+)?")
_SALTO = re.compile(r"\r\n|\r|\n")

_MENSAJE_ENCODING = "No se pudo leer el archivo: el encoding no es UTF-8 ni cp1252"


@dataclass
class ResultadoParseo:
    filas: list[dict[str, Any]] = field(default_factory=list)
    errores: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _FilaTokenizada:
    valores: list[str]
    # Línea física (1-based) donde empieza el registro, contando los saltos de
    # línea embebidos en campos entre comillas.
    linea_inicio: int


class _ErrorComillasSinCerrar(Exception):
    def __init__(self, linea: int) -> None:
        super().__init__(f"Comillas sin cerrar a partir de la línea {linea}")
        self.linea = linea


def _trim(valor: str) -> str:
    return valor.strip(_ESPACIOS_JS)


def decodificar(contenido: bytes) -> str | None:
    """UTF-8 (el BOM, si viene, lo quita el parser) y si falla cp1252. None si los
    bytes no son válidos en ninguno de los dos."""
    for encoding in ("utf-8", "cp1252"):
        try:
            return contenido.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _tokenizar(contenido: str, delimitador: str) -> list[_FilaTokenizada]:
    """Tokeniza el contenido completo (no línea por línea) para soportar comillas con
    delimitador o salto de línea embebidos y `""` como comilla escapada."""
    filas: list[_FilaTokenizada] = []
    fila: list[str] = []
    campo: list[str] = []
    dentro_de_comillas = False
    i = 0
    largo = len(contenido)
    linea_actual = 1
    linea_inicio_fila = 1
    linea_inicio_comillas = 1

    while i < largo:
        char = contenido[i]

        if char in ("\r", "\n"):
            es_crlf = char == "\r" and i + 1 < largo and contenido[i + 1] == "\n"
            if dentro_de_comillas:
                campo.append("\r\n" if es_crlf else char)
                i += 2 if es_crlf else 1
                linea_actual += 1
                continue
            fila.append("".join(campo))
            filas.append(_FilaTokenizada(fila, linea_inicio_fila))
            fila = []
            campo = []
            i += 2 if es_crlf else 1
            linea_actual += 1
            linea_inicio_fila = linea_actual
            continue

        if dentro_de_comillas:
            if char == '"':
                if i + 1 < largo and contenido[i + 1] == '"':
                    campo.append('"')
                    i += 2
                    continue
                dentro_de_comillas = False
                i += 1
                continue
            campo.append(char)
            i += 1
            continue

        if char == '"':
            dentro_de_comillas = True
            linea_inicio_comillas = linea_actual
            i += 1
            continue

        if char == delimitador:
            fila.append("".join(campo))
            campo = []
            i += 1
            continue

        campo.append(char)
        i += 1

    if dentro_de_comillas:
        raise _ErrorComillasSinCerrar(linea_inicio_comillas)

    if campo or fila:
        fila.append("".join(campo))
        filas.append(_FilaTokenizada(fila, linea_inicio_fila))

    return filas


def _es_fila_vacia(fila: list[str]) -> bool:
    return all(_trim(campo) == "" for campo in fila)


def _detectar_delimitador(primera_linea: str) -> str:
    """Cuenta `;` y `,` fuera de comillas en la primera línea; `,` gana los empates."""
    dentro_de_comillas = False
    comas = 0
    punto_y_coma = 0
    for char in primera_linea:
        if char == '"':
            dentro_de_comillas = not dentro_de_comillas
            continue
        if dentro_de_comillas:
            continue
        if char == ",":
            comas += 1
        if char == ";":
            punto_y_coma += 1
    return ";" if punto_y_coma > comas else ","


def _parsear_numero(valor_crudo: str) -> tuple[bool, Decimal | None]:
    valor = _trim(valor_crudo)
    if valor == "":
        return True, None
    sin_espacios = _RE_ESPACIOS_JS.sub("", valor)
    if not _NUMERO_PROGRESS.fullmatch(sin_espacios):
        return False, None
    return True, Decimal(sin_espacios.replace(",", "."))


def _parsear_entero(valor_crudo: str) -> int | None:
    valor = _trim(valor_crudo)
    if not _ENTERO.fullmatch(valor):
        return None
    return int(valor)


def _es_fecha_calendario_valida(anio: int, mes: int, dia: int) -> bool:
    if mes < 1 or mes > 12 or dia < 1:
        return False
    # El frontend usaba `new Date(anio, mes, 0)`, que interpreta los años 0-99 como
    # 1900-1999; se conserva para que ambos lados acepten las mismas fechas.
    if 0 <= anio <= 99:
        anio += 1900
    bisiesto = (anio % 4 == 0 and anio % 100 != 0) or anio % 400 == 0
    dias_del_mes = (31, 29 if bisiesto else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return dia <= dias_del_mes[mes - 1]


def _normalizar_fecha(valor_crudo: str) -> tuple[bool, str | None]:
    """dd/mm/aaaa o aaaa-mm-dd, siempre devuelta en ISO y validada contra el
    calendario (31/02, 2026-13-45 y 29/02 de años no bisiestos son inválidas)."""
    valor = _trim(valor_crudo)
    if valor == "":
        return True, None

    iso = _FECHA_ISO.fullmatch(valor)
    if iso:
        yyyy, mm, dd = iso.groups()
        if not _es_fecha_calendario_valida(int(yyyy), int(mm), int(dd)):
            return False, None
        return True, valor

    ddmmyyyy = _FECHA_DDMMYYYY.fullmatch(valor)
    if not ddmmyyyy:
        return False, None
    dd, mm, yyyy = ddmmyyyy.groups()
    if not _es_fecha_calendario_valida(int(yyyy), int(mm), int(dd)):
        return False, None
    return True, f"{yyyy}-{mm}-{dd}"


def _vacio() -> ResultadoParseo:
    return ResultadoParseo(errores=[{"linea": 1, "mensaje": "El archivo está vacío"}])


def parsear(contenido: bytes) -> ResultadoParseo:
    """Decodifica los bytes crudos del archivo y los parsea."""
    texto = decodificar(contenido)
    if texto is None:
        return ResultadoParseo(errores=[{"linea": 1, "mensaje": _MENSAJE_ENCODING}])
    return parsear_texto(texto)


def parsear_texto(contenido_original: str) -> ResultadoParseo:
    contenido = contenido_original.removeprefix("\ufeff")

    if _trim(contenido) == "":
        return _vacio()

    primer_salto = _SALTO.search(contenido)
    primera_linea = contenido if primer_salto is None else contenido[: primer_salto.start()]
    delimitador = _detectar_delimitador(primera_linea)

    try:
        tokenizadas = _tokenizar(contenido, delimitador)
    except _ErrorComillasSinCerrar as error:
        return ResultadoParseo(errores=[{"linea": error.linea, "mensaje": str(error)}])

    while tokenizadas and _es_fila_vacia(tokenizadas[-1].valores):
        tokenizadas.pop()

    if not tokenizadas:
        return _vacio()

    encabezado = [_trim(columna).lower() for columna in tokenizadas[0].valores]

    def indice_de(nombre: str) -> int:
        return encabezado.index(nombre) if nombre in encabezado else -1

    faltantes = [columna for columna in COLUMNAS_REQUERIDAS if indice_de(columna) == -1]
    if faltantes:
        return ResultadoParseo(
            errores=[
                {"linea": 1, "mensaje": f'Falta la columna requerida "{columna}"'}
                for columna in faltantes
            ]
        )

    idx = {columna: indice_de(columna) for columna in COLUMNAS_REQUERIDAS + COLUMNAS_OPCIONALES}
    resultado = ResultadoParseo()

    for tokenizada in tokenizadas[1:]:
        columnas = tokenizada.valores
        if _es_fila_vacia(columnas):
            continue
        linea = tokenizada.linea_inicio

        def valor(indice: int) -> str:
            if indice == -1 or indice >= len(columnas):
                return ""
            return _trim(columnas[indice])

        errores_fila: list[str] = []

        codigo_cliente = valor(idx["codigo_cliente"])
        if codigo_cliente == "":
            errores_fila.append("falta codigo_cliente")

        razon_social_cliente = valor(idx["razon_social_cliente"])

        numero_presupuesto = valor(idx["numero_presupuesto"])
        if numero_presupuesto == "":
            errores_fila.append("falta numero_presupuesto")

        descripcion_producto = valor(idx["descripcion_producto"])
        if descripcion_producto == "":
            errores_fila.append("falta descripcion_producto")

        renglon = _parsear_entero(valor(idx["renglon"]))
        if renglon is None:
            errores_fila.append("renglón no es un número entero")

        cantidad_ok, cantidad = _parsear_numero(valor(idx["cantidad_producto"]))
        if not cantidad_ok or cantidad is None:
            errores_fila.append("cantidad_producto no es numérica (formato esperado: 1250,50)")

        precio_ok, precio = _parsear_numero(valor(idx["precio_producto"]))
        if not precio_ok:
            errores_fila.append("precio_producto no es numérico (formato esperado: 1250,50)")

        importe_ok, importe_total = _parsear_numero(valor(idx["importe_total"]))
        if not importe_ok:
            errores_fila.append("importe_total no es numérico (formato esperado: 1250,50)")

        fecha_ok, fecha = _normalizar_fecha(valor(idx["fecha_generacion"]))
        if not fecha_ok:
            errores_fila.append("fecha_generacion inválida (use dd/mm/aaaa o aaaa-mm-dd)")

        proceso_comercial_crudo = valor(idx["proceso_comercial"])
        proceso_comercial: str | None = None
        if proceso_comercial_crudo in ("1", "2"):
            proceso_comercial = proceso_comercial_crudo
        elif proceso_comercial_crudo != "":
            errores_fila.append("proceso_comercial debe ser 1 o 2")

        if errores_fila:
            resultado.errores.append({"linea": linea, "mensaje": "; ".join(errores_fila)})
            continue

        resultado.filas.append(
            {
                "codigo_cliente": codigo_cliente,
                "razon_social_cliente": razon_social_cliente,
                "numero_presupuesto": numero_presupuesto,
                "proceso_comercial": proceso_comercial,
                "fecha_generacion": fecha,
                "renglon": renglon,
                "codigo_producto": valor(idx["codigo_producto"]) or None,
                "descripcion_producto": descripcion_producto,
                "cantidad_producto": cantidad,
                "precio_producto": precio,
                "importe_total": importe_total,
            }
        )

    return resultado
