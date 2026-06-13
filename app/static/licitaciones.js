/* =============================================================
   LicitacionesModule — IIFE exportada a window

   API pública:
     apiActivas()              → Promise<LicitacionActiva[]>
     openModal({ onCreated })  → abre el <dialog> de creación
     openPanelModal(config)    → abre modal de creación/edición en el panel
   ============================================================= */

window.LicitacionesModule = (function () {

    /* ─── API helpers ─────────────────────────────────────────── */

    async function apiActivas() {
        try {
            const res = await fetch('/api/licitaciones/activas');
            if (!res.ok) return [];
            return await res.json();
        } catch {
            return [];
        }
    }

    async function _post(payload) {
        const res = await fetch('/api/licitaciones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            const msg = Array.isArray(err.detail)
                ? err.detail.map(e => e.msg).join(', ')
                : err.detail || 'Error al crear la licitación';
            throw new Error(msg);
        }
        return await res.json();
    }

    async function _patch(id, payload) {
        const res = await fetch(`/api/licitaciones/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Error al actualizar la licitación');
        }
        return await res.json();
    }

    async function _delete(id) {
        const res = await fetch(`/api/licitaciones/${id}`, {
            method: 'DELETE',
            headers: { 'Accept': 'application/json' },
        });
        if (!res.ok && res.status !== 204) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Error al eliminar la licitación');
        }
    }

    /* ─── Upload-page modal (creación rápida) ─────────────────── */

    function openModal({ onCreated } = {}) {
        const dialog = document.getElementById('lic-modal-dialog');
        if (!dialog) return;

        _setupDialogForm(dialog, null, (lic) => {
            dialog.close();
            if (onCreated) onCreated(lic);
        });

        dialog.showModal();
    }

    /* ─── Panel modal (creación / edición) ───────────────────── */

    function openPanelModal({ mode = 'create', licData = null, onSaved } = {}) {
        const dialog = document.getElementById('lic-modal-dialog');
        if (!dialog) return;

        const titleEl = dialog.querySelector('[data-modal-title]');
        if (titleEl) titleEl.textContent = mode === 'edit' ? 'Editar Licitación' : 'Nueva Licitación';

        if (mode === 'edit' && licData) _fillForm(dialog, licData);
        else { const f = dialog.querySelector('form'); if (f) f.reset(); }

        _setupDialogForm(dialog, mode === 'edit' ? licData?.id : null, (lic) => {
            dialog.close();
            if (onSaved) onSaved(lic);
        });

        dialog.showModal();
    }

    /* ─── Internals ───────────────────────────────────────────── */

    function _fillForm(dialog, data) {
        const f = dialog.querySelector('form');
        if (!f) return;
        f.reset();
        ['nombre','tipo','cliente','apertura','vencimiento','tipo_gestion','modalidad','estado','monto_estimado','notas'].forEach(k => {
            const el = f.elements[k];
            if (el && data[k] != null) el.value = data[k];
        });
    }

    function _setupDialogForm(dialog, editId, onDone) {
        const errEl  = dialog.querySelector('#lic-modal-error');
        const oldForm = dialog.querySelector('form');
        if (!oldForm) return;

        // Clone to remove old event listeners
        const form = oldForm.cloneNode(true);
        oldForm.parentNode.replaceChild(form, oldForm);

        if (errEl) errEl.textContent = '';

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const submitBtn = form.querySelector('[data-submit]');
            const localErr  = dialog.querySelector('#lic-modal-error');

            const raw = Object.fromEntries(new FormData(form));
            const payload = {};
            Object.entries(raw).forEach(([k, v]) => {
                if (v !== '') payload[k] = v;
            });

            if (!payload.apertura) {
                if (localErr) localErr.textContent = 'La fecha de apertura es obligatoria';
                return;
            }

            if (submitBtn) submitBtn.disabled = true;
            if (localErr)  localErr.textContent = '';

            try {
                const result = editId
                    ? await _patch(editId, payload)
                    : await _post(payload);
                onDone(result);
            } catch (err) {
                if (localErr) localErr.textContent = err.message;
            } finally {
                if (submitBtn) submitBtn.disabled = false;
            }
        });

        // Cancel button
        const cancelBtn = dialog.querySelector('[data-cancel]');
        if (cancelBtn) {
            const newCancel = cancelBtn.cloneNode(true);
            cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
            newCancel.addEventListener('click', () => dialog.close());
        }

        // Close on backdrop click
        dialog.addEventListener('click', (e) => {
            if (e.target === dialog) dialog.close();
        }, { once: true });
    }

    /* ─── Detalle — documentos vinculados ────────────────────── */

    const _ESC_DET = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');

    const _STATUS_LBL = { completed: 'Completado', partial: 'Parcial', failed: 'Error', running: 'Procesando' };

    const _DOC_TYPE_OPTS = [
        { value: 'comparativa',  label: 'Comparativa' },
        { value: 'licitacion',   label: 'Licitación' },
        { value: 'orden_compra', label: 'Orden de compra' },
    ];

    async function _patchExtraction(id, payload) {
        const res = await fetch(`/api/extraction-results/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Error al actualizar el documento');
        }
        return await res.json();
    }

    function _setDetalleState(state) {
        document.getElementById('det-loading').classList.toggle('hidden', state !== 'loading');
        document.getElementById('det-empty').classList.toggle('hidden',   state !== 'empty');
        document.getElementById('det-table').classList.toggle('hidden',   state !== 'table');
    }

    function _renderDetalleArchivos(archivos, licId) {
        if (!archivos || !archivos.length) { _setDetalleState('empty'); return; }

        const formatDate = iso => {
            if (!iso) return '—';
            try {
                const d = new Date(iso);
                return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
            } catch { return iso; }
        };

        document.getElementById('det-tbody').innerHTML = archivos.map(a => {
            const typeLabel = (_DOC_TYPE_OPTS.find(o => o.value === a.document_type) || { label: a.document_type }).label;
            return `
            <tr id="det-row-${a.id}">
                <td><span class="doc-filename" title="${_ESC_DET(a.source_filename)}">${_ESC_DET(a.source_filename)}</span></td>
                <td><span class="tipo-chip ${_ESC_DET(a.document_type)}">${_ESC_DET(typeLabel)}</span></td>
                <td><span class="status-chip ${_ESC_DET(a.status)}">${_ESC_DET(_STATUS_LBL[a.status] || a.status)}</span></td>
                <td>${formatDate(a.created_at)}</td>
                <td>
                    <button class="btn-action det-btn-desvincular"
                        onclick="window.LicitacionesModule.desvincularDoc('${a.id}', '${licId}')">
                        Desvincular
                    </button>
                </td>
            </tr>`;
        }).join('');
        _setDetalleState('table');
    }

    async function openDetalle(licId) {
        const dialog = document.getElementById('lic-detalle-dialog');
        if (!dialog) return;

        const errEl = document.getElementById('det-error');
        if (errEl) errEl.textContent = '';

        _setDetalleState('loading');
        dialog.showModal();

        document.getElementById('det-close').onclick = () => dialog.close();
        dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); }, { once: true });

        try {
            const res = await fetch(`/api/licitaciones/${licId}`);
            if (!res.ok) throw new Error('Error al cargar la licitación');
            const lic = await res.json();

            const titleEl = document.getElementById('det-title');
            if (titleEl) titleEl.textContent = lic.nombre;

            const metaEl = document.getElementById('det-meta');
            if (metaEl) {
                const TIPO_LBL = { medicamentos:'Medicamentos', descartables:'Descartables', soluciones:'Soluciones', panales:'Pañales', formulas:'Fórmulas' };
                const EST_LBL  = { abierta:'Abierta', en_evaluacion:'En evaluación', adjudicada:'Adjudicada', cerrada:'Cerrada' };
                metaEl.innerHTML = `
                    <span class="tipo-chip ${_ESC_DET(lic.tipo)}">${_ESC_DET(TIPO_LBL[lic.tipo] || lic.tipo)}</span>
                    <span class="lic-estado-chip ${_ESC_DET(lic.estado)}">${_ESC_DET(EST_LBL[lic.estado] || lic.estado)}</span>
                `;
            }

            _renderDetalleArchivos(lic.archivos || [], licId);
        } catch (err) {
            if (errEl) errEl.textContent = err.message;
            _setDetalleState('empty');
        }
    }

    async function desvincularDoc(extractionId, licId) {
        if (!confirm('¿Desvincular este documento de la licitación?')) return;
        const errEl = document.getElementById('det-error');
        if (errEl) errEl.textContent = '';

        try {
            await _patchExtraction(extractionId, { licitacion_id: null });
            const row = document.getElementById(`det-row-${extractionId}`);
            if (row) row.remove();
            const tbody = document.getElementById('det-tbody');
            if (tbody && !tbody.children.length) _setDetalleState('empty');
            if (typeof loadLics === 'function') loadLics();
        } catch (err) {
            if (errEl) errEl.textContent = err.message;
        }
    }

    /* ─── Public exports ─────────────────────────────────────── */

    return { openModal, openPanelModal, apiActivas, _delete, openDetalle, desvincularDoc };

})();
