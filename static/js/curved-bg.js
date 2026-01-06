// Scroll-Animated Curved Background Lines
// Premium fintech motion graphics with parallax effect

class CurvedBackground {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.curves = [];
        this.scrollY = 0;
        this.animationFrame = null;
        this.isMobile = window.innerWidth < 768;

        this.init();
    }

    init() {
        console.log('🎨 Curved Background: Initializing...');
        // Create canvas element
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'curved-bg-canvas';
        this.canvas.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
            opacity: 1;
        `;

        // Insert canvas as first child of body
        document.body.insertBefore(this.canvas, document.body.firstChild);

        this.ctx = this.canvas.getContext('2d');
        this.resize();
        this.createCurves();

        // Event listeners
        window.addEventListener('resize', () => this.resize());
        window.addEventListener('scroll', () => this.onScroll(), { passive: true });

        console.log(`🎨 Curved Background: Canvas created (${this.canvas.width}x${this.canvas.height}), ${this.curves.length} curves`);

        // Start animation
        this.animate();
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
        this.isMobile = window.innerWidth < 768;
        this.createCurves();
    }

    createCurves() {
        const numCurves = this.isMobile ? 3 : 6;
        this.curves = [];

        for (let i = 0; i < numCurves; i++) {
            this.curves.push({
                points: this.generateCurvePoints(),
                opacity: 0.15 + Math.random() * 0.15, // 0.15 - 0.30 (much more visible)
                speed: 0.2 + Math.random() * 0.3, // Parallax speed multiplier
                phase: Math.random() * Math.PI * 2, // For horizontal drift
                strokeWidth: this.isMobile ? 2 : 3,
                blur: Math.random() * 1
            });
        }
    }

    generateCurvePoints() {
        const width = this.canvas.width;
        const height = this.canvas.height;
        const points = [];

        // Generate random bezier curve points
        const numPoints = 4 + Math.floor(Math.random() * 3);

        for (let i = 0; i < numPoints; i++) {
            points.push({
                x: (Math.random() * width) - width * 0.2,
                y: (i / numPoints) * height * 1.5 + Math.random() * 200,
                cpX1: Math.random() * width,
                cpY1: (i / numPoints) * height + Math.random() * 100,
                cpX2: Math.random() * width,
                cpY2: ((i + 1) / numPoints) * height + Math.random() * 100
            });
        }

        return points;
    }

    onScroll() {
        this.scrollY = window.scrollY;
    }

    drawCurve(curve, time) {
        const { points, opacity, speed, phase, strokeWidth, blur } = curve;

        this.ctx.save();

        // Apply blur if needed
        if (blur > 0) {
            this.ctx.filter = `blur(${blur}px)`;
        }

        // Calculate parallax offset
        const parallaxY = this.scrollY * speed;

        // Horizontal drift using sine wave
        const driftX = Math.sin(time * 0.0002 + phase) * 20;

        // Opacity pulsation
        const pulsation = Math.sin(time * 0.001 + phase) * 0.01;
        const finalOpacity = Math.max(0.02, opacity + pulsation);

        // Set stroke style with red tint
        this.ctx.strokeStyle = `rgba(229, 9, 20, ${finalOpacity})`;
        this.ctx.lineWidth = strokeWidth;
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        // Draw the curve
        this.ctx.beginPath();

        for (let i = 0; i < points.length - 1; i++) {
            const p1 = points[i];
            const p2 = points[i + 1];

            if (i === 0) {
                this.ctx.moveTo(
                    p1.x + driftX,
                    p1.y - parallaxY
                );
            }

            this.ctx.bezierCurveTo(
                p1.cpX2 + driftX,
                p1.cpY2 - parallaxY,
                p2.cpX1 + driftX,
                p2.cpY1 - parallaxY,
                p2.x + driftX,
                p2.y - parallaxY
            );
        }

        this.ctx.stroke();
        this.ctx.restore();
    }

    animate() {
        const time = Date.now();

        // Clear canvas
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // Draw all curves
        this.curves.forEach(curve => this.drawCurve(curve, time));

        // Continue animation
        this.animationFrame = requestAnimationFrame(() => this.animate());
    }

    destroy() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }
        if (this.canvas && this.canvas.parentNode) {
            this.canvas.parentNode.removeChild(this.canvas);
        }
        window.removeEventListener('resize', () => this.resize());
        window.removeEventListener('scroll', () => this.onScroll());
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new CurvedBackground();
    });
} else {
    new CurvedBackground();
}
