// Theme Logic
console.log('🚀 NAVBAR.JS LOADED - Version 7');
const savedTheme = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

// Sidebar Navigation Component
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('token');
    const path = window.location.pathname;

    // Only hide sidebar on auth page and landing page
    const isLandingPage = path === '/' || path.endsWith('/index.html') || path === '';
    if (path.includes('auth.html') || isLandingPage) {
        document.body.style.paddingLeft = '0';
        return;
    }

    // For protected pages, redirect if not logged in
    const isProtectedPage = !path.includes('index.html') && !path.endsWith('/');
    if (isProtectedPage && !token) {
        window.location.href = 'auth.html';
        return;
    }

    // Inject sidebar on all pages except auth
    injectSidebar(!!token);
});

function injectSidebar(isLoggedIn = true) {
    console.log('📌 injectSidebar called, isLoggedIn:', isLoggedIn);

    if (document.querySelector('.sidebar')) {
        console.log('⚠️ Sidebar already exists, skipping injection');
        return;
    }

    console.log('✅ Creating sidebar HTML...');

    const navLinks = isLoggedIn ? `
                <a href="dashboard.html" class="sidebar-link" data-page="dashboard">
                    <span class="sidebar-icon">📊</span>
                    <span>Dashboard</span>
                </a>
                <a href="upload.html" class="sidebar-link" data-page="upload">
                    <span class="sidebar-icon">⬆️</span>
                    <span>Upload Data</span>
                </a>
                <a href="transactions.html" class="sidebar-link" data-page="transactions">
                    <span class="sidebar-icon">💳</span>
                    <span>Transactions</span>
                </a>
                <a href="fraudalerts.html" class="sidebar-link" data-page="fraudalerts">
                    <span class="sidebar-icon">⚠️</span>
                    <span>Fraud Alerts</span>
                </a>
                <a href="predictive.html" class="sidebar-link" data-page="predictive">
                    <span class="sidebar-icon">🧠</span>
                    <span>Predictions</span>
                </a>
                <a href="insights.html" class="sidebar-link" data-page="insights">
                    <span class="sidebar-icon">💡</span>
                    <span>Insights</span>
                </a>
                <a href="investments.html" class="sidebar-link" data-page="investments">
                    <span class="sidebar-icon">💰</span>
                    <span>Investments</span>
                </a>
                <a href="loans.html" class="sidebar-link" data-page="loans">
                    <span class="sidebar-icon">🏦</span>
                    <span>Loans</span>
                </a>
                <a href="budget.html" class="sidebar-link" data-page="budget">
                    <span class="sidebar-icon">💸</span>
                    <span>Budget</span>
                </a>
                <a href="credit_score.html" class="sidebar-link" data-page="credit_score">
                    <span class="sidebar-icon">⭐</span>
                    <span>Credit Score</span>
                </a>
                <a href="profile.html" class="sidebar-link" data-page="profile">
                    <span class="sidebar-icon">👤</span>
                    <span>Profile</span>
                </a>
    ` : `
                <a href="index.html" class="sidebar-link" data-page="index">
                    <span class="sidebar-icon">🏠</span>
                    <span>Home</span>
                </a>
                <a href="auth.html" class="sidebar-link" data-page="auth">
                    <span class="sidebar-icon">🔐</span>
                    <span>Login / Register</span>
                </a>
    `;

    const footerButton = isLoggedIn ? `
                <button class="sidebar-link logout-btn" id="logoutBtn">
                    <span class="sidebar-icon">🚪</span>
                    <span>Logout</span>
                </button>
    ` : '';

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
            
            <div class="sidebar-footer">
                ${footerButton}
            </div>
        </div>
        
        <div class="sidebar-overlay" id="sidebarOverlay"></div>
    `;

    document.body.insertAdjacentHTML('afterbegin', sidebarHTML);

    console.log('✨ Sidebar HTML inserted into page');
    console.log('Sidebar element:', document.querySelector('.sidebar'));

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

    console.log('🔧 Setting up sidebar toggle...');
    console.log('Sidebar element:', sidebar);
    console.log('Toggle button:', sidebarToggle);

    function toggleSidebar() {
        console.log('🔄 toggleSidebar called');
        sidebar.classList.toggle('collapsed');
        document.body.classList.toggle('sidebar-collapsed');
    }

    function closeSidebar() {
        console.log('❌ closeSidebar called');
        sidebar.classList.remove('mobile-open');
        sidebarOverlay.classList.remove('active');
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function () {
            console.log('🖱️ Hamburger clicked! Window width:', window.innerWidth);
            console.log('Before toggle - Sidebar classes:', sidebar.className);

            if (window.innerWidth <= 768) {
                console.log('📱 Mobile mode - toggling sidebar');
                sidebar.classList.toggle('mobile-open');
                sidebarOverlay.classList.toggle('active');
            } else {
                console.log('💻 Desktop mode - collapsing sidebar');
                toggleSidebar();
            }

            console.log('After toggle - Sidebar classes:', sidebar.className);
        });
        console.log('✅ Click listener attached to hamburger button');
    } else {
        console.error('❌ Hamburger button not found!');
    }

    sidebarOverlay.addEventListener('click', closeSidebar);

    // Logout functionality (only if logged in)
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function () {
            localStorage.removeItem('token');
            localStorage.removeItem('username');
            window.location.href = 'auth.html';
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
