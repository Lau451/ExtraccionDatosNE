"""
Genera los documentos binarios de tests/fixtures/orden_compra/ a partir de su contenido
declarado acá. No es parte del pipeline de tests — se corre una sola vez (o cuando haga
falta regenerar un fixture) con:

    python tests/fixtures/orden_compra/_generar_fixtures.py

Los 3 documentos (PDF, Excel, imagen) representan órdenes de compra reales de cliente
según la gramática D6 de openspec/changes/orden-compra/design.md. El fixture 02
(Excel) es el caso obligatorio de C10: el documento NO numera renglones en ninguna
forma, y su CSV esperado (02_excel_sin_renglon/esperado.csv) tiene la columna
numero_renglon vacía en todas las filas.
"""

from pathlib import Path

BASE = Path(__file__).parent


def _generar_pdf_oc4471() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    destino = BASE / "01_pdf_con_renglon" / "documento.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(destino), pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    def linea(texto: str, salto: float = 0.7 * cm, size: int = 11, bold: bool = False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(2 * cm, y, texto)
        y -= salto

    linea("ORDEN DE COMPRA", size=16, bold=True)
    y -= 0.3 * cm
    linea("Numero de orden: OC-4471", bold=True)
    linea("Fecha de emision: 12/09/2026")
    linea("Cliente: HOSPITAL SAN ROQUE")
    linea("CUIT del cliente: 30-71234567-9")
    linea("Direccion de entrega: Av. Siempreviva 742")
    linea("Cantidad de entregas planificadas: 2")
    y -= 0.5 * cm

    linea("Detalle de renglones:", bold=True)
    y -= 0.2 * cm
    linea("Renglon | Descripcion | Cantidad | Precio unitario | Plan de entregas", size=10, bold=True)
    linea(
        "1 | IBUPROFENO 400MG X 20 | 100 | $1.250,00 | Entrega 1: 50 unidades a los 30 dias. "
        "Entrega 2: 50 unidades a los 60 dias.",
        size=10,
    )
    linea(
        "2 | AMOXICILINA 500MG X 16 | 80 | $980,50 | Entrega unica, sin desglose declarado.",
        size=10,
    )

    c.showPage()
    c.save()
    print(f"Generado: {destino}")


def _generar_excel_oc9012() -> None:
    import openpyxl

    destino = BASE / "02_excel_sin_renglon" / "documento.xlsx"
    destino.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Orden de compra"

    filas = [
        ["ORDEN DE COMPRA", "", "", ""],
        ["Numero de orden:", "OC-9012", "", ""],
        ["Fecha de emision:", "03/09/2026", "", ""],
        ["Cliente:", "CLINICA DEL SOL", "", ""],
        ["CUIT del cliente:", "30-55555555-3", "", ""],
        ["Direccion de entrega:", "Ruta 9 km 12", "", ""],
        ["Cantidad de entregas planificadas:", "1", "", ""],
        ["", "", "", ""],
        [
            "Este documento no numera sus renglones: no hay columna ni referencia de "
            "numero de linea en ninguna parte.",
            "",
            "",
            "",
        ],
        ["", "", "", ""],
        ["Descripcion", "Cantidad", "Precio unitario", "Entregas"],
        ["GASA ESTERIL 10X10", "40", "320,00", ""],
        ["ALCOHOL EN GEL 250ML", "25", "410,00", ""],
    ]
    for fila in filas:
        ws.append(fila)

    wb.save(str(destino))
    print(f"Generado: {destino}")


def _generar_imagen_oc7788() -> None:
    from PIL import Image, ImageDraw, ImageFont

    destino = BASE / "03_imagen_con_renglon" / "documento.png"
    destino.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (1240, 900), "white")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 30)
        font_bold = ImageFont.truetype("arialbd.ttf", 18)
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font_title = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font = ImageFont.load_default()

    y = 40

    def linea(texto: str, salto: int = 34, f=None, x: int = 40):
        nonlocal y
        draw.text((x, y), texto, fill="black", font=f or font)
        y += salto

    linea("ORDEN DE COMPRA", salto=50, f=font_title)
    linea("Numero de orden: OC-7788", f=font_bold)
    linea("Fecha de emision: 15/09/2026")
    linea("Cliente: FARMACIA DEL NORTE S.R.L.")
    linea("CUIT del cliente: 30-69876543-2")
    linea("Direccion de entrega: Av. Rivadavia 1500")
    linea("Cantidad de entregas planificadas: 3")
    y += 20

    linea("Detalle de renglones:", f=font_bold)
    y += 6
    linea(
        "Renglon | Descripcion | Cantidad | Precio unitario | Plan de entregas",
        f=font_bold,
    )
    linea(
        "1 | IBUPROFENO 600MG X 30 | 150 | $890,75 | Entrega 1: 50 un. a los 15 dias. "
        "Entrega 2: 50 un. a los 30 dias. Entrega 3: 50 un. a los 45 dias.",
        salto=44,
    )
    linea("2 | PARACETAMOL 500MG X 20 | 200 | $450,00 | Entrega unica, sin desglose declarado.")
    linea(
        "3 | DICLOFENAC GEL 60G | 80 | $610,30 | Entrega 1: 40 un. a los 10 dias. "
        "Entrega 2: 40 un. a los 20 dias.",
        salto=44,
    )

    img.save(str(destino))
    print(f"Generado: {destino}")


if __name__ == "__main__":
    _generar_pdf_oc4471()
    _generar_excel_oc9012()
    _generar_imagen_oc7788()
