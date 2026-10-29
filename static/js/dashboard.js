document.addEventListener('DOMContentLoaded', initDashboard);

// Use relative paths if served from the same server, fallback to 127.0.0.1 for local file testing
const API_BASE = (window.location.protocol === 'http:' || window.location.protocol === 'https:')
    ? ''
    : 'http://127.0.0.1:5000';

async function initDashboard() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/dashboard`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });

        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }

        const data = await res.json();
        if (res.ok) {
            // Ensure data exists before rendering
            if (data.user_stats && data.counts) {
                renderTopCards(data.user_stats, data.counts, data.income_expense_data);
            }
            if (data.intelligence) {
                renderIntelligence(data.intelligence);
            }

            // New Charts Rendering
            renderCharts_All(data);

            if (data.recent_alerts && Array.isArray(data.recent_alerts)) {
                renderAlerts(data.recent_alerts);
            }
            renderRecurring(data.recurring_payments);
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

function renderTopCards(stats, counts, incomeExpenseData) {
    document.getElementById('total-txns').innerText = counts.total_transactions;
    document.getElementById('suspicious-activity').innerText = counts.suspicious_activity;
    document.getElementById('disputed-txns').innerText = counts.disputed_transactions;

    // Security Status: Strong=green, Moderate=yellow, Weak=red
    const secStatus = document.getElementById('security-status');
    secStatus.innerText = stats.security_status || 'Not assessed';
    secStatus.style.color = stats.security_status === 'Strong' ? '#2ecc71'
        : stats.security_status === 'Moderate' ? '#f1c40f'
        : '#e74c3c';

    // Net Cash Flow: sum of (income - expense) from last 30 days
    const netEl = document.getElementById('net-cash-flow');
    if (incomeExpenseData && incomeExpenseData.length > 0) {
        const net = incomeExpenseData.reduce((acc, d) => acc + (d.income || 0) - (d.expense || 0), 0);
        netEl.innerText = (net >= 0 ? '+' : '-') + '₹' + Math.abs(Math.round(net)).toLocaleString('en-IN');
        netEl.style.color = net >= 0 ? '#2ecc71' : '#e74c3c';
    } else {
        netEl.innerText = 'No data';
        netEl.style.color = 'var(--text-muted)';
    }
}

// Old single chart render removed/replaced by renderCharts_All


function renderIntelligence(intel) {
    const predEl = document.getElementById('expense-pred');
    const noteEl = document.getElementById('expense-pred-note');
    if (intel.expense_prediction === null || intel.expense_prediction === undefined) {
        predEl.innerText = 'No data yet';
        if (noteEl) noteEl.innerText = 'Upload a bank statement to enable';
    } else {
        predEl.innerText = '₹' + Number(intel.expense_prediction).toLocaleString('en-IN');
        if (noteEl && intel.months_used) noteEl.innerText = `Based on ${intel.months_used} month(s) of data`;
    }

    const riskEl = document.getElementById('fraud-risk');
    const riskNoteEl = document.getElementById('fraud-risk-note');
    const risk = intel.fraud_risk_level || 'Not assessed';
    const flagged = intel.flagged_count !== undefined ? intel.flagged_count : null;
    riskEl.innerText = risk;
    riskEl.style.color = risk === 'Low' ? '#2ecc71' : risk === 'Medium' ? '#f1c40f' : risk === 'High' ? '#e74c3c' : 'var(--text-muted)';
    if (riskNoteEl && flagged !== null) riskNoteEl.innerText = `${flagged} flagged transaction(s)`;

    const avgEl = document.getElementById('avg-spend');
    if (avgEl) avgEl.innerText = intel.avg_monthly_spend ? '₹' + Number(intel.avg_monthly_spend).toLocaleString('en-IN') : '-';
}

function renderRecurring(recurring) {
    const el = document.getElementById('recurring-list');
    if (!el) return;
    if (!recurring || recurring.length === 0) {
        el.innerHTML = '<span style="color:#aaa; font-size:0.85rem;">No recurring payments detected yet. Upload more statements to detect patterns.</span>';
        return;
    }
    el.innerHTML = recurring.map(r => `
        <div style="background:rgba(0,0,0,0.2); padding:0.75rem 1rem; border-radius:8px; min-width:160px; flex:1;">
            <div style="font-weight:600; font-size:0.88rem;">${r.description || r.merchant || 'Payment'}</div>
            <div style="color:#2ecc71; font-weight:bold; margin:3px 0;">₹${Number(r.amount).toLocaleString('en-IN')}</div>
            <div style="font-size:0.75rem; color:#aaa;">${r.frequency || 'Monthly'} · ${r.channel || ''}</div>
        </div>
    `).join('');
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
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;width:100%;align-items:center;';
        const icon = document.createElement('div');
        icon.className = 'alert-icon';
        icon.innerHTML = '<i class="fas fa-exclamation-triangle" aria-hidden="true"></i>';
        const info = document.createElement('div');
        info.className = 'alert-info';
        const title = document.createElement('div');
        title.className = 'alert-title';
        title.textContent = `Model-flagged transaction #${a.transaction_id}`;
        const meta = document.createElement('div');
        meta.className = 'alert-meta';
        meta.textContent = `${new Date(a.timestamp).toLocaleDateString()} · ₹${Number(a.transaction_amount || 0).toLocaleString()}`;
        info.append(title, meta);
        const action = document.createElement('div');
        action.className = 'alert-action';
        const reviewButton = document.createElement('button');
        reviewButton.type = 'button';
        reviewButton.className = 'btn-sm btn-outline';
        reviewButton.textContent = 'Review';
        const result = document.createElement('div');
        result.id = `review-result-${a.transaction_id}`;
        result.style.cssText = 'display:none;width:100%;margin-top:10px;padding:10px;background:rgba(255,255,255,0.05);border-radius:6px;font-size:0.9rem;white-space:pre-wrap;';
        reviewButton.addEventListener('click', () => reviewAlert(a.transaction_id, a.transaction_amount, a.channel, a.timestamp));
        action.append(reviewButton);
        row.append(icon, info, action);
        item.append(row, result);
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
            resultDiv.textContent = data.analysis;
            resultDiv.style.color = '#ddd';
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
    const trustScore = stats.trust_score;
    if (trustScoreElement) {
        trustScoreElement.innerText = trustScore === null || trustScore === undefined ? 'N/A' : trustScore;
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
    if (data.user_stats) renderTrustGauge(data.user_stats.trust_score);

    // 6. AI Prediction (Line Comparison)
    if (data.prediction_data) renderPredictionChart(data.prediction_data);
}

