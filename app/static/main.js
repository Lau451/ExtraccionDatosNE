const inputArchivo = document.getElementById("archivo");
const estado = document.getElementById("estado");
const botonProcesar = document.getElementById("procesar-btn");

const fileLabel = document.getElementById("file-label");
const filePreview = document.getElementById("file-preview");
const fileIcon = document.getElementById("file-icon");
const nombreArchivo = document.getElementById("nombre-archivo");

// --------------------
// SELECCIÓN DE ARCHIVO
// --------------------
inputArchivo.addEventListener("change", () => {
    if (!inputArchivo.files.length) return;

    const file = inputArchivo.files[0];
    const ext = file.name.split(".").pop().toLowerCase();

    fileIcon.className = "file-icon";

    if (ext === "pdf") {
        fileIcon.classList.add("pdf");
        fileIcon.textContent = "PDF";
    } else if (["jpg", "jpeg", "png"].includes(ext)) {
        fileIcon.classList.add("image");
        fileIcon.textContent = "IMG";
    } else {
        fileIcon.classList.add("other");
        fileIcon.textContent = ext.toUpperCase();
    }

    nombreArchivo.textContent = file.name;

    fileLabel.classList.add("hidden");
    filePreview.classList.remove("hidden");
    botonProcesar.disabled = false;
});

// --------------------
// PROCESAR
// --------------------
botonProcesar.addEventListener("click", async () => {
    estado.textContent = "⏳ Procesando archivo...";
    botonProcesar.disabled = true;

    const formData = new FormData();
    formData.append("archivo", inputArchivo.files[0]);

    try {
        const response = await fetch("/procesar", {
            method: "POST",
            body: formData
        });

        if (!response.ok) throw new Error();

        estado.textContent = "✅ Archivo procesado correctamente";

    } catch {
        estado.textContent = "❌ Error al procesar el archivo";
        botonProcesar.disabled = false;
    }
});
