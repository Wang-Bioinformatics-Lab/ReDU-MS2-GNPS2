window.addEventListener('load', function() {
    // Wait for the DataTable to render
    setTimeout(function() {
        // Find all filter inputs
        var filterInputs = document.querySelectorAll('.dash-filter input');

        for (var i = 0; i < filterInputs.length; i++) {
            var input = filterInputs[i];
            var headerCell = input.closest('th');

            if (headerCell && headerCell.textContent.trim() === 'USI') {
                // Set the default filter value
                input.value = 'contains ".(mzML|mzXML)$"';

                // Trigger the input event to apply the filter
                var event = new Event('input', { bubbles: true });
                input.dispatchEvent(event);
                break;
            }
        }
    }, 1000); // Adjust the timeout as needed
});
