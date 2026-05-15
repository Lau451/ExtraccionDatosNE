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
        ['nombre','tipo','apertura','vencimiento','tipo_gestion','modalidad','estado','monto_estimado','notas'].forEach(k => {
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

    /* ─── Public exports ─────────────────────────────────────── */

    return { openModal, openPanelModal, apiActivas, _delete };

})();
