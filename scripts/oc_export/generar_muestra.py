"""Genera un CSV de muestra para Progress a partir de una OC descartable en la BD de TEST.

Crea datos sintéticos (droguería, cliente con un único código legacy, 3 productos,
3 renglones, 3 entregas, usuario exportador), exporta la OC con el servicio real
(services/presupuestacion/oc_export/service.py) y NO borra nada: la OC queda en TEST
hasta que Sistemas valide el archivo. Se limpia a pedido con --limpiar.

Los datos replican tests/oc_export/conftest.py (caso_exportable) y
tests/oc_entregas/fixtures/caso_planificacion.py.

Uso:
    python scripts/oc_export/generar_muestra.py [--salida <carpeta>]
    python scripts/oc_export/generar_muestra.py --limpiar <oc_id>

El CSV queda en <salida>/oc/ (default: C:\\Users\\LAUREANO\\OneDrive\\Escritorio\\muestra-progress).
"""

from __future__ import annotations

import argparse
import csv
import secrets
import sys
import uuid
from pathlib import Path

# Antes de tocar sys.path: el directorio supabase/ de la raíz del repo taparía al paquete.
from supabase import Client

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.presupuestacion.oc_export.service import exportar_orden_compra  # noqa: E402
from services.shared.config import get_settings  # noqa: E402
from services.shared.database import get_service_client  # noqa: E402

_PROYECTO_TEST = "grnamollopxdlstcpxhc"
_SALIDA_DEFAULT = r"C:\Users\LAUREANO\OneDrive\Escritorio\muestra-progress"
_PREFIJO_OC = "MUESTRA-PROGRESS-"
_NOMBRE_DROGUERIA = "Droguería Muestra Progress"

# (descripción, cantidad, precio) -- decimales y acentos/ñ para ejercitar cp1252
_RENGLONES = [
    ("Ibuprofeno 400 mg comprimidos x 30", "120", "15.50"),
    ("Jeringa descartable 5 ml con aguja – año 2026", "12.5", "3.75"),
    ("Alcohol en gel 500 ml (envase ñandú)", "40", "8.20"),
]
# (fecha, [(índice de renglón, cantidad)])
_ENTREGAS = [
    ("2026-10-20", [(0, "70"), (1, "7.5")]),
    ("2026-11-20", [(0, "50"), (2, "40")]),
    ("2026-12-18", [(1, "5")]),
]


def _insertar(client: Client, tabla: str, fila: dict) -> dict:
    return client.table(tabla).insert(fila).execute().data[0]


