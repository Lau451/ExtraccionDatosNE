import os
from pathlib import Path
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

INPUT_DIR = DATA_DIR / "Entrada"
OUTPUT_DIR = DATA_DIR / "Salida"
PROCESSED_DIR = DATA_DIR / "Procesados"

for d in (INPUT_DIR, OUTPUT_DIR, PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)