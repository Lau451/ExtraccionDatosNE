"""Output folders of the extractor under OUTPUT_BASE_DIR (one folder per document type,
one subfolder per client)."""
from pathlib import Path
from types import SimpleNamespace

from services.extraccion import config, robot, robot_comparativas, robot_orden_compra


def test_each_document_type_has_its_own_folder_under_the_output_base():
    assert config.LICITACIONES_OUTPUT_BASE == config.OUTPUT_BASE / "licitaciones" / "directas"
    assert config.ORDENES_COMPRA_OUTPUT_BASE == config.OUTPUT_BASE / "ordenes_compra"
    assert config.COMPARATIVAS_OUTPUT_BASE == config.OUTPUT_BASE / "comparativas"


def _redirigir(monkeypatch, tmp_path: Path, modulo) -> None:
    """Points the module's folder helpers at tmp_path while keeping the base_dir the
    module asks for, so the test sees which base each robot uses."""
    def output_dir(base_dir=config.OUTPUT_BASE, origen_id="", ensure_exists=True):
        relativa = Path(base_dir).relative_to(config.OUTPUT_BASE)
        return config.get_output_dir(tmp_path / relativa, origen_id, ensure_exists)

    def processed_dir(base_dir=config.OUTPUT_BASE, origen_id="", ensure_exists=True):
        relativa = Path(base_dir).relative_to(config.OUTPUT_BASE)
        return config.get_processed_dir(tmp_path / relativa, origen_id, ensure_exists)

    monkeypatch.setattr(modulo, "get_output_dir", output_dir)
    monkeypatch.setattr(modulo, "get_processed_dir", processed_dir)


def test_orden_compra_csv_and_source_go_to_ordenes_compra(monkeypatch, tmp_path):
    _redirigir(monkeypatch, tmp_path, robot_orden_compra)
    origen = tmp_path / "entrada.pdf"
    origen.write_bytes(b"%PDF")

    csv_path = robot_orden_compra._escribir_csv([], "OC1", "HOSPITAL")
    movido = robot_orden_compra._mover_a_procesados(origen, "OC1", ".pdf", "HOSPITAL")

    assert csv_path == tmp_path / "ordenes_compra" / "HOSPITAL" / "OC1.csv"
    assert movido == tmp_path / "ordenes_compra" / "HOSPITAL" / "Procesados" / "OC1.pdf"


def test_comparativa_csv_still_goes_to_comparativas(monkeypatch, tmp_path):
    _redirigir(monkeypatch, tmp_path, robot_comparativas)

    csv_path = robot_comparativas._escribir_csv([], "CMP1", "HOSPITAL")

    assert csv_path == tmp_path / "comparativas" / "HOSPITAL" / "CMP1.csv"


def test_licitacion_csv_and_source_go_to_licitaciones_directas(monkeypatch, tmp_path):
    _redirigir(monkeypatch, tmp_path, robot)
    origen = tmp_path / "HOSPITAL_LIC1.pdf"
    origen.write_bytes(b"%PDF")

    class _Respuesta:
        text = "item;descripcion;cantidad\n1;Gasas;10\n"

    class _Archivos:
        def upload(self, file):
            return SimpleNamespace(state="ACTIVE")

    class _Cliente:
        files = _Archivos()

    monkeypatch.setattr(robot, "get_next_client", lambda: _Cliente())
    monkeypatch.setattr(robot, "CLIENT", _Cliente())
    monkeypatch.setattr(robot, "generate_with_fallback", lambda *a, **k: _Respuesta())

    csv_path = robot.procesar_archivo(origen, origen.name)

    carpeta = tmp_path / "licitaciones" / "directas" / "HOSPITAL"
    assert Path(csv_path).parent == carpeta
    assert (carpeta / "Procesados" / "HOSPITAL_LIC1.pdf").exists()
