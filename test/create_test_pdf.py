#!/usr/bin/env python3
"""
Crea un PDF mínimo para testing de concurrencia.
"""

from pathlib import Path

def create_minimal_pdf(output_path: Path):
    """
    Crea un PDF mínimo válido para testing.
    Este es un PDF muy simple con solo texto.
    """
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Documento de prueba para testing de concurrencia) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000237 00000 n
0000000332 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
425
%%EOF
"""
    with open(output_path, "wb") as f:
        f.write(pdf_content)
    print(f"OK - PDF de prueba creado: {output_path}")


if __name__ == "__main__":
    pdf_path = Path(__file__).parent / "test_file.pdf"
    create_minimal_pdf(pdf_path)
    print(f"Tamaño: {pdf_path.stat().st_size} bytes")
