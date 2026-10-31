// Theme Logic
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

// ── Toast Notification System ─────────────────────────────────────────────────
(function () {
    const container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);

    window.showToast = function (message, type = 'info', duration = 3500) {
        const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', warn: 'fa-triangle-exclamation', info: 'fa-circle-info' };
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span style="flex:1">${message}</span><button class="toast-close" aria-label="Close">✕</button>`;
        container.appendChild(toast);
        const close = () => {
            toast.classList.add('toast-out');
            toast.addEventListener('animationend', () => toast.remove(), { once: true });
        };
        toast.querySelector('.toast-close').addEventListener('click', close);
        setTimeout(close, duration);
    };
})();

// ── Styled Confirm Modal ──────────────────────────────────────────────────────
(function () {
    const overlay = document.createElement('div');
    overlay.id = 'confirm-overlay';
    overlay.innerHTML = `
        <div id="confirm-box">
            <h3 id="confirm-title"></h3>
            <p id="confirm-msg"></p>
            <div class="confirm-actions">
                <button class="btn-cancel" id="confirm-cancel">Cancel</button>
                <button class="btn-danger" id="confirm-ok">Confirm</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    window.showConfirm = function ({ title = 'Are you sure?', message = '', okText = 'Confirm', danger = true, onConfirm }) {
        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-msg').textContent = message;
        const okBtn = document.getElementById('confirm-ok');
        okBtn.textContent = okText;
        okBtn.className = danger ? 'btn-danger' : 'btn-confirm';
        overlay.classList.add('active');

        const close = () => overlay.classList.remove('active');
        const onOk = () => { close(); if (onConfirm) onConfirm(); };

        okBtn.onclick = onOk;
        document.getElementById('confirm-cancel').onclick = close;
        overlay.onclick = (e) => { if (e.target === overlay) close(); };
    };
})();

// ── Session Expiry Warning ────────────────────────────────────────────────────
(function () {
    const WARNING_BEFORE_MS = 5 * 60 * 1000; // warn 5 min before expiry

    function parseJwtExp(token) {
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            return payload.exp ? payload.exp * 1000 : null;
        } catch { return null; }
    }

    function startSessionTimer() {
        const token = localStorage.getItem('token');
        if (!token) return;
        const exp = parseJwtExp(token);
        if (!exp) return;

        const banner = document.createElement('div');
        banner.id = 'session-warning';
        banner.innerHTML = `⚠ Your session expires in <span id="session-countdown">5:00</span>. <button onclick="extendSession()">Stay Logged In</button>`;
        document.body.appendChild(banner);

        let warned = false;
        const tick = setInterval(() => {
            const remaining = exp - Date.now();
            if (remaining <= 0) {
                clearInterval(tick);
                localStorage.removeItem('token');
                const p = window.location.pathname;
                const isPublicPage = p === '/' || p === '' || p.endsWith('/index.html')
                    || p === '/login' || p === '/register' || p === '/forgot-password';
                if (!isPublicPage) window.location.href = '/login';
                return;
            }
            if (remaining <= WARNING_BEFORE_MS) {
                if (!warned) { banner.classList.add('active'); warned = true; }
                const m = Math.floor(remaining / 60000);
                const s = Math.floor((remaining % 60000) / 1000);
                const el = document.getElementById('session-countdown');
                if (el) el.textContent = `${m}:${s.toString().padStart(2, '0')}`;
            }
        }, 1000);
    }

    window.extendSession = async function () {
        const token = localStorage.getItem('token');
        if (!token) return;
        try {
            const API_BASE = (window.location.protocol === 'http:' || window.location.protocol === 'https:') ? '' : 'http://127.0.0.1:5000';
            const res = await fetch(API_BASE + '/api/refresh-token', {
                method: 'POST', headers: { 'Authorization': 'Bearer ' + token }
            });
            if (res.ok) {
                const data = await res.json();
                if (data.token) {
                    localStorage.setItem('token', data.token);
                    const banner = document.getElementById('session-warning');
                    if (banner) banner.classList.remove('active');
                    startSessionTimer();
                    showToast('Session extended successfully', 'success');
                }
            }
        } catch { showToast('Could not extend session', 'error'); }
    };

    document.addEventListener('DOMContentLoaded', startSessionTimer);
})();

