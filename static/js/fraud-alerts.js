document.addEventListener('DOMContentLoaded', loadAlerts);

async function loadAlerts() {
  const token = localStorage.getItem('token');
  if (!token) {
    window.location.href = '/login';
    return;
  }

  const container = document.getElementById('alertsList');
  const status = document.getElementById('alerts-status');
  try {
    const response = await fetch('/api/alerts', {
      headers: { Authorization: `Bearer ${token}` }
    });
    const alerts = await response.json();
    if (!response.ok) throw new Error(alerts.error || 'Could not load flagged transactions.');
    if (!Array.isArray(alerts)) throw new Error('The alerts service returned an unexpected response.');

    container.replaceChildren();
    if (!alerts.length) {
      status.textContent = 'No flagged transactions are currently available for review.';
      return;
    }

    updateStatus(alerts);
    alerts.forEach((alert) => container.append(createAlertCard(alert, token)));
  } catch (error) {
    console.error('Failed to load investigation queue:', error);
    status.textContent = error.message || 'Failed to load flagged transactions.';
    status.classList.add('error');
    container.replaceChildren();
  }
}

function updateStatus(alerts) {
  const open = alerts.filter((alert) => !alert.review_status).length;
  const confirmed = alerts.filter((alert) => alert.review_status === 'confirmed_fraud').length;
  document.getElementById('alerts-status').textContent =
    `${open} to review · ${confirmed} confirmed as fraud. Your verdicts become training labels for the next retrain.`;
}

let currentAlerts = [];

function createAlertCard(alert, token) {
  if (!currentAlerts.includes(alert)) currentAlerts.push(alert);
  const card = document.createElement('article');
  card.className = 'alert-card glass';
  if (alert.review_status === 'confirmed_fraud') card.classList.add('is-confirmed');

  const header = document.createElement('div');
  header.className = 'alert-card-header';

  const title = document.createElement('h2');
  title.textContent = `Transaction ${alert.transaction_id || 'reference unavailable'}`;
  const badge = document.createElement('span');
  badge.className = 'risk-badge';
  const riskScore = Number(alert.risk_score);
  badge.textContent = alert.review_status === 'confirmed_fraud'
    ? 'Confirmed fraud'
    : Number.isFinite(riskScore)
      ? `Risk ${riskScore.toFixed(0)}/100 · ${['High', 'Medium', 'Low'].includes(alert.risk_level) ? alert.risk_level : 'review'}`
      : 'Flagged record · review';
  header.append(title, badge);

  const metadata = document.createElement('p');
  metadata.className = 'alert-meta';
  const amount = Number(alert.transaction_amount);
  const currency = typeof alert.currency === 'string' && /^[A-Z]{3}$/.test(alert.currency)
    ? alert.currency
    : 'INR';
  metadata.append(
    document.createTextNode(`Amount: ${formatAmount(amount, currency)} · Channel: ${alert.channel || 'Unknown'} · `),
    document.createTextNode(`Time: ${formatDate(alert.timestamp)}`)
  );

  if (Number.isFinite(alert.fraud_probability) &&
      alert.fraud_probability >= 0 && alert.fraud_probability <= 1) {
    metadata.append(document.createElement('br'));
    metadata.append(document.createTextNode(
      `Model output score: ${(alert.fraud_probability * 100).toFixed(1)}% · not a calibrated probability`
    ));
  }

  const reasons = document.createElement('ul');
  reasons.className = 'alert-reasons';
  (Array.isArray(alert.risk_reasons) ? alert.risk_reasons : []).slice(0, 6).forEach((reason) => {
    const item = document.createElement('li');
    item.textContent = String(reason);
    reasons.append(item);
  });

  const actions = document.createElement('div');
  actions.className = 'alert-actions';

  const explainButton = document.createElement('button');
  explainButton.type = 'button';
  explainButton.className = 'btn';
  explainButton.textContent = 'Explain this record with Gemini';

  const evidenceButton = document.createElement('button');
  evidenceButton.type = 'button';
  evidenceButton.className = 'btn btn-outline';
  evidenceButton.textContent = 'Investigate with report evidence';

  const result = document.createElement('div');
  result.className = 'ai-result';
  result.setAttribute('role', 'status');
  result.hidden = true;

  explainButton.addEventListener('click', () => explainTransaction(alert, token, result, explainButton));
  evidenceButton.addEventListener('click', () => openEvidenceWorkspace(alert));

  const verdicts = document.createElement('div');
  verdicts.className = 'verdict-actions';
  const verdictButton = (label, verdict, className) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `btn ${className}`;
    button.textContent = label;
    button.addEventListener('click', () => submitVerdict(alert, verdict, card, token));
    return button;
  };
  if (alert.review_status === 'confirmed_fraud') {
    verdicts.append(verdictButton('Reopen', 'reopen', 'btn-outline'));
  } else {
    verdicts.append(verdictButton('Mark legitimate', 'legitimate', 'btn-legit'), verdictButton('Confirm fraud', 'fraud', 'btn-fraud'));
  }

  actions.append(explainButton, evidenceButton, verdicts);
  card.append(header, metadata);
  if (reasons.children.length) card.append(reasons);
  card.append(actions, result);
  return card;
}

