// Everlast HR System - Auto-Fetch System for All Roles
// This system automatically fetches and updates data for all user roles

class AutoFetchSystem {
    constructor(options = {}) {
        this.fetchInterval = options.fetchInterval || 15000; // 15 seconds default (more frequent)
        this.refreshInterval = options.refreshInterval || 60000; // 1 minute default (more frequent)
        this.enabled = options.enabled !== false;
        this.userRole = options.userRole || 'employee';
        this.isRunning = false;
        this.fetchInProgress = false;
        this.connectionFailures = 0;
        this.maxFailures = 3;
        this.baseDelay = 5000; // 5 seconds base delay
        this.gatewayErrors = 0; // Track consecutive 502/503 errors
        this.gatewayErrorDelay = 0; // Current delay for gateway errors
        
        // Data cache to avoid unnecessary updates
        this.dataCache = new Map();
        
        // Debug mode
        this.debug = options.debug || false;
        
        // Device sync functionality
        this.deviceSyncEnabled = options.deviceSyncEnabled || false;
        this.lastDeviceSyncTime = null;
        this.deviceSyncInProgress = false;
        
        this.init();
    }
    
    init() {
        if (!this.enabled) return;
        
        console.log(`🔄 Auto-fetch system initialized for ${this.userRole} role`);
        console.log(`📊 Fetch interval: ${this.fetchInterval/1000}s, Refresh interval: ${this.refreshInterval/1000}s`);
        
        // Start auto-fetch
        this.startAutoFetch();
        
        // Start auto-refresh
        this.startAutoRefresh();
        
        // Handle page visibility changes
        try {
            document.addEventListener('visibilitychange', () => {
                try {
                    if (document.hidden) {
                        console.log('⏸️ Page hidden, pausing auto-fetch');
                        this.pause();
                    } else {
                        console.log('▶️ Page visible, resuming auto-fetch');
                        this.resume();
                    }
                } catch (e) {
                    // Ignore browser extension interference
                    console.debug('Visibility change handler error (likely browser extension):', e);
                }
            });
        } catch (e) {
            console.debug('Error setting up visibility change listener (likely browser extension):', e);
        }
        
        // Handle online/offline events
        try {
            window.addEventListener('online', () => {
                try {
                    console.log('🌐 Connection restored, resuming auto-fetch');
                    this.resume();
                } catch (e) {
                    console.debug('Online event handler error (likely browser extension):', e);
                }
            });
            
            window.addEventListener('offline', () => {
                try {
                    console.log('📵 Connection lost, pausing auto-fetch');
                    this.pause();
                } catch (e) {
                    console.debug('Offline event handler error (likely browser extension):', e);
                }
            });
        } catch (e) {
            console.debug('Error setting up online/offline listeners (likely browser extension):', e);
        }
        
        // Add visual indicator for auto-fetch status - DISABLED
        // this.addStatusIndicator();
        
        // Remove any existing status indicator
        const existingIndicator = document.getElementById('auto-fetch-indicator');
        if (existingIndicator) {
            existingIndicator.remove();
        }
    }
    
    startAutoFetch() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        console.log(`🚀 Starting auto-fetch with ${this.fetchInterval/1000}s interval`);
        
        // Store original interval for restoration
        this.originalFetchInterval = this.fetchInterval;
        
        this.fetchIntervalId = setInterval(() => {
            // Only fetch if page is visible and not in a form
            if (!document.hidden && !document.querySelector('form:focus')) {
                this.performFetch();
            }
        }, this.fetchInterval);
        
        // Check if we just submitted a form (detect query parameter)
        const urlParams = new URLSearchParams(window.location.search);
        const justSubmitted = urlParams.get('submitted') === '1';
        
        // Delay initial fetch longer if we just submitted a form to avoid 502 errors
        const initialDelay = justSubmitted ? 15000 : 2000; // 15 seconds after submission, 2 seconds normally
        
        if (justSubmitted) {
            console.log('⏳ Recent submission detected - delaying initial fetch to allow backend processing...');
            // Remove the query parameter from URL without reload
            const newUrl = window.location.pathname + (window.location.hash || '');
            window.history.replaceState({}, '', newUrl);
        }
        
