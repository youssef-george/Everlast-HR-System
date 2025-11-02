# EverLast ERP Auto-Fetch System Documentation

## Overview

The EverLast ERP Auto-Fetch System is a comprehensive solution that automatically fetches and updates data for all user roles (Employee, Manager, Admin, Director) without requiring manual page refreshes. This system ensures that users always see the most up-to-date information in their dashboards and related pages.

## Features

### 🔄 Automatic Data Fetching
- **Real-time Updates**: Data is automatically fetched every 30 seconds
- **Smart Caching**: Only updates UI when data actually changes
- **Role-based Data**: Different data sets for different user roles
- **Page-specific Fetching**: Only fetches relevant data for current page

### 🎯 Role-Specific Functionality

#### Employee Role
- Leave balance updates
- Recent requests (leave & permission)
- Personal statistics
- Upcoming events

#### Manager Role
- Team data and statistics
- Pending approvals for team members
- Team attendance information
- Department analytics

#### Admin Role
- All pending requests across departments
- Department analytics and statistics
- User management data
- Company-wide attendance data

#### Director Role
- Company-wide analytics
- All requests overview
- Comprehensive statistics
- Executive dashboard data

### 🚀 Performance Features
- **Connection Health Monitoring**: Automatically handles connection issues
- **Exponential Backoff**: Smart retry logic for failed requests
- **Page Visibility API**: Pauses when page is not visible
- **Online/Offline Detection**: Adapts to network conditions

## Technical Architecture

### Frontend (JavaScript)
- **File**: `static/js/auto-fetch.js`
- **Class**: `AutoFetchSystem`
- **Dependencies**: None (vanilla JavaScript)

### Backend (Python/Flask)
- **File**: `routes/api.py`
- **Blueprint**: `api_bp`
- **Endpoints**: 15+ RESTful API endpoints

### Integration Points
- **Base Template**: `templates/base.html`
- **Dashboard Routes**: `routes/dashboard.py`
- **Dashboard Templates**: All role-specific templates

## API Endpoints

### Core Endpoints
| Endpoint | Method | Description | Roles |
|----------|--------|-------------|-------|
| `/api/dashboard/stats` | GET | Dashboard statistics | All |
| `/api/requests/recent` | GET | Recent requests | All |
| `/api/leave/requests` | GET | Leave requests | All |
| `/api/leave/types` | GET | Leave types | All |
| `/api/leave/balances` | GET | Leave balances | All |

### Role-Specific Endpoints
| Endpoint | Method | Description | Roles |
|----------|--------|-------------|-------|
| `/api/team/data` | GET | Team data | Manager+ |
| `/api/approvals/pending` | GET | Pending approvals | Manager+ |
| `/api/requests/all-pending` | GET | All pending requests | Admin+ |
| `/api/analytics/departments` | GET | Department analytics | Admin+ |
| `/api/users/management` | GET | User management | Admin+ |
| `/api/analytics/company` | GET | Company analytics | Director |
| `/api/requests/overview` | GET | Requests overview | Director |

### Attendance Endpoints
| Endpoint | Method | Description | Roles |
|----------|--------|-------------|-------|
| `/api/attendance/data` | GET | Attendance data | All |
| `/api/attendance/stats` | GET | Attendance statistics | All |

### Calendar Endpoints
| Endpoint | Method | Description | Roles |
|----------|--------|-------------|-------|
| `/api/calendar/upcoming` | GET | Upcoming events | All |

## Configuration

### JavaScript Configuration
```javascript
window.autoFetch = new AutoFetchSystem({
    fetchInterval: 30000,    // 30 seconds
    refreshInterval: 120000, // 2 minutes
    enabled: true,
    userRole: 'employee'     // Current user role
});
```

### Default Settings
- **Fetch Interval**: 30 seconds
- **Refresh Interval**: 2 minutes
- **Max Failures**: 3 attempts
- **Base Delay**: 5 seconds
- **Timeout**: 10 seconds per request

## Data Flow

### 1. Initialization
1. System detects user role from `data-user-role` attribute
2. Determines which pages need auto-fetch
3. Initializes `AutoFetchSystem` class
4. Starts background fetch intervals

### 2. Data Fetching
1. System checks if page is visible and not in form
2. Determines relevant endpoints based on current page and role
3. Fetches data from multiple endpoints in parallel
4. Compares with cached data to detect changes

### 3. UI Updates
1. Only updates UI elements when data has changed
2. Uses CSS selectors to target specific elements
3. Updates statistics, lists, and charts
4. Maintains user experience without disruption

## CSS Classes for Auto-Fetch

