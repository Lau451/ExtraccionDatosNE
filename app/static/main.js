/* ============================================
   SAFE BINDING HELPER
   ============================================ */

function bindOrWarn(el, label, event, handler) {
    if (!el) {
        console.error(`[main.js] Missing element: ${label} (event: ${event})`);
        return false;
    }
    el.addEventListener(event, handler);
    return true;
}

/* ============================================
   NAVEGACIÓN FLUIDA ENTRE HOME Y UPLOAD
   ============================================ */

function initFluidNavigation() {
    const homeWrapper = document.getElementById("home-wrapper");
    if (!homeWrapper) return; // no estamos en home

    const navOverlay = document.getElementById("nav-overlay");
    const navContainer = document.getElementById("nav-container");
    const docTypesGrid = document.getElementById("doc-types-grid");

    if (!navOverlay || !navContainer || !docTypesGrid) {
        console.error("Missing required elements");
        return;
    }

    // Evita doble binding
    if (docTypesGrid.dataset.fluidNavBound === "true") return;
    docTypesGrid.dataset.fluidNavBound = "true";

    let isNavigating = false;

    // Delegación de eventos: navegar a página de upload con animación
    bindOrWarn(docTypesGrid, "#doc-types-grid", "click", (event) => {
        const card = event.target.closest(".doc-type-card[data-tipo]");
        if (!card || !docTypesGrid.contains(card)) return;

        event.preventDefault();
        event.stopPropagation();

        const tipo = card.dataset.tipo;
        if (!tipo) return;

        card.classList.add("clicking");

        // Navegar instantáneamente
        window.location.href = `/upload?tipo=${tipo}`;
    });
}

// Execute when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFluidNavigation);
} else {
    initFluidNavigation();
}

// Clean up animations when returning via browser back/forward
window.addEventListener("pageshow", (event) => {
    // Only fix animations if we came from bfcache (persisted entry)
    if (event.persisted) {
        const homeWrapper = document.getElementById("home-wrapper");
        if (homeWrapper) {
            homeWrapper.style.animation = "none";
            homeWrapper.classList.remove("navigating");
        }

        const uploadCard = document.getElementById("upload-card");
        if (uploadCard) {
            uploadCard.style.animation = "none";
        }
    }
});

/* ============================================
   UPLOAD FORM SETUP
   ============================================ */

function setupUploadForm() {
    const form = document.getElementById("upload-form");

    // Salir temprano si no estamos en una página de upload
    if (!form) {
        console.debug("No upload form found, skipping setup");
        return;
    }

    console.log("🔧 Setting up upload form");

    const inputArchivo = document.getElementById("archivo");
    const estado = document.getElementById("estado");
    const botonProcesar = document.getElementById("procesar-btn");
    const botonNuevo = document.getElementById("nuevo-btn");
    const fileLabel = document.getElementById("file-label");
    const filePreview = document.getElementById("file-preview");
    const fileIcon = document.getElementById("file-icon");
    const nombreArchivo = document.getElementById("nombre-archivo");
    const botonCancelar = document.getElementById("cancelar-btn");
    const progressContainer = document.getElementById("progress-container");
    const progressBar = document.getElementById("progress-bar");

    // Guard: verificar que existan los elementos críticos
    if (!inputArchivo || !estado || !botonProcesar) {
        console.debug("Missing critical form elements, skipping setup");
        return;
    }

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
        } else if (["xls", "xlsx", "ods"].includes(ext)) {
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

    // File input change
    bindOrWarn(inputArchivo, "#archivo", "change", () => {
        if (inputArchivo.files.length) {
            setFile(inputArchivo.files[0]);
        }
    });

    // Drag & drop
    ["dragenter", "dragover"].forEach((evento) => {
        bindOrWarn(fileLabel, "#file-label", evento, (e) => {
            e.preventDefault();
            fileLabel.classList.add("is-dragover");
        });
    });

    ["dragleave", "drop"].forEach((evento) => {
        bindOrWarn(fileLabel, "#file-label", evento, (e) => {
            e.preventDefault();
            fileLabel.classList.remove("is-dragover");
        });
    });

    bindOrWarn(fileLabel, "#file-label", "drop", (e) => {
        const file = e.dataTransfer.files[0];
        if (file) {
            setFile(file);
        }
    });

    // Form submit
    bindOrWarn(form, "#upload-form", "submit", async (e) => {
        e.preventDefault();

        if (!inputArchivo.files.length) return;

        estado.textContent = "Procesando archivo...";
        botonProcesar.disabled = true;
        progressContainer.classList.remove("hidden");
        progressBar.style.width = "0%";

        let progress = 0;
        const timer = setInterval(() => {
            progress = Math.min(progress + 7, 90);
            progressBar.style.width = `${progress}%`;
        }, 250);

        const formData = new FormData();
        formData.append("archivo", inputArchivo.files[0]);
        formData.append("tipo", document.getElementById("tipo-input")?.value || "");

        try {
            const response = await fetch("/procesar", {
                method: "POST",
                headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "fetch",
                },
                body: formData
            });

            const payload = await response.json();

            if (!response.ok) {
                throw new Error(payload?.error || "Error al procesar el archivo");
            }
            if (!payload?.resultado) {
                throw new Error("La respuesta no incluyó link de descarga");
            }

            clearInterval(timer);
            progressBar.style.width = "100%";

            estado.innerHTML = "";
            const msg = document.createElement("span");
            msg.textContent = "✅ Archivo procesado correctamente. ";

            const link = document.createElement("a");
            link.href = payload.resultado;
            link.textContent = "Descargar CSV";
            link.rel = "noopener noreferrer";

            estado.appendChild(msg);
            estado.appendChild(link);

            botonNuevo.classList.remove("hidden");
        } catch (err) {
            console.error("Processing error:", err);
            clearInterval(timer);
            estado.textContent = `❌ ${err.message || "Error al procesar el archivo"}`;
            botonProcesar.disabled = false;
        } finally {
            setTimeout(() => {
                progressContainer.classList.add("hidden");
                progressBar.style.width = "0%";
            }, 800);
        }
    });

    // Reset buttons
    bindOrWarn(botonNuevo, "#nuevo-btn", "click", resetUI);
    bindOrWarn(botonCancelar, "#cancelar-btn", "click", resetUI);
}

// Initialize on regular page load
if (!document.getElementById("home-wrapper")) {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupUploadForm);
    } else {
        setupUploadForm();
    }
}

// Setup back button on upload page
const backBtn = document.getElementById("back-btn");
if (backBtn) {
    backBtn.addEventListener("click", () => {
        window.location.href = "/";
    });
}
