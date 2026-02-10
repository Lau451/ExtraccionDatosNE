import os
import socket
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
import google.generativeai as genai

# ======================
# ENV
# ======================
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Falta GEMINI_API_KEY")

# ======================
# MODELO IA
# ======================
genai.configure(api_key=GEMINI_API_KEY)
MODEL = genai.GenerativeModel("gemini-2.5-flash")

# ======================
# PATHS
# ======================

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

OUTPUT_BASE = Path(r"C:\Users\LAUREANO\OneDrive\Escritorio\ExtraccionDatosNE\data\Salida")


def _safe_hostname() -> str:
    host = socket.gethostname().strip()
    limpio = "".join(c for c in host if c.isalnum() or c in ("-", "_"))
    return limpio or "UNKNOWN_HOST"


def _ensure_dir(dir_path: Path, label: str) -> Path:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"No se pudo crear el directorio {label}: {dir_path}") from exc
    return dir_path


def get_output_dir(base_dir: Path = OUTPUT_BASE) -> Path:
    host_dir = _ensure_dir(base_dir / _safe_hostname(), "del host")
    fecha_dir = host_dir / date.today().isoformat()
    return _ensure_dir(fecha_dir, "de salida")


def get_processed_dir(base_dir: Path = OUTPUT_BASE) -> Path:
    host_dir = _ensure_dir(base_dir / _safe_hostname(), "del host")
    fecha_dir = host_dir / date.today().isoformat()
    return _ensure_dir(fecha_dir / "Procesados", "de procesados")


def get_tmp_dir(base_dir: Path = OUTPUT_BASE) -> Path:
    host_dir = _ensure_dir(base_dir / _safe_hostname(), "del host")
    fecha_dir = host_dir / date.today().isoformat()
    return _ensure_dir(fecha_dir / "tmp", "temporal")


OUTPUT_DIR = get_output_dir()
PROCESSED_DIR = get_processed_dir()
TMP_DIR = get_tmp_dir()
