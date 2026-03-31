const inputArchivo = document.getElementById("archivo");
const estado = document.getElementById("estado");
const botonProcesar = document.getElementById("procesar-btn");
const form = document.getElementById("upload-form");
const botonNuevo = document.getElementById("nuevo-btn");

const fileLabel = document.getElementById("file-label");
const filePreview = document.getElementById("file-preview");
const fileIcon = document.getElementById("file-icon");
const nombreArchivo = document.getElementById("nombre-archivo");
const botonCancelar = document.getElementById("cancelar-btn");

const progressContainer = document.getElementById("progress-container");
const progressBar = document.getElementById("progress-bar");

const resetUI = () => {
    inputArchivo.value = "";
    estado.textContent = "";
    botonProcesar.disabled = true;

    fileLabel.classList.remove("hidden");
    filePreview.classList.add("hidden");
    nombreArchivo.textContent = "";
    fileIcon.className = "file-icon";
    fileIcon.innerHTML = "";

    progressContainer.classList.add("hidden");
    progressBar.style.width = "0%";
    progressBar.setAttribute("aria-valuenow", "0");

    botonNuevo.classList.add("hidden");
};

const setFile = (file) => {
    if (!file) return;

    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    inputArchivo.files = dataTransfer.files;

    const ext = file.name.split(".").pop().toLowerCase();

    const svgPDF = `<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="9" y1="13" x2="15" y2="13"/>
        <line x1="9" y1="17" x2="13" y2="17"/>
    </svg>`;

    const svgImage = `<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <circle cx="8.5" cy="8.5" r="1.5"/>
        <polyline points="21 15 16 10 5 21"/>
    </svg>`;

    const svgExcel = `<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
        <line x1="3" y1="9" x2="21" y2="9"/>
        <line x1="3" y1="15" x2="21" y2="15"/>
        <line x1="9" y1="3" x2="9" y2="21"/>
        <line x1="15" y1="3" x2="15" y2="21"/>
    </svg>`;

    const svgOther = `<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
    </svg>`;

    fileIcon.className = "file-icon";

    if (ext === "pdf") {
        fileIcon.classList.add("pdf");
        fileIcon.innerHTML = svgPDF;
    } else if (["jpg", "jpeg", "png"].includes(ext)) {
        fileIcon.classList.add("image");
        fileIcon.innerHTML = svgImage;
    } else if (["xls", "xlsx"].includes(ext)) {
        fileIcon.classList.add("excel");
        fileIcon.innerHTML = svgExcel;
    } else {
        fileIcon.classList.add("other");
        fileIcon.innerHTML = svgOther;
    }

    nombreArchivo.textContent = file.name;

    fileLabel.classList.add("hidden");
    filePreview.classList.remove("hidden");
    botonProcesar.disabled = false;
    botonNuevo.classList.add("hidden");
};

// --------------------
// SELECCION DE ARCHIVO
// --------------------
inputArchivo.addEventListener("change", () => {
    if (!inputArchivo.files.length) return;
    setFile(inputArchivo.files[0]);
});

// --------------------
// DRAG & DROP
// --------------------
["dragenter", "dragover"].forEach((evento) => {
    fileLabel.addEventListener(evento, (event) => {
        event.preventDefault();
        event.stopPropagation();
        fileLabel.classList.add("is-dragover");
    });
});

["dragleave", "drop"].forEach((evento) => {
    fileLabel.addEventListener(evento, (event) => {
        event.preventDefault();
        event.stopPropagation();
        fileLabel.classList.remove("is-dragover");
    });
});

fileLabel.addEventListener("drop", (event) => {
    const droppedFile = event.dataTransfer.files[0];
    if (!droppedFile) return;
    setFile(droppedFile);
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
botonNuevo.addEventListener("click", resetUI);

// --------------------
// CANCELAR ARCHIVO
// --------------------
botonCancelar.addEventListener("click", resetUI);
