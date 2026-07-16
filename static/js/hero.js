document.addEventListener('DOMContentLoaded', () => {
    
    // 1. Mouse Follow Light Effect
    const heroSection = document.querySelector('.hero-saas');
    const cursorLight = document.querySelector('.cursor-light');
    
    if (heroSection && cursorLight) {
        heroSection.addEventListener('mousemove', (e) => {
            const rect = heroSection.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            cursorLight.style.left = `${x}px`;
            cursorLight.style.top = `${y}px`;
        });
        
        heroSection.addEventListener('mouseleave', () => {
            cursorLight.style.opacity = '0';
        });
        
        heroSection.addEventListener('mouseenter', () => {
            cursorLight.style.opacity = '1';
        });
    }
    
    // 2. Ripple Effect on Buttons
    const buttons = document.querySelectorAll('.btn-premium');
    
    buttons.forEach(btn => {
        btn.addEventListener('click', function (e) {
            let x = e.clientX - e.target.getBoundingClientRect().left;
            let y = e.clientY - e.target.getBoundingClientRect().top;
            
            let ripples = document.createElement('span');
            ripples.className = 'ripple';
            ripples.style.left = x + 'px';
            ripples.style.top = y + 'px';
            this.appendChild(ripples);
            
            setTimeout(() => {
                ripples.remove();
            }, 600);
        });
    });

    // 3. Animated Counters (Intersection Observer)
    const counters = document.querySelectorAll('.animate-counter');
    const observerOptions = {
        threshold: 0.5
    };
    
    const counterObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const target = +entry.target.getAttribute('data-target');
                const duration = 2000; // 2 seconds
                const stepTime = Math.abs(Math.floor(duration / target));
                
                let current = 0;
                const isFloat = entry.target.getAttribute('data-float') === "true";
                
                const timer = setInterval(() => {
                    const increment = target / (duration / 30);
                    current += increment;
                    
                    if (current >= target) {
                        entry.target.innerText = isFloat ? target.toFixed(1) : Math.ceil(target);
                        clearInterval(timer);
                    } else {
                        entry.target.innerText = isFloat ? current.toFixed(1) : Math.ceil(current);
                    }
                }, 30);
                
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);
    
    counters.forEach(counter => {
        counterObserver.observe(counter);
    });
    
    // 4. Mouse Parallax for Dashboard Card
    const dashWrapper = document.querySelector('.dashboard-wrapper');
    if (heroSection && dashWrapper) {
        heroSection.addEventListener('mousemove', (e) => {
            const xAxis = (window.innerWidth / 2 - e.pageX) / 50;
            const yAxis = (window.innerHeight / 2 - e.pageY) / 50;
            dashWrapper.style.transform = `rotateY(${xAxis - 15}deg) rotateX(${yAxis + 5}deg)`;
        });
        
        heroSection.addEventListener('mouseleave', () => {
            dashWrapper.style.transition = "transform 0.5s ease";
            dashWrapper.style.transform = `rotateY(-15deg) rotateX(5deg)`;
        });
        
        heroSection.addEventListener('mouseenter', () => {
            dashWrapper.style.transition = "none";
        });
    }
});