// Sidebar Navigation Component
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('token');
    const path = window.location.pathname;

    // Only hide sidebar on auth/landing pages
    const isLandingPage = path === '/' || path.endsWith('/index.html') || path === '';
    const isAuthPage = path.includes('auth.html') || path === '/login' || path === '/register' || path === '/forgot-password';
    if (isAuthPage || isLandingPage) {
        document.body.style.paddingLeft = '0';
        return;
    }

    // For protected pages, redirect if not logged in
    const isProtectedPage = !path.includes('index.html') && !path.endsWith('/');
    if (isProtectedPage && !token) {
        window.location.href = '/login';
        return;
    }

    // Inject sidebar on all pages except auth
    injectSidebar(!!token);
});

function injectSidebar(isLoggedIn = true) {
    if (document.querySelector('.sidebar')) {
        return;
    }

    const navLinks = isLoggedIn ? `
                <a href="/dashboard" class="sidebar-link" data-page="dashboard" data-tip="Your financial overview — charts, fraud stats, spending forecast &amp; AI snapshot">
                    <span class="sidebar-icon">📊</span>
                    <span>Dashboard</span>
                </a>
                <a href="/upload-page" class="sidebar-link" data-page="upload" data-tip="Import your bank statements (PDF, CSV, Excel) to start analysing transactions">
                    <span class="sidebar-icon">⬆️</span>
                    <span>Upload Data</span>
                </a>
                <a href="/transactions" class="sidebar-link" data-page="transactions" data-tip="View, search and filter all your imported transactions; delete or dispute any entry">
                    <span class="sidebar-icon">💳</span>
                    <span>Transactions</span>
                </a>
                <a href="/fraud-alerts" class="sidebar-link" data-page="fraudalerts" data-tip="Transactions flagged as high-risk by the ML fraud model — review and investigate each one">
                    <span class="sidebar-icon">⚠️</span>
                    <span>Fraud Alerts</span>
                </a>
                <a href="/predictive" class="sidebar-link" data-page="predictive" data-tip="Test any transaction manually against the fraud model — enter amount, channel &amp; merchant to get a risk score">
                    <span class="sidebar-icon">🧠</span>
                    <span>Predictions</span>
                </a>
                <a href="/rag" class="sidebar-link" data-page="rag" data-tip="FinRAG Copilot — ask questions about your uploaded PDFs &amp; 10-K reports; answers cite exact page &amp; passage">
                    <span class="sidebar-icon">🔎</span>
                    <span>FinRAG Copilot</span>
                </a>
                <a href="/credit-score" class="sidebar-link" data-page="credit-score" data-tip="Estimated credit health score computed from your transaction data — fraud ratio, history length &amp; activity">
                    <span class="sidebar-icon">⭐</span>
                    <span>Credit Health</span>
                </a>
                <a href="/investments" class="sidebar-link" data-page="investments" data-tip="Track your personal portfolio — stocks, mutual funds, gold &amp; fixed deposits with P&amp;L">
                    <span class="sidebar-icon">💰</span>
                    <span>Investments</span>
                </a>
                <a href="/loans" class="sidebar-link" data-page="loans" data-tip="EMI calculator with full amortisation schedule — see how much interest you pay over the loan tenure">
                    <span class="sidebar-icon">🏦</span>
                    <span>Loans &amp; EMI</span>
                </a>
                <a href="/insights" class="sidebar-link" data-page="insights" data-tip="Live accuracy, F1, precision &amp; recall of the fraud model; datasets used; FinRAG comparison">
                    <span class="sidebar-icon">💡</span>
                    <span>Insights</span>
                </a>
                <a href="/profile" class="sidebar-link" data-page="profile" data-tip="Edit your name, change your PIN, or permanently delete your account">
                    <span class="sidebar-icon">👤</span>
                    <span>Profile</span>
                </a>
                <button class="sidebar-link logout-btn" id="logoutBtn" data-tip="Sign out and clear your session">
                    <span class="sidebar-icon">🚪</span>
                    <span>Logout</span>
                </button>
    ` : `
                <a href="/" class="sidebar-link" data-page="index">
                    <span class="sidebar-icon">🏠</span>
                    <span>Home</span>
                </a>
                <a href="/login" class="sidebar-link" data-page="auth">
                    <span class="sidebar-icon">🔐</span>
                    <span>Login / Register</span>
                </a>
    `;

    const sidebarHTML = `
        <div class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <h2 class="sidebar-logo">BFSI Intelligence</h2>
                <button class="sidebar-toggle" id="sidebarToggle">
                    <span style="font-size: 1.2rem;">☰</span>
                </button>
            </div>

            <nav class="sidebar-nav">
                ${navLinks}
            </nav>
        </div>

        <div class="sidebar-overlay" id="sidebarOverlay"></div>
    `;

    document.body.insertAdjacentHTML('afterbegin', sidebarHTML);

    // Set active link based on current page
    const currentPage = window.location.pathname.split('/').pop().replace('.html', '') || 'dashboard';
    const links = document.querySelectorAll('.sidebar-link');
    links.forEach(link => {
        if (link.getAttribute('data-page') === currentPage) {
            link.classList.add('active');
        }
    });

    // Sidebar toggle functionality
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarOverlay = document.getElementById('sidebarOverlay');

    function toggleSidebar() {
        sidebar.classList.toggle('collapsed');
        document.body.classList.toggle('sidebar-collapsed');
    }

    function closeSidebar() {
        sidebar.classList.remove('mobile-open');
        sidebarOverlay.classList.remove('active');
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function () {
            if (window.innerWidth <= 768) {
                sidebar.classList.toggle('mobile-open');
                sidebarOverlay.classList.toggle('active');
            } else {
                toggleSidebar();
            }
        });
    } else {
        console.error('Sidebar toggle button not found');
    }

    sidebarOverlay.addEventListener('click', closeSidebar);

    // Logout functionality (only if logged in)
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function () {
            localStorage.removeItem('token');
            localStorage.removeItem('username');
            window.location.href = '/login';
        });
    }

    // Adjust body padding for sidebar
    document.body.style.paddingLeft = '260px';
    document.body.style.transition = 'padding-left 0.3s ease';

    // Responsive handling
    function handleResize() {
        if (window.innerWidth <= 768) {
            document.body.style.paddingLeft = '0';
        } else if (sidebar.classList.contains('collapsed')) {
            document.body.style.paddingLeft = '80px';
        } else {
            document.body.style.paddingLeft = '260px';
        }
    }

    window.addEventListener('resize', handleResize);
    handleResize();
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const target = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', target);
    localStorage.setItem('theme', target);
}

