document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('token');
  if (!token) { window.location.href = '/login'; return; }

  const $ = (id) => document.getElementById(id);
  const app = $('rx-app');
  const thread = $('rag-answer');
  const form = $('rag-question-form');
  const input = $('rag-question');
  const sendButton = $('rag-ask-button');
  const scopeSelect = $('rag-document-select');
  const pipelineSelect = $('rag-pipeline');
  const docList = $('rag-document-list');
  const scopeAll = $('rx-scope-all');
  const sourcesPane = $('rx-sources');
  const scrim = $('rx-scrim');
  const evidence = $('rx-evidence');
  const dialog = $('rx-add-dialog');
  const importStatus = $('rag-import-message');
  const libraryStatus = $('rag-upload-message');

  const STORE_KEY = 'finrag-chat-v3';
  let documents = [];
  let catalog = [];
  let scope = '';
  let chatHistory = [];
  let transcript = [];  // rendered items, persisted for the session
  let pollTimer = null;
  let busy = false;
  let investigationQuestion = '';
  let conversationId = null;  // the saved conversation this chat appends to
  let controller = null;      // aborts the streaming answer (Stop)

  // ------------------------------------------------------------ helpers
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function icon(name) {
    const i = element('i', `fas ${name}`);
    i.setAttribute('aria-hidden', 'true');
    return i;
  }

  async function api(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { ...options.headers, Authorization: `Bearer ${token}` } });
    if (response.status === 401) { window.location.href = '/login'; throw new Error('Session expired.'); }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
    return data;
  }

  function setStatus(target, message, isError = false) {
    target.textContent = message;
    target.classList.toggle('error', isError);
  }

  function scrollToBottom() {
    thread.scrollTop = thread.scrollHeight;
  }

  function saveTranscript() {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify({ scope, chatHistory, conversationId, transcript: transcript.slice(-40) })); } catch (_) { /* storage unavailable */ }
  }

  // ------------------------------------------------------------ scope & library
  function scopeName(value = scope) {
    if (!value) return 'General chat';
    if (value === 'all') return 'All documents';
    return documents.find((d) => d.id === value)?.name || 'Document';
  }

  function updateScopeLabel() {
    const label = $('rx-scope-label');
    label.replaceChildren(element('span', 'rx-dot'));
    if (!scope) label.append('General chat with Gemini Â· pick a source for cited answers');
    else if (scope === 'all') label.append(`Searching all ${documents.length} documents Â· FinRAG picks the most relevant`);
    else {
      const doc = documents.find((d) => d.id === scope);
      const mode = doc?.enrichment?.embeddings ? 'hybrid search ready' : (doc?.status === 'enriching' ? 'enrichingâ€¦' : 'keyword search');
      label.append(`${scopeName()} Â· ${mode}`);
    }
    pipelineSelect.disabled = !scope;
    pipelineSelect.parentElement.style.opacity = scope ? '1' : '0.5';
  }

  function setScope(value, { announce = true } = {}) {
    if (value === scope) return;
    scope = value;
    scopeSelect.value = value;
    if (announce && transcript.length) {
      chatHistory = [];
      addSystem(`Now answering from: ${scopeName()}`);
    }
    renderLibrary();
    renderStarters();
    updateScopeLabel();
    closeDrawers();
    saveTranscript();
  }

  function docIcon(doc) {
    const type = doc.source?.type;
    if (type === 'sec') return 'fa-building-columns';
    if (type === 'url') return 'fa-link';
    if (type === 'catalog') return 'fa-book';
    return /\.pdf$/i.test(doc.name) ? 'fa-file-pdf' : 'fa-file-lines';
  }

  function docStatus(doc) {
    if (doc.status === 'enriching') {
      const stage = doc.enrichment?.stage || 'queued';
      const pct = stage === 'chunk metadata' && typeof doc.enrichment?.progress === 'number' ? ` ${Math.round(doc.enrichment.progress * 100)}%` : '';
      return ['enriching', `Enriching Â· ${stage}${pct}`];
    }
    if (doc.enrichment?.stage === 'failed') return ['failed', 'Keyword search only'];
    if (doc.enrichment?.embeddings) return ['ready', 'Hybrid ready'];
    return ['', 'Keyword search'];
  }

  function renderScopeOptions() {
    scopeSelect.replaceChildren(new Option('General chat', ''));
    if (documents.length > 1) scopeSelect.append(new Option(`All documents (${documents.length})`, 'all'));
    documents.forEach((doc) => scopeSelect.append(new Option(doc.name, doc.id)));
    if (scope && scope !== 'all' && !documents.some((d) => d.id === scope)) scope = '';
    if (scope === 'all' && documents.length < 2) scope = '';
    scopeSelect.value = scope;
  }

  function renderLibrary() {
    $('rag-document-count').textContent = `${documents.length} document${documents.length === 1 ? '' : 's'}`;
    scopeAll.hidden = documents.length < 2;
    scopeAll.classList.toggle('active', scope === 'all');
    const filter = $('rx-filter').value.trim().toLowerCase();
    docList.replaceChildren();

    const general = element('button', `rx-doc${scope === '' ? ' active' : ''}`);
    general.type = 'button';
    const gIcon = element('span', 'rx-doc-icon'); gIcon.append(icon('fa-comments'));
    const gBody = element('span', 'rx-doc-body');
    gBody.append(element('strong', '', 'General chat'), element('small', '', 'Gemini, no document evidence'));
    general.append(gIcon, gBody);
    general.addEventListener('click', () => setScope(''));
    docList.append(general);

    const visible = documents.filter((d) => !filter || `${d.name} ${d.metadata?.company || ''} ${d.metadata?.one_liner || ''}`.toLowerCase().includes(filter));
    if (!documents.length) {
      docList.append(element('p', 'rx-empty-list', 'No documents yet. Add a 10-K, an annual report, or any financial PDF.'));
    } else if (!visible.length) {
      docList.append(element('p', 'rx-empty-list', 'No documents match your filter.'));
    }

    visible.forEach((doc) => {
      const row = element('div', `rx-doc${doc.id === scope ? ' active' : ''}`);
      row.tabIndex = 0;
      row.setAttribute('role', 'button');
      row.setAttribute('aria-pressed', String(doc.id === scope));
      const iconBox = element('span', 'rx-doc-icon'); iconBox.append(icon(docIcon(doc)));
      const body = element('span', 'rx-doc-body');
      body.append(element('strong', '', doc.name));
      const facts = [doc.metadata?.company, doc.metadata?.document_type, doc.metadata?.fiscal_year ? `FY${doc.metadata.fiscal_year}` : '',
        doc.metadata?.market === 'India' ? 'ðŸ‡®ðŸ‡³ India' : ''].filter(Boolean).join(' Â· ');
      body.append(element('small', '', `${doc.chunk_count} passages Â· ${doc.table_count ?? 0} tables${facts ? ` Â· ${facts}` : ''}`));
      if (doc.metadata?.generated_by === 'gemini' && doc.metadata?.one_liner) body.append(element('span', 'rx-doc-summary', doc.metadata.one_liner));
      const [statusClass, statusText] = docStatus(doc);
      body.append(element('span', `rx-status ${statusClass}`, statusText));
      if (doc.status !== 'enriching' && !doc.enrichment?.embeddings) {
        const enrich = element('button', 'rx-enrich-link', statusClass === 'failed' ? 'Retry enrichment' : 'Enable hybrid search');
        enrich.type = 'button';
        enrich.title = doc.enrichment?.error || 'Generate Gemini metadata and embeddings';
        enrich.addEventListener('click', async (event) => {
          event.stopPropagation();
          enrich.disabled = true;
          try {
            await api(`/api/rag/documents/${encodeURIComponent(doc.id)}/enrich`, { method: 'POST' });
            await loadDocuments();
          } catch (error) { setStatus(libraryStatus, error.message, true); enrich.disabled = false; }
        });
        body.append(element('br'), enrich);
      }
      const actions = element('span', 'rx-doc-actions');
      const remove = element('button', 'rx-icon-btn');
      remove.type = 'button';
      remove.title = 'Delete document';
      remove.setAttribute('aria-label', `Delete ${doc.name}`);
      remove.append(icon('fa-trash-can'));
      remove.addEventListener('click', async (event) => {
        event.stopPropagation();
        if (!window.confirm(`Delete ${doc.name} and its index?`)) return;
        try {
          await api(`/api/rag/documents/${encodeURIComponent(doc.id)}`, { method: 'DELETE' });
          if (scope === doc.id) setScope('');
          await loadDocuments();
        } catch (error) { setStatus(libraryStatus, error.message, true); }
      });
      actions.append(remove);
      row.append(iconBox, body, actions);
      const choose = () => { setScope(doc.id); closeDrawers(); };
      row.addEventListener('click', choose);
      row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
      docList.append(row);
    });
  }

  async function loadDocuments() {
    const data = await api('/api/rag/documents');
    documents = data.documents || [];
    renderScopeOptions();
    renderLibrary();
    updateScopeLabel();
    clearTimeout(pollTimer);
    if (documents.some((d) => d.status === 'enriching')) {
      pollTimer = setTimeout(() => loadDocuments().catch(() => {}), 5000);
    }
  }

  // ------------------------------------------------------------ starters
  const STARTERS = {
    general: [
      ['fa-chart-line', 'Explain free cash flow', 'and why analysts watch it'],
      ['fa-scale-balanced', 'Compare EBITDA and net income', 'with a simple example'],
      ['fa-indian-rupee-sign', 'How do crore and lakh convert', 'to millions and billions?'],
      ['fa-shield-halved', 'What are common card-fraud signals', 'a bank should monitor?'],
    ],
    document: [
      ['fa-chart-column', 'What was total revenue', 'and how did it change year over year?'],
      ['fa-triangle-exclamation', 'Summarize the top 5 risk factors', 'with citations'],
      ['fa-money-bill-trend-up', 'Operating cash flow vs capital expenditures', 'and the resulting free cash flow'],
      ['fa-sitemap', 'Break down revenue by segment', 'and identify the fastest-growing one'],
    ],
  };

  function renderStarters() {
    const box = $('rx-starters');
    box.replaceChildren();
    (scope ? STARTERS.document : STARTERS.general).forEach(([iconName, title, detail]) => {
      const button = element('button', 'rx-starter');
      button.type = 'button';
      const text = element('span');
      text.append(document.createTextNode(title), element('small', '', detail));
      button.append(icon(iconName), text);
      button.addEventListener('click', () => ask(`${title} ${detail}`.replace(/\s+/g, ' ')));
      box.append(button);
    });
  }

  function showEmpty(show) {
    $('rx-empty').hidden = !show;
  }

  // ------------------------------------------------------------ rendering messages
  function renderInline(target, text, onCite) {
    // **bold** and [1] / [1, 2] citations; everything else is plain text.
    String(text).split(/(\*\*[^*]+\*\*|\[\d+(?:\s*,\s*\d+)*\])/g).forEach((part) => {
      if (!part) return;
      if (/^\*\*[^*]+\*\*$/.test(part)) { target.append(element('strong', '', part.slice(2, -2))); return; }
      const cite = part.match(/^\[(\d+(?:\s*,\s*\d+)*)\]$/);
      if (cite && onCite) {
        cite[1].split(/\s*,\s*/).forEach((n) => {
          const button = element('button', 'rx-cite', n);
          button.type = 'button';
          button.title = `Show source ${n}`;
          button.addEventListener('click', () => onCite(/^\d+$/.test(n) ? Number(n) : n));
          target.append(button);
        });
        return;
      }
      target.append(document.createTextNode(part));
    });
  }

  function renderMarkdown(text, onCite) {
    const container = element('div', 'rx-answer');
    let list = null;
    String(text || '').replace(/\$\\text\{([^}]*)\}\$/g, '$1').split('\n').forEach((raw) => {
      const line = raw.trimEnd();
      const bullet = line.match(/^\s*(?:[-*â€¢]|\d+\.)\s+(.*)$/);
      if (bullet) {
        if (!list) { list = element('ul'); container.append(list); }
        const item = element('li');
        renderInline(item, bullet[1], onCite);
        list.append(item);
        return;
      }
      list = null;
      if (!line.trim() || /^-{3,}$/.test(line.trim())) return;
      const paragraph = element('p');
      renderInline(paragraph, line.replace(/^#+\s*/, ''), onCite);
      container.append(paragraph);
    });
    return container;
  }

  function addSystem(text, persist = true) {
    thread.append(element('p', 'rx-system', text));
    if (persist) { transcript.push({ kind: 'system', text }); saveTranscript(); }
    scrollToBottom();
  }

  function addUser(text, persist = true) {
    showEmpty(false);
    const row = element('div', 'rx-msg user');
    row.append(element('div', 'rx-bubble-user', text));
    thread.append(row);
    if (persist) { transcript.push({ kind: 'user', text }); saveTranscript(); }
    scrollToBottom();
  }

  function assistantShell(subtitle) {
    const row = element('div', 'rx-msg');
    const avatar = element('span', 'rx-avatar'); avatar.append(icon('fa-wand-magic-sparkles'));
    const body = element('div', 'rx-assistant');
    const head = element('div', 'rx-assistant-head');
    head.append(element('strong', '', 'FinRAG'), element('span', '', subtitle));
    body.append(head);
    row.append(avatar, body);
    thread.append(row);
    return body;
  }

  function addTyping(withDocument) {
    const body = assistantShell(withDocument ? scopeName() : 'Gemini');
    const typing = element('div', 'rx-typing');
    const dots = element('span', 'rx-typing-dots');
    dots.append(element('span'), element('span'), element('span'));
    const stage = element('span', 'rx-stage', withDocument ? 'Startingâ€¦' : 'Thinkingâ€¦');
    typing.append(dots, stage);
    body.append(typing);
    scrollToBottom();
    let answer = null;
    return {
      setStage(label) {
        stage.textContent = `${label}â€¦`;
        stage.style.animation = 'none'; void stage.offsetWidth; stage.style.animation = '';
      },
      startAnswer() {
        answer = element('div', 'rx-streaming');
        body.append(answer);
        stage.textContent = 'Writingâ€¦';
        return answer;
      },
      markStopped(partial) {
        typing.remove();
        if (!partial && answer) answer.remove();
        body.append(element('p', 'rx-stopped', partial
          ? 'Stopped. This answer is incomplete and its figures were not checked.'
          : 'Stopped before an answer was written.'));
      },
      remove() { body.parentElement?.remove(); },
    };
  }

  function shortMethod(retrieval) {
    if (!retrieval?.method) return '';
    if (retrieval.method.startsWith('Hybrid')) return retrieval.options?.rerank ? 'Hybrid + rerank' : 'Hybrid';
    if (retrieval.method.startsWith('dense')) return 'Dense';
    return 'Sparse';
  }

  function addAssistant(data, persist = true) {
    const isDocument = data.mode === 'document';
    const subtitle = isDocument
      ? `${shortMethod(data.retrieval)} Â· ${data.retrieval?.documents_searched?.join(', ') || ''}`
      : (data.intent === 'small_talk' ? `Chat Â· ${scopeName()}` : 'Gemini');
    const body = assistantShell(subtitle);
    const openSource = (n) => openEvidence(data, n);
    body.append(renderMarkdown(data.answer, isDocument ? openSource : null));

    if (data.intent === 'general_knowledge' || (data.mode === 'conversation' && data.retrieval?.passages_retrieved === 0)) {
      const note = element('p', 'rx-note');
      note.append(icon('fa-lightbulb'), ` General knowledge Â· nothing in ${scopeName()} matched this question, so no citations.`);
      body.append(note);
    }

    if (isDocument) {
      const meta = element('div', 'rx-meta');
      if (data.confidence) {
        const pill = element('span', `rx-pill ${data.confidence.label}`);
        const ring = element('span', 'rx-ring');
        ring.style.setProperty('--value', Math.round(data.confidence.score * 100));
        pill.append(ring, `${Math.round(data.confidence.score * 100)}% confidence`);
        meta.append(pill);
      }
      const g = data.grounding;
      if (g?.numbers_checked) {
        const pill = element('span', 'rx-pill');
        pill.append(icon('fa-check-double'), `${g.numbers_grounded + (g.numbers_calculated || 0)}/${g.numbers_checked} figures verified`);
        meta.append(pill);
      }
      if (data.retrieval?.query_plan?.sub_questions?.length) {
        const pill = element('span', 'rx-pill'); pill.append(icon('fa-diagram-project'), `Multi-hop Â· ${data.retrieval.query_plan.sub_questions.length} steps`); meta.append(pill);
      }
      if (data.retrieval?.timings_ms?.total_ms) {
        const pill = element('span', 'rx-pill'); pill.append(icon('fa-bolt'), `${(data.retrieval.timings_ms.total_ms / 1000).toFixed(1)}s`); meta.append(pill);
      }
      body.append(meta);
      if (g?.unverified_numbers?.length) {
        body.append(warning('fa-triangle-exclamation', `Check ${g.unverified_numbers.join(', ')}: not found in the cited passages and not a simple calculation from them.`));
      }
    }

    if (data.sources?.length) {
      const row = element('div', 'rx-sources-row');
      data.sources.forEach((source) => {
        const chip = element('button', 'rx-source-chip');
        chip.type = 'button';
        chip.title = source.label || source.name;
        const where = [source.page ? `p. ${source.page}` : '', source.table ? `Table ${source.table}` : '', source.section || ''].filter(Boolean).join(' Â· ');
        chip.append(element('b', '', String(source.citation)), element('span', '', where || source.label || source.name));
        chip.addEventListener('click', () => openSource(source.citation));
        row.append(chip);
      });
      body.append(row);
    }

    if (data.related_questions?.length) {
      const related = element('div', 'rx-related');
      data.related_questions.forEach((question) => {
        const button = element('button');
        button.type = 'button';
        button.append(icon('fa-arrow-turn-down-right'), question);
        button.addEventListener('click', () => ask(question));
        related.append(button);
      });
      body.append(related);
    }

    const actions = element('div', 'rx-actions');
    const copy = element('button', 'rx-icon-btn');
    copy.type = 'button'; copy.title = 'Copy answer'; copy.append(icon('fa-copy'));
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(data.answer); copy.replaceChildren(icon('fa-check')); setTimeout(() => copy.replaceChildren(icon('fa-copy')), 1500); } catch (_) { /* clipboard blocked */ }
    });
    actions.append(copy);
    if (isDocument && data.retrieval) {
      const traceButton = element('button', 'rx-icon-btn');
      traceButton.type = 'button'; traceButton.title = 'How this was answered'; traceButton.append(icon('fa-route'));
      let trace = null;
      traceButton.addEventListener('click', () => {
        if (trace) { trace.remove(); trace = null; return; }
        trace = renderTrace(data.retrieval);
        body.append(trace);
      });
      const evidenceButton = element('button', 'rx-icon-btn');
      evidenceButton.type = 'button'; evidenceButton.title = 'Open evidence'; evidenceButton.append(icon('fa-book-open-reader'));
      evidenceButton.addEventListener('click', () => openSource(1));
      actions.append(evidenceButton, traceButton);
    }
    body.append(actions);

    if (persist) { transcript.push({ kind: 'assistant', data }); saveTranscript(); }
    scrollToBottom();
  }

  function warning(iconName, text) {
    const box = element('div', 'rx-warning');
    box.append(icon(iconName), element('span', '', text));
    return box;
  }

  function renderTrace(retrieval) {
    const box = element('div', 'rx-trace');
    const steps = element('ol', 'rx-steps');
    const step = (title, detail) => {
      if (!detail) return;
      const li = element('li');
      li.append(element('b', '', title), element('span', '', detail));
      steps.append(li);
    };
    const plan = retrieval.query_plan || {};
    const t = retrieval.timings_ms || {};
    if (retrieval.file_filter) step('File filter', `${retrieval.file_filter.selected.join(', ')} chosen from ${retrieval.file_filter.library_size} documents (${retrieval.file_filter.method})`);
    step('Query plan', [plan.rewritten_query ? `Rewritten: â€œ${plan.rewritten_query}â€` : 'Original query used as-is',
      t.plan_ms !== undefined ? ` Â· ${t.plan_ms} ms` : ''].join(''));
    if (plan.hypothetical_answer) step('HyDE passage', `â€œ${plan.hypothetical_answer}â€`);
    if (plan.sub_questions?.length) step('Multi-hop sub-questions', plan.sub_questions.map((q, i) => `${i + 1}. ${q}`).join('  '));
    step('Hybrid retrieval', `${retrieval.passages_considered} passages searched with BM25 + TF-IDF${retrieval.dense_used ? ' + dense embeddings' : ''}, fused with RRF Â· ${(t.sparse_ms || 0) + (t.dense_ms || 0)} ms`);
    step('Metadata reranker', `${retrieval.candidates_reranked} candidates â†’ top ${retrieval.passages_retrieved}${retrieval.options?.rerank ? '' : ' (reranker off)'} Â· ${t.rerank_ms ?? 0} ms`);
    if (t.generate_ms !== undefined) step('Grounded generation', `Gemini answer with citations Â· ${t.generate_ms} ms`);
    box.append(steps);
    return box;
  }

  // ------------------------------------------------------------ evidence drawer
  function openEvidence(data, focus) {
    const body = $('rx-evidence-body');
    body.replaceChildren();
    $('rx-evidence-title').textContent = `${data.sources.length} cited passage${data.sources.length === 1 ? '' : 's'}`;
    let focusCard = null;
    data.sources.forEach((source) => {
      const card = element('article', `rx-ev-card${source.citation === focus ? ' focus' : ''}`);
      const top = element('div', 'rx-ev-top');
      top.append(element('b', '', String(source.citation)), element('span', '', source.name));
      const tags = element('div', 'rx-ev-tags');
      [source.page ? `Page ${source.page}` : '', source.section, source.table ? `Table ${source.table}` : '', source.units ? `${source.units}` : '',
        source.content_type === 'table' ? 'Table data' : ''].filter(Boolean).forEach((t) => tags.append(element('span', '', t)));
      card.append(top, tags, element('pre', '', source.snippet || ''));
      if (source.rerank) {
        const score = element('div', 'rx-score');
        Object.entries(source.rerank).forEach(([name, value]) => {
          const row = element('div');
          const bar = element('i');
          bar.style.setProperty('--w', `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`);
          row.append(element('span', '', name.replace('_', ' ')), bar, element('span', '', value.toFixed(2)));
          score.append(row);
        });
        card.append(score);
      }
      if (source.original && source.document_id) {
        const open = element('button', 'rx-open-source');
        open.type = 'button';
        open.append(icon('fa-arrow-up-right-from-square'),
          document.createTextNode(source.original === 'pdf' && source.page ? ` Open page ${source.page}` : ' Open in document'));
        open.addEventListener('click', () => openOriginal(source, open));
        card.append(open);
      }
      if (source.citation === focus) focusCard = card;
      body.append(card);
    });
    evidence.hidden = false;
    app.classList.add('has-evidence');
    if (window.innerWidth <= 1280) scrim.hidden = false;
    if (focusCard) focusCard.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function textFragment(source) {
    // Scroll-to-text: the browser highlights the first words of the cited passage (or the table's caption).
    const snippet = String(source.snippet || '');
    let phrase;
    if (source.content_type === 'table') {
      // A table's caption is often generic ("(amounts in millions)"), so use its most specific row label.
      const caption = /^Table \d+(?: \(part \d+\))?: ([^\[\n]+)/.exec(snippet)?.[1]?.trim() || '';
      const labels = snippet.split('\n').slice(1).map((line) => line.split('|')[0].trim()).filter((label) => /[a-z]{3}/i.test(label));
      const longest = labels.sort((a, b) => b.length - a.length)[0] || '';
      phrase = caption && !caption.startsWith('(') && !/millions|thousands|crore|lakh/i.test(caption) ? caption : longest;
    } else {
      phrase = snippet.split('\n').find((line) => line.trim() && !line.includes('|')) || '';
    }
    const words = phrase.replace(/\s+/g, ' ').trim().split(' ').slice(0, 7);
    return words.length >= 3 ? `#:~:text=${encodeURIComponent(words.join(' ')).replace(/-/g, '%2D')}` : '';
  }

  async function openOriginal(source, button) {
    button.disabled = true;
    try {
      const link = await api(`/api/rag/documents/${encodeURIComponent(source.document_id)}/open`, { method: 'POST' });
      const url = link.kind === 'pdf' ? `${link.url}${source.page ? `#page=${source.page}` : ''}` : `${link.url}${textFragment(source)}`;
      window.open(url, '_blank', 'noopener');
    } catch (error) {
      button.replaceWith(element('small', 'rx-open-unavailable', error.message));
    } finally {
      button.disabled = false;
    }
  }

  function closeEvidence() {
    evidence.hidden = true;
    app.classList.remove('has-evidence');
  }

  function closeDrawers() {
    sourcesPane.classList.remove('open');
    if (window.innerWidth <= 1280) closeEvidence();
    scrim.hidden = true;
  }

  // ------------------------------------------------------------ asking
  function setStopMode(on) {
    sendButton.replaceChildren(icon(on ? 'fa-stop' : 'fa-arrow-up'));
    sendButton.setAttribute('aria-label', on ? 'Stop generating' : 'Send');
    sendButton.title = on ? 'Stop generating' : 'Send';
    sendButton.classList.toggle('is-stop', on);
    sendButton.disabled = false;
  }

  function parseEvents(buffer, onEvent) {
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const name = /^event: (.+)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (name && data !== undefined) onEvent(name, JSON.parse(data));
    }
    return buffer;
  }

  async function ask(rawQuery) {
    const query = String(rawQuery || '').trim();
    if (!query || busy) return;
    busy = true;
    setStopMode(true);
    input.value = '';
    autosize();
    addUser(query);
    const previous = chatHistory.slice(-8);
    const typing = addTyping(Boolean(scope));
    controller = new AbortController();
    let live = null;
    let streamed = '';
    let finished = false;
    try {
      const response = await fetch('/api/rag/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ document_id: scope, query, history: previous, options: scope ? pipelineSelect.value : undefined, conversation_id: conversationId }),
        signal: controller.signal,
      });
      if (response.status === 401) { window.location.href = '/login'; return; }
      if (!response.ok || !response.body) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || 'The request could not be completed.');
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer = parseEvents(buffer + decoder.decode(value, { stream: true }), (name, payload) => {
          if (name === 'stage') typing.setStage(payload.label);
          else if (name === 'token') {
            if (!live) live = typing.startAnswer();
            streamed += payload.text;
            live.textContent = streamed;
            scrollToBottom();
          } else if (name === 'done') {
            finished = true;
            typing.remove();
            addAssistant(payload);
            conversationId = payload.conversation_id || conversationId;
            chatHistory = [...previous, { role: 'user', content: query.slice(0, 1500) }, { role: 'assistant', content: String(payload.answer).slice(0, 1500) }].slice(-8);
            saveTranscript();
            loadConversations();
          } else if (name === 'error') {
            throw new Error(payload.error || 'The answer could not be generated.');
          }
        });
      }
      if (!finished) throw new Error('The connection closed before the answer finished. Please try again.');
    } catch (error) {
      if (error.name === 'AbortError') {
        typing.markStopped(streamed);
      } else if (!finished) {
        typing.remove();
        const body = assistantShell('Error');
        const box = element('div', 'rx-error');
        box.append(icon('fa-circle-exclamation'), element('span', '', error.message));
        body.append(box);
        scrollToBottom();
      }
    } finally {
      busy = false;
      controller = null;
      setStopMode(false);
      input.focus();
    }
  }

  // ------------------------------------------------------------ saved conversations
  async function loadConversations() {
    const list = $('rx-history-list');
    if (!list) return;
    try {
      const data = await api('/api/rag/conversations');
      const items = Array.isArray(data.conversations) ? data.conversations : [];
      list.replaceChildren();
      if (!items.length) {
        list.append(element('p', 'rx-empty-list', 'Your conversations are saved here.'));
        return;
      }
      items.forEach((item) => {
        const row = element('div', `rx-history-item${item.conversation_id === conversationId ? ' active' : ''}`);
        const open = element('button', 'rx-history-open');
        open.type = 'button';
        const when = item.updated_at ? new Date(item.updated_at).toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) : '';
        open.append(element('span', '', item.title || 'Untitled chat'), element('small', '', `${when} Â· ${Math.ceil((item.message_count || 0) / 2)} questions`));
        open.addEventListener('click', () => openConversation(item.conversation_id));
        const remove = element('button', 'rx-icon-btn rx-history-delete');
        remove.type = 'button';
        remove.title = 'Delete conversation';
        remove.setAttribute('aria-label', `Delete conversation ${item.title || ''}`);
        remove.append(icon('fa-trash-can'));
        remove.addEventListener('click', async () => {
          if (!window.confirm('Delete this saved conversation?')) return;
          await api(`/api/rag/conversations/${item.conversation_id}`, { method: 'DELETE' }).catch(() => null);
          if (item.conversation_id === conversationId) resetChat();
          loadConversations();
        });
        row.append(open, remove);
        list.append(row);
      });
    } catch (_) {
      list.replaceChildren(element('p', 'rx-empty-list', 'Saved conversations are unavailable.'));
    }
  }

  async function openConversation(id) {
    if (busy) return;
    try {
      const data = await api(`/api/rag/conversations/${id}`);
      resetChat();
      if (typeof data.scope === 'string' && (data.scope === '' || data.scope === 'all' || documents.some((d) => d.id === data.scope))) {
        setScope(data.scope, { announce: false });
      }
      conversationId = id;
      const messages = Array.isArray(data.messages) ? data.messages : [];
      messages.forEach((message) => {
        if (message.role === 'user') addUser(message.content);
        else if (message.payload) addAssistant(message.payload);
      });
      chatHistory = messages.slice(-8).map((m) => ({ role: m.role, content: String(m.content || '').slice(0, 1500) })).filter((m) => m.content.trim());
      saveTranscript();
      loadConversations();
      closeDrawers();
    } catch (error) {
      addSystem(error.message);
    }
  }

  function resetChat() {
    transcript = [];
    chatHistory = [];
    conversationId = null;
    thread.querySelectorAll('.rx-msg, .rx-system').forEach((node) => node.remove());
    showEmpty(true);
    closeEvidence();
    saveTranscript();
  }

  function autosize() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    $('rx-count').textContent = `${input.value.length}/1000`;
  }

  // While an answer streams, the send button is Stop. Handled on click: the (empty, required) question box
  // would otherwise make the browser block the form submit before Stop ever ran.
  sendButton.addEventListener('click', (event) => {
    if (!busy) return;
    event.preventDefault();
    controller?.abort();
  });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!busy) ask(input.value);
  });
  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); ask(input.value); }
  });
  scopeSelect.addEventListener('change', () => setScope(scopeSelect.value));
  scopeAll.addEventListener('click', () => setScope('all'));
  $('rx-filter').addEventListener('input', renderLibrary);

  $('rx-new-chat').addEventListener('click', () => {
    if (busy) controller?.abort();
    resetChat();
    loadConversations();
    input.focus();
  });

  // ------------------------------------------------------------ drawers (mobile)
  $('rx-open-sources').addEventListener('click', () => { sourcesPane.classList.add('open'); scrim.hidden = false; });
  $('rx-close-sources').addEventListener('click', closeDrawers);
  $('rx-close-evidence').addEventListener('click', () => { closeEvidence(); scrim.hidden = true; });
  scrim.addEventListener('click', closeDrawers);
  $('rx-open-nav').addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.add('mobile-open');
    document.getElementById('sidebarOverlay')?.classList.add('active');
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeDrawers(); });

  // ------------------------------------------------------------ add-source dialog
  function openAdd(tab = 'upload') {
    setStatus(importStatus, '');
    selectTab(tab);
    if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
  }

  function closeAdd() {
    if (typeof dialog.close === 'function') dialog.close(); else dialog.removeAttribute('open');
  }

  function selectTab(name) {
    dialog.querySelectorAll('.rx-tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
    dialog.querySelectorAll('.rx-tab-panel').forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
  }

  dialog.querySelectorAll('.rx-tabs button').forEach((button) => button.addEventListener('click', () => selectTab(button.dataset.tab)));
  $('rx-open-add').addEventListener('click', () => openAdd());
  $('rx-attach').addEventListener('click', () => openAdd());
  $('rx-close-add').addEventListener('click', closeAdd);
  dialog.addEventListener('click', (event) => { if (event.target === dialog) closeAdd(); });

  async function indexed(promise, button) {
    button.disabled = true;
    setStatus(importStatus, 'Parsing, chunking and indexingâ€¦ large filings can take up to a minute.');
    try {
      const data = await promise();
      await loadDocuments();
      setScope(data.document.id);
      setStatus(importStatus, `Indexed ${data.document.name}: ${data.document.chunk_count} passages, ${data.document.table_count ?? 0} tables. Metadata and embeddings are being generated in the background.`);
      setTimeout(closeAdd, 1400);
      return true;
    } catch (error) {
      setStatus(importStatus, error.message, true);
      return false;
    } finally {
      button.disabled = false;
    }
  }

  const fileInput = $('rag-file');
  const drop = $('rx-drop');
  fileInput.addEventListener('change', () => { $('rag-file-name').textContent = fileInput.files[0]?.name || 'Drop a file or click to browse'; });
  ['dragenter', 'dragover'].forEach((type) => drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add('dragging'); }));
  ['dragleave', 'drop'].forEach((type) => drop.addEventListener(type, () => drop.classList.remove('dragging')));
  drop.addEventListener('drop', (event) => {
    event.preventDefault();
    if (event.dataTransfer.files[0]) {
      fileInput.files = event.dataTransfer.files;
      $('rag-file-name').textContent = event.dataTransfer.files[0].name;
    }
  });

  $('rag-upload-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!fileInput.files[0]) { setStatus(importStatus, 'Choose a file first.', true); return; }
    const body = new FormData();
    body.append('file', fileInput.files[0]);
    if (await indexed(() => api('/api/rag/index', { method: 'POST', body }), $('rag-index-button'))) {
      event.target.reset();
      $('rag-file-name').textContent = 'Drop a file or click to browse';
    }
  });

  function renderCatalog() {
    const box = $('rag-catalog-list');
    const filter = $('rx-catalog-filter').value.trim().toLowerCase();
    box.replaceChildren();
    const items = catalog.filter((r) => !filter || r.name.toLowerCase().includes(filter));
    if (!items.length) { box.append(element('p', 'rx-hint', catalog.length ? 'No reports match.' : 'No bundled reports found.')); return; }
    items.forEach((report) => {
      const button = element('button');
      button.type = 'button';
      button.append(icon('fa-book'), element('span', '', report.name), element('small', '', `${(report.size_bytes / 1e6).toFixed(1)} MB`));
      button.addEventListener('click', () => {
        const body = new FormData();
        body.append('source_id', report.id);
        indexed(() => api('/api/rag/index', { method: 'POST', body }), button);
      });
      box.append(button);
    });
  }
  $('rx-catalog-filter').addEventListener('input', renderCatalog);

  $('rag-sec-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = { ticker: $('rag-sec-ticker').value.trim(), form: $('rag-sec-form-type').value };
    if (await indexed(() => api('/api/rag/ingest/sec', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }), event.submitter || event.target.querySelector('button'))) event.target.reset();
  });

  $('rag-url-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = { url: $('rag-url').value.trim() };
    if (await indexed(() => api('/api/rag/ingest/url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }), event.submitter || event.target.querySelector('button'))) event.target.reset();
  });

  // ------------------------------------------------------------ investigation context (from Fraud Alerts)
  function restoreInvestigationContext() {
    const banner = $('rag-investigation-context');
    try {
      const stored = sessionStorage.getItem('finrag-investigation-context');
      sessionStorage.removeItem('finrag-investigation-context');
      if (!stored) return;
      const context = JSON.parse(stored);
      if (!context || context.version !== 1) return;
      const transactionId = typeof context.transactionId === 'string' ? context.transactionId.replace(/[^\w.-]/g, '').slice(0, 80) : '';
      const amount = typeof context.amount === 'number' && Number.isFinite(context.amount) ? context.amount : Number.NaN;
      const currency = typeof context.currency === 'string' && /^[A-Z]{3}$/.test(context.currency) ? context.currency : '';
      const channel = typeof context.channel === 'string' ? context.channel.replace(/[^\w -]/g, '').trim().slice(0, 40) : '';
      const timestamp = typeof context.timestamp === 'string' ? new Date(context.timestamp) : null;
      const date = timestamp && !Number.isNaN(timestamp.getTime()) ? timestamp.toLocaleString() : 'date unavailable';
      const amountLabel = Number.isFinite(amount) ? `${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`.trim() : 'amount unavailable';
      $('rag-investigation-details').textContent = [transactionId ? `Transaction ${transactionId}` : 'Model-flagged transaction', amountLabel, channel || 'channel unavailable', date].join(' Â· ');
      banner.hidden = false;
      const details = [Number.isFinite(amount) ? `amount ${amountLabel}` : '', channel ? `channel ${channel}` : '', date !== 'date unavailable' ? `date ${date}` : ''].filter(Boolean).join(', ');
      investigationQuestion = `Considering a transaction (${details}), identify any risks, controls, or financial factors described in this report that may be relevant. Separate direct evidence from inference, cite the source and page when available, and state when no direct connection is supported.`;
      input.value = investigationQuestion;
      autosize();
    } catch (error) {
      $('rag-investigation-details').textContent = 'Transaction context could not be restored. You can continue with a manual question.';
      banner.hidden = false;
    }
  }

  $('rag-investigation-dismiss').addEventListener('click', () => {
    $('rag-investigation-context').hidden = true;
    if (input.value === investigationQuestion) { input.value = ''; autosize(); }
    investigationQuestion = '';
  });

  // ------------------------------------------------------------ boot
  function restoreTranscript() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(STORE_KEY) || 'null');
      if (!saved || !Array.isArray(saved.transcript) || !saved.transcript.length) return;
      scope = typeof saved.scope === 'string' ? saved.scope : '';
      chatHistory = Array.isArray(saved.chatHistory) ? saved.chatHistory.slice(-8) : [];
      conversationId = typeof saved.conversationId === 'string' ? saved.conversationId : null;
      transcript = saved.transcript;
      transcript.forEach((item) => {
        if (item.kind === 'user') addUser(item.text, false);
        else if (item.kind === 'assistant' && item.data) addAssistant(item.data, false);
        else if (item.kind === 'system') addSystem(item.text, false);
      });
    } catch (_) { transcript = []; }
  }

  restoreTranscript();
  renderStarters();
  updateScopeLabel();
  restoreInvestigationContext();
  autosize();
  loadConversations();
  loadDocuments().then(() => { renderStarters(); }).catch((error) => {
    docList.replaceChildren(element('p', 'rx-empty-list', error.message));
  });
  api('/api/rag/catalog').then((data) => { catalog = data.reports || []; renderCatalog(); }).catch(() => renderCatalog());
});
