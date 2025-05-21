// --- DOM Elements ---
const totalVolumeElement = document.getElementById('totalVolume');
const lastUpdatedElement = document.getElementById('lastUpdatedTime');
const fetchButton = document.getElementById('fetchVolumeButton'); // Main aggregate fetch
const fetchButtonText = fetchButton.querySelector('.button-text');
const fetchButtonSpinner = fetchButton.querySelector('.loading-spinner');

// API Key Input Elements
const wooxApiKeyInput = document.getElementById('wooxApiKey');
const wooxApiSecretInput = document.getElementById('wooxApiSecret');
const paradexApiKeyInput = document.getElementById('paradexApiKey');
// const paradexApiSecretInput = document.getElementById('paradexApiSecret'); // Paradex uses JWT, stored in apiKey field

// New Manual Fetching DOM Elements
const platformSelect = document.getElementById('platformSelect');
const fetchCurrentPlatformVolumeButton = document.getElementById('fetchCurrentPlatformVolumeButton');
const startDateInput = document.getElementById('startDate');
const endDateInput = document.getElementById('endDate');
const fetchHistoricalPlatformVolumeButton = document.getElementById('fetchHistoricalPlatformVolumeButton');
const fetchAllHistoricalVolumeButton = document.getElementById('fetchAllHistoricalVolumeButton');
const statusMessageElement = document.getElementById('statusMessage');
const saveAllKeysButton = document.getElementById('saveAllKeysButton');


const platformInputs = {
    woox: { apiKeyEl: wooxApiKeyInput, apiSecretEl: wooxApiSecretInput, platformName: 'woox' },
    paradex: { apiKeyEl: paradexApiKeyInput, apiSecretEl: null, platformName: 'paradex' } // Paradex uses JWT in apiKeyEl, no separate secret input needed here
};

const API_BASE_URL = 'http://localhost:8000/api/v1'; // Backend API URL
let historicalVolumeChartInstance = null; // To keep track of the chart instance

// --- Utility Functions ---
function formatVolume(volume) {
    if (volume === null || volume === undefined || isNaN(parseFloat(volume))) {
        return 'N/A';
    }
    const absVolume = Math.abs(parseFloat(volume));
    let sign = parseFloat(volume) < 0 ? "-" : "";

    if (absVolume >= 1e12) return sign + '$' + (absVolume / 1e12).toFixed(2) + 'T';
    if (absVolume >= 1e9) return sign + '$' + (absVolume / 1e9).toFixed(2) + 'B';
    if (absVolume >= 1e6) return sign + '$' + (absVolume / 1e6).toFixed(2) + 'M';
    if (absVolume >= 1e3) return sign + '$' + (absVolume / 1e3).toFixed(2) + 'K';
    return sign + '$' + absVolume.toFixed(2);
}

function setupPasswordToggles() {
    document.querySelectorAll('.password-toggle').forEach(button => {
        button.addEventListener('click', () => {
            const input = button.previousElementSibling;
            const eyeOpen = button.querySelector('.eye-open');
            const eyeClosed = button.querySelector('.eye-closed');
            if (input.type === 'password') {
                input.type = 'text';
                if(eyeOpen) eyeOpen.style.display = 'none';
                if(eyeClosed) eyeClosed.style.display = 'inline';
            } else {
                input.type = 'password';
                if(eyeOpen) eyeOpen.style.display = 'inline';
                if(eyeClosed) eyeClosed.style.display = 'none';
            }
        });
    });
}

function showLoadingButton(button, text = 'Fetching...') {
    if (!button) return;
    button.disabled = true;
    const buttonTextEl = button.querySelector('.button-text');
    const spinnerEl = button.querySelector('.loading-spinner');
    if (buttonTextEl) buttonTextEl.textContent = text;
    if (spinnerEl) spinnerEl.style.display = 'inline-block';
}

function hideLoadingButton(button, originalText) {
    if (!button) return;
    button.disabled = false;
    const buttonTextEl = button.querySelector('.button-text');
    const spinnerEl = button.querySelector('.loading-spinner');
    if (buttonTextEl) buttonTextEl.textContent = originalText;
    if (spinnerEl) spinnerEl.style.display = 'none';
}

