// Everlast ERP - Calendar JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const calendarEl = document.getElementById('calendar');
    let currentUserId = null; // Variable to store the currently selected user ID

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
                    extraParams: function() {
                        const params = {};
                        if (currentUserId) {
                            params.user_id = currentUserId;
                        }
                        return params;
                    },
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

        // Set initial currentUserId from URL or default
        const urlParams = new URLSearchParams(window.location.search);
        currentUserId = urlParams.get('user_id');

        // Handle user filter change
        document.getElementById('userFilter').addEventListener('change', function() {
            currentUserId = this.value; // Update the global variable
            calendar.refetchEvents(); // Refetch events with the new user ID
            // Optionally, update the URL without reloading the page
            const newUrl = new URL(window.location.href);
            if (currentUserId) {
                newUrl.searchParams.set('user_id', currentUserId);
            } else {
                newUrl.searchParams.delete('user_id');
            }
            window.history.pushState({ path: newUrl.href }, '', newUrl.href);
        });
        
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

            // Calculate total days in range
            const totalDaysInRange = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
            document.getElementById('total-days-in-range').textContent = totalDaysInRange;

            // Fetch detailed attendance summary for the selected range
            const startDate = start.toISOString().split('T')[0];
            const endDate = end.toISOString().split('T')[0];
            const selectedUserId = document.getElementById('user-filter')?.value || ''; // Assuming a user filter exists

            console.log('Fetching summary data for:', startDate, endDate, selectedUserId);
            fetch(`/calendar/summary?start_date=${startDate}&end_date=${endDate}&user_id=${selectedUserId}`)
                .then(response => {
                    console.log('Summary fetch response:', response);
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('Summary data received:', data);
                    document.getElementById('present-days').textContent = data.present_days;
                    document.getElementById('absent-days').textContent = data.absent_days;
                    document.getElementById('day-offs').textContent = data.day_offs;
                    document.getElementById('leave-days').textContent = data.leave_days;
                    document.getElementById('effective-days').textContent = data.effective_days;
                    document.getElementById('extra-hours').textContent = data.extra_hours;
                })
                .catch(error => console.error('Error fetching summary data:', error));
        }
        
        // Initial update of stats
        updateCalendarStats(calendar.view.currentStart, calendar.view.currentEnd);
    }
});