def crear_oc_muestra(client: Client) -> dict:
    sufijo = uuid.uuid4().hex[:8]
    drogueria = _insertar(client, "droguerias", {
        "nombre": _NOMBRE_DROGUERIA,
        "razon_social": "Droguería Muestra Progress SA",
        "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
        "ciudad": "Rosario",
        "provincia": "Santa Fe",
        "contacto_email": f"muestra-{uuid.uuid4()}@seed.local",
        "contacto_telefono": "0000000000",
    })
    did = drogueria["id"]
    email = f"muestra-progress-{uuid.uuid4()}@seed.local"
    usuario_id = client.auth.admin.create_user(
        {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
    ).user.id
    _insertar(client, "usuarios", {
        "id": usuario_id, "drogueria_id": did, "rol": "comercial", "nombre": "Usuario muestra Progress",
    })
    tercero = _insertar(client, "terceros", {
        "drogueria_id": did,
        "razon_social": "CLIENTE MUESTRA PROGRESS",
        "cuit": f"20{secrets.randbelow(10**9):09d}",
    })
    cliente = _insertar(client, "clientes", {"id": tercero["id"], "drogueria_id": did, "tipo": "hospital"})
    _insertar(client, "terceros_legacy_map", {
        "tercero_id": tercero["id"], "drogueria_id": did,
        "entidad_legacy": "cliente", "codigo_legacy": f"MUE{sufijo[:5].upper()}",
    })
    proceso = _insertar(client, "procesos_comerciales", {
        "drogueria_id": did, "cliente_id": cliente["id"], "clase": "cotizacion",
        "nombre": "Muestra Progress",
    })
    presupuesto = _insertar(client, "presupuestos", {
        "proceso_comercial_id": proceso["id"], "drogueria_id": did, "estado": "generado",
        "cantidad_items": 1,
    })
    item_proceso = _insertar(client, "items_proceso", {
        "proceso_comercial_id": proceso["id"], "drogueria_id": did, "numero_renglon": 1,
        "descripcion": "Renglón de presupuesto (muestra)", "cantidad": "1",
    })
    presupuesto_item = _insertar(client, "presupuesto_items", {
        "presupuesto_id": presupuesto["id"], "drogueria_id": did,
        "item_proceso_id": item_proceso["id"], "precio_unitario": "10.00", "cantidad_ofertada": "1",
    })
    oc = _insertar(client, "ordenes_compra", {
        "cliente_id": cliente["id"], "drogueria_id": did,
        "numero_oc": f"{_PREFIJO_OC}{sufijo}", "cantidad_entregas": len(_ENTREGAS),
    })
    items = []
    for n, (descripcion, cantidad, precio) in enumerate(_RENGLONES, start=1):
        producto = _insertar(client, "productos", {
            "drogueria_id": did, "codigo_interno": f"MUE-{sufijo}-{n}", "nombre": f"Producto muestra {n}",
        })
        items.append(_insertar(client, "oc_items", {
            "orden_compra_id": oc["id"], "drogueria_id": did, "numero_renglon": n,
            "descripcion": descripcion, "cantidad": cantidad, "precio_unitario": precio,
            "producto_id": producto["id"], "presupuesto_item_id": presupuesto_item["id"],
            "vinculo_origen": "manual",
        }))
    for numero, (fecha, lineas) in enumerate(_ENTREGAS, start=1):
        entrega = _insertar(client, "entregas_oc", {
            "orden_compra_id": oc["id"], "drogueria_id": did, "numero_entrega": numero,
            "fecha_entrega_planificada": fecha, "cantidad_items": len(lineas), "estado": "pendiente",
        })
        client.table("entregas_oc_items").insert([
            {
                "entrega_oc_id": entrega["id"], "drogueria_id": did, "oc_item_id": items[i]["id"],
                "cantidad_planificada": cantidad, "cantidad_entregada": "0",
            }
            for i, cantidad in lineas
        ]).execute()
    return {"oc_id": oc["id"], "drogueria_id": did, "usuario_id": usuario_id}


def limpiar(client: Client, oc_id: str) -> None:
    """Borra exactamente lo que creó crear_oc_muestra para esa OC (solo si es una OC de muestra)."""
    filas = client.table("ordenes_compra").select("*").eq("id", oc_id).execute().data
    if not filas:
        raise SystemExit(f"No existe la OC {oc_id}")
    oc = filas[0]
    if not oc["numero_oc"].startswith(_PREFIJO_OC):
        raise SystemExit(f"La OC {oc_id} no es una OC de muestra ({oc['numero_oc']}); no se toca")
    did = oc["drogueria_id"]
    droguerias = client.table("droguerias").select("nombre").eq("id", did).execute().data
    if not droguerias or droguerias[0]["nombre"] != _NOMBRE_DROGUERIA:
        raise SystemExit(f"La droguería {did} no es la de muestra; no se toca")

    items = (
        client.table("oc_items").select("producto_id,presupuesto_item_id").eq("orden_compra_id", oc_id)
        .execute().data
    )
    producto_ids = [i["producto_id"] for i in items if i["producto_id"]]
    pi_ids = list({i["presupuesto_item_id"] for i in items if i["presupuesto_item_id"]})
    presupuesto_ids = list({
        r["presupuesto_id"]
        for r in client.table("presupuesto_items").select("presupuesto_id").in_("id", pi_ids).execute().data
    }) if pi_ids else []
    proceso_ids = list({
        r["proceso_comercial_id"]
        for r in client.table("presupuestos").select("proceso_comercial_id").in_("id", presupuesto_ids)
        .execute().data
    }) if presupuesto_ids else []

    client.table("historial_cambios").delete().eq("orden_compra_id", oc_id).execute()
    # 0033: el trigger congela el plan de una OC exportada; se desmarca antes de borrar entregas.
    client.table("ordenes_compra").update(
        {"exportado_at": None, "exportado_por": None, "archivo_exportado": None}
    ).eq("id", oc_id).execute()
    client.table("entregas_oc").delete().eq("orden_compra_id", oc_id).execute()
    client.table("oc_items").delete().eq("orden_compra_id", oc_id).execute()
    client.table("ordenes_compra").delete().eq("id", oc_id).execute()
    for pid in producto_ids:
        client.table("productos").delete().eq("id", pid).execute()
    for pid in proceso_ids:
        client.table("historial_cambios").delete().eq("proceso_comercial_id", pid).execute()
    for sid in presupuesto_ids:
        client.table("presupuesto_items").delete().eq("presupuesto_id", sid).execute()
        client.table("presupuestos").delete().eq("id", sid).execute()
    for pid in proceso_ids:
        client.table("items_proceso").delete().eq("proceso_comercial_id", pid).execute()
        client.table("procesos_comerciales").delete().eq("id", pid).execute()
    client.table("terceros_legacy_map").delete().eq("tercero_id", oc["cliente_id"]).execute()
    client.table("clientes").delete().eq("id", oc["cliente_id"]).execute()
    client.table("terceros").delete().eq("id", oc["cliente_id"]).execute()
    # Todos los usuarios de la droguería sintética, no solo el exportador: si la exportación
    # falló, la OC no tiene `exportado_por` pero el usuario ya se había creado.
    usuario_ids = [
        u["id"] for u in client.table("usuarios").select("id").eq("drogueria_id", did).execute().data
    ]
    for uid in usuario_ids:
        client.table("usuarios").delete().eq("id", uid).execute()
        client.auth.admin.delete_user(uid)
    client.table("droguerias").delete().eq("id", did).execute()
    print(f"OC {oc_id} y sus datos de muestra eliminados")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", default=_SALIDA_DEFAULT, help="carpeta de salida (fuera del repo)")
    parser.add_argument("--limpiar", metavar="OC_ID", help="borra los datos de muestra de esa OC")
    args = parser.parse_args()

    settings = get_settings()
    if _PROYECTO_TEST not in settings.supabase_url:
        raise SystemExit(f"SUPABASE_URL no apunta al proyecto de test ({_PROYECTO_TEST}); abortando")
    client = get_service_client()

    if args.limpiar:
        limpiar(client, args.limpiar)
        return

    caso = crear_oc_muestra(client)
    # Antes de exportar: si la exportación falla, este id es el que necesita `--limpiar`.
    print(f"OC creada:    {caso['oc_id']} (si algo falla: --limpiar {caso['oc_id']})")
    resultado = exportar_orden_compra(
        client,
        orden_compra_id=caso["oc_id"],
        drogueria_id=caso["drogueria_id"],
        usuario_id=caso["usuario_id"],
        settings=settings.model_copy(update={"progress_docs_dir": args.salida}),
    )
    ruta = Path(args.salida) / "oc" / resultado.archivo
    print(f"OC id:        {caso['oc_id']}")
    print(f"Droguería id: {caso['drogueria_id']}")
    print(f"CSV:          {ruta}")
    print(f"Filas:        {resultado.filas}")
    print(f"Encoding:     {settings.oc_export_encoding}")
    # Releer decodificando con el mismo encoding verifica que el archivo es legible.
    with open(ruta, encoding=settings.oc_export_encoding, newline="") as f:
        print(f"Filas leídas (sin encabezado): {sum(1 for _ in csv.reader(f, delimiter=";")) - 1}")


if __name__ == "__main__":
    main()
