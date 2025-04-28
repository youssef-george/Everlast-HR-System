// Everlast ERP - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle functionality
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const contentWrapper = document.getElementById('content-wrapper');
    const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
    const mobileOverlay = document.getElementById('mobile-overlay');

    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
            
            // Save sidebar state in localStorage
            if (sidebar.classList.contains('collapsed')) {
                localStorage.setItem('sidebar-collapsed', 'true');
            } else {
                localStorage.setItem('sidebar-collapsed', 'false');
            }
        });
    }

    // Restore sidebar state from localStorage
    if (localStorage.getItem('sidebar-collapsed') === 'true' && sidebar) {
        sidebar.classList.add('collapsed');
    }

    // Mobile menu functionality
    if (mobileMenuToggle) {
        mobileMenuToggle.addEventListener('click', function() {
            sidebar.classList.add('mobile-show');
            mobileOverlay.classList.add('active');
        });
    }

    if (mobileOverlay) {
        mobileOverlay.addEventListener('click', function() {
            sidebar.classList.remove('mobile-show');
            mobileOverlay.classList.remove('active');
        });
    }

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

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Flash messages auto-dismiss
    const alerts = document.querySelectorAll('.alert-dismissible.auto-dismiss');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const dismiss = new bootstrap.Alert(alert);
            dismiss.close();
        }, 5000);
    });

    // Handle form submission with confirmation
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!confirm(this.getAttribute('data-confirm'))) {
                e.preventDefault();
                return false;
            }
        });
    });

    // Notifications system
    function loadNotifications() {
        fetch('/notifications/unread_count')
            .then(response => response.json())
            .then(data => {
                const notificationBadge = document.getElementById('notification-badge');
                if (notificationBadge) {
                    if (data.count > 0) {
                        notificationBadge.textContent = data.count;
                        notificationBadge.style.display = 'flex';
                    } else {
                        notificationBadge.style.display = 'none';
                    }
                }
            })
            .catch(error => console.error('Error loading notification count:', error));

        // Load recent notifications for dropdown
        fetch('/notifications/get_recent')
            .then(response => response.json())
            .then(data => {
                const notificationsList = document.getElementById('notifications-list');
                if (notificationsList) {
                    notificationsList.innerHTML = '';
                    
                    if (data.length === 0) {
                        notificationsList.innerHTML = '<div class="notification-item"><div class="notification-content"><div class="notification-text">No new notifications</div></div></div>';
                    } else {
                        data.forEach(notification => {
                            let iconClass = 'fas fa-bell';
                            let iconColor = 'text-primary';
                            
                            if (notification.type === 'approval') {
                                iconClass = 'fas fa-check-circle';
                                iconColor = 'text-success';
                            } else if (notification.type === 'rejection') {
                                iconClass = 'fas fa-times-circle';
                                iconColor = 'text-danger';
                            } else if (notification.type === 'comment') {
                                iconClass = 'fas fa-comment';
                                iconColor = 'text-info';
                            }
                            
                            let url = `/notifications`;
                            if (notification.reference_type && notification.reference_id) {
                                url = `/${notification.reference_type}/view/${notification.reference_id}`;
                            }
                            
                            const notificationItem = `
                                <a href="${url}" class="notification-item">
                                    <div class="notification-icon">
                                        <i class="${iconClass} ${iconColor}"></i>
                                    </div>
                                    <div class="notification-content">
                                        <div class="notification-text">${notification.message}</div>
                                        <div class="notification-time">${notification.created_at}</div>
                                    </div>
                                </a>
                            `;
                            
                            notificationsList.innerHTML += notificationItem;
                        });
                    }
                }
            })
            .catch(error => console.error('Error loading recent notifications:', error));
    }

    // Load notifications on page load
    loadNotifications();

    // Refresh notifications every 30 seconds
    setInterval(loadNotifications, 30000);

    // Mark all notifications as read
    const markAllAsRead = document.getElementById('mark-all-as-read');
    if (markAllAsRead) {
        markAllAsRead.addEventListener('click', function(e) {
            e.preventDefault();
            
            fetch('/notifications/mark_all_as_read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadNotifications();
                }
            })
            .catch(error => console.error('Error marking notifications as read:', error));
        });
    }

    // Page loader
    const pageLoader = document.getElementById('page-loader');
    if (pageLoader) {
        window.addEventListener('load', function() {
            pageLoader.classList.add('fade-out');
            setTimeout(function() {
                pageLoader.style.display = 'none';
            }, 300);
        });
    }
});