        // Perform initial fetch with appropriate delay
        setTimeout(() => {
            console.log('🔄 Performing initial data fetch...');
            this.performFetch();
        }, initialDelay);
    }
    
    startAutoRefresh() {
        this.refreshIntervalId = setInterval(() => {
            this.refreshPage();
        }, this.refreshInterval);
    }
    
    async performFetch() {
        if (this.fetchInProgress) return;
        
        // Check if we're on HTTPS but server might be HTTP (common in development)
        const currentProtocol = window.location.protocol;
        if (currentProtocol === 'https:' && window.location.hostname === '127.0.0.1') {
            console.warn('⚠️ Page loaded over HTTPS but server may be HTTP. Some API calls may fail.');
        }
        
        this.fetchInProgress = true;
        console.log('🔄 Auto-fetching data...');
        
        // Update status indicator - DISABLED
        // if (this.updateStatusIndicator) {
        //     this.updateStatusIndicator('fetching');
        // }
        
        try {
            // Determine what data to fetch based on user role and current page
            const fetchPromises = this.getFetchPromises();
            
            if (fetchPromises.length === 0) {
                console.log('ℹ️ No data to fetch for current page');
                this.fetchInProgress = false;
                // if (this.updateStatusIndicator) {
                //     this.updateStatusIndicator('success');
                // }
                return;
            }
            
            console.log(`📡 Fetching ${fetchPromises.length} data sources for ${this.userRole} role`);
            
            // Execute all fetch operations in parallel
            const results = await Promise.allSettled(fetchPromises);
            
            // Process results
            let successCount = 0;
            let sslErrorCount = 0;
            let gatewayErrorCount = 0;
            results.forEach((result, index) => {
                if (result.status === 'fulfilled') {
                    this.handleFetchSuccess(result.value);
                    successCount++;
                } else {
                    // Check if it's an SSL error (HTTP/HTTPS mismatch)
                    const error = result.reason;
                    if (error && (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR') || error.message.includes('Failed to fetch')))) {
                        sslErrorCount++;
                        // Suppress SSL errors - they're expected when page is HTTPS but server is HTTP
                        console.debug(`⚠️ SSL protocol error suppressed (HTTP/HTTPS mismatch)`);
                    } else if (error && error.message && (error.message.includes('502') || error.message.includes('503') || error.message.includes('504'))) {
                        // Track gateway errors (502, 503, 504)
                        gatewayErrorCount++;
                        console.warn(`⚠️ Gateway error detected (${error.message}) - backend may be processing`);
                    } else {
                        console.warn(`❌ Fetch operation ${index} failed:`, result.reason);
                    }
                }
            });
            
            if (sslErrorCount > 0) {
                console.debug(`⚠️ ${sslErrorCount} SSL errors suppressed (likely HTTP/HTTPS protocol mismatch)`);
            }
            
            // Handle gateway errors with exponential backoff
            if (gatewayErrorCount > 0) {
                this.gatewayErrors++;
                // Exponential backoff: 5s, 10s, 20s, 40s, max 60s
                this.gatewayErrorDelay = Math.min(5000 * Math.pow(2, this.gatewayErrors - 1), 60000);
                console.warn(`⚠️ ${gatewayErrorCount} gateway errors detected (consecutive: ${this.gatewayErrors}). Backend may be processing.`);
                
                // Temporarily increase fetch interval if we're getting gateway errors
                if (this.gatewayErrors >= 2 && this.fetchIntervalId) {
                    clearInterval(this.fetchIntervalId);
                    const newInterval = Math.max(this.originalFetchInterval, this.gatewayErrorDelay);
                    console.log(`⏳ Temporarily increasing fetch interval to ${newInterval/1000}s due to gateway errors`);
                    
                    this.fetchIntervalId = setInterval(() => {
                        if (!document.hidden && !document.querySelector('form:focus')) {
                            this.performFetch();
                        }
                    }, newInterval);
                }
            } else {
                // Reset gateway error tracking on successful fetch
                if (this.gatewayErrors > 0) {
                    console.log(`✅ Gateway errors resolved - resetting to normal interval`);
                    // Restore original interval
                    if (this.fetchIntervalId && this.fetchInterval !== this.originalFetchInterval) {
                        clearInterval(this.fetchIntervalId);
                        this.fetchInterval = this.originalFetchInterval;
                        this.fetchIntervalId = setInterval(() => {
                            if (!document.hidden && !document.querySelector('form:focus')) {
                                this.performFetch();
                            }
                        }, this.fetchInterval);
                    }
                }
                this.gatewayErrors = 0;
                this.gatewayErrorDelay = 0;
            }
            
            console.log(`✅ Auto-fetch completed: ${successCount}/${results.length} successful`);
            
            // Reset connection failures on successful fetch
            this.connectionFailures = 0;
            
            // Update status indicator - DISABLED
            // if (this.updateStatusIndicator) {
            //     this.updateStatusIndicator('success');
            // }
            
        } catch (error) {
            console.error('❌ Auto-fetch error:', error);
            this.connectionFailures++;
            this.handleConnectionError(error);
            
            // Update status indicator - DISABLED
            // if (this.updateStatusIndicator) {
            //     this.updateStatusIndicator('error');
            // }
        } finally {
            this.fetchInProgress = false;
        }
    }
    
    getFetchPromises() {
        const promises = [];
        const currentPath = window.location.pathname;
        
        console.log(`🔍 Getting fetch promises for ${this.userRole} role on ${currentPath}`);
        
        // Common data for all roles
        if (this.shouldFetchData('dashboard_stats', currentPath)) {
            console.log(`   - Adding dashboard_stats fetch`);
            promises.push(this.fetchDashboardStats());
        }
        
        // Role-specific data
        switch (this.userRole) {
            case 'employee':
                console.log(`   - Adding employee-specific fetches`);
                promises.push(...this.getEmployeeFetchPromises(currentPath));
                break;
            case 'manager':
                console.log(`   - Adding manager-specific fetches`);
                promises.push(...this.getManagerFetchPromises(currentPath));
                break;
            case 'admin':
                console.log(`   - Adding admin-specific fetches`);
                promises.push(...this.getAdminFetchPromises(currentPath));
                break;
            case 'director':
                console.log(`   - Adding director-specific fetches`);
                promises.push(...this.getDirectorFetchPromises(currentPath));
                break;
            default:
                console.warn(`   - Unknown role: ${this.userRole}`);
        }
        
        // Page-specific data
        if (currentPath.includes('/leave/')) {
            console.log(`   - Adding leave-specific fetches`);
            promises.push(...this.getLeaveFetchPromises());
        }
        
        if (currentPath.includes('/attendance/')) {
            console.log(`   - Adding attendance-specific fetches`);
            promises.push(...this.getAttendanceFetchPromises());
        }
        
        if (currentPath.includes('/final-report')) {
            console.log(`   - Adding final-report-specific fetches`);
            promises.push(...this.getFinalReportFetchPromises());
        }
        
        if (currentPath.includes('/calendar/')) {
            console.log(`   - Adding calendar-specific fetches`);
            promises.push(...this.getCalendarFetchPromises());
        }
        
        console.log(`   - Total fetch promises: ${promises.length}`);
        return promises;
    }
    
    getEmployeeFetchPromises(currentPath) {
        const promises = [];
        
        // Leave balance for sidebar
        if (this.shouldFetchData('leave_balance', currentPath)) {
            promises.push(this.fetchLeaveBalance());
        }
        
        // Recent requests
        if (this.shouldFetchData('recent_requests', currentPath)) {
            promises.push(this.fetchRecentRequests());
        }
        
        return promises;
    }
    
    getManagerFetchPromises(currentPath) {
        const promises = [];
        
        // Team data
        if (this.shouldFetchData('team_data', currentPath)) {
            promises.push(this.fetchTeamData());
        }
        
        // Pending approvals
        if (this.shouldFetchData('pending_approvals', currentPath)) {
            promises.push(this.fetchPendingApprovals());
        }
        
        return promises;
    }
    
    getAdminFetchPromises(currentPath) {
        const promises = [];
        
        // All pending requests
        if (this.shouldFetchData('all_pending_requests', currentPath)) {
            promises.push(this.fetchAllPendingRequests());
        }
        
        // Department analytics
        if (this.shouldFetchData('department_analytics', currentPath)) {
            promises.push(this.fetchDepartmentAnalytics());
        }
        
        // User management data
        if (this.shouldFetchData('user_management', currentPath)) {
            promises.push(this.fetchUserManagementData());
        }
        
        return promises;
    }
    
    getDirectorFetchPromises(currentPath) {
        const promises = [];
        
        // Company-wide analytics
        if (this.shouldFetchData('company_analytics', currentPath)) {
            promises.push(this.fetchCompanyAnalytics());
        }
        
        // All requests overview
        if (this.shouldFetchData('all_requests_overview', currentPath)) {
            promises.push(this.fetchAllRequestsOverview());
        }
        
        return promises;
    }
    
    getLeaveFetchPromises() {
        return [
            this.fetchLeaveRequests(),
            this.fetchLeaveTypes(),
            this.fetchLeaveBalances()
        ];
    }
    
    getAttendanceFetchPromises() {
        return [
            this.fetchAttendanceData(),
            this.fetchAttendanceStats()
        ];
    }
    
    getFinalReportFetchPromises() {
        const promises = [
            this.fetchAttendanceData(),
            this.fetchAttendanceStats(),
            this.fetchFinalReportData()
        ];
        
        // Don't include device sync on final-report page - it's not needed there
        // Device sync should only run on attendance page where it's more relevant
        // This also prevents timeout errors on final-report page
        // If needed, device sync can be triggered manually from attendance page
        
        return promises;
    }
    
    getCalendarFetchPromises() {
        return [
            this.fetchCalendarEvents(),
            this.fetchUpcomingEvents()
        ];
    }
    
    shouldFetchData(dataType, currentPath) {
        // Define which data should be fetched on which pages
        const fetchRules = {
            'dashboard_stats': ['/dashboard/', '/'],
            'leave_balance': ['/dashboard/', '/leave/', '/'],
            'recent_requests': ['/dashboard/', '/leave/', '/permission/'],
            'team_data': ['/dashboard/', '/leave/', '/permission/'],
            'pending_approvals': ['/dashboard/', '/leave/', '/permission/'],
            'all_pending_requests': ['/dashboard/', '/leave/', '/permission/'],
            'department_analytics': ['/dashboard/'],
            'user_management': ['/dashboard/users', '/dashboard/members'],
            'company_analytics': ['/dashboard/'],
            'all_requests_overview': ['/dashboard/'],
            'leave_requests': ['/leave/'],
            'leave_types': ['/leave/', '/dashboard/leave-types'],
            'leave_balances': ['/leave/', '/dashboard/leave-balances'],
            'attendance_data': ['/attendance/', '/final-report'],
            'attendance_stats': ['/attendance/', '/final-report'],
            'final_report_data': ['/final-report'],
            'calendar_events': ['/calendar/'],
            'upcoming_events': ['/calendar/', '/dashboard/']
        };
        
        const allowedPaths = fetchRules[dataType] || [];
        return allowedPaths.some(path => currentPath.startsWith(path));
    }
    
    // Helper function to create timeout signal (more compatible than AbortSignal.timeout)
    _createTimeoutSignal(timeoutMs) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        return { controller, timeoutId };
    }
    
    // Fetch methods
    async fetchDashboardStats() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(10000);
            
            const response = await fetch('/dashboard/api/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            
            const result = await response.json();
            console.log('📊 Dashboard stats response:', result);
            
            if (result.success) {
                return { type: 'dashboard_stats', data: result.stats };
            } else {
                throw new Error(result.message || 'Failed to fetch dashboard stats');
            }
        } catch (error) {
            // Only log if it's not an abort (timeout) or if it's a real error
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                // Suppress SSL protocol errors (usually means HTTP/HTTPS mismatch)
                if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR') || error.message.includes('Failed to fetch'))) {
                    console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                    return null;
                }
                console.warn('Failed to fetch dashboard stats:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchLeaveBalance() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(5000);
            
            const response = await fetch('/api/leave/balances', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            
            const result = await response.json();
            console.log('📊 Leave balance response:', result);
            
            // Extract data from API response format
            const data = result.data || result;
            return { type: 'leave_balance', data };
        } catch (error) {
            // Only log if it's not an abort (timeout) or if it's a real error
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                // Suppress SSL protocol errors (usually means HTTP/HTTPS mismatch)
                if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR'))) {
                    console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                    return null;
                }
                console.warn('Failed to fetch leave balance:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchRecentRequests() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(5000);
            
            const response = await fetch('/api/requests/recent', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                // Check for gateway errors (502, 503, 504)
                if (response.status === 502 || response.status === 503 || response.status === 504) {
                    throw new Error(`HTTP ${response.status}: Bad Gateway - Backend may be processing`);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            console.log('📊 Recent requests response:', result);
            
            // Extract data from API response format
            const data = result.data || result;
            return { type: 'recent_requests', data };
        } catch (error) {
            // Only log if it's not an abort (timeout)
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                // Suppress SSL protocol errors (usually means HTTP/HTTPS mismatch)
                if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR') || error.message.includes('Failed to fetch'))) {
                    console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                    return null;
                }
                console.warn('Failed to fetch recent requests:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchTeamData() {
        try {
            const response = await fetch('/api/team/data', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'team_data', data };
        } catch (error) {
            console.warn('Failed to fetch team data:', error);
            return null;
        }
    }
    
    async fetchPendingApprovals() {
        try {
            const response = await fetch('/api/approvals/pending', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'pending_approvals', data };
        } catch (error) {
            console.warn('Failed to fetch pending approvals:', error);
            return null;
        }
    }
    
    async fetchAllPendingRequests() {
        try {
            const response = await fetch('/api/requests/all-pending', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'all_pending_requests', data };
        } catch (error) {
            console.warn('Failed to fetch all pending requests:', error);
            return null;
        }
    }
    
    async fetchDepartmentAnalytics() {
        try {
            const response = await fetch('/api/analytics/departments', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'department_analytics', data };
        } catch (error) {
            console.warn('Failed to fetch department analytics:', error);
            return null;
        }
    }
    
    async fetchUserManagementData() {
        try {
            const response = await fetch('/api/users/management', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'user_management', data };
        } catch (error) {
            console.warn('Failed to fetch user management data:', error);
            return null;
        }
    }
    
    async fetchCompanyAnalytics() {
        try {
            const response = await fetch('/api/analytics/company', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'company_analytics', data };
        } catch (error) {
            console.warn('Failed to fetch company analytics:', error);
            return null;
        }
    }
    
    async fetchAllRequestsOverview() {
        try {
            const response = await fetch('/api/requests/overview', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : null  // Increased timeout to 15 seconds
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            return { type: 'all_requests_overview', data };
        } catch (error) {
            console.warn('Failed to fetch all requests overview:', error);
            return null;
        }
    }
    
    async fetchLeaveRequests() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(15000);
            
            const response = await fetch('/api/leave/requests', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                // Check for gateway errors (502, 503, 504)
                if (response.status === 502 || response.status === 503 || response.status === 504) {
                    throw new Error(`HTTP ${response.status}: Bad Gateway - Backend may be processing`);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            return { type: 'leave_requests', data };
        } catch (error) {
            // Only log if it's not an abort (timeout)
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                // Suppress SSL protocol errors
                if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR'))) {
                    console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                    return null;
                }
                console.warn('Failed to fetch leave requests:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchLeaveTypes() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(15000);
            
            const response = await fetch('/api/leave/types', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                // Check for gateway errors (502, 503, 504)
                if (response.status === 502 || response.status === 503 || response.status === 504) {
                    throw new Error(`HTTP ${response.status}: Bad Gateway - Backend may be processing`);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            return { type: 'leave_types', data };
        } catch (error) {
            // Only log if it's not an abort (timeout)
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                // Suppress SSL protocol errors
                if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR'))) {
                    console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                    return null;
                }
                console.warn('Failed to fetch leave types:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchLeaveBalances() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(15000);
            
            const response = await fetch('/api/leave/balances', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                // Check for gateway errors (502, 503, 504)
                if (response.status === 502 || response.status === 503 || response.status === 504) {
                    throw new Error(`HTTP ${response.status}: Bad Gateway - Backend may be processing`);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            return { type: 'leave_balances', data };
        } catch (error) {
            // Only log if it's not an abort (timeout)
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                // Suppress SSL protocol errors
                if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR'))) {
                    console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                    return null;
                }
                console.warn('Failed to fetch leave balances:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchAttendanceData() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(5000);
            
            const response = await fetch('/api/attendance/data', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            
            const data = await response.json();
            return { type: 'attendance_data', data };
        } catch (error) {
            // Only log if it's not an abort (timeout) or if it's a real error
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                console.warn('Failed to fetch attendance data:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchAttendanceStats() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(5000);
            
            const response = await fetch('/api/attendance/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            
            const data = await response.json();
            return { type: 'attendance_stats', data };
        } catch (error) {
            // Only log if it's not an abort (timeout) or if it's a real error
            if (error.name !== 'AbortError' && error.name !== 'TimeoutError') {
                console.warn('Failed to fetch attendance stats:', error.message || error);
            }
            return null;
        }
    }
    
    async fetchFinalReportData() {
        try {
            // Get current URL parameters to maintain the same report parameters
            const urlParams = new URLSearchParams(window.location.search);
            const queryString = urlParams.toString();
            const url = queryString ? `/final-report?${queryString}` : '/final-report';
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            // Parse the HTML response to extract the report data
            const html = await response.text();
            return { type: 'final_report_data', data: { html } };
        } catch (error) {
            console.warn('Failed to fetch final report data:', error);
            return null;
        }
    }
    
    async fetchUpcomingEvents() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(15000);
            
            const response = await fetch('/api/calendar/upcoming', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            
            const data = await response.json();
            return { type: 'upcoming_events', data };
        } catch (error) {
            // Suppress SSL protocol errors (usually means HTTP/HTTPS mismatch or redirect issues)
            if (error.name === 'AbortError' || error.name === 'TimeoutError') {
                return null;
            }
            if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR') || error.message.includes('Failed to fetch'))) {
                console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                return null;
            }
            console.warn('Failed to fetch upcoming events:', error.message || error);
            return null;
        }
    }
    
    async fetchCalendarEvents() {
        try {
            const { controller, timeoutId } = this._createTimeoutSignal(15000);
            
            const response = await fetch('/calendar/events', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                redirect: 'follow',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            
            const data = await response.json();
            return { type: 'calendar_events', data };
        } catch (error) {
            // Suppress SSL protocol errors (usually means HTTP/HTTPS mismatch or redirect issues)
            if (error.name === 'AbortError' || error.name === 'TimeoutError') {
                return null;
            }
            if (error.message && (error.message.includes('SSL') || error.message.includes('ERR_SSL_PROTOCOL_ERROR') || error.message.includes('Failed to fetch'))) {
                console.debug('SSL protocol error (likely HTTP/HTTPS mismatch) - suppressing');
                return null;
            }
            console.warn('Failed to fetch calendar events:', error.message || error);
            return null;
        }
    }
    
    handleFetchSuccess(result) {
        if (!result || !result.type || !result.data) return;
        
        // Check if data has changed
        const cacheKey = result.type;
        const cachedData = this.dataCache.get(cacheKey);
        const dataString = JSON.stringify(result.data);
        
        if (cachedData === dataString) {
            // Data hasn't changed, skip update
            return;
        }
        
        // Update cache
        this.dataCache.set(cacheKey, dataString);
        
        // Update UI based on data type
        this.updateUI(result.type, result.data);
    }
    
    updateUI(dataType, data) {
        switch (dataType) {
            case 'dashboard_stats':
                this.updateDashboardStats(data);
                break;
            case 'leave_balance':
                this.updateLeaveBalance(data);
                break;
            case 'recent_requests':
                this.updateRecentRequests(data);
                break;
            case 'team_data':
                this.updateTeamData(data);
                break;
            case 'pending_approvals':
                this.updatePendingApprovals(data);
                break;
            case 'all_pending_requests':
                this.updateAllPendingRequests(data);
                break;
            case 'department_analytics':
                this.updateDepartmentAnalytics(data);
                break;
            case 'user_management':
                this.updateUserManagement(data);
                break;
            case 'company_analytics':
                this.updateCompanyAnalytics(data);
                break;
            case 'all_requests_overview':
                this.updateAllRequestsOverview(data);
                break;
            case 'leave_requests':
                this.updateLeaveRequests(data);
                break;
            case 'leave_types':
                this.updateLeaveTypes(data);
                break;
            case 'leave_balances':
                this.updateLeaveBalances(data);
                break;
            case 'attendance_data':
                this.updateAttendanceData(data);
                break;
            case 'attendance_stats':
                this.updateAttendanceStats(data);
                break;
            case 'final_report_data':
                this.updateFinalReportData(data);
                break;
            case 'calendar_events':
                this.updateCalendarEvents(data);
                break;
            case 'upcoming_events':
                this.updateUpcomingEvents(data);
                break;
        }
    }
    
    // UI Update methods
    updateDashboardStats(data) {
        // Only update dashboard stats if we're on a dashboard page
        if (!this.isDashboardPage()) {
            return;
        }
        
        console.log('📊 Updating dashboard stats with data:', data);
        
        // Update dashboard statistics
        if (data.pending_leave_requests !== undefined) {
            console.log('🔄 Updating pending leave count:', data.pending_leave_requests);
            this.updateElement('.pending-leave-count', data.pending_leave_requests);
        }
        if (data.pending_permission_requests !== undefined) {
            console.log('🔄 Updating pending permission count:', data.pending_permission_requests);
            this.updateElement('.pending-permission-count', data.pending_permission_requests);
        }
        if (data.approved_leave_requests !== undefined) {
            console.log('🔄 Updating approved leave count:', data.approved_leave_requests);
            this.updateElement('.approved-leave-count', data.approved_leave_requests);
        }
        if (data.approved_permission_requests !== undefined) {
            console.log('🔄 Updating approved permission count:', data.approved_permission_requests);
            this.updateElement('.approved-permission-count', data.approved_permission_requests);
        }
        if (data.rejected_leave_requests !== undefined) {
            console.log('🔄 Updating rejected leave count:', data.rejected_leave_requests);
            this.updateElement('.rejected-leave-count', data.rejected_leave_requests);
        }
        if (data.total_employees !== undefined) {
            console.log('🔄 Updating total employees count:', data.total_employees);
            this.updateElement('.total-employees-count', data.total_employees);
        }
        if (data.total_departments !== undefined) {
            console.log('🔄 Updating total departments count:', data.total_departments);
            this.updateElement('.total-departments-count', data.total_departments);
        }
        if (data.total_attendance_today !== undefined) {
            console.log('🔄 Updating present today count:', data.total_attendance_today);
            this.updateElement('.total-attendance-today', data.total_attendance_today);
        }
        if (data.team_absent_today !== undefined) {
            console.log('🔄 Updating absent today count:', data.team_absent_today);
            this.updateElement('.team-absent-today', data.team_absent_today);
        }
        if (data.attendance_rate !== undefined) {
            console.log('🔄 Updating attendance rate:', data.attendance_rate);
            this.updateElement('.attendance-rate', data.attendance_rate + '%');
        }
        
        console.log('✅ Dashboard stats update completed');
    }
    
    isDashboardPage() {
        // Check if we're on the main dashboard page by looking for dashboard-specific elements
        const currentPath = window.location.pathname;
        const isDashboardRoot = currentPath === '/dashboard' || currentPath === '/dashboard/' || 
                               currentPath === '/' || currentPath === '/index';
        
        // Also check for dashboard stats elements to be sure
        const hasDashboardElements = document.querySelector('.dashboard-stats') || 
                                   document.querySelector('.stat-card') ||
                                   document.querySelector('.pending-leave-count') ||
                                   document.querySelector('.total-employees-count');
        
        return isDashboardRoot && hasDashboardElements;
    }
    
    updateLeaveBalance(data) {
        if (data.balances && Array.isArray(data.balances)) {
            const balanceContent = document.getElementById('leave-balance-content');
            if (balanceContent) {
                this.renderLeaveBalance(data.balances, balanceContent);
            }
        }
    }
    
    updateRecentRequests(data) {
        // Update recent requests in dashboard
        if (data.leave_requests && Array.isArray(data.leave_requests)) {
            this.updateRequestsList('.recent-leave-requests', data.leave_requests, 'leave');
        }
        if (data.permission_requests && Array.isArray(data.permission_requests)) {
            this.updateRequestsList('.recent-permission-requests', data.permission_requests, 'permission');
        }
    }
    
    updateTeamData(data) {
        // Update team-related data
        if (data.team_members && Array.isArray(data.team_members)) {
            this.updateTeamMembers(data.team_members);
        }
        if (data.team_attendance !== undefined) {
            this.updateElement('.team-attendance', data.team_attendance);
        }
    }
    
    updatePendingApprovals(data) {
        // Update pending approvals count and list
        if (data.count !== undefined) {
            this.updateElement('.pending-approvals-count', data.count);
        }
        if (data.requests && Array.isArray(data.requests)) {
            this.updateRequestsList('.pending-approvals-list', data.requests, 'approval');
        }
    }
    
    updateAllPendingRequests(data) {
        // Update all pending requests for admin/director
        if (data.leave_requests && Array.isArray(data.leave_requests)) {
            this.updateRequestsList('.all-pending-leave-requests', data.leave_requests, 'leave');
        }
        if (data.permission_requests && Array.isArray(data.permission_requests)) {
            this.updateRequestsList('.all-pending-permission-requests', data.permission_requests, 'permission');
        }
    }
    
    updateDepartmentAnalytics(data) {
        // Update department analytics charts
        if (data.departments && Array.isArray(data.departments)) {
            this.updateDepartmentChart(data.departments);
        }
    }
    
    updateUserManagement(data) {
        // Update user management data
        if (data.users && Array.isArray(data.users)) {
            this.updateUsersList(data.users);
        }
    }
    
    updateCompanyAnalytics(data) {
        // Update company-wide analytics
        if (data.overview) {
            this.updateCompanyOverview(data.overview);
        }
    }
    
    updateAllRequestsOverview(data) {
        // Update all requests overview
        if (data.summary) {
            this.updateRequestsSummary(data.summary);
        }
    }
    
    updateLeaveRequests(data) {
        // Update leave requests list
        if (data.requests && Array.isArray(data.requests)) {
            this.updateRequestsList('.leave-requests-list', data.requests, 'leave');
        }
    }
    
    updateLeaveTypes(data) {
        // Update leave types
        if (data.types && Array.isArray(data.types)) {
            this.updateLeaveTypesList(data.types);
        }
    }
    
    updateLeaveBalances(data) {
        // Update leave balances
        if (data.balances && Array.isArray(data.balances)) {
            this.updateLeaveBalancesList(data.balances);
        }
    }
    
    updateAttendanceData(data) {
        // Update attendance data - For attendance page, check if data changed and reload
        const currentPath = window.location.pathname;
        if (currentPath.includes('/attendance/') && data.records && Array.isArray(data.records)) {
            console.log('🔄 Checking attendance data for changes...');
            
            // Check if data has changed from cache
            const cacheKey = 'attendance_data';
            const cachedData = this.dataCache.get(cacheKey);
            const dataString = JSON.stringify(data.records);
            
            if (cachedData !== dataString) {
                console.log('✅ Attendance data has changed - reloading page...');
                
                // Store a flag to prevent infinite reload loops
                const lastReload = localStorage.getItem('lastAttendanceReload');
                const now = Date.now();
                
                // Only reload if it's been more than 20 seconds since last reload (reduced from 30s)
                if (!lastReload || (now - parseInt(lastReload)) > 20000) {
                    localStorage.setItem('lastAttendanceReload', now.toString());
                    console.log('🔄 Reloading attendance page to show updated data...');
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    console.log('⏸️ Skipping reload - too soon since last reload');
                }
            } else {
                console.log('ℹ️ No changes in attendance data');
            }
        }
    }
    
    updateAttendanceStats(data) {
        // Update attendance statistics
        if (data.stats) {
            this.updateAttendanceStatsDisplay(data.stats);
        }
    }
    
    updateCalendarEvents(data) {
        // Update calendar events - refresh FullCalendar if available
        if (window.calendar && typeof window.calendar.refetchEvents === 'function') {
            console.log('🔄 Refreshing FullCalendar events...');
            window.calendar.refetchEvents();
        }
        
        // Also update any custom calendar events list if present
        if (data.events && Array.isArray(data.events)) {
            this.updateCalendarEventsList(data.events);
        }
    }
    
    updateUpcomingEvents(data) {
        // Update upcoming events
        if (data.events && Array.isArray(data.events)) {
            this.updateUpcomingEventsList(data.events);
        }
    }
    
    // Helper methods for UI updates
    updateElement(selector, value) {
        const element = document.querySelector(selector);
        if (element) {
            console.log(`🔄 Updating element ${selector} with value: ${value}`);
            element.textContent = value;
        } else {
            // Only warn about missing elements on dashboard pages
            if (this.isDashboardPage()) {
                console.warn(`⚠️ Dashboard element not found: ${selector}`);
            } else {
                console.debug(`📍 Element ${selector} not found (expected on non-dashboard page)`);
            }
        }
    }
    
    renderLeaveBalance(balances, container) {
        if (balances.length === 0) {
            container.innerHTML = '<div class="text-center text-muted">No leave balance data available</div>';
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
        
        container.innerHTML = html;
    }
    
    updateRequestsList(selector, requests, type) {
        const container = document.querySelector(selector);
        if (!container) return;
        
        if (requests.length === 0) {
            container.innerHTML = '<div class="text-center text-muted">No requests found</div>';
            return;
        }
        
        let html = '';
        requests.forEach(request => {
            const statusClass = this.getStatusClass(request.status);
            const typeIcon = type === 'leave' ? 'calendar-times' : type === 'permission' ? 'door-open' : 'clock';
            
            html += `
                <div class="request-item">
                    <div class="request-info">
                        <i class="fas fa-${typeIcon} me-2"></i>
                        <span class="request-title">${request.title || 'Request'}</span>
                    </div>
                    <span class="badge bg-${statusClass}">${request.status}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    getStatusClass(status) {
        switch (status) {
            case 'pending': return 'warning';
            case 'approved': return 'success';
            case 'rejected': return 'danger';
            default: return 'secondary';
        }
    }
    
    updateTeamMembers(members) {
        // Update team members list
        const container = document.querySelector('.team-members-list');
        if (!container) return;
        
        let html = '';
        members.forEach(member => {
            html += `
                <div class="team-member">
                    <div class="member-info">
                        <span class="member-name">${member.name}</span>
                        <span class="member-role">${member.role}</span>
                    </div>
                    <span class="member-status ${member.status}">${member.status}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    updateDepartmentChart(departments) {
        // Update department analytics chart
        if (window.departmentChartInstance && departments.length > 0) {
            const labels = departments.map(dept => dept.name);
            const employeesData = departments.map(dept => dept.employees);
            const leavesData = departments.map(dept => dept.leaves);
            const permissionsData = departments.map(dept => dept.permissions);
            
            window.departmentChartInstance.data.labels = labels;
            window.departmentChartInstance.data.datasets[0].data = employeesData;
            window.departmentChartInstance.data.datasets[1].data = leavesData;
            window.departmentChartInstance.data.datasets[2].data = permissionsData;
            window.departmentChartInstance.update();
        }
    }
    
    updateUsersList(users) {
        // Update users list
        const container = document.querySelector('.users-list');
        if (!container) return;
        
        let html = '';
        users.forEach(user => {
            html += `
                <div class="user-item">
                    <div class="user-info">
                        <span class="user-name">${user.name}</span>
                        <span class="user-email">${user.email}</span>
                    </div>
                    <span class="user-role">${user.role}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    updateCompanyOverview(overview) {
        // Update company overview statistics
        Object.keys(overview).forEach(key => {
            this.updateElement(`.company-${key}`, overview[key]);
        });
    }
    
    updateRequestsSummary(summary) {
        // Update requests summary
        Object.keys(summary).forEach(key => {
            this.updateElement(`.requests-${key}`, summary[key]);
        });
    }
    
    updateLeaveTypesList(types) {
        // Update leave types list
        const container = document.querySelector('.leave-types-list');
        if (!container) return;
        
        let html = '';
        types.forEach(type => {
            html += `
                <div class="leave-type-item">
                    <span class="leave-type-name">${type.name}</span>
                    <span class="leave-type-color" style="background-color: ${type.color}"></span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    updateLeaveBalancesList(balances) {
        // Update leave balances list
        const container = document.querySelector('.leave-balances-list');
        if (!container) return;
        
        let html = '';
        balances.forEach(balance => {
            html += `
                <div class="leave-balance-item">
                    <span class="balance-user">${balance.user_name}</span>
                    <span class="balance-type">${balance.leave_type}</span>
                    <span class="balance-remaining">${balance.remaining_days}/${balance.total_days}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    updateAttendanceRecords(records) {
        // Update attendance records
        const container = document.querySelector('.attendance-records');
        if (!container) return;
        
        let html = '';
        records.forEach(record => {
            html += `
                <div class="attendance-record">
                    <span class="record-user">${record.user_name}</span>
                    <span class="record-date">${record.date}</span>
                    <span class="record-status ${record.status}">${record.status}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    updateAttendanceStatsDisplay(stats) {
        // Update attendance statistics display
        Object.keys(stats).forEach(key => {
            this.updateElement(`.attendance-${key}`, stats[key]);
        });
    }
    
    updateFinalReportData(data) {
        // Update Final Report data by refreshing the page content
        if (data.html) {
            // Parse the HTML and update the report table
            const parser = new DOMParser();
            const doc = parser.parseFromString(data.html, 'text/html');
            const newTable = doc.querySelector('#finalReportTable');
            const currentTable = document.querySelector('#finalReportTable');
            
            if (newTable && currentTable) {
                // Update the table content
                currentTable.innerHTML = newTable.innerHTML;
                console.log('✅ Final Report data updated successfully');
            }
        }
    }
    
    updateCalendarEventsList(events) {
        // Update calendar events list
        const container = document.querySelector('.calendar-events-list');
        if (!container) return;
        
        let html = '';
        events.forEach(event => {
            html += `
                <div class="calendar-event">
                    <span class="event-title">${event.title}</span>
                    <span class="event-date">${event.date}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    updateUpcomingEventsList(events) {
        // Update upcoming events list
        const container = document.querySelector('.upcoming-events-list');
        if (!container) return;
        
        let html = '';
        events.forEach(event => {
            html += `
                <div class="upcoming-event">
                    <span class="event-title">${event.title}</span>
                    <span class="event-date">${event.date}</span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    handleConnectionError(error) {
        if (this.connectionFailures <= this.maxFailures) {
            const delay = this.baseDelay * Math.pow(2, this.connectionFailures - 1);
            console.warn(`Connection error: ${error.message}. Retrying in ${delay/1000} seconds...`);
            
            setTimeout(() => {
                if (this.isRunning) {
                    this.performFetch();
                }
            }, delay);
        } else {
            console.error('Max connection failures reached. Pausing auto-fetch...');
            this.pause();
        }
    }
    
    refreshPage() {
        // Auto-reload disabled by user request
        console.log('📵 Auto-reload disabled - skipping page refresh');
        return;
    }
    
    getCSRFToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }
    
    // addStatusIndicator() - REMOVED - Status indicator disabled
    
    pause() {
        if (this.fetchIntervalId) {
            clearInterval(this.fetchIntervalId);
        }
        if (this.refreshIntervalId) {
            clearInterval(this.refreshIntervalId);
        }
        this.isRunning = false;
        // if (this.updateStatusIndicator) {
        //     this.updateStatusIndicator('paused');
        // }
        console.log('⏸️ Auto-fetch paused');
    }
    
    resume() {
        if (!this.isRunning) {
            this.connectionFailures = 0;
            this.startAutoFetch();
            this.startAutoRefresh();
        }
    }
    
    destroy() {
        this.pause();
        this.dataCache.clear();
    }
    
    // Fetch all data method for manual refresh
    async fetchAllData() {
        console.log('🔄 Manual fetch all data triggered...');
        await this.performFetch();
        return Promise.resolve();
    }
    
    // Device Sync Methods
    async performDeviceSync() {
        // Don't sync if manual sync is in progress or if auto-fetch sync is already running
        if (!this.deviceSyncEnabled || this.deviceSyncInProgress || window.syncInProgress) {
            if (window.syncInProgress) {
                console.log('⏸️ Skipping auto device sync - manual sync in progress');
            }
            return;
        }
        
        // Double-check role - don't attempt sync for employees
        if (this.userRole === 'employee') {
            console.log('ℹ️ Device sync skipped - employee role (admin-only feature)');
            return;
        }
        
        this.deviceSyncInProgress = true;
        console.log('🔄 Starting device sync...');
        
        try {
            const response = await fetch('/attendance/manual-sync', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                signal: AbortSignal.timeout(30000) // 30 second timeout
            });
            
            if (!response.ok) {
                if (response.status === 403) {
                    console.warn('Device sync access denied (403). This feature is admin-only.');
                    this.deviceSyncEnabled = false;
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.lastDeviceSyncTime = new Date();
                console.log('✅ Device sync completed successfully');
                console.log(`📊 Sync results:`, data);
                
                // Show notification if new records were added
                if (data.records_added > 0) {
                    this.showSyncNotification(data);
                }
                
                // Reset connection failures on successful sync
                this.connectionFailures = 0;
            } else {
                console.warn('⚠️ Device sync completed with warnings:', data.message);
            }
            
        } catch (error) {
            // Extract error message properly
            let errorMessage = 'Unknown error';
            if (error instanceof Error) {
                errorMessage = error.message || error.toString();
            } else if (typeof error === 'string') {
                errorMessage = error;
            } else if (error && error.message) {
                errorMessage = error.message;
            }
            
            // Handle specific error types
            if (error.name === 'AbortError' || error.name === 'TimeoutError' || 
                errorMessage.includes('aborted') || errorMessage.includes('timeout') ||
                errorMessage.includes('signal timed out')) {
                console.warn('⏸️ Device sync timed out (this is normal for long-running syncs)');
                // Don't count timeout as a failure - it's expected for long syncs
                return;
            } else if (errorMessage.includes('403') || errorMessage.includes('Forbidden')) {
                console.warn('⚠️ Device sync access denied. This feature is admin-only.');
                this.deviceSyncEnabled = false;
                return;
            } else {
                console.error('❌ Device sync failed:', errorMessage);
                console.error('Error details:', error);
                this.connectionFailures++;
                
                if (this.connectionFailures >= this.maxFailures) {
                    console.error('Max device sync failures reached. Disabling device sync...');
                    this.deviceSyncEnabled = false;
                }
            }
        } finally {
            this.deviceSyncInProgress = false;
        }
    }
    
    showSyncNotification(data) {
        // Create a simple notification
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 9999;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
            max-width: 300px;
            animation: slideInRight 0.3s ease;
        `;
        
        notification.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
                <i class="fas fa-sync-alt" style="animation: spin 1s linear infinite;"></i>
                <div>
                    <div style="font-weight: 600;">New Data Synced!</div>
                    <div style="font-size: 12px; opacity: 0.9;">
                        ${data.records_added} new records added
                        ${data.records_updated > 0 ? `, ${data.records_updated} updated` : ''}
                    </div>
                </div>
            </div>
        `;
        
        // Add CSS animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.style.animation = 'slideInRight 0.3s ease reverse';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 5000);
    }
    
    shouldPerformDeviceSync() {
        if (!this.deviceSyncEnabled) return false;
        
        // Only sync if it's been more than 1 minute since last sync
        if (!this.lastDeviceSyncTime) return true;
        
        const timeSinceLastSync = Date.now() - this.lastDeviceSyncTime.getTime();
        return timeSinceLastSync >= 60000; // 1 minute
    }
}

// Auto-initialize on pages that need it
document.addEventListener('DOMContentLoaded', function() {
    // Remove any existing status indicators first
    const existingIndicator = document.getElementById('auto-fetch-indicator');
    if (existingIndicator) {
        existingIndicator.remove();
    }
    
    // Get user role from body attribute
    const userRole = document.body.getAttribute('data-user-role') || 'employee';
    
    console.log(`🔍 Auto-fetch initialization check:`);
    console.log(`   - Detected role: ${userRole}`);
    console.log(`   - Current path: ${window.location.pathname}`);
    
    // Check if we're on a page that needs auto-fetch - DISABLED
    const currentPath = window.location.pathname;
    const fetchPages = [
        '/dashboard/',
        '/leave/',
        '/attendance/',
        '/calendar/',
        '/permission/',
        '/final-report',
        '/'
    ];
    
    // Auto-fetch enabled for automatic data updates
    const shouldEnableAutoFetch = true;
    
    console.log(`   - Should enable auto-fetch: ${shouldEnableAutoFetch}`);
    console.log(`   - Matching pages: ${fetchPages.filter(page => currentPath.startsWith(page))}`);
    
    if (shouldEnableAutoFetch) {
        console.log(`🚀 Initializing auto-fetch system for ${userRole} role...`);
        
        // Use 30-second interval for attendance page to keep data fresh, 30 seconds for other pages
        const isAttendancePage = currentPath.includes('/attendance/');
        const fetchInterval = 30000; // 30 seconds for all pages (including attendance)
        
        // Initialize auto-fetch system with device sync
        window.autoFetch = new AutoFetchSystem({
            fetchInterval: fetchInterval, // 30 seconds for all pages
            refreshInterval: 300000, // 5 minutes for full refresh (disabled in code)
            enabled: true,
            userRole: userRole,
            debug: true, // Enable debug mode
            // Only enable device sync for admin/product_owner roles
            deviceSyncEnabled: (userRole === 'admin' || userRole === 'product_owner')
        });
        
        console.log(`✅ Auto-fetch system enabled for ${userRole} role on ${currentPath}`);
        if (isAttendancePage) {
            console.log(`📊 Attendance page: Auto-fetching data every 30 seconds while app is running`);
        } else {
            console.log(`📊 Fetch interval: 30s, Auto-reload disabled`);
        }
    } else {
        console.log(`❌ Auto-fetch not enabled for path: ${currentPath}`);
        console.log(`   - Supported paths: ${fetchPages.join(', ')}`);
    }
});

// Export for use in other scripts
window.AutoFetchSystem = AutoFetchSystem;
