// Așteaptă ca întregul document HTML să fie încărcat și gata de utilizare
document.addEventListener('DOMContentLoaded', function() {

    // --- LOGICA PENTRU SELECTAREA TUTUROR COMENZILOR ---
    const selectAllCheckbox = document.getElementById('select-all-orders');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            // Găsește toate checkbox-urile de pe rândurile comenzilor
            const checkboxes = document.querySelectorAll('.order-checkbox');
            // Setează starea fiecărui checkbox să fie aceeași cu a celui de "select all"
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
        });
    }

    // --- LOGICA PENTRU TRIMITEREA AUTOMATĂ A FORMULARULUI DE FILTRE ---
    const filterForm = document.getElementById('filter-form');
    if (filterForm) {
        // Găsește toate elementele de tip <select> (dropdown-uri) din formular
        const selects = filterForm.querySelectorAll('select');
        selects.forEach(select => {
            // Adaugă un eveniment care se declanșează la schimbarea valorii
            select.addEventListener('change', function() {
                // Trimite formularul către server
                filterForm.submit();
            });
        });

        // Găsește câmpul de căutare text
        const searchInput = filterForm.querySelector('input[name="search"]');
        let searchTimeout; // Variabilă pentru a gestiona delay-ul la tastare

        if (searchInput) {
            // Adaugă un eveniment care se declanșează la fiecare tastă apăsată
            searchInput.addEventListener('keyup', function() {
                // Anulează timeout-ul anterior pentru a nu trimite cereri la fiecare literă
                clearTimeout(searchTimeout);
                // Setează un nou timeout. Formularul va fi trimis la 500ms DUPĂ ce utilizatorul s-a oprit din tastat.
                searchTimeout = setTimeout(() => {
                    filterForm.submit();
                }, 500); // 0.5 secunde delay
            });
        }
    }

    // --- LOGICA PENTRU ACȚIUNI (ex: Generare AWB) ---
    const generateAwbButton = document.getElementById('generate-awb-button');
    if (generateAwbButton) {
        generateAwbButton.addEventListener('click', function() {
            const selectedOrders = [];
            // Găsește toate comenzile selectate
            document.querySelectorAll('.order-checkbox:checked').forEach(checkbox => {
                selectedOrders.push(checkbox.value);
            });

            if (selectedOrders.length === 0) {
                alert('Te rog selectează cel puțin o comandă.');
                return;
            }

            // Aici poți adăuga logica pentru a trimite comenzile selectate la server
            // De exemplu, folosind fetch() pentru a apela un endpoint API.
            console.log('Se generează AWB pentru comenzile:', selectedOrders);
            // fetch('/generate-awbs', {
            //     method: 'POST',
            //     headers: { 'Content-Type': 'application/json' },
            //     body: JSON.stringify({ order_ids: selectedOrders })
            // }).then(response => {
            //     // gestionează răspunsul
            // });
        });
    }
});