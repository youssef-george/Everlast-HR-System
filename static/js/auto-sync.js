// Auto-sync and auto-refresh functionality for attendance and calendar pages
class AutoSync {
    constructor(options = {}) {
        this.syncInterval = options.syncInterval || 60000; // 1 minute default
        this.refreshInterval = options.refreshInterval || 120000; // 2 minutes default
        this.enabled = options.enabled !== false;
        this.syncEndpoint = options.syncEndpoint || '/attendance/manual-sync';
        this.isRunning = false;
        this.syncInProgress = false;
        this.connectionFailures = 0;
        this.maxFailures = 3;
        this.backoffMultiplier = 2;
        this.baseDelay = 5000; // 5 seconds base delay
        
        this.init();
    }
    
    init() {
        if (!this.enabled) return;
        
        // Start auto-sync
        this.startAutoSync();
        
        // Start auto-refresh
        this.startAutoRefresh();
        
        // Sync status indicator removed as requested
        
        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pause();
            } else {
                this.resume();
            }
        });
    }
    
    startAutoSync() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.syncIntervalId = setInterval(() => {
            // Only sync if page is visible and not in a form
            if (!document.hidden && !document.querySelector('form:focus')) {
                this.performSync();
            }
        }, this.syncInterval);
        
        // Perform initial sync with a small delay to let page load
        setTimeout(() => {
            this.performSync();
        }, 2000);
    }
    
    startAutoRefresh() {
        this.refreshIntervalId = setInterval(() => {
            this.refreshPage();
        }, this.refreshInterval);
    }
    
    async performSync() {
        if (this.syncInProgress) return;
        
        this.syncInProgress = true;
        
        try {
            const response = await fetch(this.syncEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                // Add timeout and retry logic
                signal: AbortSignal.timeout(30000) // 30 second timeout for device connection
            });
            
            // Check response status first
            if (!response.ok) {
                if (response.status === 403) {
                    console.warn('Auto-sync access denied (403). This feature is admin-only.');
                    this.enabled = false; // Disable auto-sync for this session
                    return; // Don't throw error, just disable silently
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            // Reset connection failures on successful request
            this.connectionFailures = 0;
            
            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                if (text.includes('403 Forbidden')) {
                    console.warn('Auto-sync access denied. This feature is admin-only.');
                    this.enabled = false; // Disable auto-sync for this session
                    return; // Don't throw error, just disable silently
                }
                console.error('Expected JSON response but got:', contentType, text.substring(0, 200));
                throw new Error(`Server returned ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.status === 'success') {
                // Log success but don't show notification (UI handled elsewhere)
                console.log('Auto-sync completed successfully:', data.message);
                if (data.records_added && data.records_added > 0) {
                    console.log(`${data.records_added} new records added`);
                }
            } else if (data.status === 'info') {
                // Don't show info notifications for auto-sync (UI handled elsewhere)
                // Silently ignore info messages to avoid console spam
            } else {
                console.error('Auto-sync failed:', data.message);
                // Only show error notifications for auto-sync failures
                this.showNotification('Auto-sync failed: ' + data.message, 'danger');
            }
        } catch (error) {
            console.error('Sync error:', error);
            this.connectionFailures++;
            
            // Handle specific error types with exponential backoff
            if (error.name === 'AbortError') {
                this.handleConnectionError('Device connection timeout - this is normal during heavy usage');
            } else if (error.message.includes('Failed to fetch') || error.message.includes('ERR_CONNECTION_RESET')) {
                this.handleConnectionError('Connection lost - server may be restarting');
            } else if (error.message.includes('403') || error.message.includes('FORBIDDEN')) {
                // Don't show 403 errors to users - these are expected for non-admin users
                console.warn('Sync access denied - user may not have admin privileges');
                // Disable auto-sync for this session
                this.pause();
            } else if (error.message.includes('signal timed out')) {
                // Handle specific timeout error more gracefully
                this.handleConnectionError('Device connection timeout - attendance device may be busy');
            } else {
                this.showNotification('Sync error: ' + error.message, 'danger');
            }
        } finally {
            this.syncInProgress = false;
        }
    }
    
    handleConnectionError(message) {
        if (this.connectionFailures <= this.maxFailures) {
            // Use exponential backoff
            const delay = this.baseDelay * Math.pow(this.backoffMultiplier, this.connectionFailures - 1);
            console.warn(`${message}. Retrying in ${delay/1000} seconds... (attempt ${this.connectionFailures}/${this.maxFailures})`);
            
            // Only show notification for critical failures and only for timeout errors after multiple attempts
            if (this.connectionFailures === this.maxFailures && !message.includes('timeout')) {
                this.showNotification('Connection lost - sync paused', 'warning');
            }
            
            // Schedule retry
            setTimeout(() => {
                if (this.isRunning) {
                    this.performSync();
                }
            }, delay);
        } else {
            console.error('Max connection failures reached. Pausing sync...');
            // Don't show intrusive notifications for timeout errors - they're common
            if (message.includes('timeout')) {
                console.warn('Auto-sync paused due to repeated timeouts. This is normal during heavy device usage.');
            } else {
                this.showNotification('Connection lost - sync paused. Please refresh the page.', 'danger');
            }
            this.pause();
        }
    }
    
    refreshPage() {
        // Only refresh if page is visible and not in the middle of a form
        if (document.hidden || document.querySelector('form:focus')) return;
        
        // Reload the page to get fresh data
        window.location.reload();
    }
    
    // Sync status indicator removed as requested
    
    showNotification(message, type = 'info') {
        // For auto-sync, only show critical error notifications
        // Other sync status is handled by the manual sync UI
        if (type === 'danger' || type === 'warning') {
            // Remove any existing auto-sync notifications first
            const existingNotifications = document.querySelectorAll('.auto-sync-alert');
            existingNotifications.forEach(notif => notif.remove());
            
            // Create enhanced notification element only for errors/warnings
            const notification = document.createElement('div');
            notification.className = `alert alert-${type} alert-dismissible fade show auto-sync-alert`;
            notification.style.position = 'fixed';
            notification.style.top = '70px';
            notification.style.right = '20px';
            notification.style.zIndex = '1001';
            notification.style.minWidth = '350px';
            notification.style.borderRadius = '12px';
            notification.style.border = 'none';
            notification.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
            
            const iconClass = type === 'danger' ? 'fas fa-exclamation-triangle' : 'fas fa-info-circle';
            const title = type === 'danger' ? 'Auto-Sync Error' : 'Auto-Sync Notice';
            
            notification.innerHTML = `
                <div class="d-flex align-items-start">
                    <div class="flex-shrink-0">
                        <i class="${iconClass} fa-lg me-3"></i>
                    </div>
                    <div class="flex-grow-1">
                        <h6 class="alert-heading mb-1">${title}</h6>
                        <div>${message}</div>
                        <small class="text-muted mt-1 d-block">This is an automatic background process</small>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
            
            document.body.appendChild(notification);
            
            // Auto-remove after 10 seconds for errors, 6 seconds for warnings
            const timeout = type === 'danger' ? 10000 : 6000;
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, timeout);
        } else {
            // For info/success, just log to console
            console.log(`Auto-sync ${type}:`, message);
        }
    }
    
    getCSRFToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }
    
    pause() {
        if (this.syncIntervalId) {
            clearInterval(this.syncIntervalId);
        }
        if (this.refreshIntervalId) {
            clearInterval(this.refreshIntervalId);
        }
        this.isRunning = false;
    }
    
    resume() {
        if (!this.isRunning) {
            // Reset connection failures when resuming
            this.connectionFailures = 0;
            this.startAutoSync();
            this.startAutoRefresh();
        }
    }
    
    // Add connection health check
    async checkConnectionHealth() {
        try {
            const response = await fetch('/notifications/unread_count', {
                method: 'GET',
                signal: AbortSignal.timeout(5000) // 5 second timeout for health check
            });
            return response.ok;
        } catch (error) {
            console.warn('Connection health check failed:', error);
            return false;
        }
    }
    
    destroy() {
        this.pause();
        // Sync status indicator removed as requested
    }
}

