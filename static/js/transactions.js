(() => {
  const token = localStorage.getItem('token');
  const apiBase = window.location.protocol === 'file:' ? 'http://localhost:5000' : window.location.origin;
  const elements = {
    rows: document.getElementById('transaction-rows'),
    resultCount: document.getElementById('result-count'),
    loadedCount: document.getElementById('loaded-count'),
    search: document.getElementById('transaction-search'),
    selectVisible: document.getElementById('select-visible'),
    bulkBar: document.getElementById('bulk-bar'),
    selectedCount: document.getElementById('selected-count'),
    customDateToggle: document.getElementById('custom-date-toggle'),
    customDateFilter: document.getElementById('custom-date-filter'),
    startDate: document.getElementById('start-date'),
    endDate: document.getElementById('end-date'),
    refresh: document.getElementById('refresh-transactions')
  };

  let transactions = [];
  let selectedIds = new Set();
  let selectedStatus = 'all';
  let page = 1;
  const pageSize = 50;
  let totalMatching = 0;
  let summary = {};
  let dateRange = { start: null, end: null };
  let searchTimer = null;
  let requestSequence = 0;

  if (!token) {
    window.location.href = 'auth.html';
    return;
  }

  function escapeCsv(value) {
    let text = String(value ?? '');
    if (/^[\t\r ]*[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  }

  function localDateString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function dateTimeParam(date, endOfDay = false) {
    const value = new Date(date);
    if (endOfDay) value.setHours(23, 59, 59, 999);
    else value.setHours(0, 0, 0, 0);
    return `${localDateString(value)}T${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}:${String(value.getSeconds()).padStart(2, '0')}.${String(value.getMilliseconds()).padStart(3, '0')}`;
  }

  function isFlagged(transaction) {
    return transaction.is_fraud === true || Number(transaction.is_fraud) === 1;
  }

  function isDisputed(transaction) {
    return transaction.disputed === true;
  }

  function hasReviewResult(transaction) {
    return transaction.is_fraud === true || transaction.is_fraud === false || transaction.is_fraud === 0 || transaction.is_fraud === 1 || transaction.is_fraud === '0' || transaction.is_fraud === '1';
  }

  function transactionId(transaction) {
    return String(transaction.transaction_id ?? transaction._id ?? '');
  }

  function displayDate(value, options = { day: '2-digit', month: 'short', year: 'numeric' }) {
    if (!value) return 'Date unavailable';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat(undefined, options).format(date);
  }

  function formatAmount(transaction) {
    const amount = Number(transaction.transaction_amount);
    if (!Number.isFinite(amount)) return 'Amount unavailable';

    const currencyValue = String(transaction.currency || 'INR').trim();
    const direction = String(transaction.direction || '').toLowerCase();
    const sign = amount < 0 || direction === 'debit' ? '\u2212' : direction === 'credit' ? '+' : '';
    const magnitude = Math.abs(amount);
    let formatted;
    if (/^[A-Za-z]{3}$/.test(currencyValue)) {
      try {
        formatted = new Intl.NumberFormat(undefined, {
          style: 'currency',
          currency: currencyValue.toUpperCase(),
          maximumFractionDigits: 2
        }).format(magnitude);
      } catch {
        formatted = `${currencyValue.toUpperCase()} ${new Intl.NumberFormat().format(magnitude)}`;
      }
    } else {
      formatted = `${currencyValue} ${new Intl.NumberFormat().format(magnitude)}`;
    }
    return `${sign}${formatted}`;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderMessage(title, detail, icon = 'fa-circle-info') {
    const row = document.createElement('tr');
    const cell = element('td', 'table-message');
    cell.colSpan = 9;
    const state = element('div', 'empty-state');
    const symbol = element('i');
    symbol.className = `fa-solid ${icon}`;
    symbol.setAttribute('aria-hidden', 'true');
    state.append(symbol, element('strong', '', title), element('span', '', detail));
    cell.append(state);
    row.append(cell);
    elements.rows.replaceChildren(row);
  }

  function updateMetrics() {
    document.getElementById('metric-total').textContent = Number(summary.total || 0).toLocaleString();
    document.getElementById('metric-flagged').textContent = Number(summary.flagged || 0).toLocaleString();
    document.getElementById('metric-credits').textContent = Number(summary.credits || 0).toLocaleString();
    document.getElementById('metric-debits').textContent = Number(summary.debits || 0).toLocaleString();
    document.getElementById('metric-latest').textContent = summary.latest ? displayDate(summary.latest) : 'No activity';
  }

  function visibleTransactions() {
    return transactions;
  }

  function queryParams() {
    const params = new URLSearchParams();
    if (dateRange.start) params.set('start_date', dateRange.start);
    if (dateRange.end) params.set('end_date', dateRange.end);
    if (selectedStatus !== 'all') params.set('status', selectedStatus);
    const search = elements.search.value.trim();
    if (search) params.set('q', search);
    return params;
  }

  function buildTransactionRow(transaction) {
    const id = transactionId(transaction);
    const row = document.createElement('tr');
    const selectionCell = document.createElement('td');
    selectionCell.className = 'select-column';
    const checkbox = element('input', 'custom-check');
    checkbox.type = 'checkbox';
    checkbox.checked = selectedIds.has(id);
    checkbox.setAttribute('aria-label', `Select transaction ${id}`);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) selectedIds.add(id);
      else selectedIds.delete(id);
      updateSelection(visibleTransactions());
    });
    selectionCell.append(checkbox);

    const refCell = element('td', 'transaction-ref', id || 'Reference unavailable');
    const dateCell = element('td', 'transaction-date', displayDate(transaction.timestamp, { day: '2-digit', month: 'short', year: 'numeric' }));

    const descriptionCell = document.createElement('td');
    const description = transaction.description || transaction.category || transaction.customer_id || 'Transaction activity';
    descriptionCell.append(element('span', 'transaction-description', String(description)));
    if (transaction.category && transaction.description) {
      descriptionCell.append(element('span', 'transaction-subtext', String(transaction.category)));
    }

    const directionValue = String(transaction.direction || 'unknown').toLowerCase();
    const directionCell = document.createElement('td');
    const direction = element('span', `direction-label${directionValue === 'credit' ? ' is-credit' : directionValue === 'debit' ? ' is-debit' : ''}`);
    const directionIcon = element('i');
    directionIcon.className = `fa-solid ${directionValue === 'credit' ? 'fa-arrow-down' : directionValue === 'debit' ? 'fa-arrow-up' : 'fa-minus'}`;
    directionIcon.setAttribute('aria-hidden', 'true');
    direction.append(directionIcon, document.createTextNode(directionValue[0].toUpperCase() + directionValue.slice(1)));
    directionCell.append(direction);

    const channelCell = element('td', '', String(transaction.channel || 'Not recorded'));
    const amountCell = element('td', 'amount-value', formatAmount(transaction));

    const statusCell = document.createElement('td');
    const flagged = isFlagged(transaction);
    const assessed = hasReviewResult(transaction);
    const disputed = isDisputed(transaction);
    const badge = element('span', `status-badge ${flagged ? 'is-flagged' : assessed ? 'is-unflagged' : 'is-unknown'}`);
    badge.append(element('span', 'status-dot'), document.createTextNode(flagged ? 'Review' : assessed ? 'Not flagged' : 'Not assessed'));
    statusCell.append(badge);
    if (disputed) {
      const disputedBadge = element('span', 'disputed-badge');
      const disputedIcon = element('i');
      disputedIcon.className = 'fa-solid fa-flag';
      disputedIcon.setAttribute('aria-hidden', 'true');
      disputedBadge.append(disputedIcon, document.createTextNode('Disputed'));
      statusCell.append(document.createElement('br'), disputedBadge);
    }

    const actionCell = document.createElement('td');
    if (id) {
      const disputeButton = element('button', `row-action${disputed ? ' is-disputed' : ''}`);
      disputeButton.type = 'button';
      disputeButton.setAttribute('aria-label', `${disputed ? 'Remove dispute flag from' : 'Flag as disputed'} transaction ${id}`);
      disputeButton.title = disputed ? 'Remove dispute flag' : 'Flag as disputed';
      const disputeIcon = element('i');
      disputeIcon.className = 'fa-solid fa-flag';
      disputeIcon.setAttribute('aria-hidden', 'true');
      disputeButton.append(disputeIcon);
      disputeButton.addEventListener('click', () => toggleDispute(id, disputed));

      const deleteButton = element('button', 'row-action');
      deleteButton.type = 'button';
      deleteButton.setAttribute('aria-label', `Delete transaction ${id}`);
      deleteButton.title = 'Delete transaction';
      const deleteIcon = element('i');
      deleteIcon.className = 'fa-regular fa-trash-can';
      deleteIcon.setAttribute('aria-hidden', 'true');
      deleteButton.append(deleteIcon);
      deleteButton.addEventListener('click', () => deleteTransaction(id));
      actionCell.append(disputeButton, deleteButton);
    }

    row.append(selectionCell, refCell, dateCell, descriptionCell, directionCell, channelCell, amountCell, statusCell, actionCell);
    return row;
  }

  function updateSelection(visible) {
    elements.selectedCount.textContent = String(selectedIds.size);
    elements.bulkBar.hidden = selectedIds.size === 0;
    const visibleIds = visible.map(transactionId).filter(Boolean);
    const selectedVisible = visibleIds.filter((id) => selectedIds.has(id)).length;
    elements.selectVisible.checked = visibleIds.length > 0 && selectedVisible === visibleIds.length;
    elements.selectVisible.indeterminate = selectedVisible > 0 && selectedVisible < visibleIds.length;
    elements.selectVisible.disabled = visibleIds.length === 0;
  }

  function renderTransactions() {
    updateMetrics();
    const fragment = document.createDocumentFragment();
    transactions.forEach((transaction) => fragment.append(buildTransactionRow(transaction)));
    const filtered = queryParams().toString() !== '';
    if (transactions.length) elements.rows.replaceChildren(fragment);
    else if (!filtered) renderMessage('No transaction records yet', 'Upload a transaction file to see account activity here.', 'fa-arrow-up-from-bracket');
    else renderMessage('No matching transactions', 'Adjust the search or filters to see more records.');

    const first = totalMatching ? (page - 1) * pageSize + 1 : 0;
    const last = (page - 1) * pageSize + transactions.length;
    elements.resultCount.textContent = `${totalMatching.toLocaleString()} matching record${totalMatching === 1 ? '' : 's'}`;
    elements.loadedCount.textContent = totalMatching ? `Showing ${first.toLocaleString()}–${last.toLocaleString()} of ${totalMatching.toLocaleString()}` : 'No records';
    document.getElementById('page-prev').disabled = page <= 1;
    document.getElementById('page-next').disabled = last >= totalMatching;
    updateSelection(transactions);
  }

  async function loadTransactions() {
    const requestId = ++requestSequence;
    const params = queryParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    elements.refresh.classList.add('is-loading');
    elements.refresh.disabled = true;
    if (!transactions.length) {
      elements.rows.replaceChildren();
      const loadingRow = document.createElement('tr');
      const loadingCell = element('td', 'table-message');
      loadingCell.colSpan = 9;
      const spinner = element('span', 'loading-spinner');
      spinner.setAttribute('aria-hidden', 'true');
      loadingCell.append(spinner, document.createTextNode('Loading transaction records'));
      loadingRow.append(loadingCell);
      elements.rows.append(loadingRow);
    }

    try {
      const response = await fetch(`${apiBase}/api/transactions?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const data = await response.json();
      if (requestId !== requestSequence) return;
      if (!Array.isArray(data.items)) throw new Error('Unexpected transaction response');
      transactions = data.items;
      totalMatching = data.total || 0;
      summary = data.summary || {};
      renderTransactions();
    } catch (error) {
      if (requestId !== requestSequence) return;
      console.error('Unable to load transactions:', error);
      elements.resultCount.textContent = 'Transaction records could not be loaded';
      renderMessage('Unable to load transactions', 'Check your connection and try refreshing this view.', 'fa-triangle-exclamation');
    } finally {
      if (requestId === requestSequence) {
        elements.refresh.classList.remove('is-loading');
        elements.refresh.disabled = false;
      }
    }
  }

  function reload(resetPage = true) {
    if (resetPage) page = 1;
    loadTransactions();
  }

  async function deleteTransaction(id) {
    if (!window.confirm(`Delete transaction ${id}? This action cannot be undone.`)) return;
    try {
      const response = await fetch(`${apiBase}/api/transactions/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      selectedIds.delete(id);
      if (transactions.length === 1 && page > 1) page -= 1;
      loadTransactions();
    } catch (error) {
      console.error('Unable to delete transaction:', error);
      window.alert('The transaction could not be deleted. Please try again.');
    }
  }

  async function toggleDispute(id, currentlyDisputed) {
    try {
      const response = await fetch(`${apiBase}/api/transactions/${encodeURIComponent(id)}/dispute`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ disputed: !currentlyDisputed })
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const data = await response.json();
      const transaction = transactions.find((item) => transactionId(item) === id);
      if (transaction) transaction.disputed = data.disputed;
      renderTransactions();
    } catch (error) {
      console.error('Unable to update dispute status:', error);
      window.alert('The dispute flag could not be updated. Please try again.');
    }
  }

  function exportTransactions(rows, filenameSuffix) {
    if (!rows.length) {
      window.alert('There are no transactions to export for the current view.');
      return;
    }
    const columns = ['transaction_id', 'timestamp', 'description', 'direction', 'transaction_amount', 'currency', 'channel', 'model_review', 'disputed'];
    const csvRows = rows.map((transaction) => [
      transactionId(transaction), transaction.timestamp, transaction.description || transaction.category || '',
      transaction.direction || 'unknown', Number(transaction.transaction_amount), transaction.currency || 'INR',
      transaction.channel || '', isFlagged(transaction) ? 'flagged for review' : hasReviewResult(transaction) ? 'not flagged' : 'not assessed',
      isDisputed(transaction) ? 'disputed' : ''
    ].map((value) => typeof value === 'number' ? String(value) : escapeCsv(value)).join(','));
    const csv = [columns.join(','), ...csvRows].join('\r\n');
    const url = URL.createObjectURL(new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `transactions-${filenameSuffix}-${localDateString(new Date())}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function exportStatement(button) {
    button.disabled = true;
    try {
      const response = await fetch(`${apiBase}/api/transactions/export?${queryParams()}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `statement-${localDateString(new Date())}.csv`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Unable to export statement:', error);
      window.alert('The statement could not be exported. Please try again.');
    } finally {
      button.disabled = false;
    }
  }

  function setActive(buttons, activeButton) {
    buttons.forEach((button) => {
      const active = button === activeButton;
      button.classList.toggle('is-active', active);
      if (button.hasAttribute('aria-pressed')) button.setAttribute('aria-pressed', String(active));
    });
  }

  function applyDateRange(range) {
    const now = new Date();
    const start = new Date(now);
    let startValue = null;
    let endValue = dateTimeParam(now, true);
    if (range === '1w') start.setDate(now.getDate() - 6);
    else if (range === '1m') start.setDate(now.getDate() - 29);
    else if (range === 'this_month') start.setDate(1);
    else if (range === 'all') endValue = null;
    if (range !== 'all') startValue = dateTimeParam(start);
    elements.customDateFilter.hidden = true;
    elements.customDateToggle.setAttribute('aria-expanded', 'false');
    dateRange = { start: startValue, end: endValue };
    reload();
  }

  document.querySelectorAll('.date-chip[data-range]').forEach((button) => {
    button.addEventListener('click', () => {
      setActive(document.querySelectorAll('.date-chip[data-range]'), button);
      applyDateRange(button.dataset.range);
    });
  });

  document.querySelectorAll('.status-filter').forEach((button) => {
    button.addEventListener('click', () => {
      setActive(document.querySelectorAll('.status-filter'), button);
      selectedStatus = button.dataset.status;
      reload();
    });
  });

  elements.search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => reload(), 300);
  });
  elements.refresh.addEventListener('click', () => reload(false));
  document.getElementById('page-prev').addEventListener('click', () => { page = Math.max(1, page - 1); loadTransactions(); });
  document.getElementById('page-next').addEventListener('click', () => { page += 1; loadTransactions(); });

  elements.customDateToggle.addEventListener('click', () => {
    elements.customDateFilter.hidden = !elements.customDateFilter.hidden;
    elements.customDateToggle.setAttribute('aria-expanded', String(!elements.customDateFilter.hidden));
  });

  document.getElementById('apply-custom-date').addEventListener('click', () => {
    const start = elements.startDate.value;
    const end = elements.endDate.value;
    if (!start || !end) {
      window.alert('Select both a start date and an end date.');
      return;
    }
    if (start > end) {
      window.alert('The start date must be on or before the end date.');
      return;
    }
    setActive(document.querySelectorAll('.date-chip[data-range]'), null);
    elements.customDateFilter.hidden = true;
    elements.customDateToggle.setAttribute('aria-expanded', 'false');
    dateRange = { start: dateTimeParam(new Date(`${start}T00:00:00`)), end: dateTimeParam(new Date(`${end}T00:00:00`), true) };
    reload();
  });

  elements.selectVisible.addEventListener('change', () => {
    const visible = visibleTransactions();
    visible.forEach((transaction) => {
      const id = transactionId(transaction);
      if (!id) return;
      if (elements.selectVisible.checked) selectedIds.add(id);
      else selectedIds.delete(id);
    });
    renderTransactions();
  });

  document.getElementById('clear-selection').addEventListener('click', () => {
    selectedIds.clear();
    renderTransactions();
  });

  document.getElementById('export-selected').addEventListener('click', () => {
    const selected = transactions.filter((transaction) => selectedIds.has(transactionId(transaction)));
    exportTransactions(selected, 'selected');
  });

  document.getElementById('export-all').addEventListener('click', (event) => exportStatement(event.currentTarget));

  document.addEventListener('keydown', (event) => {
    if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
    const active = document.activeElement;
    if (active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName)) return;
    event.preventDefault();
    elements.search.focus();
  });

  loadTransactions();
})();