### Statistics Classes
- `.pending-leave-count` - Pending leave requests count
- `.pending-permission-count` - Pending permission requests count
- `.approved-leave-count` - Approved leave requests count
- `.approved-permission-count` - Approved permission requests count
- `.rejected-leave-count` - Rejected leave requests count
- `.rejected-permission-count` - Rejected permission requests count
- `.total-employees-count` - Total employees count
- `.total-departments-count` - Total departments count
- `.attendance-rate` - Attendance rate percentage
- `.total-attendance-today` - Present today count
- `.team-present-today` - Team present today count
- `.team-absent-today` - Team absent today count

### List Classes
- `.recent-leave-requests` - Recent leave requests list
- `.recent-permission-requests` - Recent permission requests list
- `.pending-approvals-list` - Pending approvals list
- `.all-pending-leave-requests` - All pending leave requests
- `.all-pending-permission-requests` - All pending permission requests

## Error Handling

### Connection Issues
- **Exponential Backoff**: Delays increase with each failure
- **Max Retries**: Stops after 3 consecutive failures
- **Graceful Degradation**: Continues working with cached data

### Network Problems
- **Online/Offline Detection**: Pauses when offline
- **Page Visibility**: Pauses when page is hidden
- **Timeout Handling**: 10-second timeout per request

### Data Issues
- **JSON Validation**: Validates response format
- **Null Checks**: Handles missing or null data
- **Fallback Values**: Uses default values when data unavailable

## Performance Considerations

### Optimization Strategies
1. **Data Caching**: Prevents unnecessary UI updates
2. **Parallel Requests**: Fetches multiple endpoints simultaneously
3. **Smart Fetching**: Only fetches relevant data for current page
4. **Debounced Updates**: Prevents rapid successive updates

### Memory Management
- **Cache Cleanup**: Automatically clears old cached data
- **Event Cleanup**: Removes event listeners on page unload
- **Interval Cleanup**: Clears intervals when system is destroyed

## Browser Compatibility

### Supported Browsers
- Chrome 60+
- Firefox 55+
- Safari 12+
- Edge 79+

### Required Features
- Fetch API
- Promise support
- ES6 Classes
- Page Visibility API
- Online/Offline events

## Testing

### Manual Testing
1. Login as different user roles
2. Navigate to different pages
3. Observe automatic data updates
4. Check browser console for errors

### Automated Testing
Run the test script:
```bash
python test_auto_fetch.py
```

### Test Coverage
- API endpoint accessibility
- JavaScript file loading
- Data format validation
- Error handling scenarios

## Troubleshooting

### Common Issues

#### Auto-fetch not working
1. Check browser console for JavaScript errors
2. Verify user role is correctly set
3. Ensure page is in the fetch pages list
4. Check network connectivity

#### Data not updating
1. Verify API endpoints are accessible
2. Check for CSRF token issues
3. Ensure user has proper permissions
4. Check for JavaScript errors

#### Performance issues
1. Reduce fetch interval
2. Check for memory leaks
3. Verify data caching is working
4. Monitor network requests

### Debug Mode
Enable debug logging by setting:
```javascript
window.autoFetch.debug = true;
```

## Security Considerations

### CSRF Protection
- All API requests include CSRF tokens
- Tokens are automatically extracted from meta tags
- Invalid tokens result in 403 errors

### Role-based Access
- Each endpoint checks user permissions
- Data is filtered based on user role
- Sensitive data is only accessible to authorized roles

### Rate Limiting
- Built-in request throttling
- Exponential backoff for failed requests
- Maximum retry limits

## Future Enhancements

### Planned Features
1. **WebSocket Support**: Real-time updates via WebSockets
2. **Push Notifications**: Browser notifications for important updates
3. **Offline Support**: Service worker for offline functionality
4. **Advanced Caching**: IndexedDB for persistent caching

### Performance Improvements
1. **Request Batching**: Combine multiple requests
2. **Data Compression**: Compress API responses
3. **CDN Integration**: Serve static assets from CDN
4. **Lazy Loading**: Load data only when needed

## Maintenance

### Regular Tasks
1. Monitor API endpoint performance
2. Check for JavaScript errors in logs
3. Update browser compatibility as needed
4. Review and optimize fetch intervals

### Updates
1. Test thoroughly before deploying changes
2. Maintain backward compatibility
3. Update documentation with changes
4. Notify users of significant updates

## Support

### Getting Help
1. Check this documentation first
2. Review browser console for errors
3. Test with different user roles
4. Contact system administrator

### Reporting Issues
When reporting issues, include:
1. User role and page where issue occurs
2. Browser and version
3. Console error messages
4. Steps to reproduce
5. Expected vs actual behavior

---

**Version**: 1.0.0  
**Last Updated**: January 2025  
**Maintainer**: EverLast ERP Development Team
