# 🔄 EverLast ERP - Auto-Fetch System

## Overview

The auto-fetch system automatically updates data on all dashboard pages without requiring manual refresh or sync button clicks. It provides real-time data updates for all user roles (Employee, Manager, Admin, Director).

## ✨ Features

- **🔄 Automatic Data Updates**: Fetches data every 15 seconds
- **👥 Role-Based Data**: Different data for different user roles
- **📊 Visual Status Indicator**: Small indicator in top-right corner
- **🛡️ Error Handling**: Smart retry logic with exponential backoff
- **⚡ Performance Optimized**: Only updates UI when data changes
- **🌐 Connection Aware**: Pauses when offline, resumes when online
- **👁️ Visibility Aware**: Pauses when page is hidden

## 🚀 How It Works

### 1. **Initialization**
- System detects user role from `data-user-role` attribute
- Initializes appropriate data fetching for the role
- Starts automatic fetching every 15 seconds

### 2. **Data Fetching**
- Fetches relevant data based on current page and user role
- Uses parallel requests for better performance
- Caches data to avoid unnecessary UI updates

### 3. **UI Updates**
- Updates specific elements only when data changes
- Smooth transitions with visual feedback
- Maintains user experience during updates

## 📁 Files Modified/Created

### New Files:
- `static/js/auto-fetch.js` - Main auto-fetch system
- `routes/api.py` - API endpoints for data fetching
- `test_auto_fetch_simple.html` - Simple test page
- `test_api_endpoints.py` - API testing script

### Modified Files:
- `templates/base.html` - Added auto-fetch script
- `routes/dashboard.py` - Added data attributes
- `templates/dashboard/*.html` - Added CSS classes for targeting
- `app.py` - Registered API blueprint

## 🎯 Data Types Auto-Fetched

### For All Roles:
- Dashboard statistics
- Leave request counts
- Permission request counts
- Recent activity

### Role-Specific:
- **Employee**: Personal leave balance, recent requests
- **Manager**: Team statistics, pending approvals
- **Admin**: Company-wide statistics, all requests
- **Director**: Executive dashboard, analytics

## 🔧 Configuration

### Intervals (in `static/js/auto-fetch.js`):
```javascript
fetchInterval: 15000,    // 15 seconds - data fetch
refreshInterval: 60000,  // 1 minute - page refresh
```

### Debug Mode:
```javascript
debug: true  // Enables console logging
```

## 🧪 Testing

### 1. **Simple Test Page**
Open `test_auto_fetch_simple.html` in your browser to see:
- Auto-fetch system initialization
- Real-time data updates
- Console logs
- Status indicator

### 2. **API Testing**
Run the API test script:
```bash
python test_api_endpoints.py
```

### 3. **Browser Console**
Check browser console for detailed logs:
- System initialization
- Fetch operations
- Error messages
- Performance metrics

## 📊 Status Indicator

A small colored dot in the top-right corner shows system status:
- 🟢 **Green**: System running, data up-to-date
- 🟡 **Yellow (Pulsing)**: Currently fetching data
- 🔴 **Red**: Error occurred
- ⚫ **Gray**: System paused

## 🛠️ Troubleshooting

### Auto-Fetch Not Working?

1. **Check Console Logs**:
   ```javascript
   // Look for these messages:
   "🔄 Auto-fetch system initialized for [role] role"
   "🚀 Starting auto-fetch with 15s interval"
   "📡 Fetching X data sources for [role] role"
   ```

2. **Verify User Role**:
   ```html
   <!-- Check if this is set correctly -->
   <body data-user-role="admin">
   ```

3. **Check API Endpoints**:
   - Ensure `routes/api.py` is registered
   - Verify API endpoints return data
   - Check authentication

4. **Network Issues**:
   - Check browser network tab
   - Verify server is running
   - Check for CORS issues

### Common Issues:

**Issue**: "No data to fetch for current page"
**Solution**: Ensure you're on a supported page (dashboard, leave, attendance, etc.)

**Issue**: "Auto-fetch system failed to initialize"
**Solution**: Check browser console for JavaScript errors

**Issue**: "Fetch operation failed"
**Solution**: Check API endpoints and authentication

## 🔄 Manual Control

You can control the auto-fetch system manually:

```javascript
// Pause auto-fetch
window.autoFetch.pause();

// Resume auto-fetch
window.autoFetch.resume();

// Force immediate fetch
window.autoFetch.performFetch();

// Destroy system
window.autoFetch.destroy();
```

## 📈 Performance

- **Memory Usage**: Minimal - uses efficient caching
- **Network Usage**: Optimized - only fetches changed data
- **CPU Usage**: Low - uses efficient intervals
- **Battery Impact**: Minimal - pauses when page hidden

## 🔒 Security

- **CSRF Protection**: All requests include CSRF tokens
- **Role-Based Access**: Users only see their authorized data
- **Input Validation**: All API endpoints validate input
- **Error Handling**: Sensitive data not exposed in errors

## 🚀 Future Enhancements

- WebSocket support for real-time updates
- Push notifications for important changes
- Customizable fetch intervals per user
- Advanced caching strategies
- Offline data synchronization

## 📞 Support

If you encounter issues:

1. Check browser console for error messages
2. Verify API endpoints are working
3. Test with the provided test files
4. Check network connectivity
5. Verify user authentication

---

**Note**: The auto-fetch system is designed to be non-intrusive and efficient. It will automatically pause when the page is not visible and resume when needed.
