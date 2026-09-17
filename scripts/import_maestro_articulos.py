"""Importa el maestro de artículos legacy (CSV ';', encoding cp1252) al
esquema nuevo de productos (services/productos/).

Reusa el pipeline de import ya existente (services/presupuestacion/imports)
en vez de insertar directo: importar_productos ya sabe hacer upsert por
codigo_interno y desactivar los códigos que dejaron de estar en el archivo.

Decisiones de mapeo (acordadas en la conversación de diseño del módulo, no
inventadas acá):
  - Rubro -> clasificacion: ver RUBRO_A_CLASIFICACION.
  - Envase legacy mezclaba 3 conceptos (forma farmacéutica, envase real,
    característica HELADERA) — se separan acá, no se migra tal cual.
  - codigo_anmat se extrae de Descripcion con un regex condicionado a Rubro
    (PM explícito para descartables, número final suelto para medicamentos)
    porque el patrón de formato depende del tipo de producto, verificado
    contra el CSV real (~99% de correlación Rubro/patrón).
  - categoria_id (Familia) y droga (molécula) quedan NULL: el dato legacy
    correspondiente (Sub Rubro) está sólo 28% poblado y mezcla categoría con
    principio activo sin consistencia — no hay base confiable para
    auto-derivarlos. Se clasifican a mano después.
  - nombre = Descrip Tipo cuando existe (versión genérica sin marca ni
    código de laboratorio, confirmado contra el CSV real), con fallback a
    Descripcion completa en las filas sin Descrip Tipo (22.8%, las mismas
    con Tipo=0/sin asignar). La Descripcion completa se preserva siempre en
    datos_sistema.legacy_descripcion_completa, se use o no como nombre.
    No se intenta separar marca/presentación de la Descripcion con NLP —
    fuera de alcance de este script.

Uso:
    python scripts/import_maestro_articulos.py --csv <ruta.csv> --drogueria-id <uuid> [--execute] [--limit N]

Sin --execute corre en modo dry-run: parsea el CSV, resuelve qué catálogos
haría falta crear y muestra un resumen, sin escribir nada en la base.
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.presupuestacion.core.database import get_service_client  # noqa: E402
from services.presupuestacion.imports import repository as imports_repo  # noqa: E402
from services.presupuestacion.imports.models import ImportProductoRow  # noqa: E402
from services.presupuestacion.imports.service import importar_productos  # noqa: E402
from services.productos import service as productos_service  # noqa: E402
from services.productos.models import (  # noqa: E402
    CaracteristicaCreate,
    EnvaseCreate,
    MarcaCreate,
    ProductoCaracteristicaCreate,
)

# -- mapeos fijos -------------------------------------------------------------

RUBRO_A_CLASIFICACION = {
    "MEDICAMENTOS": "medicamento",
    "DESCARTABLES": "descartable",
    "SUEROS": "solucion",
    "SOL. DE GRAN VOLUMEN": "solucion",
    "COSMETICOS": "cosmetico",
    "NUTRICION": "nutricion",
    "REACTIVOS": "reactivo",
}

ENVASE_A_FORMA_FARMACEUTICA = {
    "COMPRIMIDO", "SUSPENSION", "GOTA", "CREMA", "CAPSULA", "CAPSULA BLANDA",
}
ENVASE_A_ENVASE_REAL = {
    "BOTELLA", "LATA", "SACHET", "F/AMP", "AMPOLLA", "SOBRES",
    "CAJA X 100 UNIDADES",
}
ENVASE_A_CARACTERISTICA = {"HELADERA": "HELADERA"}

CARACTERISTICA_LEGACY_A_NOMBRE = {
    "PRODUCTO CON VALE": "VALE",
    "PSICOTROPICOS": "PSICOTROPICO",
    "PRODUCTO REFRIGERADO": "HELADERA",
    "LIBRE DE LATEX": "LIBRE_DE_LATEX",
    "LIBRE DE GLUTEN": "LIBRE_DE_GLUTEN",
}
CARACTERISTICAS_A_SEMBRAR = sorted(set(CARACTERISTICA_LEGACY_A_NOMBRE.values()) | {"HELADERA"})

_PM_RE = re.compile(r"PM[\s:-]*(\d+(?:-\d+)?)", re.IGNORECASE)
_BARE_TRAILING_RE = re.compile(r"(?<![A-Za-z0-9])(\d{4,6})\s*$")
_ESPACIOS_RE = re.compile(r"\s+")


def _limpiar(valor):
    if valor is None:
        return None
    if isinstance(valor, float) and pd.isna(valor):
        return None  # pandas representa celdas vacías como NaN (float) incluso con dtype=str
    if isinstance(valor, str):
        valor = _ESPACIOS_RE.sub(" ", valor).strip()
        return valor or None
    return valor


def extraer_codigo_anmat(descripcion: str, rubro: str) -> str | None:
    m = _PM_RE.search(descripcion)
    if m:
        return f"PM-{m.group(1)}"
    if rubro == "MEDICAMENTOS":
        m = _BARE_TRAILING_RE.search(descripcion)
        if m:
            return m.group(1)
    return None


def clasificar_envase(envase_legacy: str | None) -> tuple[str | None, str | None, str | None]:
    """Devuelve (forma_farmaceutica, envase_real, caracteristica) a partir
    del valor crudo de Envase — nunca más de uno no-None a la vez."""
    if not envase_legacy:
        return None, None, None
    valor = envase_legacy.upper()
    if valor in ENVASE_A_CARACTERISTICA:
        return None, None, ENVASE_A_CARACTERISTICA[valor]
    if valor in ENVASE_A_FORMA_FARMACEUTICA:
        return envase_legacy, None, None
    if valor in ENVASE_A_ENVASE_REAL:
        return None, envase_legacy, None
    return None, None, None  # valor no reconocido: se deja sin clasificar, no se inventa


def cargar_csv(ruta: Path) -> list[dict]:
    """Devuelve list[dict], no un DataFrame: pandas 3.0 infiere su dtype
    nativo "str" en cualquier Series derivada (incluso vía .apply/.astype) y
    ese dtype convierte None de vuelta a su propio sentinel de NA, que en
    frontera con Python aparece como float('nan') — rompe cualquier `if not
    valor`/`.upper()` río abajo. Limpiar sobre dicts planos, fuera de
    pandas, evita el problema de raíz en vez de perseguirlo columna por
    columna."""
    df = pd.read_csv(ruta, sep=";", encoding="cp1252", dtype=str)
    filas = df.to_dict("records")
    return [{columna: _limpiar(valor) for columna, valor in fila.items()} for fila in filas]


def detectar_duplicados(filas: list[dict]) -> list[tuple[str, str, str]]:
    """(Descripcion, Marca) idénticos bajo Articulo distinto — señal de
    productos repetidos en el maestro viejo. Se reporta, no se resuelve acá."""
    pares: list[tuple[str, str, str]] = []
    vistos: dict[tuple[str, str], str] = {}
    for fila in filas:
        clave = (fila["Descripcion"] or "", fila["Marca"] or "")
        if clave in vistos:
            pares.append((fila["Articulo"], vistos[clave], fila["Descripcion"] or ""))
        else:
            vistos[clave] = fila["Articulo"]
    return pares


def resolver_catalogo(
    *,
    client,
    drogueria_id: str,
    nombres: set[str],
    listar,
    crear_body_cls,
    crear_fn,
) -> dict[str, str]:
    """Mapa NOMBRE_UPPER -> id, creando en el catálogo lo que falte."""
    existentes = listar(client, drogueria_id=drogueria_id)
    mapa = {fila["nombre"].upper(): fila["id"] for fila in existentes}
    for nombre in sorted(nombres):
        if nombre.upper() in mapa:
            continue
        creado = crear_fn(client, drogueria_id=drogueria_id, body=crear_body_cls(nombre=nombre))
        mapa[nombre.upper()] = creado["id"]
    return mapa


def construir_datos_sistema(fila: "pd.Series") -> dict:
    proveedores = [
        fila.get(f"proveedor {i}") for i in range(1, 6) if fila.get(f"proveedor {i}")
    ]
    return {
        "legacy_descripcion_completa": fila.get("Descripcion"),
        "legacy_clasificacion_texto": fila.get("Clasificacion"),
        "legacy_sub_rubro": fila.get("Sub Rubro"),
        "legacy_tipo": fila.get("Tipo"),
        "legacy_descrip_tipo": fila.get("Descrip Tipo"),
        "legacy_referencia_rotacion": fila.get("Referencia"),
        "legacy_stock_maximo": fila.get("Stock Maximo"),
        "legacy_proveedores": proveedores or None,
        "legacy_envase_raw": fila.get("Envase"),
    }


def _decimal_o_none(valor: str | None) -> Decimal | None:
    if not valor:
        return None
    try:
        return Decimal(valor.replace(",", "."))
    except InvalidOperation:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--drogueria-id", default=None, help="Requerido con --execute")
    parser.add_argument("--usuario-id", default=None, help="UUID de usuarios.id (created_by/updated_by), requerido con --execute")
    parser.add_argument("--execute", action="store_true", help="Sin esto, corre en dry-run (no escribe nada)")
    parser.add_argument("--limit", type=int, default=None, help="Procesar sólo las primeras N filas (para probar)")
    args = parser.parse_args()

    if args.execute and (not args.drogueria_id or not args.usuario_id):
        parser.error("--execute requiere --drogueria-id y --usuario-id")

    filas_csv = cargar_csv(args.csv)
    if args.limit:
        filas_csv = filas_csv[: args.limit]

    rubros_sin_mapear = sorted({f["Rubro"] for f in filas_csv if f["Rubro"]} - set(RUBRO_A_CLASIFICACION))
    if rubros_sin_mapear:
        print(f"AVISO: Rubro sin mapeo a clasificacion, se deja NULL: {rubros_sin_mapear}")

    duplicados = detectar_duplicados(filas_csv)
    if duplicados:
        print(f"AVISO: {len(duplicados)} pares de codigo_interno con misma Descripcion+Marca (posibles duplicados reales):")
        for cod_a, cod_b, desc in duplicados:
            print(f"  {cod_a} / {cod_b} — {desc}")

    marcas_legacy = {f["Marca"] for f in filas_csv if f["Marca"]}
    envases_reales_legacy: set[str] = set()
    caracteristicas_por_fila: dict[str, set[str]] = {}
    filas_import: list[ImportProductoRow] = []
    sin_codigo_anmat = 0

    for fila in filas_csv:
        rubro = fila["Rubro"]
        descripcion = fila["Descripcion"] or ""
        # Descrip Tipo es la version generica (sin marca ni codigo de
        # laboratorio) cuando existe. Ausente exactamente en las filas con
        # Tipo=0 (22.8% del maestro, ya identificado como sucio) — ahi no
        # queda otra que la Descripcion completa.
        nombre = fila.get("Descrip Tipo") or descripcion or fila["Articulo"]
        forma_farm, envase_real, caract_envase = clasificar_envase(fila.get("Envase"))
        if envase_real:
            envases_reales_legacy.add(envase_real)

        caracts = set()
        if caract_envase:
            caracts.add(caract_envase)
        caract_legacy = fila.get("Caracteristica")
        if caract_legacy and caract_legacy.upper() in CARACTERISTICA_LEGACY_A_NOMBRE:
            caracts.add(CARACTERISTICA_LEGACY_A_NOMBRE[caract_legacy.upper()])
        if caracts:
            caracteristicas_por_fila[fila["Articulo"]] = caracts

        codigo_anmat = extraer_codigo_anmat(descripcion, rubro)
        if codigo_anmat is None:
            sin_codigo_anmat += 1

        filas_import.append(
            ImportProductoRow(
                codigo_interno=fila["Articulo"],
                nombre=nombre,
                categoria_id=None,  # Familia: Sub Rubro legacy demasiado sucio, se clasifica a mano
                clasificacion=RUBRO_A_CLASIFICACION.get(rubro),
                droga=None,  # molécula: fuera de alcance de esta carga, ver diseño acordado
                presentacion=fila.get("Presentacion"),
                forma_farmaceutica=forma_farm,
                marca_id=None,  # se completa en el segundo paso, tras resolver el catálogo
                envase_id=None,  # idem
                alicuota_iva=_decimal_o_none(fila.get("Alicuota_IVA")),
                codigo_anmat=codigo_anmat,
                datos_sistema=construir_datos_sistema(fila),
            )
        )

    print(f"Filas leídas: {len(filas_csv)}")
    print(f"Marcas distintas a resolver: {len(marcas_legacy)}")
    print(f"Envases reales distintos a resolver: {len(envases_reales_legacy)}")
    print(f"Filas con al menos una característica: {len(caracteristicas_por_fila)}")
    print(f"Filas sin codigo_anmat extraído: {sin_codigo_anmat}")

    if not args.execute:
        print("\nDRY-RUN (no se escribió nada). Corré con --execute para aplicar.")
        return

    client = get_service_client()

    marcas_por_nombre = resolver_catalogo(
        client=client,
        drogueria_id=args.drogueria_id,
        nombres=marcas_legacy,
        listar=productos_service.listar_marcas,
        crear_body_cls=MarcaCreate,
        crear_fn=productos_service.crear_marca,
    )
    envases_por_nombre = resolver_catalogo(
        client=client,
        drogueria_id=args.drogueria_id,
        nombres=envases_reales_legacy,
        listar=productos_service.listar_envases,
        crear_body_cls=EnvaseCreate,
        crear_fn=productos_service.crear_envase,
    )
    caracteristicas_por_nombre = resolver_catalogo(
        client=client,
        drogueria_id=args.drogueria_id,
        nombres=set(CARACTERISTICAS_A_SEMBRAR),
        listar=productos_service.listar_caracteristicas,
        crear_body_cls=CaracteristicaCreate,
        crear_fn=productos_service.crear_caracteristica,
    )

    for fila_import, fila_csv in zip(filas_import, filas_csv):
        marca = fila_csv.get("Marca")
        if marca:
            fila_import.marca_id = marcas_por_nombre.get(marca.upper())
        _, envase_real, _ = clasificar_envase(fila_csv.get("Envase"))
        if envase_real:
            fila_import.envase_id = envases_por_nombre.get(envase_real.upper())

    resultado = importar_productos(
        client, drogueria_id=args.drogueria_id, productos=filas_import, usuario_id=args.usuario_id,
    )
    print(f"\nproductos: creados={resultado['creados']} actualizados={resultado['actualizados']} desactivados={resultado['desactivados']}")

    codigos = list(caracteristicas_por_fila.keys())
    mapa_producto_ids = imports_repo.mapear_productos_por_codigo(client, drogueria_id=args.drogueria_id, codigos=codigos)
    asignadas = 0
    for codigo, nombres_caract in caracteristicas_por_fila.items():
        producto_id = mapa_producto_ids.get(codigo)
        if producto_id is None:
            continue
        ya_asignadas = {
            c["caracteristica_id"]
            for c in productos_service.listar_caracteristicas_producto(
                client, producto_id=producto_id, drogueria_id=args.drogueria_id
            )
        }
        for nombre in nombres_caract:
            caract_id = caracteristicas_por_nombre.get(nombre.upper())
            if caract_id is None or caract_id in ya_asignadas:
                continue
            productos_service.asignar_caracteristica_producto(
                client,
                producto_id=producto_id,
                drogueria_id=args.drogueria_id,
                body=ProductoCaracteristicaCreate(caracteristica_id=caract_id),
                usuario_id=args.usuario_id,
            )
            asignadas += 1
    print(f"características asignadas: {asignadas}")


if __name__ == "__main__":
    main()
