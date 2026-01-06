document.addEventListener('DOMContentLoaded', initDashboard);

// Use relative paths if served from the same server, fallback to 127.0.0.1 for local file testing
const API_BASE = (window.location.protocol === 'http:' || window.location.protocol === 'https:')
    ? ''
    : 'http://127.0.0.1:5000';

async function initDashboard() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = 'auth.html';
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/dashboard`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });

        if (res.status === 401) {
            window.location.href = 'auth.html'; // Token expired
            return;
        }

        const data = await res.json();
        if (res.ok) {
            // Ensure data exists before rendering
            if (data.user_stats && data.counts) {
                renderTopCards(data.user_stats, data.counts);
            }
            if (data.intelligence) {
                renderIntelligence(data.intelligence);
            }

            // New Charts Rendering
            renderCharts_All(data);

            if (data.recent_alerts && Array.isArray(data.recent_alerts)) {
                renderAlerts(data.recent_alerts);
            }
            if (data.user_stats) {
                renderTrustCard(data.user_stats);
            }
        } else {
            console.error('Dashboard error:', data);
            // Show error message
            const container = document.querySelector('.container');
            if (container) {
                container.innerHTML = '<div class="glass card"><h2>Error Loading Dashboard</h2><p>' + (data.error || 'Unknown error') + '</p></div>';
            }
        }
    } catch (e) {
        console.error('Failed to load dashboard:', e);
        // Show actual error message
        const container = document.querySelector('.container');
        if (container) {
            container.innerHTML = `<div class="glass card">
                <h2>Something went wrong</h2>
                <p style="color: #e74c3c; font-weight: bold;">${e.message}</p>
                <p style="font-size: 0.9em; color: #ccc;">Check console for details.</p>
                <button class="btn" onclick="location.reload()">Retry</button>
            </div>`;
        }
    }
}

function renderTopCards(stats, counts) {
    document.getElementById('total-txns').innerText = counts.total_transactions;
    document.getElementById('suspicious-activity').innerText = counts.suspicious_activity;
    document.getElementById('pending-verifications').innerText = counts.pending_verifications;

    // Security Status Color
    const secStatus = document.getElementById('security-status');
    secStatus.innerText = stats.security_status;
    secStatus.style.color = stats.security_status === 'Strong' ? '#2ecc71' : (stats.security_status === 'Moderate' ? '#f1c40f' : '#e74c3c');

    document.getElementById('current-balance').innerText = '₹' + stats.balance.toLocaleString();
}

// Old single chart render removed/replaced by renderCharts_All


function renderIntelligence(intel) {
    document.getElementById('expense-pred').innerText = '₹' + intel.expense_prediction.toLocaleString();

    const riskEl = document.getElementById('fraud-risk');
    riskEl.innerText = intel.fraud_risk_level;
    riskEl.style.color = intel.fraud_risk_level === 'Low' ? '#2ecc71' : (intel.fraud_risk_level === 'Medium' ? '#f1c40f' : '#e74c3c');
}

function renderAlerts(alerts) {
    const list = document.getElementById('alerts-list');
    list.innerHTML = '';

    if (alerts.length === 0) {
        list.innerHTML = '<div class="text-muted">No recent alerts</div>';
        return;
    }

    alerts.forEach(a => {
        const item = document.createElement('div');
        item.className = 'alert-item glass';
        item.style.flexDirection = 'column'; // Allow expansion
        item.innerHTML = `
            <div style="display:flex; width:100%; align-items:center;">
                <div class="alert-icon"><i class="fas fa-exclamation-triangle"></i></div>
                <div class="alert-info">
                    <div class="alert-title">Suspicious Txn #${a.transaction_id}</div>
                    <div class="alert-meta">${new Date(a.timestamp).toLocaleDateString()} • ₹${a.transaction_amount.toLocaleString()}</div>
                </div>
                <div class="alert-action">
                    <button class="btn-sm btn-outline" onclick="reviewAlert('${a.transaction_id}', '${a.transaction_amount}', '${a.channel}', '${a.timestamp}')">Review</button>
                </div>
            </div>
            <div id="review-result-${a.transaction_id}" style="display:none; width:100%; margin-top:10px; padding:10px; background:rgba(255,255,255,0.05); border-radius:6px; font-size:0.9rem;"></div>
        `;
        list.appendChild(item);
    });
}

async function reviewAlert(id, amount, channel, timestamp) {
    const resultDiv = document.getElementById(`review-result-${id}`);
    if (!resultDiv) return;

    if (resultDiv.style.display === 'block') {
        resultDiv.style.display = 'none'; // Toggle off
        return;
    }

    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Analyzing...</div>';

    try {
        const token = localStorage.getItem('token');
        const res = await fetch(API_BASE + '/api/analyze', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                amount: parseFloat(amount) || 0,
                channel: channel || 'Unknown',
                timestamp: timestamp || new Date().toISOString()
            })
        });

        const data = await res.json();

        if (res.ok && data.analysis) {
            let formatted = data.analysis
                .replace(/\n\n/g, '<br><br>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            resultDiv.innerHTML = `<div style="color:#ddd;">${formatted}</div>`;
        } else {
            resultDiv.innerHTML = '<div style="color:orange;">Analysis unavailable.</div>';
        }
    } catch (e) {
        resultDiv.innerHTML = '<div style="color:red;">Error loading analysis.</div>';
    }
}

function renderTrustCard(stats) {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    document.getElementById('user-name').innerText = user.name || 'User';

    const kycElement = document.getElementById('user-kyc');
    if (kycElement) {
        kycElement.innerText = stats.kyc_status || 'Pending';
    }

    const trustScoreElement = document.getElementById('trust-score');
    const trustScore = stats.trust_score || 0;
    if (trustScoreElement) {
        trustScoreElement.innerText = trustScore;
    }

    // Circle progress handled by gauge chart now
}

function renderCharts_All(data) {
    // 1. Transaction Volume (Line)
    renderVolumeChart(data.chart_data);

    // 2. Income vs Expense (Area)
    if (data.income_expense_data) renderIncomeExpenseChart(data.income_expense_data);

    // 3. Spending Categories (Donut)
    if (data.category_data) renderCategoryChart(data.category_data);

    // 4. Fraud Alerts Trend (Bar)
    if (data.fraud_trend_data) renderFraudTrendChart(data.fraud_trend_data);

    // 5. Trust Score (Gauge)
    if (data.user_stats) renderTrustGauge(data.user_stats.trust_score || 0);

    // 6. AI Prediction (Line Comparison)
    if (data.prediction_data) renderPredictionChart(data.prediction_data);
}

// --- Chart Rendering Functions ---

function renderVolumeChart(chartData) {
    const ctx = document.getElementById('txnVolumeChart');
    if (!ctx) return;

    const labels = chartData.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const values = chartData.map(d => d.value);

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Volume',
                data: values,
                borderColor: '#4e54c8',
                backgroundColor: 'rgba(78, 84, 200, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: getCommonChartOptions({ yTitle: 'Amount (₹)' })
    });
}

function renderIncomeExpenseChart(data) {
    const ctx = document.getElementById('incomeExpenseChart');
    if (!ctx) return;

    const labels = data.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const income = data.map(d => d.income);
    const expense = data.map(d => d.expense);

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Income',
                    data: income,
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    fill: true,
                    tension: 0.4
                },
                {
                    label: 'Expense',
                    data: expense,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    fill: true,
                    tension: 0.4
                }
            ]
        },
        options: getCommonChartOptions({ yTitle: 'Amount (₹)' })
    });
}

function renderCategoryChart(data) {
    const ctx = document.getElementById('categoryChart');
    if (!ctx) return;

    const labels = data.map(d => d.category);
    const values = data.map(d => d.amount);

    // Generate colors
    const colors = ['#4e54c8', '#8f94fb', '#2ecc71', '#f1c40f', '#e74c3c', '#9b59b6'];

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#ccc' } }
            }
        }
    });
}

function renderFraudTrendChart(data) {
    const ctx = document.getElementById('fraudTrendChart');
    if (!ctx) return;

    const labels = data.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const values = data.map(d => d.count);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Fraud Alerts',
                data: values,
                backgroundColor: '#e74c3c',
                borderRadius: 4
            }]
        },
        options: getCommonChartOptions({ yTitle: 'Alerts' })
    });
}

function renderTrustGauge(score) {
    const ctx = document.getElementById('trustGaugeChart');
    if (!ctx) return;

    // Determine color
    let color = '#e74c3c';
    let label = 'Risky';
    if (score > 70) { color = '#2ecc71'; label = 'Excellent'; }
    else if (score > 40) { color = '#f1c40f'; label = 'Fair'; }

    // Update text
    const textEl = document.getElementById('trust-score-val');
    if (textEl) {
        textEl.innerText = score;
        textEl.style.color = color;
        textEl.nextElementSibling.innerText = label;
    }

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Trust', 'Gap'],
            datasets: [{
                data: [score, 100 - score],
                backgroundColor: [color, 'rgba(255,255,255,0.1)'],
                borderWidth: 0,
                circumference: 180,
                rotation: 270,
                cutout: '80%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            }
        }
    });
}

function renderPredictionChart(data) {
    const ctx = document.getElementById('predictionChart');
    if (!ctx) return;

    const labels = data.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const actual = data.map(d => d.actual);
    const predicted = data.map(d => d.predicted);

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Actual',
                    data: actual,
                    borderColor: '#4e54c8',
                    backgroundColor: 'rgba(78, 84, 200, 0.1)',
                    tension: 0.4
                },
                {
                    label: 'AI Prediction',
                    data: predicted,
                    borderColor: '#f1c40f',
                    borderDash: [5, 5],
                    tension: 0.4,
                    pointStyle: 'rectRot'
                }
            ]
        },
        options: getCommonChartOptions({ yTitle: 'Spending (₹)' })
    });
}

function getCommonChartOptions({ yTitle } = {}) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: '#ccc' } }
        },
        scales: {
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#aaa' },
                title: { display: !!yTitle, text: yTitle, color: '#aaa' }
            },
            x: {
                grid: { display: false },
                ticks: { color: '#aaa' }
            }
        }
    };
}

// --- Chatbot Functions ---

function toggleChat() {
    const win = document.getElementById('chat-window');
    win.classList.toggle('hidden');
}

function handleChatKey(e) {
    if (e.key === 'Enter') sendMessage();
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;

    // Add User Msg
    addMsg(msg, 'user-msg');
    input.value = '';

    // Show Typing
    const typingId = addMsg('Thinking...', 'bot-msg');

    try {
        const res = await fetch(API_BASE + '/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify({ query: msg })
        });
        const data = await res.json();

        // Remove typing
        document.getElementById(typingId).remove();

        if (data.response) {
            addMsg(data.response, 'bot-msg');
        } else {
            addMsg('Sorry, I encountered an error.', 'bot-msg');
        }
    } catch (e) {
        if (document.getElementById(typingId)) {
            document.getElementById(typingId).innerText = 'Connection error.';
        }
    }
}

function addMsg(text, className) {
    const body = document.getElementById('chat-body');
    const div = document.createElement('div');
    div.className = `chat-msg ${className}`;
    div.innerText = text;
    div.id = 'msg-' + Date.now();
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    return div.id;
}


// --- Modal Functions ---

function openModal(id) {
    document.getElementById('modal-overlay').style.display = 'flex';
    document.querySelectorAll('.modal-content').forEach(el => el.style.display = 'none');
    document.getElementById(id).style.display = 'block';
}

function closeModal() {
    document.getElementById('modal-overlay').style.display = 'none';
}

async function submitTransfer() {
    const recipient = document.getElementById('transfer-recipient').value;
    const amount = document.getElementById('transfer-amount').value;

    if (!recipient || !amount) {
        alert('Please fill all fields');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/transfer`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify({ recipient_id: recipient, amount: amount })
        });
        const data = await res.json();
        if (res.ok) {
            alert('Transfer Successful!');
            closeModal();
            initDashboard(); // Refresh data
        } else {
            alert('Error: ' + data.error);
        }
    } catch (e) {
        console.error(e);
        alert('Transfer failed');
    }
}

async function submitLoan() {
    const amount = document.getElementById('loan-amount').value;
    const purpose = document.getElementById('loan-purpose').value;

    try {
        const res = await fetch(`${API_BASE}/api/loan/apply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify({ amount: amount, purpose: purpose })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            closeModal();
        } else {
            alert('Error: ' + data.error);
        }
    } catch (e) { console.error(e); alert('Request failed'); }
}

async function submitInsurance() {
    const type = document.getElementById('insurance-type').value;
    const coverage = document.getElementById('insurance-coverage').value;

    try {
        const res = await fetch(`${API_BASE}/api/insurance/apply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            },
            body: JSON.stringify({ type: type, coverage: coverage })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            closeModal();
        } else {
            alert('Error: ' + data.error);
        }
    } catch (e) { console.error(e); alert('Request failed'); }
}
