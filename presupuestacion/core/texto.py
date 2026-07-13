import re
import unicodedata


def normalizar_descripcion(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    sin_puntuacion = re.sub(r"[^\w\s]", " ", sin_tildes)
    return re.sub(r"\s+", " ", sin_puntuacion).strip().upper()
