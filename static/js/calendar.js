// Everlast ERP - Calendar JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const calendarEl = document.getElementById('calendar');
    let currentUserId = null; // Variable to store the currently selected user ID
    let retryCount = 0;
    const maxRetries = 3;
    let isRetrying = false;

    // Retry function for calendar events with exponential backoff
    function retryCalendarEvents() {
        if (retryCount < maxRetries && !isRetrying) {
            isRetrying = true;
            retryCount++;
            const delay = Math.min(2000 * Math.pow(2, retryCount - 1), 30000); // Max 30 seconds
            console.log(`Retrying calendar events fetch (attempt ${retryCount}/${maxRetries}) in ${delay/1000} seconds`);
            
            setTimeout(() => {
                if (calendar) {
                    calendar.refetchEvents();
                }
                isRetrying = false;
            }, delay);
        } else if (retryCount >= maxRetries) {
            console.error('Max retry attempts reached for calendar events');
        }
    }

    if (calendarEl) {
        // Show global loading indicator
        if (window.showGlobalLoader) {
            window.showGlobalLoader();
        }
        
        // Initialize the calendar (make it global for auto-fetch access)
        window.calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth'
            },
            // Ensure calendar shows all past days and future dates
            validRange: {
                start: '2015-01-01',  // Show from 2015
                end: '2035-12-31'    // Show until 2035
            },
            customButtons: {
                prev: {
                    text: '‹',
                    click: function() {
                        calendar.prev();
                    }
                },
                next: {
                    text: '›',
                    click: function() {
                        calendar.next();
                    }
                }
            },
            themeSystem: 'bootstrap5',
            height: 'auto',
            // Ensure all dates are clickable and visible
            dayMaxEvents: true,
            moreLinkClick: 'popover',
            // Better date handling
            nowIndicator: true,
            // Ensure past days are fully functional
            selectable: true,
            selectMirror: true,
            unselectAuto: false,
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
                            console.log('Sending user_id parameter:', currentUserId);
                        } else {
                            console.log('No user filter applied - showing all users');
                        }
                        return params;
                    },
                    method: 'GET',
                    withCredentials: true,
                    success: function(response) {
                        console.log('Calendar events loaded successfully:', response);
                        // Reset retry count and retry flag on successful load
                        retryCount = 0;
                        isRetrying = false;
                        // Hide global loading indicator
                        if (window.hideGlobalLoader) {
                            window.hideGlobalLoader();
                        }
                    },
                    failure: function(xhr, status, error) {
                        console.error('Calendar events fetch error:', {
                            status: status,
                            error: error,
                            responseText: xhr.responseText,
                            statusCode: xhr.status,
                            readyState: xhr.readyState
                        });
                        
                        // Hide global loading indicator
                        if (window.hideGlobalLoader) {
                            window.hideGlobalLoader();
                        }
                        
                        // Handle specific error types
                        if (status === 'timeout') {
                            console.warn('Calendar events request timed out - server may be restarting');
                            retryCalendarEvents();
                            return;
                        } else if (status === 'error' && (error === 'Failed to fetch' || error.includes('ERR_CONNECTION_RESET'))) {
                            console.warn('Connection lost - server may be restarting');
                            retryCalendarEvents();
                            return;
                        } else if (xhr.responseText && xhr.responseText.includes('<!DOCTYPE html>')) {
                            alert('Please log in to view calendar events. You will be redirected to the login page.');
                            window.location.href = '/auth/login';
                        } else if (xhr.status === 0) {
                            console.warn('Network error - server may be restarting');
                            retryCalendarEvents();
                            return;
                        } else {
                            console.error('Calendar events error:', error);
                            // Only show alert for actual errors, not connection issues
                            if (xhr.status >= 400) {
                                alert('There was an error while fetching events! Check console for details.');
                            } else {
                                retryCalendarEvents();
                            }
                        }
                    },
                    eventDataTransform: function(event) {
                        // Enhanced color-coding with modern color palette
                        let backgroundColor, borderColor, textColor;
                        
                        // Modern color scheme based on status and type
                        if (event.type === 'leave') {
                            // Leave requests - Blue theme
                            if (event.status === 'approved') {
                                backgroundColor = '#10b981';  // Emerald green
                                borderColor = '#059669';
                                textColor = '#ffffff';
                            } else if (event.status === 'rejected') {
                                backgroundColor = '#ef4444';  // Red
                                borderColor = '#dc2626';
                                textColor = '#ffffff';
                            } else { // pending
                                backgroundColor = '#f59e0b';  // Amber
                                borderColor = '#d97706';
                                textColor = '#ffffff';
                            }
                        } else if (event.type === 'permission') {
                            // Permission requests - Purple theme
                            if (event.status === 'approved') {
                                backgroundColor = '#8b5cf6';  // Violet
                                borderColor = '#7c3aed';
                                textColor = '#ffffff';
                            } else if (event.status === 'rejected') {
                                backgroundColor = '#ef4444';  // Red
                                borderColor = '#dc2626';
                                textColor = '#ffffff';
                            } else { // pending
                                backgroundColor = '#f59e0b';  // Amber
                                borderColor = '#d97706';
                                textColor = '#ffffff';
                            }
                        } else if (event.type === 'attendance') {
                            // Attendance events - Teal theme
                            if (event.status === 'Present') {
                                backgroundColor = '#06b6d4';  // Cyan
                                borderColor = '#0891b2';
                                textColor = '#ffffff';
                            } else if (event.status === 'Absent') {
                                backgroundColor = '#ef4444';  // Red
                                borderColor = '#dc2626';
                                textColor = '#ffffff';
                            } else if (event.status === 'Leave Request') {
                                backgroundColor = '#f59e0b';  // Amber
                                borderColor = '#d97706';
                                textColor = '#ffffff';
                            } else if (event.status === 'Permission') {
                                backgroundColor = '#8b5cf6';  // Violet
                                borderColor = '#7c3aed';
                                textColor = '#ffffff';
                            } else if (event.status === 'Day Off') {
                                backgroundColor = '#6b7280';  // Gray
                                borderColor = '#4b5563';
                                textColor = '#ffffff';
                            } else if (event.status === 'Day Off / Present') {
                                backgroundColor = '#10b981';  // Emerald green
                                borderColor = '#059669';
                                textColor = '#ffffff';
                            } else {
                                backgroundColor = '#6366f1';  // Indigo
                                borderColor = '#4f46e5';
                                textColor = '#ffffff';
                            }
                        } else {
                            // Default colors
                            backgroundColor = '#6366f1';
                            borderColor = '#4f46e5';
                            textColor = '#ffffff';
                        }
                        
                        // Apply colors
                        event.backgroundColor = backgroundColor;
                        event.borderColor = borderColor;
                        event.textColor = textColor;
                        
                        // Add subtle shadow and rounded corners
                        event.classNames = ['modern-event'];
                        
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
            viewDidMount: function(info) {
                // Debug: Log when view changes
                console.log('Calendar view changed to:', info.view.type, 'Date range:', info.view.activeStart, 'to', info.view.activeEnd);
            },
            loading: function(isLoading) {
                // Show/hide loading indicator
                const loadingDiv = document.getElementById('calendar-loading');
                if (loadingDiv) {
                    loadingDiv.style.display = isLoading ? 'flex' : 'none';
                }
            }
        });
        
        try {
            calendar.render();
            // After render, ensure toolbar buttons work even with custom CSS
            setTimeout(() => {
                // Prev/Next/Today
                const prevBtn = document.querySelector('.fc-prev-button');
                const nextBtn = document.querySelector('.fc-next-button');
                const todayBtn = document.querySelector('.fc-today-button');
                if (prevBtn) { prevBtn.addEventListener('click', () => calendar.prev(), { once: false }); }
                if (nextBtn) { nextBtn.addEventListener('click', () => calendar.next(), { once: false }); }
                if (todayBtn) { todayBtn.addEventListener('click', () => calendar.today(), { once: false }); }
                // Month view (only)
                const monthBtn = document.querySelector('.fc-dayGridMonth-button');
                if (monthBtn) monthBtn.addEventListener('click', () => calendar.changeView('dayGridMonth'));
            }, 0);
        } catch (error) {
            console.error('Error rendering calendar:', error);
            // Hide loading indicator if there's an error
            const loadingDiv = document.getElementById('calendar-loading');
            if (loadingDiv) {
                loadingDiv.style.display = 'none';
            }
        }

        // Set initial currentUserId from URL or default
        const urlParams = new URLSearchParams(window.location.search);
        currentUserId = urlParams.get('user_id');
        console.log('Initial currentUserId:', currentUserId);

        // Handle user filter change (if element exists)
        const userFilter = document.getElementById('userFilter');
        
        // Update the user filter dropdown to match the current selection
        if (currentUserId && userFilter) {
            userFilter.value = currentUserId;
            console.log('Set user filter dropdown to:', currentUserId);
        }
        
        if (userFilter) {
            console.log('User filter element found:', userFilter);
            userFilter.addEventListener('change', function() {
                const userId = this.value;
                console.log('User filter changed to:', userId);
                currentUserId = userId || null;
                // Update URL without full reload
                const url = new URL(window.location.href);
                if (userId) { url.searchParams.set('user_id', userId); } else { url.searchParams.delete('user_id'); }
                window.history.replaceState({}, '', url);
                // Refetch events with new params
                calendar.refetchEvents();
            });
        } else {
            console.log('User filter element not found - user role may not have access to filter');
        }
        
        
        
    }
});
