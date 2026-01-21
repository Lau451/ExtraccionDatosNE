import os
from dotenv import load_dotenv

import os
import time
import google.generativeai as genai
from pathlib import Path


load_dotenv()

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configurar la conexión con Gemini
genai.configure(api_key=GEMINI_API_KEY)
# Usamos gemini-1.5-flash que es excelente para documentos y OCR
model = genai.GenerativeModel('gemini-2.5-flash') 

# Directorios
base_dir = Path(__file__).parent
input_folder = base_dir / "Entrada"
output_folder = base_dir / "Salida"
processed_folder = base_dir / "Procesados"

# Crear carpetas si no existen
input_folder.mkdir(exist_ok=True)
output_folder.mkdir(exist_ok=True)
processed_folder.mkdir(exist_ok=True)

print("🤖 Robot de Extracción iniciado. Esperando archivos en 'Entrada'...")

while True:
    # Buscar archivos (PDF, JPG, PNG)
    archivos = [f for f in input_folder.iterdir() if f.is_file() and f.suffix.lower() in ['.pdf', '.jpg', '.jpeg', '.png']]

    for archivo in archivos:
        print(f"📄 Analizando: {archivo.name}...")
        nombre_sin_extension = archivo.stem
        
        try:
            # 1. Subir el archivo a la API
            archivo_subido = genai.upload_file(str(archivo))
            
            # 2. Preparar el Prompt Dinámico con el nombre del archivo
            prompt_final = f"""
            Analiza este documento y extrae la información solicitada en formato CSV.
            
            CAMPOS A EXTRAER:
            1. item: El número de renglón o índice.
            2. cantidad: La cantidad del producto solicitado.
            3. descripcion: El nombre o detalle del producto.
            4. origen: Debe ser exactamente este valor: {nombre_sin_extension}

            REGLAS OBLIGATORIAS:
            - Devuelve ÚNICAMENTE un CSV válido.
            - Usa punto y coma (;) como separador para evitar errores con las comas en las descripciones.
            - Incluye encabezado: item;cantidad;descripcion;origen
            - Sin texto adicional, sin saludos, sin bloques de código (```).
            - Una fila por cada producto encontrado.
            - Si no encuentras un dato, deja el espacio vacío.
            """

            # 3. Generar la respuesta
            respuesta = model.generate_content([prompt_final, archivo_subido])
            
            # Limpieza básica por si la IA incluye delimitadores de código
            contenido_csv = respuesta.text.replace("```csv", "").replace("```", "").strip()

            # 4. Guardar el resultado en la carpeta Salida
            nombre_salida = f"{nombre_sin_extension}.csv"
            ruta_salida = output_folder / nombre_salida
            
            with open(ruta_salida, "w", encoding="utf-8") as f:
                f.write(contenido_csv)
                
            print(f"✅ CSV generado con éxito: {nombre_salida}")

            # 5. Mover el archivo original a "Procesados"
            archivo.rename(processed_folder / archivo.name)

        except Exception as e:
            print(f"❌ Error procesando {archivo.name}: {e}")

    # Esperar 5 segundos antes de la siguiente revisión
    time.sleep(5)