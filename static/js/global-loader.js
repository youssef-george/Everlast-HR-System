// Global Loading Indicator for Everlast ERP
// This script provides a universal loading indicator for all pages

(function() {
    'use strict';
    
    // Create the global loader HTML
    function createLoaderHTML() {
        return `
            <div id="global-loader" class="global-loader" style="display: none;">
                <div class="loader-overlay">
                    <div class="loader-content">
                        <div class="loader-spinner">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                        </div>
                        <div class="loader-text">
                            <h5 class="text-primary mb-2">Loading...</h5>
                            <p class="text-muted">Please wait while we process your request</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    // Add loader styles
    function addLoaderStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .global-loader {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: 9999;
                background: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(2px);
            }
            
            .loader-overlay {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 100%;
                height: 100%;
            }
            
            .loader-content {
                text-align: center;
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                max-width: 300px;
                width: 90%;
            }
            
            .loader-spinner {
                margin-bottom: 1rem;
            }
            
            .spinner-border {
                width: 3rem;
                height: 3rem;
                border-width: 0.3em;
            }
            
            .loader-text h5 {
                font-weight: 600;
                margin-bottom: 0.5rem;
            }
            
            .loader-text p {
                font-size: 0.9rem;
                margin: 0;
            }
            
            /* Animation for smooth show/hide */
            .global-loader {
                opacity: 0;
                transition: opacity 0.3s ease-in-out;
            }
            
            .global-loader.show {
                opacity: 1;
            }
        `;
        document.head.appendChild(style);
    }
    
    // Show loader
    function showLoader() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.style.display = 'block';
            setTimeout(() => {
                loader.classList.add('show');
            }, 10);
        }
    }
    
    // Hide loader
    function hideLoader() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.classList.remove('show');
            setTimeout(() => {
                loader.style.display = 'none';
            }, 300);
        }
    }
    
    // Initialize loader
    function initLoader() {
        // Add styles
        addLoaderStyles();
        
        // Add loader HTML to body
        document.body.insertAdjacentHTML('beforeend', createLoaderHTML());
        
        // Make functions globally available
        window.showGlobalLoader = showLoader;
        window.hideGlobalLoader = hideLoader;
    }
    
    // Auto-hide loader when page is fully loaded
    function autoHideLoader() {
        if (document.readyState === 'complete') {
            hideLoader();
        } else {
            window.addEventListener('load', hideLoader);
        }
    }
    
    // Show loader on form submissions
    function handleFormSubmissions() {
        document.addEventListener('submit', function(e) {
            // Don't show loader for forms with data-no-loader attribute
            if (e.target.hasAttribute('data-no-loader')) {
                return;
            }
            showLoader();
        });
    }
    
    // Show loader on link clicks (for navigation)
    function handleLinkClicks() {
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            if (link && link.href && !link.hasAttribute('data-no-loader')) {
                // Only show loader for internal links
                if (link.hostname === window.location.hostname || link.href.startsWith('/')) {
                    showLoader();
                }
            }
        });
    }
    
    // Show loader on AJAX requests
    function handleAjaxRequests() {
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            showLoader();
            return originalFetch.apply(this, args)
                .finally(() => {
                    // Small delay to prevent flickering
                    setTimeout(hideLoader, 500);
                });
        };
        
        // Handle XMLHttpRequest
        const originalXHR = window.XMLHttpRequest;
        window.XMLHttpRequest = function() {
            const xhr = new originalXHR();
            const originalOpen = xhr.open;
            const originalSend = xhr.send;
            
            xhr.open = function(...args) {
                this._method = args[0];
                this._url = args[1];
                return originalOpen.apply(this, args);
            };
            
            xhr.send = function(...args) {
                // Only show loader for non-GET requests or specific endpoints
                if (this._method !== 'GET' || this._url.includes('/calendar/events')) {
                    showLoader();
                }
                
                const originalOnLoad = this.onload;
                const originalOnError = this.onerror;
                
                this.onload = function() {
                    if (originalOnLoad) originalOnLoad.apply(this, arguments);
                    setTimeout(hideLoader, 500);
                };
                
                this.onerror = function() {
                    if (originalOnError) originalOnError.apply(this, arguments);
                    setTimeout(hideLoader, 500);
                };
                
                return originalSend.apply(this, args);
            };
            
            return xhr;
        };
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initLoader();
            autoHideLoader();
            handleFormSubmissions();
            handleLinkClicks();
            handleAjaxRequests();
        });
    } else {
        initLoader();
        autoHideLoader();
        handleFormSubmissions();
        handleLinkClicks();
        handleAjaxRequests();
    }
    
    // Show loader immediately for slow page loads
    if (document.readyState === 'loading') {
        showLoader();
    }
    
})();