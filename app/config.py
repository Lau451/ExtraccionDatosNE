import importlib.util
import os
from pathlib import Path

from dotenv import load_dotenv
import google.generativeai as genai

# ======================
# ENV
# ======================
BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_PATH = BASE_DIR / "config_local.py"

load_dotenv()


def _load_local_config(config_path: Path):
    if not config_path.exists():
        return None

    try:
        spec = importlib.util.spec_from_file_location("config_local", config_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("No se pudo crear el loader del archivo")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        raise RuntimeError(
            f"El archivo de configuracion local existe pero es invalido: {config_path}. "
            f"Detalle: {exc}"
        ) from exc


LOCAL_CONFIG = _load_local_config(LOCAL_CONFIG_PATH)


def _resolve_output_base_dir() -> Path:
    env_path = os.getenv("OUTPUT_BASE_DIR")
    if env_path:
        return Path(env_path).expanduser()

    if LOCAL_CONFIG is not None:
        local_value = getattr(LOCAL_CONFIG, "OUTPUT_BASE_DIR", None)
        if not local_value:
            raise RuntimeError(
                f"El archivo {LOCAL_CONFIG_PATH} existe pero no define OUTPUT_BASE_DIR. "
                "Agrega OUTPUT_BASE_DIR o define la variable de entorno OUTPUT_BASE_DIR."
            )
        return Path(local_value).expanduser()

    raise RuntimeError(
        f"No se encontro configuracion local de rutas. Falta {LOCAL_CONFIG_PATH} y no esta definida "
        "la variable de entorno OUTPUT_BASE_DIR. Copia config_local.example.py a config_local.py "
        "o define OUTPUT_BASE_DIR en el entorno."
    )


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
DATA_DIR = BASE_DIR / "data"
OUTPUT_BASE = _resolve_output_base_dir()


def _safe_folder_value(raw_value: str, default_value: str) -> str:
    raw = str(raw_value).strip()
    if not raw:
        return ""

    limpio_chars = []
    prev_sep = False
    for ch in raw:
        if ch.isalnum() or ch in ("-", "_"):
            limpio_chars.append(ch)
            prev_sep = False
        elif not prev_sep:
            limpio_chars.append("_")
            prev_sep = True

    limpio = "".join(limpio_chars).strip("_")
    return limpio or default_value


def _ensure_dir(dir_path: Path, label: str) -> Path:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"No se pudo crear el directorio {label}: {dir_path}") from exc
    return dir_path


def _base_work_dir(
    base_dir: Path,
    origen_id: str = "",
) -> Path:
    current_dir = _ensure_dir(base_dir, "de salida")
    if origen_id.strip():
        origen_name = _safe_folder_value(origen_id, "ORIGEN")
        current_dir = _ensure_dir(current_dir / origen_name, "del origen")

    return current_dir


def get_output_dir(
    base_dir: Path = OUTPUT_BASE,
    origen_id: str = "",
) -> Path:
    return _base_work_dir(base_dir, origen_id=origen_id)


def get_processed_dir(
    base_dir: Path = OUTPUT_BASE,
    origen_id: str = "",
) -> Path:
    base_work_dir = _base_work_dir(base_dir, origen_id=origen_id)
    return _ensure_dir(base_work_dir / "Procesados", "de procesados")


def get_tmp_dir(
    base_dir: Path = OUTPUT_BASE,
    origen_id: str = "",
) -> Path:
    base_work_dir = _base_work_dir(base_dir, origen_id=origen_id)
    return _ensure_dir(base_work_dir / "tmp", "temporal")
