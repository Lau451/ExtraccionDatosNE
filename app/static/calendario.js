/* =============================================================
   CalendarioModule — IIFE exportada a window
   ============================================================= */

window.CalendarioModule = (function () {

    let allItems = [];
    let currentComp = '';
    let currentSearch = '';
    let baseYear = new Date().getFullYear();

    const MESES = [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
    ];

    const COMP_LBL = {
        cargada: 'Cargada',
        pedida: 'Pedida',
        sin_comparativa: 'Sin comparativa',
    };

    const ESC = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');

    /* ─── API ─────────────────────────────────────────────────── */

    function getDateRange() {
        return {
            desde: `${baseYear}-01-01`,
            hasta: `${baseYear + 1}-12-31`,
        };
    }

    function updateYearDisplay() {
        const el = document.getElementById('year-range-label');
        if (el) el.textContent = `${baseYear} – ${baseYear + 1}`;
    }

    function navegarAño(delta) {
        baseYear += delta;
        updateYearDisplay();
        loadCalendario();
    }

    async function loadCalendario() {
        setState('loading');
        try {
            const { desde, hasta } = getDateRange();
            const res = await fetch(`/api/licitaciones/calendario?desde=${desde}&hasta=${hasta}`);
            if (!res.ok) throw new Error('Error al cargar el calendario');
            allItems = await res.json();
            render();
        } catch {
            setState('empty');
        }
    }

    async function marcarPedida(id) {
        const btn = document.querySelector(`[data-pedir="${id}"]`);
        if (btn) btn.disabled = true;
        try {
            const res = await fetch(`/api/licitaciones/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ comparativa_estado: 'pedida' }),
            });
            if (!res.ok) throw new Error('Error al actualizar');
            const item = allItems.find(i => i.id === id);
            if (item) item.comparativa_estado = 'pedida';
            rerenderRow(id);
        } catch {
            if (btn) btn.disabled = false;
        }
    }

    async function anularPedida(id) {
        const btn = document.querySelector(`[data-anular="${id}"]`);
        if (btn) btn.disabled = true;
        try {
            const res = await fetch(`/api/licitaciones/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ comparativa_estado: null }),
            });
            if (!res.ok) throw new Error('Error al anular');
            const item = allItems.find(i => i.id === id);
            if (item) item.comparativa_estado = 'sin_comparativa';
            rerenderRow(id);
        } catch {
            if (btn) btn.disabled = false;
        }
    }

    /* ─── Agrupación por mes ──────────────────────────────────── */

    function groupByMonth(items) {
        const map = {};
        for (const it of items) {
            const dateStr = it.apertura || it.vencimiento;
            let key, label;
            if (dateStr) {
                const d = new Date(dateStr + 'T00:00:00');
                const y = d.getFullYear();
                const m = d.getMonth();
                key = `${y}-${String(m + 1).padStart(2, '0')}`;
                label = `${MESES[m]} ${y}`;
            } else {
                key = 'sin-fecha';
                label = 'Sin fecha';
            }
            if (!map[key]) map[key] = { key, label, items: [] };
            map[key].items.push(it);
        }
        return Object.values(map).sort((a, b) => {
            if (a.key === 'sin-fecha') return 1;
            if (b.key === 'sin-fecha') return -1;
            return a.key.localeCompare(b.key);
        });
    }

    /* ─── Estado de la vista ─────────────────────────────────── */

    function setState(state) {
        document.getElementById('loading-state').classList.toggle('hidden', state !== 'loading');
        document.getElementById('empty-state').classList.toggle('hidden',   state !== 'empty');
        document.getElementById('cal-months').classList.toggle('hidden',    state !== 'months');
    }

    /* ─── Chips y helpers ─────────────────────────────────────── */

    function compChip(estado) {
        const cls = estado === 'cargada' ? 'comp-chip--cargada'
                  : estado === 'pedida'  ? 'comp-chip--pedida'
                  : 'comp-chip--sin';
        return `<span class="comp-chip ${cls}">${ESC(COMP_LBL[estado] || estado)}</span>`;
    }

    function formatDate(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso + 'T00:00:00');
            return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
        } catch { return iso; }
    }

    /* ─── HTML de cada fila ───────────────────────────────────── */

    function rowHtml(it) {
        const fechaLabel = it.apertura
            ? `Apertura: ${formatDate(it.apertura)}`
            : it.vencimiento
            ? `Vence: ${formatDate(it.vencimiento)}`
            : '—';

        let accionBtn = '<div></div>';
        if (it.comparativa_estado === 'sin_comparativa') {
            accionBtn = `<button class="btn-action btn-pedir" data-pedir="${ESC(it.id)}"
                onclick="window.CalendarioModule.marcarPedida('${ESC(it.id)}')">Pedir</button>`;
        } else if (it.comparativa_estado === 'pedida') {
            accionBtn = `<button class="btn-action btn-anular" data-anular="${ESC(it.id)}"
                onclick="window.CalendarioModule.anularPedida('${ESC(it.id)}')">Anular</button>`;
        }

        return `
        <div class="cal-row" id="cal-row-${ESC(it.id)}">
            <span class="cal-row-nombre" title="${ESC(it.nombre)}">${ESC(it.nombre)}</span>
            <span class="cal-row-fecha">${ESC(fechaLabel)}</span>
            ${compChip(it.comparativa_estado)}
            ${accionBtn}
        </div>`;
    }

    /* ─── HTML de cada mes ────────────────────────────────────── */

    function renderMonth(group) {
        return `
        <section class="cal-month">
            <div class="cal-month-header">
                <span>${ESC(group.label)}</span>
                <span class="cal-month-count">${group.items.length}</span>
            </div>
            ${group.items.map(rowHtml).join('')}
        </section>`;
    }

    /* ─── Render principal ───────────────────────────────────── */

    function render() {
        const tokens = currentSearch.toLowerCase().split(/\s+/).filter(Boolean);
        const filtered = allItems.filter(it => {
            if (currentComp && it.comparativa_estado !== currentComp) return false;
            if (!tokens.length) return true;
            const nombre = it.nombre.toLowerCase();
            return tokens.every(t => nombre.includes(t));
        });

        if (!filtered.length) {
            setState('empty');
            return;
        }

        const groups = groupByMonth(filtered);
        document.getElementById('cal-months').innerHTML = groups.map(renderMonth).join('');
        setState('months');
    }

    /* ─── Re-render de fila individual ───────────────────────── */

    function rerenderRow(id) {
        const item = allItems.find(i => i.id === id);
        if (!item) { render(); return; }

        if (currentComp && item.comparativa_estado !== currentComp) {
            render();
            return;
        }

        const row = document.getElementById(`cal-row-${id}`);
        if (!row) { render(); return; }
        row.outerHTML = rowHtml(item);
    }

    /* ─── Filtros ─────────────────────────────────────────────── */

    function bindFilters() {
        document.querySelectorAll('.filter-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentComp = btn.dataset.comp;
                render();
            });
        });

        let searchTimer;
        document.getElementById('search-input').addEventListener('input', e => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                currentSearch = e.target.value;
                render();
            }, 250);
        });
    }

    /* ─── Init ───────────────────────────────────────────────── */

    bindFilters();
    updateYearDisplay();
    loadCalendario();

    return { loadCalendario, marcarPedida, anularPedida, render, navegarAño };

})();
