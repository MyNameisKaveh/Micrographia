document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element References ---
    const microbeSearchInput = document.getElementById('microbeSearchInput');
    const gramFilterSelect = document.getElementById('gramFilterSelect'); // New filter element
    const searchButton = document.getElementById('searchButton');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const errorContainer = document.getElementById('errorContainer');
    const searchResultsContainer = document.getElementById('searchResultsContainer');
    const microbeDetailSection = document.getElementById('microbeDetailSection');

    // Microbe Detail Fields
    const microbeScientificName = document.getElementById('microbeScientificName');
    const microbeRank = document.getElementById('microbeRank');
    const microbeDescription = document.getElementById('microbeDescription'); // Will be populated by general summary
    // const isolationSource = document.getElementById('isolationSource'); // Replaced by biosampleRecordsList
    const ncbiTaxIdSpan = document.getElementById('ncbiTaxId'); // Span for the TaxID value
    const taxonomyLineage = document.getElementById('taxonomyLineage');
    const gramStain = document.getElementById('gramStain');
    const cellShape = document.getElementById('cellShape');
    const oxygenRequirement = document.getElementById('oxygenRequirement');
    // const genomeSize = document.getElementById('genomeSize'); // Replaced by nuccoreRecordsList
    const gcContent = document.getElementById('gcContent'); // Keep for now, might be a summary field
    const microbeImage = document.getElementById('microbeImage');
    const noImageText = document.getElementById('noImageText');
    const externalLinksList = document.getElementById('externalLinksList');

    // New list containers from HTML
    const nuccoreRecordsList = document.getElementById('nuccoreRecordsList');
    const biosampleRecordsList = document.getElementById('biosampleRecordsList');

    // Comparison UI Elements
    const comparisonTrayArea = document.getElementById('comparisonTrayArea');
    const comparisonSelectedList = document.getElementById('comparisonSelectedList');
    const compareSelectedButton = document.getElementById('compareSelectedButton');
    const comparisonCount = document.getElementById('comparisonCount');
    const clearComparisonButton = document.getElementById('clearComparisonButton');
    const comparisonDisplayArea = document.getElementById('comparisonDisplayArea');
    const comparisonTableContainer = document.getElementById('comparisonTableContainer');
    const comparisonPlaceholderText = document.getElementById('comparisonPlaceholderText'); // New
    const filterStatus = document.getElementById('filterStatus'); // New

    const API_BASE_URL = "https://micrographia-kavehs-projects-7d3a910a.vercel.app";

    // --- Global State for Comparison ---
    let selectedForComparison = [];
    const MAX_COMPARE_ITEMS = 5;

    // --- Initial State ---
    if (microbeDetailSection) microbeDetailSection.style.display = 'none';
    if (loadingIndicator) loadingIndicator.style.display = 'none';
    if (errorContainer) errorContainer.style.display = 'none';
    if (comparisonTrayArea) comparisonTrayArea.style.display = 'none';
    if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'none'; // Initial hide
    if (filterStatus) filterStatus.style.display = 'none';
    if (comparisonPlaceholderText && comparisonTableContainer.children.length === 0) { // Show placeholder initially
        comparisonPlaceholderText.style.display = 'block';
    }


    // --- Event Listeners ---
    if (searchButton) {
        searchButton.addEventListener('click', () => {
            performSearch(microbeSearchInput.value);
        });
    }

    if (microbeSearchInput) {
        microbeSearchInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                performSearch(microbeSearchInput.value);
            }
        });
    }

    if (compareSelectedButton) {
        compareSelectedButton.addEventListener('click', () => {
            fetchAndDisplayComparison();
        });
    }

    if (clearComparisonButton) {
        clearComparisonButton.addEventListener('click', () => {
            selectedForComparison = [];
            document.querySelectorAll('.compare-checkbox').forEach(checkbox => checkbox.checked = false);
            updateComparisonTray();
            if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'none';
            if (comparisonPlaceholderText && comparisonTableContainer) { // Show placeholder when clearing
                comparisonTableContainer.innerHTML = ''; // Clear table
                comparisonPlaceholderText.style.display = 'block';
            }
        });
    }


    // --- Search Functionality ---
    async function performSearch(searchTerm) {
        const term = searchTerm.trim();
        if (!term) {
            showError("Please enter a microbe name to search.");
            if (searchResultsContainer) searchResultsContainer.innerHTML = '';
            if (microbeDetailSection) microbeDetailSection.style.display = 'none';
            if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'none';
            return;
        }

        showLoading(true);
        hideError();
        if (searchResultsContainer) searchResultsContainer.innerHTML = '';
        if (microbeDetailSection) microbeDetailSection.style.display = 'none';
        if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'none';
        if (comparisonPlaceholderText && comparisonTableContainer) { // Ensure placeholder is managed
             comparisonTableContainer.innerHTML = ''; // Clear previous table if any
             comparisonPlaceholderText.style.display = 'block';
        }


        const gramFilterValue = gramFilterSelect ? gramFilterSelect.value : 'any';
        let endpointPath = `/api/microbe/search?name=${encodeURIComponent(term)}`;

        if (gramFilterValue !== 'any') {
            endpointPath += `&gram_filter=${encodeURIComponent(gramFilterValue)}`;
            if (filterStatus) {
                const filterText = gramFilterSelect.options[gramFilterSelect.selectedIndex].text;
                filterStatus.textContent = `Filtered by: ${filterText}`;
                filterStatus.style.display = 'block';
            }
        } else {
            if (filterStatus) {
                filterStatus.textContent = '';
                filterStatus.style.display = 'none';
            }
        }

        try {
            const response = await fetch(`${API_BASE_URL}${endpointPath}`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
                throw new Error(errorData.error || `Search failed with status: ${response.status}`);
            }
            const results = await response.json();
            showLoading(false);

            if (results && results.length > 0) {
                displaySearchResults(results);
            } else {
                if (searchResultsContainer) {
                    const currentFilterValue = gramFilterSelect ? gramFilterSelect.value : 'any';
                    const currentFilterText = gramFilterSelect ? gramFilterSelect.options[gramFilterSelect.selectedIndex].text : '';
                    if (currentFilterValue !== 'any') {
                        searchResultsContainer.innerHTML = `<p>No results found for "${term}" with filter: ${currentFilterText}.</p>`;
                    } else {
                        searchResultsContainer.innerHTML = `<p>No results found for "${term}".</p>`;
                    }
                }
            }
        } catch (error) {
            showLoading(false);
            showError(`Search error: ${error.message}`);
            console.error("Search error:", error);
        }
    }

    // --- Display Search Results ---
    function displaySearchResults(results) {
        if (!searchResultsContainer) return;
        searchResultsContainer.innerHTML = '';

        const ul = document.createElement('ul');
        ul.className = 'search-results-list';

        results.forEach(result => {
            const li = document.createElement('li');

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'compare-checkbox';
            checkbox.dataset.taxId = result.tax_id;
            checkbox.dataset.name = result.scientific_name;
            checkbox.checked = selectedForComparison.some(item => item.tax_id === result.tax_id);
            checkbox.addEventListener('change', handleCompareCheckboxChange);

            const nameSpan = document.createElement('span');
            nameSpan.textContent = `${result.scientific_name} (TaxID: ${result.tax_id})`;
            nameSpan.style.cursor = 'pointer';
            nameSpan.addEventListener('click', () => {
                fetchMicrobeDetails(result.tax_id);
            });

            li.appendChild(checkbox);
            li.appendChild(nameSpan);
            ul.appendChild(li);
        });
        searchResultsContainer.appendChild(ul);
        updateComparisonTray(); // Update tray in case some items were already selected
    }

    function handleCompareCheckboxChange(event) {
        const checkbox = event.target;
        const taxId = checkbox.dataset.taxId;
        const name = checkbox.dataset.name;

        if (checkbox.checked) {
            if (selectedForComparison.length < MAX_COMPARE_ITEMS) {
                if (!selectedForComparison.some(item => item.tax_id === taxId)) {
                    selectedForComparison.push({ tax_id: taxId, name: name });
                }
            } else {
                checkbox.checked = false; // Prevent checking more than max
                showError(`You can select a maximum of ${MAX_COMPARE_ITEMS} microbes for comparison.`);
                // alert(`You can select a maximum of ${MAX_COMPARE_ITEMS} for comparison.`);
            }
        } else {
            selectedForComparison = selectedForComparison.filter(item => item.tax_id !== taxId);
        }
        updateComparisonTray();
    }

    // --- Update Comparison Tray ---
    function updateComparisonTray() {
        if (!comparisonTrayArea || !comparisonSelectedList || !comparisonCount || !compareSelectedButton) return;

        if (selectedForComparison.length > 0) {
            comparisonTrayArea.style.display = 'block';
        } else {
            comparisonTrayArea.style.display = 'none';
        }

        comparisonSelectedList.innerHTML = '';
        selectedForComparison.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item.name;
            // Optional: Add a remove button per item in tray
            // const removeBtn = document.createElement('button');
            // removeBtn.textContent = 'X';
            // removeBtn.onclick = () => { ... remove item, uncheck checkbox, update tray ... };
            // li.appendChild(removeBtn);
            comparisonSelectedList.appendChild(li);
        });

        comparisonCount.textContent = selectedForComparison.length;
        compareSelectedButton.disabled = selectedForComparison.length < 2;
    }


    // --- Fetch Microbe Details (Single) ---
    async function fetchMicrobeDetails(taxId) {
        showLoading(true);
        hideError();
        // if (searchResultsContainer) searchResultsContainer.innerHTML = '';
        if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'none';
        if (comparisonPlaceholderText && comparisonTableContainer) { // Manage placeholder
            comparisonTableContainer.innerHTML = '';
            comparisonPlaceholderText.style.display = 'block';
        }

        // Clear previous details
        const UIElementsToClear = [
            microbeScientificName, microbeRank, microbeDescription, ncbiTaxIdSpan,
            taxonomyLineage, gramStain, cellShape, oxygenRequirement,
            gcContent, externalLinksList, nuccoreRecordsList, biosampleRecordsList
        ];
        UIElementsToClear.forEach(el => {
            if (el) el.innerHTML = ''; // Clear content
        });

        if (microbeImage) {
            microbeImage.src = ''; // Clear src
            microbeImage.style.display = 'none';
        }
        if (noImageText) noImageText.style.display = 'none';

        try {
            const response = await fetch(`${API_BASE_URL}/api/microbe/detail?tax_id=${encodeURIComponent(taxId)}`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
                throw new Error(errorData.error || `Failed to fetch details with status: ${response.status}`);
            }
            const data = await response.json();
            showLoading(false);
            if (microbeDetailSection) microbeDetailSection.style.display = 'block';
            renderMicrobeDetails(data);

        } catch (error) {
            showLoading(false);
            showError(`Detail fetch error: ${error.message}`);
            if (microbeDetailSection) microbeDetailSection.style.display = 'none';
            console.error("Detail fetch error:", error);
        }
    }

    // --- Render Microbe Details (Single) ---
    function formatLineage(lineageArray) {
        if (!lineageArray || lineageArray.length === 0) {
            return '<p>No lineage information available.</p>';
        }
        let html = '<ul>';
        lineageArray.forEach(item => {
            html += `<li><span class="rank-label">${item.rank}:</span> ${item.scientific_name}</li>`;
        });
        html += '</ul>';
        return html;
    }

    function renderMicrobeDetails(data) {
        if (!data) {
            showError("Received no data to display microbe details.");
            if (microbeDetailSection) microbeDetailSection.style.display = 'none';
            return;
        }

        if (microbeScientificName) microbeScientificName.textContent = data.scientific_name || 'N/A';
        if (microbeRank) microbeRank.textContent = data.rank || 'N/A';

        if (ncbiTaxIdSpan) { // Make TaxID a link
            ncbiTaxIdSpan.innerHTML = ''; // Clear previous
            if (data.tax_id && data.tax_id !== 'N/A') {
                const taxIdLink = document.createElement('a');
                taxIdLink.href = `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${data.tax_id}`;
                taxIdLink.textContent = data.tax_id;
                taxIdLink.target = '_blank';
                ncbiTaxIdSpan.appendChild(taxIdLink);
            } else {
                ncbiTaxIdSpan.textContent = 'N/A';
            }
        }

        if (taxonomyLineage) taxonomyLineage.innerHTML = formatLineage(data.lineage);
        if (gramStain) gramStain.textContent = data.gram_stain_derived || 'Not Determined';
        if (oxygenRequirement) oxygenRequirement.textContent = data.oxygen_requirement_derived || 'N/A';

        // Populate Nuccore Records
        if (nuccoreRecordsList) {
            nuccoreRecordsList.innerHTML = ''; // Clear previous
            if (data.genome_info && data.genome_info.length > 0) {
                data.genome_info.forEach(record => {
                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'record-item'; // For styling
                    let content = '';
                    if (record.nuccore_id && record.nuccore_id !== "N/A"){
                        content += `<p class="record-title"><strong>Accession:</strong> <a href="https://www.ncbi.nlm.nih.gov/nuccore/${record.nuccore_id}" target="_blank">${record.nuccore_id}</a></p>`;
                    } else {
                        content += `<p class="record-title"><strong>Accession:</strong> N/A</p>`;
                    }
                    if (record.title) content += `<p><em>${record.title}</em></p>`;
                    if (record.sequence_length && record.sequence_length !== "N/A") content += `<p>Length: ${record.sequence_length} bp</p>`;
                    if (record.molecule_type && record.molecule_type !== "N/A") content += `<p>Molecule: ${record.molecule_type}</p>`;
                    itemDiv.innerHTML = content;
                    nuccoreRecordsList.appendChild(itemDiv);
                });
            } else {
                nuccoreRecordsList.innerHTML = '<p>No genomic records found.</p>';
            }
        }

        // Populate BioSample Records
        if (biosampleRecordsList) {
            biosampleRecordsList.innerHTML = ''; // Clear previous
            if (data.biosample_info && data.biosample_info.length > 0) {
                data.biosample_info.forEach(record => {
                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'record-item'; // For styling
                    let content = '';
                    if (record.accession && record.accession !== "N/A"){
                        content += `<p class="record-title"><strong>Accession:</strong> <a href="https://www.ncbi.nlm.nih.gov/biosample/${record.accession}" target="_blank">${record.accession}</a></p>`;
                    } else {
                         content += `<p class="record-title"><strong>Accession:</strong> N/A</p>`;
                    }
                    if (record.title) content += `<p><em>${record.title}</em></p>`;
                    if (record.attributes && record.attributes.length > 0) {
                        content += '<ul class="attribute-list">';
                        record.attributes.forEach(attr => {
                            // Display a few key attributes or all of them
                             if (['isolation source', 'host', 'geographic location', 'collection date', 'strain', 'isolate', 'sample name', 'sample type'].includes(attr.name.toLowerCase()) || record.attributes.length <= 8) { // Show more attributes if not too many
                                content += `<li><strong>${attr.name}:</strong> ${attr.value || 'N/A'}</li>`;
                            }
                        });
                         if (record.attributes.length > 8) { // Indicate if some attributes are hidden
                            content += `<li>... and more attributes not shown here.</li>`;
                        }
                        content += '</ul>';
                    }
                    itemDiv.innerHTML = content;
                    biosampleRecordsList.appendChild(itemDiv);
                });
            } else {
                biosampleRecordsList.innerHTML = '<p>No BioSample records found.</p>';
            }
        }

        // Summary/Description (placeholder for now)
        if (microbeDescription) microbeDescription.textContent = data.description || "Detailed summary not available from this source.";

        // Other placeholders
        if (cellShape) cellShape.textContent = data.cell_shape || 'N/A';
        if (gcContent) gcContent.textContent = data.gc_content || 'N/A'; // Assuming this might be a summary field if available

        // Image
        if (data.image_url && microbeImage) {
            microbeImage.src = data.image_url;
            microbeImage.alt = `Image of ${data.scientific_name}`;
            microbeImage.style.display = 'block';
            if (noImageText) noImageText.style.display = 'none';
        } else if (microbeImage) {
            microbeImage.style.display = 'none';
            if (noImageText) noImageText.style.display = 'block';
        }

        // External Links - Keep this for general links if backend adds them
        // The specific NCBI links are now more integrated above.
        if (externalLinksList) {
            externalLinksList.innerHTML = '';
            // Example: if backend provided a generic "ncbi_main_page" link
            if(data.external_links && data.external_links.ncbi_taxonomy) { // This part is hypothetical based on previous thoughts
                 const li = document.createElement('li');
                 const a = document.createElement('a');
                 a.href = data.external_links.ncbi_taxonomy;
                 a.textContent = `NCBI Taxonomy Home for ${data.scientific_name}`;
                 a.target = '_blank';
                 li.appendChild(a);
                 externalLinksList.appendChild(li);
            } else { // Default link if not provided by backend
                 const li = document.createElement('li');
                 const a = document.createElement('a');
                 a.href = `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${data.tax_id}`;
                 a.textContent = `View on NCBI Taxonomy Browser`;
                 a.target = '_blank';
                 li.appendChild(a);
                 externalLinksList.appendChild(li);
            }
            // Add more general links if provided by backend in data.external_links
        }
    }

    // --- Fetch and Display Comparison ---
    async function fetchAndDisplayComparison() {
        if (selectedForComparison.length < 2) {
            showError("Please select at least two microbes to compare.");
            return;
        }

        showLoading(true);
        hideError();
        if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'none';
        if (microbeDetailSection) microbeDetailSection.style.display = 'none';
        if (comparisonPlaceholderText && comparisonTableContainer) { // Ensure placeholder is hidden before showing table
            comparisonPlaceholderText.style.display = 'none';
        }

        const taxIdsToCompare = selectedForComparison.map(item => item.tax_id);

        try {
            const response = await fetch(`${API_BASE_URL}/api/microbes/details`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ tax_ids: taxIdsToCompare }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
                throw new Error(errorData.error || `Comparison fetch failed: ${response.status}`);
            }
            const comparisonData = await response.json();
            showLoading(false);

            if (comparisonData.results && comparisonData.results.length > 0) {
                if (comparisonDisplayArea) comparisonDisplayArea.style.display = 'block';
                if (comparisonPlaceholderText) comparisonPlaceholderText.style.display = 'none'; // Hide placeholder
                renderComparisonTable(comparisonData.results);
                if (comparisonData.errors && Object.keys(comparisonData.errors).length > 0) {
                    let errorMsg = "Note: Some microbes could not be fetched for comparison: ";
                    for (const [taxId, err] of Object.entries(comparisonData.errors)) {
                        const microbeName = selectedForComparison.find(m => m.tax_id === taxId)?.name || `TaxID ${taxId}`;
                        errorMsg += `${microbeName} (${err}); `;
                    }
                    showError(errorMsg); // Show this as a non-fatal error, table still renders with available data
                }
            } else {
                showError("No data returned for the selected microbes for comparison.", true); // Keep placeholder visible
                 if (comparisonData.errors && Object.keys(comparisonData.errors).length > 0) {
                    // Error message already shown by showError called above if some results exist
                 }
                 if (comparisonPlaceholderText) comparisonPlaceholderText.style.display = 'block'; // Ensure placeholder is visible on full fail
            }
        } catch (error) {
            showLoading(false);
            if (comparisonPlaceholderText) comparisonPlaceholderText.style.display = 'block'; // Ensure placeholder visible on error
            showError(`Comparison error: ${error.message}`);
            console.error("Comparison fetch error:", error);
        }
    }

    // --- Render Comparison Table ---
    function renderComparisonTable(microbeDataList) {
        if (!comparisonTableContainer) return;

        if (!microbeDataList || microbeDataList.length === 0) {
            comparisonTableContainer.innerHTML = ''; // Clear any previous table
            if (comparisonPlaceholderText) {
                comparisonPlaceholderText.textContent = 'No data available to display in comparison table.';
                comparisonPlaceholderText.style.display = 'block';
            }
            return;
        }

        comparisonTableContainer.innerHTML = ''; // Clear placeholder or previous table
        if (comparisonPlaceholderText) comparisonPlaceholderText.style.display = 'none';


        const table = document.createElement('table');
        table.className = 'comparison-table';

        // Header Row
        const thead = table.createTHead();
        const headerRow = thead.insertRow();
        const thFeature = document.createElement('th');
        thFeature.textContent = 'Feature';
        headerRow.appendChild(thFeature);

        microbeDataList.forEach(microbe => {
            const thMicrobe = document.createElement('th');
            thMicrobe.textContent = microbe.scientific_name || `TaxID: ${microbe.tax_id}`;
            headerRow.appendChild(thMicrobe);
        });

        // Data Rows
        const tbody = table.createTBody();
        const featuresToCompare = [
            { key: 'tax_id', label: 'NCBI TaxID' },
            { key: 'rank', label: 'Rank' },
            { key: 'gram_stain_derived', label: 'Gram Stain' },
            { key: 'oxygen_requirement_derived', label: 'Oxygen Requirement' },
            { key: 'primary_genome_size_bp', label: 'Genome Size (bp)' },
            { key: 'primary_isolation_source', label: 'Isolation Source' }
            // Add more features here as needed, e.g., cell_shape, gc_content if available
        ];

        featuresToCompare.forEach(feature => {
            const row = tbody.insertRow();
            const cellFeature = row.insertCell();
            cellFeature.textContent = feature.label;
            cellFeature.style.fontWeight = 'bold';

            microbeDataList.forEach(microbe => {
                const cellValue = row.insertCell();
                // Access nested data safely, e.g. microbe.genomics?.genome_size
                let value = microbe[feature.key];
                // Special handling for potentially nested or formatted values if any were missed by backend primary_ fields
                // For now, assuming backend provides primary_genome_size_bp and primary_isolation_source directly
                cellValue.textContent = (value !== undefined && value !== null && value !== "") ? value : 'N/A';
            });
        });

        comparisonTableContainer.appendChild(table);
    }


    // --- Utility Functions ---
    function showLoading(isLoading) {
        if (loadingIndicator) loadingIndicator.style.display = isLoading ? 'block' : 'none';
    }

    function showError(message, isMinor = false) { // Added isMinor to potentially style differently or avoid hiding main content
        if (errorContainer) {
            errorContainer.textContent = message;
            errorContainer.style.display = 'block';
        }
        // If it's a minor error (e.g. some comparison items failed but table shown), don't hide everything
        if (!isMinor && microbeDetailSection) microbeDetailSection.style.display = 'none';
        if (!isMinor && comparisonDisplayArea) comparisonDisplayArea.style.display = 'none';

    }

    function hideError() {
        if (errorContainer) {
            errorContainer.textContent = '';
            errorContainer.style.display = 'none';
        }
    }

});
