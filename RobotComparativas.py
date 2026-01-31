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
# Usamos gemini-2.5-flash que es excelente para documentos y OCR
model = genai.GenerativeModel('gemini-2.5-flash') 

# Directorios
base_dir = Path(__file__).parent
input_folder = base_dir / "Entrada_Comparativas"
output_folder = base_dir / "Salida_Comparativas"
processed_folder = base_dir / "Procesados"

input_folder.mkdir(exist_ok=True)
output_folder.mkdir(exist_ok=True)
processed_folder.mkdir(exist_ok=True)

print("🤖 Analizador de Comparativas iniciado...")

while True:
    archivos = [f for f in input_folder.iterdir() if f.is_file() and f.suffix.lower() in ['.pdf', '.jpg', '.jpeg', '.png', '.csv']]

    for archivo in archivos:
        print(f"📄 Archivo detectado: {archivo.name}")
        nombre_entidad = archivo.stem
        
        try:
            # 1. Subir archivo
            print("⏳ Subiendo archivo a la nube de Google...")
            archivo_subido = genai.upload_file(str(archivo))
            
            # 2. Prompt con lógica de Negocio (Top 3 precios)
            print("🧠 Gemini está analizando y comparando precios (esto puede tardar)...")
            prompt_comparativa = f"""
            Analiza esta tabla comparativa de precios de licitación.
            
            Tu objetivo es extraer, para cada producto/ítem listado, los datos de los 3 proveedores que ofrecieron los precios más bajos.

            CAMPOS POR FILA EN EL CSV:
            1. entidad: Usa exactamente este valor: {nombre_entidad}
            2. item: Número de renglón o ítem.
            3. producto: Descripción del producto.
            4. proveedor: Nombre de la empresa que cotiza.
            5. marca: Marca del producto ofrecida por ese proveedor (si no hay, dejar vacío).
            6. precio: Valor unitario o total cotizado por ese proveedor.

            REGLAS LÓGICAS:
            - Por cada ítem del documento, identifica a todos los proveedores que cotizaron.
            - Selecciona únicamente los 3 proveedores con el precio más bajo para ese ítem.
            - Si un ítem tiene menos de 3 proveedores, trae los que haya.
            - Si un proveedor dice "No cotiza", ignóralo.

            FORMATO DE SALIDA:
            - CSV con delimitador punto y coma (;).
            - Encabezado: entidad;item;producto;proveedor;marca;precio
            - Sin texto adicional, solo el contenido del CSV.
            """

            # 3. Generación
            respuesta = model.generate_content([prompt_comparativa, archivo_subido])
            
            # Limpieza y guardad00
            print("📝 Respuesta recibida. Limpiando datos...")
            contenido_csv = respuesta.text.replace("```csv", "").replace("```", "").strip()
            
            nombre_salida = f"Resumen_{nombre_entidad}.csv"
            with open(output_folder / nombre_salida, "w", encoding="utf-8") as f:
                f.write(contenido_csv)
                
            print(f"✅ Comparativa analizada: {nombre_salida}")
            archivo.rename(processed_folder / archivo.name)

        except Exception as e:
            print(f"❌ Error en {archivo.name}: {e}")

    time.sleep(5)