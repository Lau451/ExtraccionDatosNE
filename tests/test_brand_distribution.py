"""Tests for _clean_brand and _distribute_brands in parsers.py."""

import pytest
from app.parsers import _clean_brand, _distribute_brands


# ---------------------------------------------------------------------------
# _clean_brand
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("ELEA PM59408",                   "ELEA"),
    ("ELEA PHOENIX PM59408",           "ELEA PHOENIX"),
    ("KLONAL PM58743",                 "KLONAL"),
    ("RICHET PM44738",                 "RICHET"),
    ("LEPETIT/LAFEDAR PM48886/44893",  "LEPETIT/LAFEDAR"),
    ("SOUBERIAN CHOBE PM34774",        "SOUBERIAN CHOBE"),
    ("DENVER C.48432",                 "DENVER"),
    ("DENVER FARMA PM48432",           "DENVER FARMA"),
    ("LAFEDAR C.38921",                "LAFEDAR"),
    ("LAFEDAR VTO 07/26",              "LAFEDAR"),
    ("RICHET CAJA X 200",              "RICHET"),
    ("BETA PM48647 x8",                "BETA"),
    ("RSTONEL ELEA PM59408",           "RSTONEL ELEA"),
    ("LACTAMAX PM48647",               "LACTAMAX"),
    ("ANDROMACO PM40720",              "ANDROMACO"),
    ("ELEA",                           "ELEA"),          # no code — unchanged
    ("No cotiza",                      "No cotiza"),     # not a brand — caller skips
])
def test_clean_brand(raw, expected):
    assert _clean_brand(raw) == expected


# ---------------------------------------------------------------------------
# _distribute_brands  — helper to build minimal table rows
# ---------------------------------------------------------------------------

# Column layout: 0=Proveedor, 1=Item, 2=Cant, 3=Descripcion, 4=Unidad, 5=PU, 6=Importe
NCOLS = 7


def _row(proveedor="", item="", cant="", desc="", unidad="", pu="", importe=""):
    return [proveedor or None, item or None, cant or None, desc or None,
            unidad or None, pu or None, importe or None]


class TestDistributeBrands:

    def test_brands_distributed_after_brand_list_row(self):
        """Brand list on first provider row → brands injected into subsequent price rows."""
        rows = [
            # Header
            _row("Proveedor", "Item", "Cant", "Descripcion", "Unidad", "PU", "Importe"),
            # Item header
            _row(item="278", cant="120", desc="Valsartan 26 mg comp"),
            # Brand-list row (NUEVA ERA, no price)
            _row(proveedor="NUEVA ERA ROSARIO", desc="ELEA PM59408\nELEA PHOENIX PM59408\nELEA PM59408\nNo cotiza\nNo cotiza"),
            # Price rows (no brand yet)
            _row(proveedor="SRL", cant="120", pu="1567"),
            _row(proveedor="COMPAÑIA MEDICA SRL", cant="120", pu="1661"),
            _row(proveedor="DROGUERIA BOSCH S.C.", cant="120", pu="1681"),
        ]
        result = _distribute_brands(rows)

        # Brand-list row cleared
        assert result[2][3] == ""
        # Price rows got brands in order
        assert result[3][3] == "ELEA"
        assert result[4][3] == "ELEA PHOENIX"
        assert result[5][3] == "ELEA"

    def test_brands_distributed_before_brand_list_row(self):
        """Brand list in a middle row → providers BEFORE it also get brands."""
        rows = [
            _row("Proveedor", "Item", "Cant", "Descripcion", "Unidad", "PU", "Importe"),
            _row(item="6", cant="100", desc="Aciclovir 500 mg f.a. liof."),
            # Price rows BEFORE the brand list (no brand)
            _row(proveedor="LITORAL S.A.", cant="100", pu="21905"),
            _row(proveedor="VI-FARMA S.R.L.", cant="100", pu="22800"),
            _row(proveedor="COMPAÑIA MEDICA SRL", cant="100", pu="24800"),
            # Brand-list row (no price)
            _row(proveedor="DROGUERIA LIDER", desc="KLONAL PM58743\nKLONAL PM58743\nKLONAL PM58743\nKLONAL PM58743\nKLONAL PM58743\nNo cotiza\nNo cotiza"),
            # Price row AFTER the brand list
            _row(proveedor="S.R.L.", cant="100", pu="25862"),
        ]
        result = _distribute_brands(rows)

        assert result[5][3] == ""        # brand-list row cleared
        assert result[2][3] == "KLONAL"  # LITORAL
        assert result[3][3] == "KLONAL"  # VI-FARMA
        assert result[4][3] == "KLONAL"  # COMPAÑIA MEDICA
        assert result[6][3] == "KLONAL"  # S.R.L. (4th price row)

    def test_no_cotiza_entries_skipped(self):
        """'No cotiza' lines in the brand list are ignored, not assigned to providers."""
        rows = [
            _row("Proveedor", "Item", "Cant", "Descripcion", "Unidad", "PU", "Importe"),
            _row(item="1", desc="Drug A"),
            _row(proveedor="PROV A", desc="ELEA PM1\nNo cotiza\nNo cotiza"),
            _row(proveedor="PROV B", cant="10", pu="100"),
        ]
        result = _distribute_brands(rows)
        # Only 1 valid brand → only first price row gets it
        assert result[3][3] == "ELEA"

    def test_no_brand_list_row_unchanged(self):
        """Items without a multiline brand cell are left untouched."""
        rows = [
            _row("Proveedor", "Item", "Cant", "Descripcion", "Unidad", "PU", "Importe"),
            _row(item="5", desc="Drug B"),
            _row(proveedor="PROV A", cant="10", pu="100"),
            _row(proveedor="PROV B", cant="10", pu="200"),
        ]
        original = [list(r) for r in rows]
        result = _distribute_brands(rows)
        assert result == original

    def test_pm_codes_stripped_in_distributed_brands(self):
        """Brands injected into price rows have PM codes removed."""
        rows = [
            _row("Proveedor", "Item", "Cant", "Descripcion", "Unidad", "PU", "Importe"),
            _row(item="10", desc="Drug C"),
            _row(proveedor="PROV A", desc="LAFEDAR PM44893\nDENVER PM48432\nNo cotiza"),
            _row(proveedor="PROV B", cant="50", pu="500"),
            _row(proveedor="PROV C", cant="50", pu="600"),
        ]
        result = _distribute_brands(rows)
        assert result[3][3] == "LAFEDAR"
        assert result[4][3] == "DENVER"

    def test_brand_list_row_with_price_distributes_to_all(self):
        """pdfplumber sometimes merges the brand list into the first provider row,
        which also has a price. Brands should distribute to all price rows including
        the row that holds the brand list."""
        rows = [
            _row("Proveedor", "Item", "Cant", "Descripcion", "Unidad", "PU", "Importe"),
            _row(item="1", cant="105", desc="Sulfadiazina de plata"),
            # First provider: has brands AND a price (pdfplumber merged cells)
            _row(proveedor="VI-FARMA", cant="105",
                 desc="DENVER C.48432\nLEPETIT/LAFEDAR PM48886/44893\nNo cotiza",
                 pu="11970"),
            # Other providers: price only, no brand
            _row(proveedor="LIDER", cant="105", pu="12749"),
            _row(proveedor="20 DE JUNIO", cant="105", pu="13000"),
        ]
        result = _distribute_brands(rows)
        assert result[2][3] == "DENVER"          # first provider gets brand[0]
        assert result[3][3] == "LEPETIT/LAFEDAR"  # second provider gets brand[1]
        assert not result[4][3]                   # no brand left (No cotiza filtered)