function showStatusMessage(message, isError = false) {
    if (!statusMessageElement) return;
    statusMessageElement.innerHTML = message; // Use innerHTML to allow basic HTML like <br> or <ul>
    statusMessageElement.style.display = 'block';
    statusMessageElement.style.color = isError ? 'var(--theme-gold)' : 'var(--theme-text-primary)';
    statusMessageElement.style.backgroundColor = isError ? '#4d3400' : 'var(--theme-medium-gray)';
}

function hideStatusMessage() {
    if (!statusMessageElement) return;
    statusMessageElement.style.display = 'none';
    statusMessageElement.textContent = '';
}

// --- API Key Management ---
async function saveAllApiKeys() {
    showLoadingButton(saveAllKeysButton, 'Saving...');
    hideStatusMessage();
    let allSuccess = true;
    let messages = [];

    for (const platformKey in platformInputs) {
        const platformConfig = platformInputs[platformKey];
        const apiKey = platformConfig.apiKeyEl.value.trim();
        const apiSecret = platformConfig.apiSecretEl ? platformConfig.apiSecretEl.value.trim() : null;
        
        if (apiKey) {
            const payload = {
                platform_name: platformConfig.platformName,
                api_key: apiKey,
            };
            if (apiSecret) {
                payload.api_secret = apiSecret;
            }
            if (platformConfig.platformName === 'paradex') {
                payload.jwt_token = apiKey; // Paradex uses JWT
            }

            try {
                const response = await fetch(`${API_BASE_URL}/keys`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok) {
                    messages.push(`Error saving ${platformConfig.platformName} key: ${result.detail || response.statusText}`);
                    allSuccess = false;
                } else {
                    messages.push(`${platformConfig.platformName} API key saved/updated successfully.`);
                }
            } catch (error) {
                messages.push(`Error saving ${platformConfig.platformName} key: ${error.message}`);
                allSuccess = false;
            }
        }
    }

    if (messages.length > 0) {
        showStatusMessage(messages.join('<br>'), !allSuccess); // Use <br> for newlines in HTML
    } else {
        showStatusMessage('No API keys were entered to save.', false);
    }
    hideLoadingButton(saveAllKeysButton, 'Save All API Keys');
}

// --- Main Application Logic ---

async function fetchHistoricalDataForChart() {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setFullYear(endDate.getFullYear() - 1); // Default to 1 year ago

    const startQuery = startDate.toISOString().split('T')[0];
    const endQuery = endDate.toISOString().split('T')[0];

    try {
        const response = await fetch(
            `${API_BASE_URL}/volume/historical?start_date=${startQuery}&end_date=${endQuery}&granularity=daily`
        );
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Failed to fetch historical volume: ${errorData.detail || response.statusText}`);
        }
        const historicalData = await response.json();
        renderHistoricalChart(historicalData.data);
    } catch (error) {
        console.error('Error fetching historical data for chart:', error);
        showStatusMessage(`Chart Error: ${error.message}`, true);
    }
}

async function fetchAndDisplayAggregatedCurrentVolume() {
    showLoadingButton(fetchButton, 'Fetching...');
    if (totalVolumeElement) totalVolumeElement.innerHTML = '<div class="loading-spinner"></div>';
    if (lastUpdatedElement) lastUpdatedElement.textContent = 'Updating...';
    hideStatusMessage();

    try {
        const response = await fetch(`${API_BASE_URL}/volume/current`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Failed to fetch aggregated current volume: ${errorData.detail || response.statusText}`);
        }
        const data = await response.json();
        
        if (totalVolumeElement) totalVolumeElement.textContent = formatVolume(data.total_volume_24h_usd);
        if (lastUpdatedElement) lastUpdatedElement.textContent = new Date(data.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        let breakdownHtml = 'Individual Platforms (24h USD Volume):<ul class="list-disc list-inside ml-4">';
        data.individual_platforms.forEach(p => {
            breakdownHtml += `<li>${p.platform_name}: ${formatVolume(p.volume_24h_usd)} ${p.error ? `(Error: ${p.error})` : ''}</li>`;
        });
        breakdownHtml += '</ul>';
        showStatusMessage(breakdownHtml, false);

        // Fetch and render historical chart after current volume is displayed
        await fetchHistoricalDataForChart();

    } catch (error) {
        console.error('Error fetching aggregated current volume:', error);
        if (totalVolumeElement) totalVolumeElement.textContent = 'Error';
        if (lastUpdatedElement) lastUpdatedElement.textContent = 'Failed';
        showStatusMessage(`Error: ${error.message}`, true);
    } finally {
        hideLoadingButton(fetchButton, 'Fetch & Aggregate Volume');
    }
}