// Global function for manual sync trigger
window.triggerSync = function() {
    if (window.autoSync) {
        window.autoSync.performSync();
    } else {
        // Fallback: direct API call
        fetch('/attendance/manual-sync', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
            }
        })
        .then(response => {
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                return response.text().then(text => {
                    throw new Error(`Server returned ${response.status}: ${response.statusText}. Response: ${text.substring(0, 200)}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                alert('Sync completed successfully!');
                window.location.reload();
            } else if (data.status === 'info') {
                alert(data.message);
            } else {
                alert('Sync failed: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Sync error:', error);
            
            // Handle specific error types
            if (error.name === 'AbortError' || error.message.includes('signal timed out')) {
                alert('Device connection timeout - the attendance device may be busy. Please try again in a moment.');
            } else if (error.message.includes('Failed to fetch') || error.message.includes('ERR_CONNECTION_RESET')) {
                alert('Connection lost - server may be restarting. Please try again in a moment.');
            } else {
                alert('Sync failed: ' + error.message);
            }
        });
    }
};


// Helper function to show sync notifications
function showSyncNotification(message, type = 'info') {
    // Remove existing notifications
    const existing = document.querySelector('.sync-notification');
    if (existing) {
        existing.remove();
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show sync-notification`;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
    notification.style.minWidth = '300px';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Auto-initialize on pages that need it
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on a page that needs auto-sync
    const currentPath = window.location.pathname;
    const syncPages = ['/attendance/', '/calendar/', '/calendar/attendance-report', '/dashboard/director'];
    
    // Check if user is admin (only admins should have manual sync access)
    const userRole = document.querySelector('body').getAttribute('data-user-role') || 
                    document.querySelector('[data-user-role]')?.getAttribute('data-user-role');
    
    // Only enable auto-sync for admin users (manual sync is admin-only)
    const isAdmin = userRole === 'admin';
    
    // Auto-sync disabled by user request
    console.log('Auto-sync disabled by user request');
    
    // if (syncPages.some(page => currentPath.startsWith(page)) && isAdmin) {
    //     // Initialize auto-sync for admin users only
    //     window.autoSync = new AutoSync({
    //         syncInterval: 60000, // 1 minute (auto fetch data every 1 min)
    //         refreshInterval: 120000, // 2 minutes (faster refresh)
    //         enabled: true
    //     });
    //     console.log('Auto-sync enabled for admin user on', currentPath);
    // } else if (syncPages.some(page => currentPath.startsWith(page))) {
    //     // For non-admin users, just log that auto-sync is disabled
    //     console.log('Auto-sync disabled for non-admin users (role:', userRole, ')');
    // }
});
