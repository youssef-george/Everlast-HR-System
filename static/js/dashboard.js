// Everlast ERP - Dashboard JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Mini Calendar
    const miniCalendarEl = document.getElementById('mini-calendar');
    if (miniCalendarEl) {
        const miniCalendar = new FullCalendar.Calendar(miniCalendarEl, {
            initialView: 'dayGridMonth',
            headerToolbar: {
                left: 'prev,next',
                center: 'title',
                right: ''
            },
            height: 350,
            themeSystem: 'bootstrap5',
            dayMaxEventRows: 2,
            moreLinkClick: 'day',
            eventSources: [
                {
                    url: '/calendar/events',
                    method: 'GET',
                    failure: function() {
                        console.error('There was an error while fetching events for mini calendar');
                    },
                    color: '#005d99'
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
            }
        });
        
        miniCalendar.render();
    }
    
    // Admin Dashboard - Department Analytics Chart
    const departmentChartCanvas = document.getElementById('departmentChart');
    if (departmentChartCanvas) {
        // Get department data from global variable with error handling
        let departmentData = [];
        try {
            departmentData = window.departmentData || [];
            if (!Array.isArray(departmentData)) {
                console.warn('Department data is not an array, using empty array');
                departmentData = [];
            }
        } catch (error) {
            console.error('Error accessing department data:', error);
            departmentData = [];
        }
        
        if (departmentData.length > 0) {
            if (window.departmentChartInstance) {
                try { window.departmentChartInstance.destroy(); } catch (e) {}
            }
            const labels = departmentData.map(dept => dept.name);
            const employeesData = departmentData.map(dept => dept.employees);
            const leavesData = departmentData.map(dept => dept.leaves);
            const permissionsData = departmentData.map(dept => dept.permissions);
            
            window.departmentChartInstance = new Chart(departmentChartCanvas, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Employees',
                            data: employeesData,
                            backgroundColor: '#005d99',
                            borderColor: '#005d99',
                            borderWidth: 1
                        },
                        {
                            label: 'Leaves',
                            data: leavesData,
                            backgroundColor: '#17a74a',
                            borderColor: '#17a74a',
                            borderWidth: 1
                        },
                        {
                            label: 'Permissions',
                            data: permissionsData,
                            backgroundColor: '#006e94',
                            borderColor: '#006e94',
                            borderWidth: 1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        title: {
                            display: true,
                            text: 'Department Analytics'
                        }
                    }
                }
            });
        }
    }
    
    // Admin Dashboard - Request Status Chart
    const requestStatusChartCanvas = document.getElementById('requestStatusChart');
    if (requestStatusChartCanvas) {
        const pendingLeaves = parseInt(requestStatusChartCanvas.dataset.pendingLeaves || 0);
        const approvedLeaves = parseInt(requestStatusChartCanvas.dataset.approvedLeaves || 0);
        const rejectedLeaves = parseInt(requestStatusChartCanvas.dataset.rejectedLeaves || 0);
        
        const pendingPermissions = parseInt(requestStatusChartCanvas.dataset.pendingPermissions || 0);
        const approvedPermissions = parseInt(requestStatusChartCanvas.dataset.approvedPermissions || 0);
        const rejectedPermissions = parseInt(requestStatusChartCanvas.dataset.rejectedPermissions || 0);
        
        if (window.requestStatusChartInstance) {
            try { window.requestStatusChartInstance.destroy(); } catch (e) {}
        }
        window.requestStatusChartInstance = new Chart(requestStatusChartCanvas, {
            type: 'doughnut',
            data: {
                labels: ['Pending Leaves', 'Approved Leaves', 'Rejected Leaves', 'Pending Permissions', 'Approved Permissions', 'Rejected Permissions'],
                datasets: [{
                    data: [pendingLeaves, approvedLeaves, rejectedLeaves, pendingPermissions, approvedPermissions, rejectedPermissions],
                    backgroundColor: ['#ffc107', '#17a74a', '#dc3545', '#fd7e14', '#20c997', '#d63384'],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                    },
                    title: {
                        display: true,
                        text: 'Request Status Overview'
                    }
                }
            }
        });
    }
    
    // Employee Dashboard - Request History Chart
    const employeeRequestHistoryCanvas = document.getElementById('employeeRequestHistory');
    if (employeeRequestHistoryCanvas) {
        let leaveData = [];
        let permissionData = [];
        
        try {
            leaveData = window.leaveRequestsData || [];
            if (!Array.isArray(leaveData)) {
                console.warn('Leave data is not an array, using empty array');
                leaveData = [];
            }
        } catch (error) {
            console.error('Error accessing leave data:', error);
            leaveData = [];
        }
        
        try {
            permissionData = window.permissionRequestsData || [];
            if (!Array.isArray(permissionData)) {
                console.warn('Permission data is not an array, using empty array');
                permissionData = [];
            }
        } catch (error) {
            console.error('Error accessing permission data:', error);
            permissionData = [];
        }
        
        // Group by month
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        let leavesByMonth = Array(12).fill(0);
        let permissionsByMonth = Array(12).fill(0);
        
        // Current year
        const currentYear = new Date().getFullYear();
        
        leaveData.forEach(leave => {
            const leaveDate = new Date(leave.created_at);
            if (leaveDate.getFullYear() === currentYear) {
                leavesByMonth[leaveDate.getMonth()]++;
            }
        });
        
        permissionData.forEach(permission => {
            const permissionDate = new Date(permission.created_at);
            if (permissionDate.getFullYear() === currentYear) {
                permissionsByMonth[permissionDate.getMonth()]++;
            }
        });
        
        if (window.employeeRequestHistoryChartInstance) {
            try { window.employeeRequestHistoryChartInstance.destroy(); } catch (e) {}
        }
        window.employeeRequestHistoryChartInstance = new Chart(employeeRequestHistoryCanvas, {
            type: 'line',
            data: {
                labels: months,
                datasets: [
                    {
                        label: 'Leaves',
                        data: leavesByMonth,
                        backgroundColor: 'rgba(0, 93, 153, 0.2)',
                        borderColor: '#005d99',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: true
                    },
                    {
                        label: 'Permissions',
                        data: permissionsByMonth,
                        backgroundColor: 'rgba(23, 167, 74, 0.2)',
                        borderColor: '#17a74a',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: true,
                        text: 'Request History ' + currentYear
                    }
                }
            }
        });
    }
    
    // Manager Dashboard - Employee Attendance Chart
    const employeeAttendanceChartCanvas = document.getElementById('employeeAttendanceChart');
    if (employeeAttendanceChartCanvas) {
        let employeeData = [];
        try {
            // Try to get data from global variable first, then fallback to dataset
            employeeData = window.employeeAttendanceData || JSON.parse(employeeAttendanceChartCanvas.dataset.employees || '[]');
            if (!Array.isArray(employeeData)) {
                console.warn('Employee attendance data is not an array, using empty array');
                employeeData = [];
            }
        } catch (error) {
            console.error('Error accessing employee attendance data:', error);
            employeeData = [];
        }
        
        if (employeeData.length > 0) {
            const labels = employeeData.map(emp => emp.name);
            const presentDays = employeeData.map(emp => emp.present_days);
            const absentDays = employeeData.map(emp => emp.absent_days);
            
            if (window.employeeAttendanceChartInstance) {
                try { window.employeeAttendanceChartInstance.destroy(); } catch (e) {}
            }
            window.employeeAttendanceChartInstance = new Chart(employeeAttendanceChartCanvas, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Present Days',
                            data: presentDays,
                            backgroundColor: '#17a74a',
                            borderColor: '#17a74a',
                            borderWidth: 1
                        },
                        {
                            label: 'Absent Days',
                            data: absentDays,
                            backgroundColor: '#dc3545',
                            borderColor: '#dc3545',
                            borderWidth: 1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                        },
                        title: {
                            display: true,
                            text: 'Employee Attendance Overview'
                        }
                    }
                }
            });
        }
    }
});
