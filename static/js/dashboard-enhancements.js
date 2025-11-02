// Dashboard Enhancements for EverLast ERP
// Enhanced UI interactions and chart functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize dashboard enhancements
    initializeChartInteractions();
    initializeButtonGroups();
    initializeDropdowns();
    initializeLoadingStates();
    initializeStatsAnimations();
});

// Chart Interaction Functions
function initializeChartInteractions() {
    // Department Analytics Chart Toggle
    const chartButtons = document.querySelectorAll('[data-chart]');
    chartButtons.forEach(button => {
        button.addEventListener('click', function() {
            const chartType = this.getAttribute('data-chart');
            const card = this.closest('.employee-card');
            
            // Update active state
            card.querySelectorAll('[data-chart]').forEach(btn => {
                btn.classList.remove('active');
            });
            this.classList.add('active');
            
            // Show loading state
            const chartContainer = card.querySelector('.chart-container');
            if (chartContainer) {
                const loading = chartContainer.querySelector('.chart-loading');
                if (loading) {
                    loading.classList.remove('d-none');
                }
            }
            
            // Simulate chart update (replace with actual chart update logic)
            setTimeout(() => {
                if (chartContainer) {
                    const loading = chartContainer.querySelector('.chart-loading');
                    if (loading) {
                        loading.classList.add('d-none');
                    }
                }
                console.log(`Switched to ${chartType} chart`);
            }, 1000);
        });
    });
}

// Button Group Functions
function initializeButtonGroups() {
    const buttonGroups = document.querySelectorAll('.btn-group');
    buttonGroups.forEach(group => {
        const buttons = group.querySelectorAll('.employee-btn');
        buttons.forEach(button => {
            button.addEventListener('click', function() {
                // Remove active class from siblings
                buttons.forEach(btn => btn.classList.remove('active'));
                // Add active class to clicked button
                this.classList.add('active');
            });
        });
    });
}

// Dropdown Functions
function initializeDropdowns() {
    const dropdowns = document.querySelectorAll('.dropdown');
    dropdowns.forEach(dropdown => {
        const button = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        
        if (button && menu) {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                // Close other dropdowns
                document.querySelectorAll('.dropdown-menu.show').forEach(openMenu => {
                    if (openMenu !== menu) {
                        openMenu.classList.remove('show');
                    }
                });
                
                // Toggle current dropdown
                menu.classList.toggle('show');
            });
        }
    });
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
                menu.classList.remove('show');
            });
        }
    });
}

// Loading State Functions
function initializeLoadingStates() {
    // Add loading states to charts
    const charts = document.querySelectorAll('canvas');
    charts.forEach(chart => {
        const container = chart.closest('.chart-container');
        if (container) {
            const loading = container.querySelector('.chart-loading');
            if (loading) {
                // Show loading on chart hover
                chart.addEventListener('mouseenter', function() {
                    loading.classList.remove('d-none');
                });
                
                chart.addEventListener('mouseleave', function() {
                    loading.classList.add('d-none');
                });
            }
        }
    });
}

// Stats Animation Functions
function initializeStatsAnimations() {
    const statCards = document.querySelectorAll('.employee-stat-card');
    
    // Only proceed if stat cards exist
    if (statCards.length > 0) {
        // Intersection Observer for animation on scroll
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-in');
                }
            });
        }, {
            threshold: 0.1
        });
        
        statCards.forEach(card => {
            if (card && card instanceof Node) {
                observer.observe(card);
                
                // Add hover effects
                card.addEventListener('mouseenter', function() {
                    this.style.transform = 'translateY(-5px) scale(1.02)';
                });
                
                card.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateY(0) scale(1)';
                });
            }
        });
    }
}

// Enhanced Table Functions
function initializeTableEnhancements() {
    const tables = document.querySelectorAll('.employee-table');
    tables.forEach(table => {
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach((row, index) => {
            // Add staggered animation
            row.style.animationDelay = `${index * 0.1}s`;
            
            // Add click effects
            row.addEventListener('click', function() {
                rows.forEach(r => r.classList.remove('table-row-selected'));
                this.classList.add('table-row-selected');
            });
        });
    });
}

// Real-time Updates Simulation
function simulateRealTimeUpdates() {
    // Update stats every 1 minute
    setInterval(() => {
        const statValues = document.querySelectorAll('.employee-stat-value');
        statValues.forEach(stat => {
            const currentValue = parseInt(stat.textContent) || 0;
            const newValue = currentValue + Math.floor(Math.random() * 3) - 1;
            if (newValue >= 0) {
                stat.textContent = newValue;
                stat.style.color = '#667eea';
                setTimeout(() => {
                    stat.style.color = '';
                }, 1000);
            }
        });
    }, 60000); // 1 minute
}

// Initialize all enhancements
function initializeAllEnhancements() {
    initializeChartInteractions();
    initializeButtonGroups();
    initializeDropdowns();
    initializeLoadingStates();
    initializeStatsAnimations();
    initializeTableEnhancements();
    simulateRealTimeUpdates();
}

// Export functions for global use
window.DashboardEnhancements = {
    initializeChartInteractions,
    initializeButtonGroups,
    initializeDropdowns,
    initializeLoadingStates,
    initializeStatsAnimations,
    initializeTableEnhancements,
    simulateRealTimeUpdates,
    initializeAllEnhancements
};

