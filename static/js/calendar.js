// Everlast ERP - Calendar JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const calendarEl = document.getElementById('calendar');
    
    if (calendarEl) {
        // Initialize the calendar
        const calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek'
            },
            customButtons: {
                prev: {
                    text: '↑',
                    click: function() {
                        calendar.prev();
                    }
                },
                next: {
                    text: '↓',
                    click: function() {
                        calendar.next();
                    }
                },
                today: {
                    text: 'Today',
                    click: function() {
                        calendar.today();
                    }
                }
            },
            themeSystem: 'bootstrap5',
            height: 'auto',
            eventTimeFormat: {
                hour: '2-digit',
                minute: '2-digit',
                meridiem: false,
                hour12: false
            },
            buttonText: {
                today: 'Today',
                month: 'Month',
                week: 'Week',
                day: 'Day',
                list: 'List'
            },
            eventSources: [
                {
                    url: '/calendar/events',
                    method: 'GET',
                    failure: function() {
                        alert('There was an error while fetching events!');
                    },
                    eventDataTransform: function(event) {
                        // Color-coding based on request type and status
                        let color;
                        
                        // Base colors for status
                        if (event.status === 'approved') {
                            color = '#17a74a';  // Success green
                        } else if (event.status === 'rejected') {
                            color = '#dc3545';  // Danger red
                        } else { // pending
                            color = '#ffc107';  // Warning yellow
                        }
                        
                        // Add opacity/variation based on type and if it's a personal request
                        if (event.title.startsWith('My')) {
                            // Highlight personal requests with a stronger color
                            event.backgroundColor = color;
                            event.borderColor = '#005d99';
                            event.textColor = '#ffffff';
                        } else if (event.type === 'leave') {
                            // Leave requests (team members)
                            event.backgroundColor = color;
                            event.borderColor = color;
                            event.textColor = '#ffffff';
                        } else { // permission
                            // Permission requests (team members)
                            event.backgroundColor = color;
                            event.borderColor = '#006e94'; // Tertiary color
                            event.textColor = '#ffffff';
                        }
                        
                        return event;
                    }
                }
            ],
            eventClick: function(info) {
                if (info.event.url) {
                    window.location.href = info.event.url;
                    return false;
                }
            },
            eventDidMount: function(info) {
                // Add a tooltip showing the event title
                const tooltip = new bootstrap.Tooltip(info.el, {
                    title: info.event.title,
                    placement: 'top',
                    trigger: 'hover',
                    container: 'body'
                });
            },
            datesSet: function(dateInfo) {
                // Update calendar stats when date range changes
                updateCalendarStats(dateInfo.start, dateInfo.end);
            },
            loading: function(isLoading) {
                // Show/hide loading indicator
                const loadingDiv = document.getElementById('calendar-loading');
                if (loadingDiv) {
                    loadingDiv.style.display = isLoading ? 'flex' : 'none';
                }
            }
        });
        
        calendar.render();
        
        // Filter events by type
        const leaveFilterCheckbox = document.getElementById('leave-filter');
        const permissionFilterCheckbox = document.getElementById('permission-filter');
        const pendingFilterCheckbox = document.getElementById('pending-filter');
        const approvedFilterCheckbox = document.getElementById('approved-filter');
        const rejectedFilterCheckbox = document.getElementById('rejected-filter');
        
        function updateFilters() {
            const showLeave = leaveFilterCheckbox?.checked ?? true;
            const showPermission = permissionFilterCheckbox?.checked ?? true;
            const showPending = pendingFilterCheckbox?.checked ?? true;
            const showApproved = approvedFilterCheckbox?.checked ?? true;
            const showRejected = rejectedFilterCheckbox?.checked ?? true;
            
            const events = calendar.getEvents();
            
            events.forEach(event => {
                const eventData = event.extendedProps;
                let visible = true;
                
                // Filter by type
                if ((!showLeave && eventData.type === 'leave') || 
                    (!showPermission && eventData.type === 'permission')) {
                    visible = false;
                }
                
                // Filter by status
                if ((!showPending && eventData.status === 'pending') || 
                    (!showApproved && eventData.status === 'approved') ||
                    (!showRejected && eventData.status === 'rejected')) {
                    visible = false;
                }
                
                event.setProp('display', visible ? 'auto' : 'none');
            });
            
            // Update counters
            updateCalendarStats(calendar.view.currentStart, calendar.view.currentEnd);
        }
        
        // Add event listeners to filters
        if (leaveFilterCheckbox) leaveFilterCheckbox.addEventListener('change', updateFilters);
        if (permissionFilterCheckbox) permissionFilterCheckbox.addEventListener('change', updateFilters);
        if (pendingFilterCheckbox) pendingFilterCheckbox.addEventListener('change', updateFilters);
        if (approvedFilterCheckbox) approvedFilterCheckbox.addEventListener('change', updateFilters);
        if (rejectedFilterCheckbox) rejectedFilterCheckbox.addEventListener('change', updateFilters);
        
        // Function to update calendar statistics
        function updateCalendarStats(start, end) {
            // Get all visible events
            const events = calendar.getEvents().filter(event => event.display !== 'none');
            
            // Count leave requests
            const leaveRequests = events.filter(event => event.extendedProps.type === 'leave');
            const pendingLeaves = leaveRequests.filter(event => event.extendedProps.status === 'pending');
            const approvedLeaves = leaveRequests.filter(event => event.extendedProps.status === 'approved');
            const rejectedLeaves = leaveRequests.filter(event => event.extendedProps.status === 'rejected');
            
            // Count permission requests
            const permissionRequests = events.filter(event => event.extendedProps.type === 'permission');
            const pendingPermissions = permissionRequests.filter(event => event.extendedProps.status === 'pending');
            const approvedPermissions = permissionRequests.filter(event => event.extendedProps.status === 'approved');
            const rejectedPermissions = permissionRequests.filter(event => event.extendedProps.status === 'rejected');
            
            // Update counters
            const totalLeaveCounter = document.getElementById('total-leaves');
            const pendingLeaveCounter = document.getElementById('pending-leaves');
            const approvedLeaveCounter = document.getElementById('approved-leaves');
            const rejectedLeaveCounter = document.getElementById('rejected-leaves');
            
            const totalPermissionCounter = document.getElementById('total-permissions');
            const pendingPermissionCounter = document.getElementById('pending-permissions');
            const approvedPermissionCounter = document.getElementById('approved-permissions');
            const rejectedPermissionCounter = document.getElementById('rejected-permissions');
            
            if (totalLeaveCounter) totalLeaveCounter.textContent = leaveRequests.length;
            if (pendingLeaveCounter) pendingLeaveCounter.textContent = pendingLeaves.length;
            if (approvedLeaveCounter) approvedLeaveCounter.textContent = approvedLeaves.length;
            if (rejectedLeaveCounter) rejectedLeaveCounter.textContent = rejectedLeaves.length;
            
            if (totalPermissionCounter) totalPermissionCounter.textContent = permissionRequests.length;
            if (pendingPermissionCounter) pendingPermissionCounter.textContent = pendingPermissions.length;
            if (approvedPermissionCounter) approvedPermissionCounter.textContent = approvedPermissions.length;
            if (rejectedPermissionCounter) rejectedPermissionCounter.textContent = rejectedPermissions.length;
        }
    }
});