// ── Global info-icon tooltip engine ──────────────────────────────────────────
// Appended to <body> so it's never clipped by overflow:hidden card containers.
(function () {
    const tip = document.createElement('div');
    tip.id = 'info-tooltip';
    document.body.appendChild(tip);

    const GAP = 10; // px gap between icon and tooltip

    function position(icon) {
        const r = icon.getBoundingClientRect();
        const tw = tip.offsetWidth;
        const th = tip.offsetHeight;
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        const isSidebarLink = icon.classList.contains('sidebar-link');

        let top, left;

        if (isSidebarLink) {
            // Show to the RIGHT of the sidebar link, vertically centred
            top  = r.top + r.height / 2 - th / 2;
            left = r.right + GAP;
            // Clamp vertically
            top = Math.max(8, Math.min(top, vh - th - 8));
            // If it goes off the right edge, flip to left of sidebar
            if (left + tw + 8 > vw) left = r.left - tw - GAP;
        } else {
            // Default: prefer above the icon
            top = r.top - th - GAP;
            if (top < 8) top = r.bottom + GAP;
            left = r.left + r.width / 2 - tw / 2;
            left = Math.max(8, Math.min(left, vw - tw - 8));
        }

        tip.style.top  = top  + 'px';
        tip.style.left = left + 'px';

        // Arrow caret for non-sidebar (above/below)
        if (!isSidebarLink) {
            const arrowLeft = (r.left + r.width / 2) - left;
            tip.style.setProperty('--arrow-left', arrowLeft + 'px');
        } else {
            tip.style.setProperty('--arrow-left', '-9999px'); // hide arrow for sidebar
        }
    }

    document.addEventListener('mouseover', function (e) {
        const icon = e.target.closest('.info-icon, .sidebar-link[data-tip]');
        if (!icon) return;
        const text = icon.getAttribute('data-tip');
        if (!text) return;
        tip.textContent = text;
        tip.classList.add('visible');
        position(icon);
    });

    document.addEventListener('mouseout', function (e) {
        if (!e.target.closest('.info-icon, .sidebar-link[data-tip]')) return;
        tip.classList.remove('visible');
    });

    window.addEventListener('scroll', function () { tip.classList.remove('visible'); }, true);
    window.addEventListener('resize', function () { tip.classList.remove('visible'); });
})();