// --- Chart Rendering Functions ---

function showChartEmpty(canvas, message) {
    canvas.style.display = 'none';
    let empty = canvas.parentElement.querySelector('.chart-empty');
    if (!empty) {
        empty = document.createElement('p');
        empty.className = 'chart-empty text-muted';
        empty.style.cssText = 'display:grid;place-items:center;height:100%;text-align:center;padding:1rem;';
        canvas.parentElement.appendChild(empty);
    }
    empty.textContent = message;
}

function clearChartEmpty(canvas) {
    canvas.style.display = '';
    canvas.parentElement.querySelector('.chart-empty')?.remove();
}

function renderVolumeChart(chartData) {
    const ctx = document.getElementById('txnVolumeChart');
    if (!ctx) return;
    if (!chartData?.length) { showChartEmpty(ctx, 'No transaction volume available for this period.'); return; }
    clearChartEmpty(ctx);

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
    if (!data?.length) { showChartEmpty(ctx, 'Income and expense direction is not available yet.'); return; }
    clearChartEmpty(ctx);

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
    if (!data?.length) { showChartEmpty(ctx, 'No categorized debit transactions available.'); return; }
    clearChartEmpty(ctx);

    const labels = data.map(d => d.category);
    const values = data.map(d => d.amount);

    const palette = [
        '#4e54c8','#2ecc71','#e74c3c','#f1c40f','#9b59b6','#3b82f6',
        '#f97316','#06b6d4','#10b981','#a78bfa','#fbbf24','#f472b6',
        '#60a5fa','#34d399','#fb923c','#4ade80','#8f94fb','#ef4444'
    ];
    const colors = labels.map((_, i) => palette[i % palette.length]);

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { bottom: 4 } },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#ccc',
                        boxWidth: 12,
                        padding: 10,
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => ` ${ctx.label}: ₹${Number(ctx.raw).toLocaleString('en-IN')}`
                    }
                }
            }
        }
    });
}

function renderFraudTrendChart(data) {
    const ctx = document.getElementById('fraudTrendChart');
    if (!ctx) return;
    if (!data?.length) { showChartEmpty(ctx, 'No model-flagged transactions in this period.'); return; }
    clearChartEmpty(ctx);

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
    const textEl = document.getElementById('trust-score-val');
    if (score === null || score === undefined) {
        ctx.style.display = 'none';
        if (textEl) {
            textEl.innerText = 'N/A';
            textEl.nextElementSibling.innerText = 'Not assessed';
        }
        return;
    }
    ctx.style.display = '';

    // Determine color
    let color = '#e74c3c';
    let label = 'Risky';
    if (score > 70) { color = '#2ecc71'; label = 'Excellent'; }
    else if (score > 40) { color = '#f1c40f'; label = 'Fair'; }

    // Update text
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
    if (!data?.length) { showChartEmpty(ctx, 'Insufficient validated history for a forecast.'); return; }
    clearChartEmpty(ctx);

    const labels = data.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }));
    const actual = data.map(d => d.actual ?? null);

    // Bridge the prediction line from the last actual point → forecast point
    // Without this, predicted has only one non-null value (a dot, not a line).
    const predicted = data.map(d => d.predicted ?? null);
    const lastActualIdx = actual.reduce((acc, v, i) => v !== null ? i : acc, -1);
    if (lastActualIdx >= 0 && predicted[predicted.length - 1] !== null) {
        predicted[lastActualIdx] = actual[lastActualIdx];
    }

    new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Actual Spend',
                    data: actual,
                    borderColor: '#4e54c8',
                    backgroundColor: 'rgba(78, 84, 200, 0.1)',
                    fill: true,
                    tension: 0.4,
                    spanGaps: false
                },
                {
                    label: 'AI Prediction',
                    data: predicted,
                    borderColor: '#f1c40f',
                    borderDash: [6, 4],
                    backgroundColor: 'rgba(241, 196, 15, 0.08)',
                    tension: 0.4,
                    pointStyle: 'rectRot',
                    pointRadius: 5,
                    spanGaps: true
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
