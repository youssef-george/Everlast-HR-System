// Everlast ERP - Mobile Enhancement JavaScript

document.addEventListener('DOMContentLoaded', function() {
    'use strict';
    
    // Mobile detection
    const isMobile = window.innerWidth <= 991.98;
    const isTablet = window.innerWidth > 768 && window.innerWidth <= 991.98;
    const isPhone = window.innerWidth <= 768;
    
    // Add mobile class to body for CSS targeting
    if (isMobile) {
        document.body.classList.add('mobile-device');
    }
    if (isTablet) {
        document.body.classList.add('tablet-device');
    }
    if (isPhone) {
        document.body.classList.add('phone-device');
    }
    
    // Mobile touch enhancements
    if (isMobile) {
        // Add touch feedback to buttons
        const buttons = document.querySelectorAll('.btn, .nav-link, .mobile-menu-toggle');
        buttons.forEach(function(button) {
            button.addEventListener('touchstart', function() {
                this.classList.add('touch-active');
            });
            
            button.addEventListener('touchend', function() {
                setTimeout(() => {
                    this.classList.remove('touch-active');
                }, 150);
            });
        });
        
        // Add touch feedback to cards
        const cards = document.querySelectorAll('.card');
        cards.forEach(function(card) {
            card.addEventListener('touchstart', function() {
                this.classList.add('touch-active');
            });
            
            card.addEventListener('touchend', function() {
                setTimeout(() => {
                    this.classList.remove('touch-active');
                }, 150);
            });
        });
    }
    
    // Mobile form enhancements
    if (isMobile) {
        // Prevent zoom on input focus (iOS)
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach(function(input) {
            input.addEventListener('focus', function() {
                if (this.style.fontSize !== '16px') {
                    this.style.fontSize = '16px';
                }
            });
        });
        
        // Add mobile-friendly form validation
        const forms = document.querySelectorAll('form');
        forms.forEach(function(form) {
            form.addEventListener('submit', function(e) {
                const requiredFields = form.querySelectorAll('[required]');
                let isValid = true;
                
                requiredFields.forEach(function(field) {
                    if (!field.value.trim()) {
                        field.classList.add('is-invalid');
                        isValid = false;
                    } else {
                        field.classList.remove('is-invalid');
                    }
                });
                
                if (!isValid) {
                    e.preventDefault();
                    showMobileAlert('Please fill in all required fields', 'warning');
                }
            });
        });
    }
    
    // Mobile table enhancements
    if (isMobile) {
        // Make tables horizontally scrollable
        const tables = document.querySelectorAll('.table');
        tables.forEach(function(table) {
            if (!table.closest('.table-responsive')) {
                const wrapper = document.createElement('div');
                wrapper.className = 'table-responsive';
                table.parentNode.insertBefore(wrapper, table);
                wrapper.appendChild(table);
            }
        });
        
        // Add mobile table actions
        const tableRows = document.querySelectorAll('.table tbody tr');
        tableRows.forEach(function(row) {
            row.addEventListener('click', function(e) {
                // Don't trigger if clicking on buttons or links
                if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.closest('button') || e.target.closest('a')) {
                    return;
                }
                
                // Toggle row selection
                this.classList.toggle('table-row-selected');
            });
        });
    }
    
    // Mobile modal enhancements
    if (isMobile) {
        // Adjust modal height for mobile
        const modals = document.querySelectorAll('.modal');
        modals.forEach(function(modal) {
            modal.addEventListener('shown.bs.modal', function() {
                const modalDialog = this.querySelector('.modal-dialog');
                const viewportHeight = window.innerHeight;
                const maxHeight = viewportHeight * 0.9;
                
                if (modalDialog.offsetHeight > maxHeight) {
                    modalDialog.style.maxHeight = maxHeight + 'px';
                    modalDialog.style.overflowY = 'auto';
                }
            });
        });
    }
    
    // Mobile navigation enhancements
    if (isMobile) {
        // Close mobile menu when clicking outside
        document.addEventListener('click', function(e) {
            const sidebar = document.getElementById('sidebar');
            const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
            
            if (sidebar && sidebar.classList.contains('mobile-show')) {
                if (!sidebar.contains(e.target) && !mobileMenuToggle.contains(e.target)) {
                    closeMobileMenu();
                }
            }
        });
        
        // Add swipe gestures for mobile menu
        let startX = 0;
        let startY = 0;
        let endX = 0;
        let endY = 0;
        
        document.addEventListener('touchstart', function(e) {
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
        });
        
        document.addEventListener('touchend', function(e) {
            endX = e.changedTouches[0].clientX;
            endY = e.changedTouches[0].clientY;
            
            const diffX = startX - endX;
            const diffY = startY - endY;
            
            // Swipe left to close mobile menu
            if (Math.abs(diffX) > Math.abs(diffY) && diffX > 50) {
                const sidebar = document.getElementById('sidebar');
                if (sidebar && sidebar.classList.contains('mobile-show')) {
                    closeMobileMenu();
                }
            }
            
            // Swipe right to open mobile menu (from left edge)
            if (Math.abs(diffX) > Math.abs(diffY) && diffX < -50 && startX < 50) {
                const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
                if (mobileMenuToggle) {
                    mobileMenuToggle.click();
                }
            }
        });
    }
    
    // Mobile performance optimizations
    if (isMobile) {
        // Lazy load images
        const images = document.querySelectorAll('img[data-src]');
        const imageObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    observer.unobserve(img);
                }
            });
        });
        
        images.forEach(function(img) {
            imageObserver.observe(img);
        });
        
        // Debounce scroll events
        let scrollTimeout;
        window.addEventListener('scroll', function() {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(function() {
                // Handle scroll events here
                updateScrollIndicators();
            }, 10);
        });
    }
    
    // Mobile orientation change handling
    window.addEventListener('orientationchange', function() {
        setTimeout(function() {
            // Recalculate layout after orientation change
            window.dispatchEvent(new Event('resize'));
            
            // Close mobile menu on orientation change
            closeMobileMenu();
        }, 100);
    });
    
    // Mobile keyboard handling
    if (isMobile) {
        // Handle virtual keyboard
        let initialViewportHeight = window.innerHeight;
        
        window.addEventListener('resize', function() {
            const currentHeight = window.innerHeight;
            const heightDifference = initialViewportHeight - currentHeight;
            
            if (heightDifference > 150) {
                // Virtual keyboard is open
                document.body.classList.add('keyboard-open');
            } else {
                // Virtual keyboard is closed
                document.body.classList.remove('keyboard-open');
            }
        });
    }
    
    // Mobile notification system
    function showMobileAlert(message, type = 'info') {
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.mobile-alert');
        existingAlerts.forEach(function(alert) {
            alert.remove();
        });
        
        // Create new alert
        const alert = document.createElement('div');
        alert.className = `mobile-alert alert alert-${type} alert-dismissible fade show`;
        alert.style.cssText = `
            position: fixed;
            top: 20px;
            left: 20px;
            right: 20px;
            z-index: 9999;
            border-radius: 12px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
            font-size: 14px;
            padding: 1rem;
        `;
        
        alert.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="fas fa-${getAlertIcon(type)} me-2"></i>
                <span>${message}</span>
                <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        document.body.appendChild(alert);
        
        // Auto-remove after 5 seconds
        setTimeout(function() {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 5000);
    }
    
    function getAlertIcon(type) {
        const icons = {
            'success': 'check-circle',
            'danger': 'exclamation-triangle',
            'warning': 'exclamation-circle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    }
    
    // Mobile utility functions
    function closeMobileMenu() {
        const sidebar = document.getElementById('sidebar');
        const mobileOverlay = document.getElementById('mobile-overlay');
        
        if (sidebar) {
            sidebar.classList.remove('mobile-show');
        }
        if (mobileOverlay) {
            mobileOverlay.classList.remove('active');
        }
        document.body.style.overflow = '';
    }
    
    function updateScrollIndicators() {
        const sidebarNavContainer = document.querySelector('.sidebar-nav-container');
        if (!sidebarNavContainer) return;
        
        const isScrollable = sidebarNavContainer.scrollHeight > sidebarNavContainer.clientHeight;
        const isAtTop = sidebarNavContainer.scrollTop <= 1;
        const isAtBottom = sidebarNavContainer.scrollTop + sidebarNavContainer.clientHeight >= sidebarNavContainer.scrollHeight - 1;
        
        sidebarNavContainer.classList.toggle('scrollable-top', isScrollable && !isAtTop);
        sidebarNavContainer.classList.toggle('scrollable-bottom', isScrollable && !isAtBottom);
    }
    
    // Mobile-specific CSS classes
    if (isMobile) {
        // Add mobile-specific classes
        document.body.classList.add('mobile-layout');
        
        // Add touch feedback styles
        const style = document.createElement('style');
        style.textContent = `
            .touch-active {
                transform: scale(0.98);
                opacity: 0.8;
                transition: all 0.1s ease;
            }
            
            .table-row-selected {
                background-color: rgba(99, 102, 241, 0.1) !important;
            }
            
            .keyboard-open .mobile-header {
                position: relative;
            }
            
            .keyboard-open .content-wrapper {
                padding-bottom: 0;
            }
            
            .mobile-layout .btn {
                min-height: 44px;
                min-width: 44px;
            }
            
            .mobile-layout .form-control,
            .mobile-layout .form-select {
                min-height: 44px;
            }
            
            .mobile-layout .nav-link {
                min-height: 44px;
                display: flex;
                align-items: center;
            }
        `;
        document.head.appendChild(style);
    }
    
    // Expose mobile functions globally
    window.mobileUtils = {
        showAlert: showMobileAlert,
        closeMenu: closeMobileMenu,
        isMobile: isMobile,
        isTablet: isTablet,
        isPhone: isPhone
    };
});