async function fetchCurrentPlatformVolume() {
    const platform = platformSelect.value;
    showLoadingButton(fetchCurrentPlatformVolumeButton, 'Fetching...');
    hideStatusMessage();

    try {
        const response = await fetch(`${API_BASE_URL}/volume/current/${platform}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Failed to fetch current volume for ${platform}: ${errorData.detail || response.statusText}`);
        }
        const data = await response.json();
        if (data.error) {
            showStatusMessage(`Error for ${platform}: ${data.error}. Volume: ${formatVolume(data.volume_24h_usd)}`, true);
        } else {
            showStatusMessage(`${platform} 24h Volume: ${formatVolume(data.volume_24h_usd)} (Last updated: ${new Date(data.last_updated).toLocaleTimeString()})`, false);
        }
    } catch (error) {
        console.error(`Error fetching current volume for ${platform}:`, error);
        showStatusMessage(`Error for ${platform}: ${error.message}`, true);
    } finally {
        hideLoadingButton(fetchCurrentPlatformVolumeButton, 'Fetch Current Volume (Selected Platform)');
    }
}

async function fetchHistoricalPlatformData() {
    const platform = platformSelect.value;
    const start = startDateInput.value;
    const end = endDateInput.value;

    if (!start || !end) {
        showStatusMessage('Please select both start and end dates.', true);
        return;
    }
    if (new Date(start) > new Date(end)) {
        showStatusMessage('Start date cannot be after end date.', true);
        return;
    }

    showLoadingButton(fetchHistoricalPlatformVolumeButton, 'Fetching...');
    hideStatusMessage();

    try {
        const response = await fetch(`${API_BASE_URL}/volume/historical/fetch-platform/${platform}?start_date=${start}&end_date=${end}`, {
            method: 'POST'
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || `Failed to trigger historical fetch for ${platform}`);
        }
        showStatusMessage(`Historical data fetch for ${platform} (${start} to ${end}) initiated. Status: ${result.status}. Fetched: ${result.fetched}, Stored: ${result.stored}. Errors: ${JSON.stringify(result.errors || [])}`, false);
    } catch (error) {
        console.error(`Error triggering historical fetch for ${platform}:`, error);
        showStatusMessage(`Error for ${platform}: ${error.message}`, true);
    } finally {
        hideLoadingButton(fetchHistoricalPlatformVolumeButton, 'Fetch Historical (Selected Platform)');
    }
}

async function fetchAllHistoricalData() {
    const start = startDateInput.value;
    const end = endDateInput.value;

    let url = `${API_BASE_URL}/volume/historical/fetch-all`;
    const params = new URLSearchParams();
    if (start) params.append('start_date', start);
    if (end) params.append('end_date', end);
    if (params.toString()) url += `?${params.toString()}`;

    showLoadingButton(fetchAllHistoricalVolumeButton, 'Fetching All...');
    hideStatusMessage();

    try {
        const response = await fetch(url, { method: 'POST' });
        const results = await response.json();
        if (!response.ok) {
            throw new Error(results.detail || `Failed to trigger historical fetch for all platforms`);
        }
        let message = "Historical data fetch for all platforms initiated.<br>Results:<br>";
        results.forEach(r => {
            message += `- ${r.platform}: ${r.status}, Fetched: ${r.fetched}, Stored: ${r.stored}, Errors: ${JSON.stringify(r.errors || [])}<br>`;
        });
        showStatusMessage(message, false);
    } catch (error) {
        console.error('Error triggering all historical fetch:', error);
        showStatusMessage(`Error: ${error.message}`, true);
    } finally {
        hideLoadingButton(fetchAllHistoricalVolumeButton, 'Fetch All Historical Data (All Platforms)');
    }
}

