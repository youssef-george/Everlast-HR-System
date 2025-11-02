/**
 * Everlast ERP - Responsive Sidebar Manager
 * Handles mobile sidebar behavior, touch events, and responsive layout
 */

class ResponsiveSidebar {
    constructor(options = {}) {
        // Configuration
        this.config = {
            breakpoints: {
                mobile: 768,
                tablet: 992,
                desktop: 1200
            },
            classes: {
                sidebarOpen: 'sidebar-open',
                sidebarClosed: 'sidebar-closed',
                mobileShow: 'mobile-show',
                bodyScrollLock: 'body-scroll-lock',
                hamburgerActive: 'hamburger-active'
            },
            selectors: {
                sidebar: '#sidebar',
                mobileToggle: '#mobile-menu-toggle',
                mobileOverlay: '#mobile-overlay',
                body: 'body',
                pageWrapper: '.page-wrapper',
                contentWrapper: '.content-wrapper'
            },
            animation: {
                duration: 300,
                easing: 'cubic-bezier(0.4, 0, 0.2, 1)'
            },
            touch: {
                threshold: 50,
                maxTime: 300
            },
            zIndex: {
                sidebar: 1050,
                overlay: 1040
            },
            ...options
        };

        // State
        this.state = {
            isOpen: false,
            isMobile: false,
            touchStartX: 0,
            touchStartY: 0,
            touchStartTime: 0,
            isScrollLocked: false
        };

        // Elements
        this.elements = {};
        
        // Initialize
        this.init();
    }

    init() {
        this.cacheElements();
        this.bindEvents();
        this.checkViewport();
        this.setupMutationObserver();
        
        // Initial state
        this.updateLayout();
        
        console.log('ResponsiveSidebar initialized');
    }

    cacheElements() {
        this.elements = {
            sidebar: document.querySelector(this.config.selectors.sidebar),
            mobileToggle: document.querySelector(this.config.selectors.mobileToggle),
            mobileOverlay: document.querySelector(this.config.selectors.mobileOverlay),
            body: document.querySelector(this.config.selectors.body),
            pageWrapper: document.querySelector(this.config.selectors.pageWrapper),
            contentWrapper: document.querySelector(this.config.selectors.contentWrapper)
        };

        // Validate required elements
        if (!this.elements.sidebar) {
            console.error('ResponsiveSidebar: Sidebar element not found');
            return;
        }
        if (!this.elements.body) {
            console.error('ResponsiveSidebar: Body element not found');
            return;
        }
        if (!this.elements.pageWrapper) {
            console.error('ResponsiveSidebar: Page Wrapper element not found');
            return;
        }
        if (!this.elements.contentWrapper) {
            console.error('ResponsiveSidebar: Content Wrapper element not found');
            return;
        }
    }

