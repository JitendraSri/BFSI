document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('token');
  const uploadForm = document.getElementById('rag-upload-form');
  const fileInput = document.getElementById('rag-file');
  const fileName = document.getElementById('rag-file-name');
  const uploadMessage = document.getElementById('rag-upload-message');
  const catalogSelect = document.getElementById('rag-catalog-select');
  const catalogButton = document.getElementById('rag-catalog-button');
  const catalogMessage = document.getElementById('rag-catalog-message');
  const documentList = document.getElementById('rag-document-list');
  const documentCount = document.getElementById('rag-document-count');
  const documentSelect = document.getElementById('rag-document-select');
  const questionForm = document.getElementById('rag-question-form');
  const askButton = document.getElementById('rag-ask-button');
  const answerPanel = document.getElementById('rag-answer');
  let documents = [];

  async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { ...options.headers, Authorization: `Bearer ${token}` }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
    return data;
  }

  function setMessage(message, isError = false) {
    uploadMessage.textContent = message;
    uploadMessage.classList.toggle('error', isError);
  }

  function renderDocuments(preferredId = documentSelect.value) {
    documentCount.textContent = String(documents.length);
    documentSelect.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = documents.length ? 'Choose a document' : 'Index a document to begin';
    documentSelect.append(placeholder);

    documents.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.name;
      documentSelect.append(option);
    });
    if (documents.some((item) => item.id === preferredId)) documentSelect.value = preferredId;
    askButton.disabled = !documentSelect.value;

    documentList.replaceChildren();
    if (!documents.length) {
      const empty = document.createElement('p');
      empty.className = 'rag-empty';
      empty.textContent = 'Your indexed documents will appear here.';
      documentList.append(empty);
      return;
    }

    documents.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'rag-document-row';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `rag-document-item${item.id === documentSelect.value ? ' selected' : ''}`;
      const name = document.createElement('span');
      name.className = 'rag-document-name';
      name.textContent = item.name;
      const meta = document.createElement('span');
      meta.className = 'rag-document-meta';
      meta.textContent = `${item.chunk_count} searchable passages`;
      button.append(name, meta);
      button.addEventListener('click', () => {
        documentSelect.value = item.id;
        renderDocuments(item.id);
      });
      const deleteButton = document.createElement('button');
      deleteButton.type = 'button';
      deleteButton.className = 'rag-document-delete';
      deleteButton.title = 'Delete indexed document';
      deleteButton.setAttribute('aria-label', `Delete ${item.name}`);
      deleteButton.innerHTML = '<i class="fas fa-trash" aria-hidden="true"></i>';
      deleteButton.addEventListener('click', async () => {
        if (!window.confirm(`Delete ${item.name} and its indexed passages?`)) return;
        deleteButton.disabled = true;
        try {
          await apiRequest(`/api/rag/documents/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
          const nextSelection = documentSelect.value === item.id ? '' : documentSelect.value;
          await loadDocuments(nextSelection);
          if (!nextSelection) answerPanel.replaceChildren();
        } catch (error) {
          setMessage(error.message, true);
          deleteButton.disabled = false;
        }
      });
      row.append(button, deleteButton);
      documentList.append(row);
    });
  }

  async function loadDocuments(preferredId) {
    const data = await apiRequest('/api/rag/documents');
    documents = data.documents || [];
    renderDocuments(preferredId);
  }

  async function loadCatalog() {
    const data = await apiRequest('/api/rag/catalog');
    catalogSelect.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = data.reports.length ? 'Choose a 10-K report' : 'No local reports found';
    catalogSelect.append(placeholder);
    data.reports.forEach((report) => {
      const option = document.createElement('option');
      option.value = report.id;
      option.textContent = report.name;
      catalogSelect.append(option);
    });
  }

  catalogSelect.addEventListener('change', () => {
    catalogButton.disabled = !catalogSelect.value;
  });

  catalogButton.addEventListener('click', async () => {
    if (!catalogSelect.value) return;
    catalogButton.disabled = true;
    catalogMessage.textContent = 'Indexing report…';
    catalogMessage.classList.remove('error');
    const formData = new FormData();
    formData.append('source_id', catalogSelect.value);
    try {
      const data = await apiRequest('/api/rag/index', { method: 'POST', body: formData });
      await loadDocuments(data.document.id);
      catalogMessage.textContent = `Indexed ${data.document.name} (${data.document.chunk_count} passages).`;
    } catch (error) {
      catalogMessage.textContent = error.message;
      catalogMessage.classList.add('error');
    } finally {
      catalogButton.disabled = !catalogSelect.value;
    }
  });

  fileInput.addEventListener('change', () => {
    fileName.textContent = fileInput.files[0]?.name || 'Choose a document';
  });

  uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!fileInput.files[0]) return;
    const button = document.getElementById('rag-index-button');
    button.disabled = true;
    setMessage('Extracting text and building the index…');
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    try {
      const data = await apiRequest('/api/rag/index', { method: 'POST', body: formData });
      await loadDocuments(data.document.id);
      setMessage(`Indexed ${data.document.name} (${data.document.chunk_count} passages).`);
      uploadForm.reset();
      fileName.textContent = 'Choose a document';
    } catch (error) {
      setMessage(error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  documentSelect.addEventListener('change', () => renderDocuments(documentSelect.value));

  questionForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const query = document.getElementById('rag-question').value.trim();
    if (!query || !documentSelect.value) return;
    askButton.disabled = true;
    askButton.innerHTML = '<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i> Searching';
    answerPanel.replaceChildren();
    const loading = document.createElement('p');
    loading.className = 'rag-empty';
    loading.textContent = 'Finding relevant passages and preparing an answer…';
    answerPanel.append(loading);
    try {
      const data = await apiRequest('/api/rag/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: documentSelect.value, query })
      });
      renderAnswer(data);
    } catch (error) {
      answerPanel.replaceChildren();
      const message = document.createElement('p');
      message.className = 'rag-message error';
      message.textContent = error.message;
      answerPanel.append(message);
    } finally {
      askButton.disabled = !documentSelect.value;
      askButton.innerHTML = 'Ask <i class="fas fa-arrow-right" aria-hidden="true"></i>';
    }
  });

  function renderAnswer(data) {
    answerPanel.replaceChildren();
    const heading = document.createElement('h3');
    heading.textContent = 'Answer';
    const answer = document.createElement('p');
    answer.className = 'rag-answer-text';
    answer.textContent = data.answer;
    answerPanel.append(heading, answer);

    if (data.sources?.length) {
      const title = document.createElement('h3');
      title.textContent = 'Sources';
      const sources = document.createElement('div');
      sources.className = 'rag-sources';
      data.sources.forEach((source) => {
        const label = document.createElement('span');
        label.className = 'rag-source';
        label.textContent = `[${source.citation}] ${source.name}${source.page ? ` · page ${source.page}` : ''}`;
        sources.append(label);
      });
      answerPanel.append(title, sources);
    }
  }

  loadDocuments().catch((error) => {
    documentList.replaceChildren();
    const message = document.createElement('p');
    message.className = 'rag-message error';
    message.textContent = error.message;
    documentList.append(message);
  });
  loadCatalog().catch((error) => {
    catalogSelect.replaceChildren();
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'FinRAG reports unavailable';
    catalogSelect.append(option);
    catalogMessage.textContent = error.message;
    catalogMessage.classList.add('error');
  });
});