async function submitVerdict(alert, verdict, card, token) {
  card.querySelectorAll('button').forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch(`/api/alerts/${encodeURIComponent(alert.transaction_id)}/review`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The verdict could not be saved.');

    if (verdict === 'legitimate') {
      currentAlerts = currentAlerts.filter((item) => item !== alert);
      const note = document.createElement('article');
      note.className = 'alert-card glass verdict-note';
      note.append(document.createTextNode(`Transaction ${alert.transaction_id} marked legitimate. `));
      const undo = document.createElement('button');
      undo.type = 'button';
      undo.className = 'btn btn-outline';
      undo.textContent = 'Undo';
      undo.addEventListener('click', async () => {
        undo.disabled = true;
        const reopened = await fetch(`/api/alerts/${encodeURIComponent(alert.transaction_id)}/review`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ verdict: 'reopen' })
        });
        if (reopened.ok) {
          delete alert.review_status;
          note.replaceWith(createAlertCard(alert, token));
          updateStatus(currentAlerts);
        } else {
          undo.disabled = false;
        }
      });
      note.append(undo);
      card.replaceWith(note);
    } else {
      if (verdict === 'fraud') alert.review_status = 'confirmed_fraud';
      else delete alert.review_status;
      card.replaceWith(createAlertCard(alert, token));
    }
    updateStatus(currentAlerts);
  } catch (error) {
    console.error('Verdict failed:', error);
    window.alert(error.message || 'The verdict could not be saved.');
    card.querySelectorAll('button').forEach((button) => { button.disabled = false; });
  }
}

function formatAmount(amount, currency) {
  if (!Number.isFinite(amount)) return 'Not available';
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2
    }).format(amount);
  } catch {
    return `${currency} ${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
}

function formatDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : 'Date unavailable';
}

async function explainTransaction(alert, token, result, button) {
  button.disabled = true;
  result.hidden = false;
  result.textContent = 'Generating a transaction explanation…';
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        amount: Number(alert.transaction_amount) || 0,
        channel: alert.channel || 'Unknown',
        account_age: 'Unknown',
        kyc_verified: 'Unknown',
        timestamp: alert.timestamp || new Date().toISOString()
      })
    });
    const data = await response.json();
    if (!response.ok || !data.analysis) {
      throw new Error(data.error || 'The AI explanation service did not return an answer.');
    }
    result.textContent = data.analysis;
  } catch (error) {
    console.error('Transaction explanation failed:', error);
    result.textContent = error.message || 'Could not generate an explanation. Please try again.';
  } finally {
    button.disabled = false;
  }
}

function openEvidenceWorkspace(alert) {
  try {
    const timestamp = alert.timestamp ? new Date(alert.timestamp) : null;
    sessionStorage.setItem('finrag-investigation-context', JSON.stringify({
      version: 1,
      transactionId: String(alert.transaction_id || ''),
      amount: Number(alert.transaction_amount),
      currency: typeof alert.currency === 'string' ? alert.currency.toUpperCase() : '',
      channel: String(alert.channel || ''),
      timestamp: timestamp && !Number.isNaN(timestamp.getTime()) ? timestamp.toISOString() : ''
    }));
    window.location.href = '/rag';
  } catch (error) {
    console.error('Could not transfer transaction context to the document workspace:', error);
    document.getElementById('alerts-status').textContent =
      'Could not open the evidence workspace. Please enable session storage and try again.';
    document.getElementById('alerts-status').classList.add('error');
  }
}