function renderHistoricalChart(apiData) {
    const chartCanvas = document.getElementById('historicalVolumeChart');
    if (!chartCanvas) {
        console.error("Chart canvas not found!");
        return;
    }
    const ctx = chartCanvas.getContext('2d');

    if (historicalVolumeChartInstance) {
        historicalVolumeChartInstance.destroy(); // Destroy previous instance if exists
    }

    const labels = apiData.map(item => item.timestamp); // Assuming timestamp is 'YYYY-MM-DD'
    const dataPoints = apiData.map(item => parseFloat(item.total_volume_usd));

    historicalVolumeChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Aggregated Volume (USD)',
                data: dataPoints,
                borderColor: 'var(--theme-gold)',
                backgroundColor: 'rgba(255, 210, 48, 0.2)',
                tension: 0.1,
                fill: true,
                pointBackgroundColor: 'var(--theme-gold)',
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: 'var(--theme-gold)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: { color: 'var(--theme-text-secondary)' },
                    grid: { color: 'var(--theme-light-gray)' }
                },
                y: {
                    ticks: { 
                        color: 'var(--theme-text-secondary)',
                        callback: function(value) { return formatVolume(value); } 
                    },
                    grid: { color: 'var(--theme-light-gray)' }
                }
            },
            plugins: {
                legend: {
                    labels: { color: 'var(--theme-text-primary)' }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += formatVolume(context.parsed.y);
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// --- WebSocket for Real-time Updates ---
function connectWebSocket() {
    const wsUrl = `ws://localhost:8000/api/v1/volume/ws/live-volume`; 
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WebSocket connection established for live volume.");
        showStatusMessage("Live updates connected.", false);
    };

    socket.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            if (message.error) {
                console.error("WebSocket message error:", message.error);
                return;
            }
            if (message.total_volume_24h_usd !== undefined && totalVolumeElement) {
                totalVolumeElement.textContent = formatVolume(message.total_volume_24h_usd);
            }
            if (message.last_updated && lastUpdatedElement) {
                lastUpdatedElement.textContent = new Date(message.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            }
        } catch (e) {
            console.error("Error processing WebSocket message:", e);
        }
    };

    socket.onerror = (error) => {
        console.error("WebSocket error:", error);
        showStatusMessage("Live updates connection error.", true);
    };

    socket.onclose = (event) => {
        console.log("WebSocket connection closed.", event.reason, event.code);
        showStatusMessage("Live updates disconnected. Attempting to reconnect...", true);
        setTimeout(connectWebSocket, 5000); 
    };
}

// --- Event Listeners & Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    setupPasswordToggles();
    
    if(fetchButton) {
        fetchButton.addEventListener('click', fetchAndDisplayAggregatedCurrentVolume);
    }
    if(fetchCurrentPlatformVolumeButton) {
        fetchCurrentPlatformVolumeButton.addEventListener('click', fetchCurrentPlatformVolume);
    }
    if(fetchHistoricalPlatformVolumeButton) {
        fetchHistoricalPlatformVolumeButton.addEventListener('click', fetchHistoricalPlatformData);
    }
    if(fetchAllHistoricalVolumeButton) {
        fetchAllHistoricalVolumeButton.addEventListener('click', fetchAllHistoricalData);
    }
    if(saveAllKeysButton) {
        saveAllKeysButton.addEventListener('click', saveAllApiKeys);
    }

    const today = new Date().toISOString().split('T')[0];
    const oneYearAgo = new Date(new Date().setFullYear(new Date().getFullYear() - 1)).toISOString().split('T')[0];
    if(startDateInput) startDateInput.value = oneYearAgo;
    if(endDateInput) endDateInput.value = today;
    
    fetchAndDisplayAggregatedCurrentVolume(); // This will also trigger chart rendering
    connectWebSocket();
});

function getCurrentTotalVolume() {
    const currentText = totalVolumeElement.textContent;
    if (currentText.startsWith('$')) {
        return currentText;
    }
    return "Data not available"; 
}
window.getCurrentTotalVolume = getCurrentTotalVolume;
