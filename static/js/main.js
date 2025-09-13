// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // Logic for select-all checkbox
    const selectAllCheckbox = document.getElementById('select-all-orders');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.order-checkbox');
            checkboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
        });
    }

    // Logic for filter forms to submit on change
    const filterForms = document.querySelectorAll('.filter-form');
    filterForms.forEach(form => {
        const selects = form.querySelectorAll('select');
        selects.forEach(select => {
            select.addEventListener('change', function() {
                form.submit();
            });
        });
    });
});