    bindEvents() {
        // Mobile toggle
        if (this.elements.mobileToggle) {
            this.elements.mobileToggle.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggle();
            });
        }

        // Overlay click
        if (this.elements.mobileOverlay) {
            this.elements.mobileOverlay.addEventListener('click', () => {
                this.close();
            });
        }

        // Window resize
        window.addEventListener('resize', this.debounce(() => {
            this.checkViewport();
            this.updateLayout();
        }, 250));

        // Touch events for swipe gestures
        this.bindTouchEvents();

        // Keyboard events
        this.bindKeyboardEvents();

        // Focus management
        this.bindFocusEvents();
    }

    bindTouchEvents() {
        if (!this.elements.sidebar) return;

        // Touch start
        this.elements.sidebar.addEventListener('touchstart', (e) => {
            this.state.touchStartX = e.touches[0].clientX;
            this.state.touchStartY = e.touches[0].clientY;
            this.state.touchStartTime = Date.now();
        }, { passive: true });

        // Touch end
        this.elements.sidebar.addEventListener('touchend', (e) => {
            if (!this.state.isMobile) return;

            const touchEndX = e.changedTouches[0].clientX;
            const touchEndY = e.changedTouches[0].clientY;
            const touchEndTime = Date.now();

            const deltaX = touchEndX - this.state.touchStartX;
            const deltaY = touchEndY - this.state.touchStartY;
            const deltaTime = touchEndTime - this.state.touchStartTime;

            // Check if it's a swipe gesture
            if (Math.abs(deltaX) > this.config.touch.threshold && 
                Math.abs(deltaY) < this.config.touch.threshold && 
                deltaTime < this.config.touch.maxTime) {
                
                if (deltaX < 0 && this.state.isOpen) {
                    // Swipe left to close
                    this.close();
                }
            }
        }, { passive: true });

        // Body touch events for swipe to open
        this.elements.body.addEventListener('touchstart', (e) => {
            if (!this.state.isMobile || this.state.isOpen) return;

            this.state.touchStartX = e.touches[0].clientX;
            this.state.touchStartTime = Date.now();
        }, { passive: true });

        this.elements.body.addEventListener('touchend', (e) => {
            if (!this.state.isMobile || this.state.isOpen) return;

            const touchEndX = e.changedTouches[0].clientX;
            const touchEndTime = Date.now();
            const deltaX = touchEndX - this.state.touchStartX;
            const deltaTime = touchEndTime - this.state.touchStartTime;

            // Swipe right from left edge to open
            if (this.state.touchStartX < 20 && 
                deltaX > this.config.touch.threshold && 
                deltaTime < this.config.touch.maxTime) {
                this.open();
            }
        }, { passive: true });
    }

    bindKeyboardEvents() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.state.isOpen && this.state.isMobile) {
                this.close();
            }
        });
    }

    bindFocusEvents() {
        // Trap focus within sidebar when open on mobile
        if (this.elements.sidebar) {
            this.elements.sidebar.addEventListener('keydown', (e) => {
                if (!this.state.isMobile || !this.state.isOpen) return;

                if (e.key === 'Tab') {
                    this.trapFocus(e);
                }
            });
        }
    }

    checkViewport() {
        const width = window.innerWidth;
        const wasMobile = this.state.isMobile;
        
        this.state.isMobile = width < this.config.breakpoints.mobile;
        
        // If switching from mobile to desktop, ensure sidebar is properly shown
        if (wasMobile && !this.state.isMobile && this.state.isOpen) {
            this.unlockBodyScroll();
            this.state.isOpen = false;
        }
    }

    updateLayout() {
        if (!this.elements.sidebar) return;

        if (this.state.isMobile) {
            // Mobile layout
            this.elements.sidebar.style.transform = this.state.isOpen ? 'translateX(0)' : 'translateX(-100%)';
            
            if (this.elements.mobileOverlay) {
                this.elements.mobileOverlay.style.display = this.state.isOpen ? 'block' : 'none';
                this.elements.mobileOverlay.style.opacity = this.state.isOpen ? '1' : '0';
            }
            
            // Update hamburger animation
            if (this.elements.mobileToggle) {
                this.elements.mobileToggle.classList.toggle(this.config.classes.hamburgerActive, this.state.isOpen);
            }
        } else {
            // Desktop layout
            this.elements.sidebar.style.transform = '';
            
            if (this.elements.mobileOverlay) {
                this.elements.mobileOverlay.style.display = 'none';
            }
            
            if (this.elements.mobileToggle) {
                this.elements.mobileToggle.classList.remove(this.config.classes.hamburgerActive);
            }
        }

        // Update body classes
        this.elements.body.classList.toggle(this.config.classes.sidebarOpen, this.state.isOpen && this.state.isMobile);
    }

    open() {
        if (!this.state.isMobile) return;

        this.state.isOpen = true;
        this.lockBodyScroll();
        this.updateLayout();
        
        // Focus management
        this.focusFirstElement();
        
        this.emit('sidebar:open');
    }

    close() {
        if (!this.state.isMobile) return;

        this.state.isOpen = false;
        this.unlockBodyScroll();
        this.updateLayout();
        
        // Return focus to toggle button
        if (this.elements.mobileToggle) {
            this.elements.mobileToggle.focus();
        }
        
        this.emit('sidebar:close');
    }

    toggle() {
        if (this.state.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    lockBodyScroll() {
        if (this.state.isScrollLocked) return;
        
        this.state.isScrollLocked = true;
        this.elements.body.classList.add(this.config.classes.bodyScrollLock);
        
        // Store current scroll position
        this.scrollPosition = window.pageYOffset;
        this.elements.body.style.top = `-${this.scrollPosition}px`;
    }

    unlockBodyScroll() {
        if (!this.state.isScrollLocked) return;
        
        this.state.isScrollLocked = false;
        this.elements.body.classList.remove(this.config.classes.bodyScrollLock);
        this.elements.body.style.top = '';
        
        // Restore scroll position
        if (this.scrollPosition !== undefined) {
            window.scrollTo(0, this.scrollPosition);
        }
    }

    focusFirstElement() {
        if (!this.elements.sidebar) return;
        
        const focusableElements = this.elements.sidebar.querySelectorAll(
            'a[href], button, textarea, input[type="text"], input[type="radio"], input[type="checkbox"], select'
        );
        
        if (focusableElements.length > 0) {
            focusableElements[0].focus();
        }
    }

    trapFocus(e) {
        const focusableElements = this.elements.sidebar.querySelectorAll(
            'a[href], button, textarea, input[type="text"], input[type="radio"], input[type="checkbox"], select'
        );
        
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        
        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                lastElement.focus();
                e.preventDefault();
            }
        } else {
            if (document.activeElement === lastElement) {
                firstElement.focus();
                e.preventDefault();
            }
        }
    }

    setupMutationObserver() {
        if (typeof MutationObserver === 'undefined') return;

        this.observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    this.handleClassChange(mutation.target);
                }
            });
        });

        this.observer.observe(this.elements.body, {
            attributes: true,
            attributeFilter: ['class']
        });
    }

    handleClassChange(target) {
        // Handle any class changes that might affect sidebar state
        if (target === this.elements.body) {
            // React to body class changes if needed
        }
    }

    emit(eventName, data = {}) {
        const event = new CustomEvent(eventName, {
            detail: { ...data, sidebar: this }
        });
        document.dispatchEvent(event);
    }

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Public API
    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
        
        this.unlockBodyScroll();
        
        // Remove event listeners
        window.removeEventListener('resize', this.checkViewport);
        
        console.log('ResponsiveSidebar destroyed');
    }

    getState() {
        return { ...this.state };
    }

    isMobileView() {
        return this.state.isMobile;
    }

    isOpen() {
        return this.state.isOpen;
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize responsive sidebar
    window.responsiveSidebar = new ResponsiveSidebar();
    
    // Global event listeners for custom events
    document.addEventListener('sidebar:open', function(e) {
        console.log('Sidebar opened');
    });
    
    document.addEventListener('sidebar:close', function(e) {
        console.log('Sidebar closed');
    });
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResponsiveSidebar;
}