// Everlast HR System - Main JavaScript v1.1

// Prevent MutationObserver errors from external scripts
(function() {
    'use strict';
    
    // Override MutationObserver to add error handling
    const OriginalMutationObserver = window.MutationObserver;
    window.MutationObserver = function(callback) {
        return new OriginalMutationObserver(function(mutations, observer) {
            try {
                callback(mutations, observer);
            } catch (error) {
                // Silently ignore MutationObserver callback errors from external scripts
                // This prevents console spam from third-party libraries
            }
        });
    };
    
    // Copy static methods
    Object.setPrototypeOf(window.MutationObserver, OriginalMutationObserver);
    Object.defineProperty(window.MutationObserver, 'prototype', {
        value: OriginalMutationObserver.prototype,
        writable: false
    });
    
    // Override observe method to validate target
    const originalObserve = OriginalMutationObserver.prototype.observe;
    OriginalMutationObserver.prototype.observe = function(target, options) {
        try {
            // Enhanced validation - check multiple conditions
            if (!target) {
                console.warn('MutationObserver.observe: target is null/undefined, skipping');
                return;
            }
            
            // Check if it's a valid Node
            if (!(target instanceof Node)) {
                console.warn('MutationObserver.observe: target is not a Node:', typeof target, target);
                return;
            }
            
            // Check nodeType to ensure it's a valid DOM node
            if (typeof target.nodeType === 'undefined') {
                console.warn('MutationObserver.observe: target has no nodeType property');
                return;
            }
            
            // Check if node is connected to the document
            if (target.nodeType === Node.ELEMENT_NODE && !document.contains(target)) {
                console.warn('MutationObserver.observe: target element is not in document, skipping');
                return;
            }
            
            return originalObserve.call(this, target, options);
        } catch (error) {
            // Silently ignore MutationObserver errors from external scripts
            console.warn('MutationObserver.observe error caught:', error.message);
            return;
        }
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle functionality
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const contentWrapper = document.getElementById('content-wrapper');
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileOverlay = document.getElementById('mobile-overlay');
    const navMenu = document.querySelector('.nav-menu');
    const sidebarNavContainer = document.querySelector('.sidebar-nav-container');

    // Enhanced session-based sidebar state management
    const SidebarManager = {
        // Session keys
        SESSION_KEY: 'everlast_sidebar_state',
        USER_SESSION_KEY: 'everlast_user_session',
        LAST_ACTIVITY_KEY: 'everlast_last_activity',
        
        // Session timeout (30 minutes - matches Flask session timeout)
        SESSION_TIMEOUT: 30 * 60 * 1000,
        
        // Current session ID
        currentSessionId: null,
        
        // Initialize session tracking
        init() {
            this.currentSessionId = this.getOrCreateSessionId();
            this.updateLastActivity();
            this.setupActivityTracking();
            this.checkSessionValidity();
        },
        
        // Get or create a unique session ID
        getOrCreateSessionId() {
            let sessionId = sessionStorage.getItem(this.USER_SESSION_KEY);
            if (!sessionId) {
                sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                sessionStorage.setItem(this.USER_SESSION_KEY, sessionId);
            }
            return sessionId;
        },
        
        // Update last activity timestamp
        updateLastActivity() {
            const now = Date.now();
            sessionStorage.setItem(this.LAST_ACTIVITY_KEY, now.toString());
            localStorage.setItem(this.LAST_ACTIVITY_KEY, now.toString());
        },
        
        // Setup activity tracking
        setupActivityTracking() {
            const events = ['click', 'keypress', 'scroll', 'mousemove', 'touchstart'];
            events.forEach(event => {
                document.addEventListener(event, () => {
                    this.updateLastActivity();
                }, { passive: true });
            });
        },
        
        // Check if current session is valid
        checkSessionValidity() {
            const lastActivity = localStorage.getItem(this.LAST_ACTIVITY_KEY);
            const now = Date.now();
            
            if (lastActivity && (now - parseInt(lastActivity)) > this.SESSION_TIMEOUT) {
                // Session has timed out, reset sidebar state
                this.resetSidebarState();
                return false;
            }
            return true;
        },
        
        // Save sidebar state for current session
        saveSidebarState(isCollapsed) {
            const stateData = {
                collapsed: isCollapsed,
                sessionId: this.currentSessionId,
                timestamp: Date.now()
            };
            
            // Save to both sessionStorage and localStorage
            sessionStorage.setItem(this.SESSION_KEY, JSON.stringify(stateData));
            localStorage.setItem(this.SESSION_KEY, JSON.stringify(stateData));
            localStorage.setItem('sidebar-user-collapsed', isCollapsed ? 'true' : 'false');
        },
        
        // Load sidebar state for current session
        loadSidebarState() {
            // First check sessionStorage (more reliable for active sessions)
            let stateData = sessionStorage.getItem(this.SESSION_KEY);
            
            if (stateData) {
                try {
                    const state = JSON.parse(stateData);
                    // Verify it's from the current session
                    if (state.sessionId === this.currentSessionId) {
                        return state.collapsed;
                    }
                } catch (e) {
                    console.warn('Failed to parse sidebar state from sessionStorage');
                }
            }
            
            // Fallback to localStorage
            stateData = localStorage.getItem(this.SESSION_KEY);
            if (stateData) {
                try {
                    const state = JSON.parse(stateData);
                    // Check if session is still valid
                    if (this.checkSessionValidity() && state.sessionId === this.currentSessionId) {
                        return state.collapsed;
                    }
                } catch (e) {
                    console.warn('Failed to parse sidebar state from localStorage');
                }
            }
            
            // Check if user explicitly collapsed it (legacy support)
            const userExplicitlyCollapsed = localStorage.getItem('sidebar-user-collapsed') === 'true';
            if (userExplicitlyCollapsed && this.checkSessionValidity()) {
                return true;
            }
            
            // Default to expanded
            return false;
        },
        
        // Reset sidebar state (called on logout/timeout)
        resetSidebarState() {
            sessionStorage.removeItem(this.SESSION_KEY);
            localStorage.removeItem(this.SESSION_KEY);
            localStorage.removeItem('sidebar-user-collapsed');
            localStorage.removeItem('sidebar-collapsed');
            
            // Reset to expanded state
            if (sidebar) {
                sidebar.classList.remove('collapsed');
            }
            if (contentWrapper) {
                contentWrapper.style.marginLeft = getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width');
            }
            setupSidebarTooltips(false);
        },
        
        // Check if we're on a page that should reset sidebar (login, error pages)
        shouldResetSidebar() {
            const currentPath = window.location.pathname;
            const resetPages = ['/login', '/auth/login', '/logout', '/auth/logout'];
            return resetPages.some(page => currentPath.includes(page));
        }
    };

    // Helper: Initialize/destroy tooltips on sidebar items based on collapsed state
    function setupSidebarTooltips(isCollapsed) {
        if (!sidebar) return;
        const links = sidebar.querySelectorAll('.nav-menu .nav-link');
        links.forEach(function(link) {
            try {
                const textEl = link.querySelector('.nav-text');
                const titleText = textEl ? textEl.textContent.trim() : (link.getAttribute('title') || '').trim();
                if (isCollapsed && titleText) {
                    link.setAttribute('data-bs-toggle', 'tooltip');
                    link.setAttribute('data-bs-placement', 'right');
                    link.setAttribute('title', titleText);
                    if (!link._tooltipInstance) {
                        // Check if there's already a global tooltip instance
                        const existingGlobalTooltip = bootstrap.Tooltip.getInstance(link);
                        if (existingGlobalTooltip) {
                            link._tooltipInstance = existingGlobalTooltip;
                        } else {
                            link._tooltipInstance = new bootstrap.Tooltip(link);
                        }
                    }
                } else {
                    if (link._tooltipInstance) {
                        link._tooltipInstance.dispose();
                        link._tooltipInstance = null;
                    }
                    link.removeAttribute('data-bs-toggle');
                    link.removeAttribute('data-bs-placement');
                    // Preserve any original title added by developer; otherwise clear to avoid duplicate native tooltips
                    if (!textEl) {
                        // leave as-is
                    } else {
                        link.removeAttribute('title');
                    }
                }
            } catch (e) {
                // Ignore tooltip errors
            }
        });

        // Footer logout icon tooltip (already has title)
        const logoutBtn = sidebar.querySelector('.logout-icon-btn');
        if (logoutBtn) {
            if (isCollapsed) {
                if (!logoutBtn._tooltipInstance) {
                    logoutBtn.setAttribute('data-bs-toggle', 'tooltip');
                    logoutBtn.setAttribute('data-bs-placement', 'right');
                    logoutBtn._tooltipInstance = new bootstrap.Tooltip(logoutBtn);
                }
            } else {
                if (logoutBtn._tooltipInstance) {
                    logoutBtn._tooltipInstance.dispose();
                    logoutBtn._tooltipInstance = null;
                }
                logoutBtn.removeAttribute('data-bs-toggle');
                logoutBtn.removeAttribute('data-bs-placement');
            }
        }
    }

    function applySidebarState(collapsed) {
        if (!sidebar) return;
        sidebar.classList.toggle('collapsed', collapsed);
        if (contentWrapper) contentWrapper.style.marginLeft = collapsed ? getComputedStyle(document.documentElement).getPropertyValue('--sidebar-collapsed-width') : getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width');
        setupSidebarTooltips(collapsed);
    }

    // Initialize sidebar manager
    SidebarManager.init();
    
    // Check if we should reset sidebar (login/error pages)
    if (SidebarManager.shouldResetSidebar()) {
        SidebarManager.resetSidebarState();
    }

    // Sidebar toggle functionality
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            const willCollapse = !sidebar.classList.contains('collapsed');
            applySidebarState(willCollapse);
            // Save state using the enhanced session manager
            SidebarManager.saveSidebarState(willCollapse);
        });
    }

    // Restore sidebar state using the enhanced session manager
    const shouldCollapse = SidebarManager.loadSidebarState();
    applySidebarState(shouldCollapse);

    // Enhanced mobile menu functionality
    if (mobileMenuToggle && sidebar) {
        mobileMenuToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            sidebar.classList.add('mobile-show');
            if (mobileOverlay) {
                mobileOverlay.classList.add('active');
            }
            // Prevent body scroll when mobile menu is open
            document.body.style.overflow = 'hidden';
        });
    }

    if (mobileOverlay && sidebar) {
        mobileOverlay.addEventListener('click', function() {
            closeMobileMenu();
        });
    }
    
    // Function to close mobile menu
    function closeMobileMenu() {
        if (sidebar) {
            sidebar.classList.remove('mobile-show');
        }
        if (mobileOverlay) {
            mobileOverlay.classList.remove('active');
        }
        // Restore body scroll
        document.body.style.overflow = '';
    }
    
    // Close mobile menu when clicking on nav links
    const navLinks = document.querySelectorAll('.sidebar .nav-link');
    navLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            // Close mobile menu after a short delay to allow navigation
            setTimeout(closeMobileMenu, 150);
        });
    });
    
    // Close mobile menu on window resize if screen becomes large
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 992) {
            closeMobileMenu();
        }
    });
    
    // Close mobile menu on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar && sidebar.classList.contains('mobile-show')) {
            closeMobileMenu();
        }
    });

    // Dark/Light mode toggle
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    const body = document.body;

    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', function() {
            body.classList.toggle('dark-mode');
            
            // Save theme preference in localStorage
            if (body.classList.contains('dark-mode')) {
                localStorage.setItem('dark-mode', 'true');
                darkModeToggle.innerHTML = '<i class="fas fa-sun"></i>';
            } else {
                localStorage.setItem('dark-mode', 'false');
                darkModeToggle.innerHTML = '<i class="fas fa-moon"></i>';
            }
        });
    }

    // Restore theme preference from localStorage
    if (localStorage.getItem('dark-mode') === 'true') {
        body.classList.add('dark-mode');
        if (darkModeToggle) {
            darkModeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        }
    }

    // Enhanced Collapsible Submenu System
    const CollapsibleSubmenu = {
        // Initialize all collapsible submenus
        init() {
            this.initializeSubmenus();
            this.setupSidebarCollapseHandler();
            this.setupOutsideClickHandler();
        },
        
        // Initialize submenu functionality
        initializeSubmenus() {
            const submenus = document.querySelectorAll('.sidebar .nav-item.dropdown');
            console.log('Initializing collapsible submenus:', submenus.length);
            
            submenus.forEach((submenu, index) => {
                this.initializeSubmenu(submenu, index);
            });
        },
        
        // Initialize individual submenu
        initializeSubmenu(submenu, index) {
            const toggle = submenu.querySelector('.nav-link.dropdown-toggle');
            const menu = submenu.querySelector('.dropdown-menu');
            
            if (!toggle || !menu) {
                console.warn(`Submenu ${index} missing toggle or menu`);
                return;
            }
            
            // Add submenu class for styling
            submenu.classList.add('collapsible-submenu');
            menu.classList.add('submenu-content');
            
            // Set initial state
            this.setSubmenuState(submenu, false);
            
            // Remove any existing event listeners to prevent duplicates
            toggle.removeEventListener('click', this.handleToggleClick);
            
            // Add click handler with proper binding
            this.handleToggleClick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                
                // Prevent rapid clicking
                if (submenu._isToggling) {
                    console.log('Toggle in progress, ignoring click');
                    return;
                }
                
                submenu._isToggling = true;
                this.toggleSubmenu(submenu);
                
                // Reset toggle flag after animation
                setTimeout(() => {
                    submenu._isToggling = false;
                }, 350);
            };
            
            toggle.addEventListener('click', this.handleToggleClick);
            
            // Add hover handler for collapsed sidebar
            this.setupHoverHandler(submenu);
            
            console.log(`Submenu ${index} initialized:`, toggle.textContent.trim());
        },
        
        // Toggle submenu open/closed
        toggleSubmenu(submenu) {
            const isOpen = submenu.classList.contains('show');
            const sidebar = document.getElementById('sidebar');
            const isCollapsed = sidebar && sidebar.classList.contains('collapsed');
            
            console.log('Toggle submenu:', {
                isOpen,
                isCollapsed,
                submenuText: submenu.querySelector('.nav-text')?.textContent
            });
            
            // Close other submenus first
            this.closeAllSubmenus();
            
            if (!isOpen) {
                this.openSubmenu(submenu);
            } else {
                this.closeSubmenu(submenu);
            }
        },
        
        // Open submenu with animation
        openSubmenu(submenu) {
            const menu = submenu.querySelector('.submenu-content');
            const sidebar = document.getElementById('sidebar');
            const isCollapsed = sidebar && sidebar.classList.contains('collapsed');
            
            submenu.classList.add('show');
            menu.classList.add('show');
            
            if (isCollapsed) {
                // For collapsed sidebar, show as floating popup
                this.showFloatingSubmenu(submenu);
            } else {
                // For expanded sidebar, show as inline submenu
                this.showInlineSubmenu(submenu);
            }
            
            console.log('Submenu opened:', submenu.querySelector('.nav-text').textContent);
        },
        
        // Close submenu with animation
        closeSubmenu(submenu) {
            const menu = submenu.querySelector('.submenu-content');
            
            submenu.classList.remove('show');
            menu.classList.remove('show');
            
            // Reset styles
            this.resetSubmenuStyles(submenu);
            
            console.log('Submenu closed:', submenu.querySelector('.nav-text').textContent);
        },
        
        // Show inline submenu (expanded sidebar)
        showInlineSubmenu(submenu) {
            const menu = submenu.querySelector('.submenu-content');
            
            // Set inline styles for smooth animation
            menu.style.display = 'block';
            menu.style.position = 'static';
            menu.style.top = 'auto';
            menu.style.left = 'auto';
            menu.style.right = 'auto';
            menu.style.width = '100%';
            menu.style.maxHeight = '0';
            menu.style.overflow = 'hidden';
            menu.style.opacity = '0';
            menu.style.transform = 'translateY(-10px)';
            menu.style.transition = 'all 0.3s ease';
            menu.style.background = 'rgba(0, 0, 0, 0.02)';
            menu.style.borderLeft = '3px solid #005d99';
            menu.style.borderRadius = '0';
            menu.style.boxShadow = 'none';
            menu.style.padding = '0';
            menu.style.margin = '0';
            menu.style.zIndex = 'auto';
            
            // Trigger animation
            requestAnimationFrame(() => {
                menu.style.maxHeight = menu.scrollHeight + 'px';
                menu.style.opacity = '1';
                menu.style.transform = 'translateY(0)';
                menu.style.padding = '0.5rem 0';
            });
        },
        
        // Show floating submenu (collapsed sidebar)
        showFloatingSubmenu(submenu) {
            const menu = submenu.querySelector('.submenu-content');
            const toggle = submenu.querySelector('.nav-link.dropdown-toggle');
            
            // Calculate position
            const rect = toggle.getBoundingClientRect();
            const sidebar = document.getElementById('sidebar');
            const sidebarRect = sidebar.getBoundingClientRect();
            
            console.log('Showing floating submenu:', {
                toggleRect: rect,
                sidebarRect: sidebarRect,
                calculatedLeft: sidebarRect.right + 10
            });
            
            // Set floating styles
            menu.style.display = 'block';
            menu.style.position = 'fixed';
            menu.style.top = Math.max(10, rect.top) + 'px'; // Ensure it's not above viewport
            menu.style.left = (sidebarRect.right + 10) + 'px';
            menu.style.right = 'auto';
            menu.style.width = '220px'; // Slightly wider for better visibility
            menu.style.maxHeight = 'none';
            menu.style.overflow = 'visible';
            menu.style.opacity = '1';
            menu.style.transform = 'translateY(0)';
            menu.style.transition = 'all 0.2s ease';
            menu.style.background = 'white';
            menu.style.border = '2px solid #005d99';
            menu.style.borderRadius = '8px';
            menu.style.boxShadow = '0 8px 32px rgba(0, 0, 0, 0.2)';
            menu.style.padding = '0.75rem 0';
            menu.style.margin = '0';
            menu.style.zIndex = '9999';
            menu.style.visibility = 'visible';
            menu.style.pointerEvents = 'auto';
            
            // Ensure it's visible
            menu.classList.add('show');
            submenu.classList.add('show');
            
            console.log('Floating submenu styles applied');
        },
        
        // Reset submenu styles
        resetSubmenuStyles(submenu) {
            const menu = submenu.querySelector('.submenu-content');
            
            menu.style.maxHeight = '0';
            menu.style.opacity = '0';
            menu.style.transform = 'translateY(-10px)';
            
            // Clean up after animation
            setTimeout(() => {
                if (!submenu.classList.contains('show')) {
                    menu.style.display = 'none';
                    menu.style.position = '';
                    menu.style.top = '';
                    menu.style.left = '';
                    menu.style.right = '';
                    menu.style.width = '';
                    menu.style.maxHeight = '';
                    menu.style.overflow = '';
                    menu.style.background = '';
                    menu.style.border = '';
                    menu.style.borderRadius = '';
                    menu.style.boxShadow = '';
                    menu.style.padding = '';
                    menu.style.zIndex = '';
                }
            }, 300);
        },
        
        // Set submenu state
        setSubmenuState(submenu, isOpen) {
            if (isOpen) {
                submenu.classList.add('show');
            } else {
                submenu.classList.remove('show');
            }
        },
        
        // Close all submenus
        closeAllSubmenus() {
            document.querySelectorAll('.sidebar .nav-item.dropdown.show').forEach(submenu => {
                this.closeSubmenu(submenu);
            });
        },
        
        // Setup hover handler for collapsed sidebar
        setupHoverHandler(submenu) {
            const toggle = submenu.querySelector('.nav-link.dropdown-toggle');
            const menu = submenu.querySelector('.submenu-content');
            
            // Hover to show in collapsed mode
            toggle.addEventListener('mouseenter', () => {
                const sidebar = document.getElementById('sidebar');
                const isCollapsed = sidebar && sidebar.classList.contains('collapsed');
                
                if (isCollapsed && !submenu.classList.contains('show')) {
                    console.log('Hover showing submenu in collapsed mode');
                    this.openSubmenu(submenu);
                }
            });
            
            // Leave to hide in collapsed mode (with delay to prevent flickering)
            let hideTimeout;
            submenu.addEventListener('mouseleave', () => {
                const sidebar = document.getElementById('sidebar');
                const isCollapsed = sidebar && sidebar.classList.contains('collapsed');
                
                if (isCollapsed && submenu.classList.contains('show')) {
                    hideTimeout = setTimeout(() => {
                        console.log('Hover hiding submenu in collapsed mode');
                        this.closeSubmenu(submenu);
                    }, 300); // Small delay to prevent flickering
                }
            });
            
            // Cancel hide timeout if mouse re-enters
            submenu.addEventListener('mouseenter', () => {
                if (hideTimeout) {
                    clearTimeout(hideTimeout);
                    hideTimeout = null;
                }
            });
        },
        
        // Setup sidebar collapse handler
        setupSidebarCollapseHandler() {
            const sidebar = document.getElementById('sidebar');
            if (!sidebar) {
                console.warn('Sidebar element not found, skipping collapse handler setup');
                return;
            }
            
            try {
                // Watch for sidebar collapse/expand
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                            const isCollapsed = sidebar.classList.contains('collapsed');
                            
                            if (isCollapsed) {
                                // Close all submenus when sidebar collapses
                                this.closeAllSubmenus();
                            }
                        }
                    });
                });
                
                observer.observe(sidebar, { attributes: true });
                console.log('Sidebar collapse handler initialized successfully');
            } catch (error) {
                console.error('Error setting up sidebar collapse handler:', error);
            }
        },
        
        // Setup outside click handler
        setupOutsideClickHandler() {
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.sidebar .nav-item.dropdown')) {
                    this.closeAllSubmenus();
                }
            });
        }
    };

    // Global function to safely initialize dropdowns (now using CollapsibleSubmenu)
    window.safeInitializeDropdowns = function() {
        CollapsibleSubmenu.init();
    };

    // Global function to safely initialize tooltips and popovers
    window.safeInitializeTooltipsAndPopovers = function() {
        // Initialize tooltips safely
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.forEach(function (tooltipTriggerEl) {
            // Check if tooltip is already initialized
            const existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
            if (existingTooltip) {
                console.log('Disposing existing tooltip instance');
                existingTooltip.dispose();
            }
            
            try {
                new bootstrap.Tooltip(tooltipTriggerEl);
            } catch (error) {
                console.warn('Error initializing tooltip:', error);
            }
        });

        // Initialize popovers safely
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.forEach(function (popoverTriggerEl) {
            // Check if popover is already initialized
            const existingPopover = bootstrap.Popover.getInstance(popoverTriggerEl);
            if (existingPopover) {
                console.log('Disposing existing popover instance');
                existingPopover.dispose();
            }
            
            try {
                new bootstrap.Popover(popoverTriggerEl);
            } catch (error) {
                console.warn('Error initializing popover:', error);
            }
        });
    };

    // Global function to dispose all Bootstrap instances
    window.disposeAllBootstrapInstances = function() {
        // Dispose all tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.forEach(function (tooltipTriggerEl) {
            const existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
            if (existingTooltip) {
                existingTooltip.dispose();
            }
        });

        // Dispose all popovers
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.forEach(function (popoverTriggerEl) {
            const existingPopover = bootstrap.Popover.getInstance(popoverTriggerEl);
            if (existingPopover) {
                existingPopover.dispose();
            }
        });

        // Dispose all dropdowns
        const sidebarDropdowns = document.querySelectorAll('.sidebar .nav-item.dropdown');
        sidebarDropdowns.forEach(function(dropdown) {
            const toggle = dropdown.querySelector('.nav-link.dropdown-toggle');
            if (toggle) {
                const existingInstance = bootstrap.Dropdown.getInstance(toggle);
                if (existingInstance) {
                    existingInstance.dispose();
                }
            }
        });
    };

    // Sidebar dropdown functionality
    const sidebarDropdowns = document.querySelectorAll('.sidebar .nav-item.dropdown');
    // Use the previously defined navMenu if available; avoid redeclaration errors
    const sidebarNavMenu = document.querySelector('.sidebar .nav-menu');
    
    console.log('Found sidebar dropdowns:', sidebarDropdowns.length);
    console.log('Bootstrap available:', typeof bootstrap !== 'undefined');
    console.log('jQuery available:', typeof $ !== 'undefined');
    
    // Dispose all existing Bootstrap instances first to prevent conflicts
    window.disposeAllBootstrapInstances();

    // Use the safe initialization function
    window.safeInitializeDropdowns();

    // Use the safe initialization function for tooltips and popovers
    window.safeInitializeTooltipsAndPopovers();
    
    // Fallback initialization after a short delay to ensure DOM is fully ready
    setTimeout(function() {
        console.log('Running fallback dropdown initialization...');
        window.safeInitializeDropdowns();
    }, 500);

    // Flash messages auto-dismiss (removing auto-dismiss to prevent quick disappearance)
    // We're commenting this out to prevent notifications from disappearing too quickly
    /*
    const alerts = document.querySelectorAll('.alert-dismissible.auto-dismiss');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const dismiss = new bootstrap.Alert(alert);
            dismiss.close();
        }, 5000);
    });
    */

    // Handle form submission with confirmation
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!confirm(this.getAttribute('data-confirm'))) {
                e.preventDefault();
                return false;
            }
        });
    });

    // Notification system removed - replaced with SMTP email notifications for admins

    // Page loader - Enhanced with better error handling
    function hidePageLoader() {
        const pageLoader = document.getElementById('page-loader');
        if (pageLoader) {
            pageLoader.classList.add('fade-out');
            setTimeout(function() {
                pageLoader.style.display = 'none';
                pageLoader.style.visibility = 'hidden';
            }, 300);
        }
    }
    
    // Multiple fallback methods to ensure loader is hidden
    function initPageLoader() {
        // Method 1: Hide immediately if DOM is ready
        if (document.readyState === 'complete') {
            hidePageLoader();
            return;
        }
        
        // Method 2: Hide when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', hidePageLoader);
        } else {
            // DOM is already ready
            setTimeout(hidePageLoader, 100);
        }
        
        // Method 3: Fallback after 1 second
        setTimeout(hidePageLoader, 1000);
        
        // Method 4: Emergency fallback after 3 seconds
        setTimeout(hidePageLoader, 3000);
        
        // Method 5: Hide on window load
        window.addEventListener('load', hidePageLoader);
    }
    
    // Initialize page loader hiding
    initPageLoader();
    
    // Sidebar scroll indicators
    function updateScrollIndicators() {
        if (!sidebarNavContainer) return;
        
        const isScrollable = sidebarNavContainer.scrollHeight > sidebarNavContainer.clientHeight;
        const isAtTop = sidebarNavContainer.scrollTop === 0;
        const isAtBottom = sidebarNavContainer.scrollTop + sidebarNavContainer.clientHeight >= sidebarNavContainer.scrollHeight - 1;
        
        sidebarNavContainer.classList.toggle('scrollable-top', isScrollable && !isAtTop);
        sidebarNavContainer.classList.toggle('scrollable-bottom', isScrollable && !isAtBottom);
    }
    
    // Initialize scroll indicators
    if (sidebarNavContainer) {
        updateScrollIndicators();
        sidebarNavContainer.addEventListener('scroll', updateScrollIndicators);
        
        // Update on window resize
        window.addEventListener('resize', updateScrollIndicators);
    }
    
    // Load leave balance for employees
    function loadLeaveBalance() {
        const userRole = document.body.getAttribute('data-user-role');
        if (userRole !== 'employee') return;
        
        const balanceContent = document.getElementById('leave-balance-content');
        if (!balanceContent) return;
        
        fetch('/leave/my-leave-balance')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success' && data.balances) {
                    renderLeaveBalance(data.balances);
                } else {
                    showBalanceError(data.message || 'Failed to load leave balance');
                }
            })
            .catch(error => {
                console.error('Error loading leave balance:', error);
                showBalanceError('Error loading leave balance');
            });
    }
    
    function renderLeaveBalance(balances) {
        const balanceContent = document.getElementById('leave-balance-content');
        if (!balanceContent) return;
        
        if (balances.length === 0) {
            balanceContent.innerHTML = '<div class="text-center text-muted">No leave balance data available</div>';
            return;
        }
        
        let html = '';
        balances.forEach(balance => {
            const percentage = balance.total_days > 0 ? (balance.remaining_days / balance.total_days) * 100 : 0;
            const progressClass = percentage > 50 ? 'high' : percentage > 25 ? 'medium' : 'low';
            
            html += `
                <div class="balance-item">
                    <div class="balance-type">${balance.leave_type}</div>
                    <div class="balance-days">
                        <span class="balance-remaining">${balance.remaining_days}</span>
                        <span class="balance-total">/ ${balance.total_days}</span>
                    </div>
                </div>
                <div class="balance-progress">
                    <div class="balance-progress-bar ${progressClass}" style="width: ${Math.max(0, percentage)}%"></div>
                </div>
            `;
        });
        
        balanceContent.innerHTML = html;
    }
    
    function showBalanceError(message) {
        const balanceContent = document.getElementById('leave-balance-content');
        if (balanceContent) {
            balanceContent.innerHTML = `<div class="text-center text-danger">${message}</div>`;
        }
    }
    
    // Load leave balance when page loads
    loadLeaveBalance();
    
    // Refresh leave balance every 5 minutes for employees
    if (document.body.getAttribute('data-user-role') === 'employee') {
        setInterval(loadLeaveBalance, 60000); // 1 minute
    }
    
    // Global function to reset sidebar state (called on logout/timeout)
    window.resetSidebarState = function() {
        SidebarManager.resetSidebarState();
    };
    
    // Enhanced Bootstrap/Metronic compatibility
    // Handle both custom sidebar and Bootstrap sidebar systems
    const bootstrapSidebarToggle = document.getElementById('sidebarToggle');
    if (bootstrapSidebarToggle) {
        bootstrapSidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            // Toggle Bootstrap sidebar
            document.body.classList.toggle('sb-sidenav-toggled');
            
            // Also sync with our custom sidebar if it exists
            if (sidebar) {
                const isBootstrapCollapsed = document.body.classList.contains('sb-sidenav-toggled');
                applySidebarState(isBootstrapCollapsed);
                SidebarManager.saveSidebarState(isBootstrapCollapsed);
            }
        });
    }
    
    // Sync Bootstrap sidebar state on page load
    if (bootstrapSidebarToggle && sidebar) {
        const isBootstrapCollapsed = document.body.classList.contains('sb-sidenav-toggled');
        if (isBootstrapCollapsed !== shouldCollapse) {
            // Sync states
            if (shouldCollapse) {
                document.body.classList.add('sb-sidenav-toggled');
            } else {
                document.body.classList.remove('sb-sidenav-toggled');
            }
        }
    }
    
    // Handle page navigation and state persistence
    // Save state before page unload
    window.addEventListener('beforeunload', function() {
        if (sidebar) {
            const isCollapsed = sidebar.classList.contains('collapsed');
            SidebarManager.saveSidebarState(isCollapsed);
        }
    });
    
    // Handle browser back/forward navigation
    window.addEventListener('pageshow', function(event) {
        // Restore state after page navigation
        if (event.persisted) {
            const shouldCollapse = SidebarManager.loadSidebarState();
            applySidebarState(shouldCollapse);
            
            // Sync with Bootstrap sidebar if present
            if (bootstrapSidebarToggle) {
                if (shouldCollapse) {
                    document.body.classList.add('sb-sidenav-toggled');
                } else {
                    document.body.classList.remove('sb-sidenav-toggled');
                }
            }
        }
    });
    
    // Periodic session validity check (every 5 minutes)
    setInterval(function() {
        if (!SidebarManager.checkSessionValidity()) {
            console.log('Session expired, sidebar state reset');
        }
    }, 5 * 60 * 1000);
    
    // Debug function to test dropdown functionality
    window.debugDropdowns = function() {
        const dropdowns = document.querySelectorAll('.sidebar .nav-item.dropdown');
        console.log('=== Dropdown Debug Info ===');
        console.log('Total dropdowns found:', dropdowns.length);
        
        dropdowns.forEach((dropdown, index) => {
            const toggle = dropdown.querySelector('.nav-link.dropdown-toggle');
            const menu = dropdown.querySelector('.dropdown-menu');
            const isVisible = menu && menu.style.display !== 'none' && menu.classList.contains('show');
            
            console.log(`Dropdown ${index}:`, {
                text: toggle ? toggle.textContent.trim() : 'No text',
                hasToggle: !!toggle,
                hasMenu: !!menu,
                isVisible: isVisible,
                classes: dropdown.className,
                menuClasses: menu ? menu.className : 'No menu'
            });
        });
    };
    
    // Force dropdown to show (for testing)
    window.forceShowDropdown = function() {
        const dropdown = document.querySelector('.sidebar .nav-item.dropdown');
        const menu = dropdown.querySelector('.dropdown-menu');
        
        if (dropdown && menu) {
            dropdown.classList.add('show');
            menu.classList.add('show');
            menu.style.setProperty('display', 'block', 'important');
            menu.style.setProperty('opacity', '1', 'important');
            menu.style.setProperty('visibility', 'visible', 'important');
            menu.style.setProperty('transform', 'translateY(0)', 'important');
            menu.style.setProperty('pointer-events', 'auto', 'important');
            menu.style.setProperty('z-index', '9999', 'important');
            menu.style.setProperty('position', 'absolute', 'important');
            menu.style.setProperty('top', '100%', 'important');
            menu.style.setProperty('left', '0', 'important');
            menu.style.setProperty('right', '0', 'important');
            menu.style.setProperty('background-color', 'white', 'important');
            menu.style.setProperty('border', '2px solid #007bff', 'important');
            menu.style.setProperty('border-radius', '8px', 'important');
            menu.style.setProperty('box-shadow', '0 4px 20px rgba(0,0,0,0.3)', 'important');
            menu.style.setProperty('padding', '10px 0', 'important');
            menu.style.setProperty('min-width', '200px', 'important');
            
            console.log('Dropdown forced to show with aggressive styling');
            console.log('Menu element:', menu);
            console.log('Menu computed styles:', window.getComputedStyle(menu));
        }
    };
    
    // Force dropdown to hide (for testing)
    window.forceHideDropdown = function() {
        const dropdown = document.querySelector('.sidebar .nav-item.dropdown');
        const menu = dropdown.querySelector('.dropdown-menu');
        
        if (dropdown && menu) {
            dropdown.classList.remove('show');
            menu.classList.remove('show');
            menu.style.setProperty('display', 'none', 'important');
            console.log('Dropdown forced to hide');
        }
    };
    
    // Test dropdown toggle functionality
    window.testDropdownToggle = function() {
        const dropdown = document.querySelector('.sidebar .nav-item.dropdown');
        const menu = dropdown.querySelector('.dropdown-menu');
        const toggle = dropdown.querySelector('.nav-link.dropdown-toggle');
        
        if (!dropdown || !menu || !toggle) {
            console.error('❌ Dropdown elements not found!');
            return;
        }
        
        const isOpen = dropdown.classList.contains('show') && menu.classList.contains('show');
        console.log('=== Dropdown Toggle Test ===');
        console.log('Current state:', isOpen ? 'OPEN' : 'CLOSED');
        
        if (isOpen) {
            console.log('🔄 Closing dropdown...');
            dropdown.classList.remove('show');
            menu.classList.remove('show');
            menu.style.setProperty('display', 'none', 'important');
            menu.style.setProperty('opacity', '0', 'important');
            menu.style.setProperty('visibility', 'hidden', 'important');
            menu.style.setProperty('transform', 'translateY(-10px)', 'important');
            menu.style.setProperty('pointer-events', 'none', 'important');
            console.log('✅ Dropdown closed');
        } else {
            console.log('🔄 Opening dropdown...');
            dropdown.classList.add('show');
            menu.classList.add('show');
            menu.style.setProperty('display', 'block', 'important');
            menu.style.setProperty('opacity', '1', 'important');
            menu.style.setProperty('visibility', 'visible', 'important');
            menu.style.setProperty('transform', 'translateY(0)', 'important');
            menu.style.setProperty('pointer-events', 'auto', 'important');
            menu.style.setProperty('z-index', '9999', 'important');
            menu.style.setProperty('position', 'absolute', 'important');
            menu.style.setProperty('top', '100%', 'important');
            menu.style.setProperty('left', '0', 'important');
            menu.style.setProperty('right', '0', 'important');
            menu.style.setProperty('background-color', 'white', 'important');
            menu.style.setProperty('border', '2px solid #007bff', 'important');
            menu.style.setProperty('border-radius', '8px', 'important');
            menu.style.setProperty('box-shadow', '0 4px 20px rgba(0,0,0,0.3)', 'important');
            menu.style.setProperty('padding', '10px 0', 'important');
            menu.style.setProperty('min-width', '200px', 'important');
            console.log('✅ Dropdown opened');
        }
        
        // Check final state
        const finalState = dropdown.classList.contains('show') && menu.classList.contains('show');
        console.log('Final state:', finalState ? 'OPEN' : 'CLOSED');
        console.log('Menu display style:', menu.style.display);
        console.log('Menu visibility style:', menu.style.visibility);
        console.log('Menu opacity style:', menu.style.opacity);
        
        return finalState;
    };
    
    // Auto-test dropdown on page load
    window.autoTestDropdown = function() {
        console.log('🧪 Starting automatic dropdown test...');
        
        // Test 1: Open dropdown
        console.log('\n--- Test 1: Opening dropdown ---');
        const opened = window.testDropdownToggle();
        
        // Wait 2 seconds, then close
        setTimeout(() => {
            console.log('\n--- Test 2: Closing dropdown ---');
            const closed = window.testDropdownToggle();
            
            // Wait 2 seconds, then open again
            setTimeout(() => {
                console.log('\n--- Test 3: Opening dropdown again ---');
                const openedAgain = window.testDropdownToggle();
                
                console.log('\n🎉 Auto-test completed!');
                console.log('Final result:', openedAgain ? 'OPEN' : 'CLOSED');
            }, 2000);
        }, 2000);
    };
    
    // Auto-run debug after page load
    setTimeout(function() {
        window.debugDropdowns();
    }, 1000);
    
    // Test function for collapsible submenu
    window.testCollapsibleSubmenu = function() {
        console.log('🧪 Testing Collapsible Submenu System...');
        
        const submenu = document.querySelector('.sidebar .nav-item.dropdown.collapsible-submenu');
        if (!submenu) {
            console.error('❌ No collapsible submenu found!');
            return;
        }
        
        const toggle = submenu.querySelector('.nav-link.dropdown-toggle');
        const menu = submenu.querySelector('.submenu-content');
        const sidebar = document.getElementById('sidebar');
        const isCollapsed = sidebar && sidebar.classList.contains('collapsed');
        
        console.log('Submenu elements found:', {
            submenu: !!submenu,
            toggle: !!toggle,
            menu: !!menu,
            isOpen: submenu.classList.contains('show'),
            isCollapsed: isCollapsed
        });
        
        // Test toggle
        console.log('🔄 Testing toggle functionality...');
        CollapsibleSubmenu.toggleSubmenu(submenu);
        
        setTimeout(() => {
            console.log('🔄 Testing toggle again...');
            CollapsibleSubmenu.toggleSubmenu(submenu);
        }, 2000);
    };
    
    // Test function specifically for collapsed sidebar
    window.testCollapsedSidebar = function() {
        console.log('🧪 Testing Collapsed Sidebar Functionality...');
        
        const sidebar = document.getElementById('sidebar');
        const submenu = document.querySelector('.sidebar .nav-item.dropdown.collapsible-submenu');
        
        if (!sidebar || !submenu) {
            console.error('❌ Sidebar or submenu not found!');
            return;
        }
        
        // Collapse sidebar
        sidebar.classList.add('collapsed');
        console.log('✅ Sidebar collapsed');
        
        // Test submenu in collapsed mode
        setTimeout(() => {
            console.log('🔄 Testing submenu in collapsed mode...');
            CollapsibleSubmenu.toggleSubmenu(submenu);
            
            setTimeout(() => {
                console.log('🔄 Testing submenu close in collapsed mode...');
                CollapsibleSubmenu.toggleSubmenu(submenu);
                
                // Restore sidebar
                setTimeout(() => {
                    sidebar.classList.remove('collapsed');
                    console.log('✅ Sidebar restored');
                }, 2000);
            }, 2000);
        }, 1000);
    };
    
    // Auto-test after initialization
    setTimeout(() => {
        console.log('🚀 Collapsible Submenu System initialized');
        console.log('Run testCollapsibleSubmenu() to test the functionality');
    }, 1500);
});
