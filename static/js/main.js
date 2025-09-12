const toggleModal = (event) => {
  event.preventDefault();
  const modal = document.getElementById(event.currentTarget.dataset.target);
  if (modal) modal.getAttribute('open') === null ? modal.showModal() : modal.close();
};

document.addEventListener('DOMContentLoaded', function () {
    const table = document.querySelector('.main-table');
    const columnTogglerContainer = document.getElementById('column-toggler');
    const ALL_COLUMNS = { 
        'selector': '', 'comanda': 'Comanda', 'data': 'Data', 'status': 'Status AWB Hub', 
        'payment_status': 'Payment Status', 'fulfillment_status': 'Fulfillment Status',
        'produse': 'Produse', 'awb': 'AWB', 'status_curier': 'Status Curier', 'printat': 'Printat?',
        'printat_la': 'Printat la', 'actiuni': 'Acțiuni'
    };
    const DEFAULT_COLUMNS = [
        'selector', 'comanda', 'data', 'status', 'payment_status', 'fulfillment_status',
        'produse', 'awb', 'status_curier', 'printat', 'actiuni'
    ];
    let visibleColumns = JSON.parse(localStorage.getItem('visibleColumns_awbhub')) || DEFAULT_COLUMNS;

    function applyColumnVisibility() {
        if (!table) return;
        const styleSheet = document.getElementById('column-styles') || document.createElement('style');
        styleSheet.id = 'column-styles';
        let css = '';
        for (const key in ALL_COLUMNS) {
            if (!visibleColumns.includes(key)) {
                css += `th[data-column-key="${key}"], td[data-column-key="${key}"] { display: none; } `;
            }
        }
        styleSheet.innerHTML = css;
        document.head.appendChild(styleSheet);
    }

    function renderColumnManager() {
        if (!columnTogglerContainer) return;
        columnTogglerContainer.innerHTML = '';
        for (const [key, title] of Object.entries(ALL_COLUMNS)) {
            if (key === 'selector' || !title) continue;
            const label = document.createElement('label');
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.dataset.columnKey = key;
            checkbox.checked = visibleColumns.includes(key);
            checkbox.addEventListener('change', (event) => {
                const changedKey = event.target.dataset.columnKey;
                visibleColumns = event.target.checked ? [...visibleColumns, changedKey] : visibleColumns.filter(c => c !== changedKey);
                localStorage.setItem('visibleColumns_awbhub', JSON.stringify(visibleColumns));
                applyColumnVisibility();
            });
            label.append(checkbox, ' ' + title);
            columnTogglerContainer.appendChild(label);
        }
    }

    if (table) { renderColumnManager(); applyColumnVisibility(); }

    const filterDetails = document.getElementById('filter-details');
    if (filterDetails) {
        if (sessionStorage.getItem('filters_open') === 'true') filterDetails.setAttribute('open', '');
        filterDetails.addEventListener('toggle', () => sessionStorage.setItem('filters_open', filterDetails.open));
    }

    const progressBar = document.getElementById('syncProgressBar');
    const progressText = document.getElementById('syncProgressText');
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/sync/ws`);

    ws.onmessage = e => {
        let d = JSON.parse(e.data);
        const actions = {
            sync_start: () => {
                if (progressText) progressText.textContent = d.message;
                if (progressBar) { progressBar.style.display = "block"; progressBar.removeAttribute('value'); }
                document.querySelectorAll('#syncOrdersButton, #syncCouriersButton, #fullSyncButton').forEach(b => b && (b.disabled = true));
            },
            progress_update: () => {
                if (progressText) progressText.textContent = d.total > 0 ? `${d.message} (${d.current}/${d.total})` : d.message;
                if (progressBar) progressBar.value = d.total > 0 ? (d.current / d.total * 100) : null;
            },
            sync_end: () => {
                if (progressText) progressText.textContent = d.message + " Reîncărcare...";
                if (progressBar) progressBar.value = 100;
                setTimeout(() => window.location.reload(), 2000);
            },
            sync_error: () => {
                if (progressText) progressText.textContent = "A apărut o eroare. Pagina se va reîncărca.";
                setTimeout(() => window.location.reload(), 5000);
            }
        };
        if (actions[d.type]) actions[d.type]();
    };

    function startSync(url, body) {
        fetch(url, { method: 'POST', body: body }).then(res => res.status === 409 && res.json().then(d => alert(d.message)));
    }
    document.getElementById('syncOrdersButton')?.addEventListener('click', () => startSync('/sync/orders', new URLSearchParams(new FormData(document.getElementById('days-form')))));
    document.getElementById('syncCouriersButton')?.addEventListener('click', () => startSync('/sync/couriers', new FormData()));
    document.getElementById('fullSyncButton')?.addEventListener('click', () => startSync('/sync/full', new URLSearchParams(new FormData(document.getElementById('days-form')))));

    const filterForm = document.getElementById('filterForm');
    if (filterForm) {
        let debounceTimeout;
        const submitForm = () => {
            clearTimeout(debounceTimeout);
            filterForm.submit();
        };
        const debounceSubmit = () => {
            clearTimeout(debounceTimeout);
            debounceTimeout = setTimeout(submitForm, 500);
        };
        filterForm.querySelectorAll('select, input[type="date"]').forEach(el => el.addEventListener('change', submitForm));
        filterForm.querySelectorAll('input[type="text"]').forEach(el => el.addEventListener('keyup', debounceSubmit));
    }

    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const printButton = document.getElementById('print-selected-button');
    const selectAllBanner = document.getElementById('select-all-banner');

    function updateSelectedState() {
        const checkedBoxes = document.querySelectorAll('.awb-checkbox:checked');
        const totalVisible = document.querySelectorAll('.awb-checkbox').length;
        if (selectAllCheckbox) selectAllCheckbox.checked = checkedBoxes.length > 0 && checkedBoxes.length === totalVisible;

        const isSelectAllActive = document.getElementById('select_all_filtered_confirm')?.value === 'true';
        let selectionText = ``;
        if (isSelectAllActive) {
            const total = selectAllBanner.dataset.totalOrders;
            selectionText = `Toate cele <strong>${total}</strong> comenzi sunt selectate. <a href="#" id="unselect-all-link" style="margin-left:1rem;">Deselectează tot</a>`;
        } else if (checkedBoxes.length > 0 && checkedBoxes.length === totalVisible && totalVisible > 0) {
            const total = selectAllBanner.dataset.totalOrders;
            selectionText = `Toate cele ${checkedBoxes.length} comenzi de pe pagină sunt selectate. <a href="#" id="select-all-filtered-link" style="margin-left:1rem;">Selectează toate cele ${total} comenzi</a>`;
        }
        if(selectAllBanner) {
            selectAllBanner.innerHTML = selectionText;
            selectAllBanner.style.display = selectionText ? 'block' : 'none';
        }
    }

    document.body.addEventListener('change', e => {
        if (e.target.matches('.awb-checkbox')) updateSelectedState();
        if (e.target === selectAllCheckbox) {
            document.querySelectorAll('.awb-checkbox').forEach(cb => cb.checked = e.target.checked);
            if (document.getElementById('select_all_filtered_confirm')) {
                document.getElementById('select_all_filtered_confirm').value = 'false';
            }
            updateSelectedState();
        }
    });

    document.body.addEventListener('click', e => {
        if (e.target.id === 'select-all-filtered-link' || e.target.id === 'unselect-all-link') {
            e.preventDefault();
            const selectAllConfirm = document.getElementById('select_all_filtered_confirm');
            if (selectAllConfirm) {
                selectAllConfirm.value = e.target.id === 'select-all-filtered-link' ? 'true' : 'false';
            }
            if (selectAllCheckbox && !selectAllCheckbox.checked) {
                 selectAllCheckbox.checked = true;
                 document.querySelectorAll('.awb-checkbox').forEach(cb => cb.checked = true);
            }
            if (e.target.id === 'unselect-all-link' && selectAllCheckbox) {
                selectAllCheckbox.checked = false;
                document.querySelectorAll('.awb-checkbox').forEach(cb => cb.checked = false);
            }
            updateSelectedState();
        }
    });
    
    printButton?.addEventListener('click', function () {
        const selectAllConfirmInput = document.getElementById('select_all_filtered_confirm');
        let awbsToPrint = [];

        if (selectAllConfirmInput?.value === "true") {
             let params = new URLSearchParams(window.location.search);
             params.delete('page');
             params.delete('sort_by');
             printButton.textContent = "Se încarcă AWB-urile...";
             printButton.disabled = true;
             fetch(`/get_awbs_for_filters?${params.toString()}`)
                .then(res => res.json())
                .then(data => {
                    if (data.awbs && data.awbs.length > 0) {
                        sendPrintRequest(data.awbs);
                    } else {
                        alert('Niciun AWB găsit pentru filtrele selectate.');
                        printButton.textContent = "Printează AWB-urile Selectate";
                        printButton.disabled = false;
                    }
                })
                .catch(() => {
                    alert('A apărut o eroare la preluarea AWB-urilor.');
                    printButton.textContent = "Printează AWB-urile Selectate";
                    printButton.disabled = false;
                });
        } else {
            awbsToPrint = Array.from(document.querySelectorAll('.awb-checkbox:checked')).map(cb => cb.value);
            if (awbsToPrint.length === 0) return alert('Te rog selectează cel puțin un AWB.');
            sendPrintRequest(awbsToPrint);
        }
    });

    function sendPrintRequest(awbs) {
        const originalButtonText = "Printează AWB-urile Selectate";
        printButton.textContent = "Se pregătește PDF...";
        printButton.disabled = true;
        let formData = new FormData();
        formData.append('awbs', awbs.join(','));

        fetch('/labels/merge_for_print', { method: 'POST', body: formData })
            .then(res => res.ok ? res.blob() : res.json().then(err => Promise.reject(new Error(err.detail || 'Eroare la generarea PDF-ului.'))))
            .then(blob => {
                const url = URL.createObjectURL(blob);
                const iframe = document.createElement('iframe');
                iframe.style.display = 'none';
                iframe.src = url;
                document.body.appendChild(iframe);
                iframe.onload = () => { try { iframe.contentWindow.print(); } catch (err) { alert("Eroare la deschiderea dialogului de printare. Dezactivați pop-up blocker-ul."); } };
            })
            .catch(err => alert(`Nu s-a putut genera documentul. Motiv: ${err.message}`))
            .finally(() => { printButton.textContent = originalButtonText; printButton.disabled = false; });
    }

    updateSelectedState();
    
    document.getElementById('page-input').addEventListener('change', function() {
        document.getElementById('goToPageForm').submit();
    });
});

