// Connection Monitor for Everlast ERP
// Monitors connection health and provides user feedback

class ConnectionMonitor {
    constructor() {
        this.isOnline = navigator.onLine;
        this.connectionCheckInterval = null;
        this.lastSuccessfulRequest = Date.now();
        this.connectionStatus = 'online';
        
        this.init();
    }
    
    init() {
        // Listen for online/offline events
        window.addEventListener('online', () => {
            this.handleConnectionChange('online');
        });
        
        window.addEventListener('offline', () => {
            this.handleConnectionChange('offline');
        });
        
        // Start periodic connection health checks
        this.startHealthChecks();
    }
    
    startHealthChecks() {
        // Check connection health every 1 minute
        this.connectionCheckInterval = setInterval(() => {
            this.checkConnectionHealth();
        }, 60000);
    }
    
    async checkConnectionHealth() {
        try {
            const response = await fetch('/notifications/unread_count', {
                method: 'GET',
                signal: AbortSignal.timeout(5000)
            });
            
            if (response.ok) {
                this.lastSuccessfulRequest = Date.now();
                if (this.connectionStatus !== 'online') {
                    this.handleConnectionChange('online');
                }
            } else {
                this.handleConnectionChange('degraded');
            }
        } catch (error) {
            console.warn('Connection health check failed:', error);
            this.handleConnectionChange('offline');
        }
    }
    
    handleConnectionChange(status) {
        const previousStatus = this.connectionStatus;
        this.connectionStatus = status;
        
        // Only show notifications for status changes
        if (previousStatus !== status) {
            this.showConnectionStatus(status);
        }
    }
    
    showConnectionStatus(status) {
        const statusMessages = {
            'online': 'Connection restored',
            'offline': 'Connection lost - check your internet connection',
            'degraded': 'Connection unstable - some features may not work properly'
        };
        
        const statusClasses = {
            'online': 'success',
            'offline': 'danger',
            'degraded': 'warning'
        };
        
        const message = statusMessages[status];
        const className = statusClasses[status];
        
        if (message) {
            this.showNotification(message, className);
        }
    }
    
    showNotification(message, type = 'info') {
        // Remove existing connection status notifications
        const existing = document.querySelector('.connection-status-notification');
        if (existing) {
            existing.remove();
        }
        
        // Create notification
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show connection-status-notification`;
        notification.style.position = 'fixed';
        notification.style.top = '20px';
        notification.style.left = '50%';
        notification.style.transform = 'translateX(-50%)';
        notification.style.zIndex = '9999';
        notification.style.minWidth = '300px';
        notification.style.textAlign = 'center';
        notification.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-triangle' : 'exclamation-circle'}"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds for online status, 10 seconds for others
        const autoRemoveDelay = type === 'success' ? 5000 : 10000;
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, autoRemoveDelay);
    }
    
    destroy() {
        if (this.connectionCheckInterval) {
            clearInterval(this.connectionCheckInterval);
        }
    }
}

// Initialize connection monitor when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.connectionMonitor = new ConnectionMonitor();
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (window.connectionMonitor) {
        window.connectionMonitor.destroy();
    }
});
