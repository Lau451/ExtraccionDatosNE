const inputArchivo = document.getElementById("archivo");
const estado = document.getElementById("estado");
const botonProcesar = document.getElementById("procesar-btn");
const form = document.getElementById("upload-form");
const botonNuevo = document.getElementById("nuevo-btn");

const fileLabel = document.getElementById("file-label");
const filePreview = document.getElementById("file-preview");
const fileIcon = document.getElementById("file-icon");
const nombreArchivo = document.getElementById("nombre-archivo");

const progressContainer = document.getElementById("progress-container");
const progressBar = document.getElementById("progress-bar");

// --------------------
// SELECCION DE ARCHIVO
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
    } else if (["xls", "xlsx"].includes(ext)) {
        fileIcon.classList.add("other");
        fileIcon.textContent = "XLS";
    } else {
        fileIcon.classList.add("other");
        fileIcon.textContent = ext.toUpperCase();
    }

    nombreArchivo.textContent = file.name;

    fileLabel.classList.add("hidden");
    filePreview.classList.remove("hidden");
    botonProcesar.disabled = false;
    botonNuevo.classList.add("hidden");
});

// --------------------
// PROCESAR
// --------------------
form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!inputArchivo.files.length) return;

    estado.textContent = "Procesando archivo...";
    botonProcesar.disabled = true;
    botonNuevo.classList.add("hidden");
    progressContainer.classList.remove("hidden");
    progressBar.style.width = "0%";
    progressBar.setAttribute("aria-valuenow", "0");

    let progress = 0;
    const progressTimer = setInterval(() => {
        progress = Math.min(progress + 7, 90);
        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute("aria-valuenow", String(progress));
    }, 250);

    const formData = new FormData();
    formData.append("archivo", inputArchivo.files[0]);

    try {
        const response = await fetch("/procesar", {
            method: "POST",
            body: formData
        });

        if (!response.ok) throw new Error();

        clearInterval(progressTimer);
        progressBar.style.width = "100%";
        progressBar.setAttribute("aria-valuenow", "100");

        estado.textContent = "Archivo procesado correctamente. El CSV fue guardado en el servidor.";
        botonNuevo.classList.remove("hidden");
    } catch {
        clearInterval(progressTimer);
        estado.textContent = "Error al procesar el archivo";
        botonProcesar.disabled = false;
    } finally {
        setTimeout(() => {
            progressContainer.classList.add("hidden");
            progressBar.style.width = "0%";
            progressBar.setAttribute("aria-valuenow", "0");
        }, 800);
    }
});

// --------------------
// NUEVO ARCHIVO
// --------------------
botonNuevo.addEventListener("click", () => {
    inputArchivo.value = "";
    estado.textContent = "";
    botonProcesar.disabled = true;

    fileLabel.classList.remove("hidden");
    filePreview.classList.add("hidden");
    nombreArchivo.textContent = "";
    fileIcon.className = "file-icon";

    progressContainer.classList.add("hidden");
    progressBar.style.width = "0%";
    progressBar.setAttribute("aria-valuenow", "0");

    botonNuevo.classList.add("hidden");
});
