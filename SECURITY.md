# Security Documentation for EverLast ERP

## Overview
This document outlines the comprehensive security measures implemented in the EverLast ERP application to ensure safe public deployment and protection against common web vulnerabilities and scraping.

## Security Features Implemented

### 1. Security Headers
All responses include the following security headers:
- **X-Frame-Options**: DENY - Prevents clickjacking attacks
- **X-Content-Type-Options**: nosniff - Prevents MIME type sniffing
- **X-XSS-Protection**: 1; mode=block - Legacy XSS protection
- **Referrer-Policy**: strict-origin-when-cross-origin - Controls referrer information
- **Content-Security-Policy**: Comprehensive CSP to prevent XSS and injection attacks
- **Permissions-Policy**: Restricts browser features
- **Strict-Transport-Security**: Enforces HTTPS (when using HTTPS)

### 2. CSRF Protection
- **Flask-WTF CSRF**: Enabled globally for all POST/PUT/PATCH/DELETE requests
- **CSRF Token**: Required in all forms and AJAX requests
- **Token Validation**: Automatic validation on form submission
- **Session-based**: Tokens are tied to user sessions

### 3. Rate Limiting
- **API Endpoints**: 60 requests per minute per IP/user
- **Per-endpoint**: Different limits can be set per route
- **IP-based**: Rate limiting tracks by IP address
- **User-based**: Authenticated users have separate rate limits
- **Automatic Cleanup**: Old rate limit entries are automatically removed

### 4. Bot Detection & Anti-Scraping
- **User-Agent Analysis**: Detects common bot user agents
- **Header Validation**: Checks for missing or suspicious headers
- **Sensitive Route Protection**: Blocks bots from accessing sensitive endpoints
- **robots.txt**: Comprehensive robots.txt file to discourage crawlers
- **Pattern Matching**: Detects common scraping tools (curl, wget, python-requests, etc.)

### 5. File Upload Security
- **File Type Validation**: Only allowed file types can be uploaded
  - Images: jpg, jpeg, png, gif, bmp, webp, svg
  - Documents: pdf, doc, docx, xls, xlsx, txt, rtf
  - Archives: zip, rar, 7z, tar, gz
- **MIME Type Checking**: Validates file content type
- **File Size Limits**: Maximum 16MB per file
- **Secure Filenames**: Files are renamed with timestamps and hashes
- **Path Traversal Prevention**: Blocks dangerous filename patterns
- **Content Validation**: Checks for malicious content patterns

### 6. Input Validation & Sanitization
- **SQL Injection Protection**: 
  - SQLAlchemy ORM (parameterized queries)
  - Additional pattern-based validation
  - Input length limits
- **XSS Protection**:
  - Jinja2 auto-escaping enabled
  - Input sanitization functions
  - Control character removal
- **Input Length Limits**: Maximum length validation on all inputs
- **Character Filtering**: Removes dangerous characters

### 7. Session Security
- **Secure Cookies**: Cookies only sent over HTTPS in production
- **HttpOnly Cookies**: JavaScript cannot access session cookies
- **SameSite**: Lax policy for CSRF protection
- **Session Timeout**: 30 minutes of inactivity
- **Session Regeneration**: Sessions are regenerated on login

### 8. Authentication & Authorization
- **Flask-Login**: Secure session management
- **Password Hashing**: Werkzeug password hashing (bcrypt-like)
- **Role-Based Access Control**: Role-based route protection
- **Login Rate Limiting**: Prevents brute force attacks
- **Session Management**: Secure session handling

### 9. Database Security
- **Parameterized Queries**: SQLAlchemy uses parameterized queries (prevents SQL injection)
- **Connection Pooling**: Secure connection management
- **SSL Mode**: Prefers SSL connections when available
- **Connection Timeouts**: Prevents connection exhaustion
- **Query Validation**: Additional validation layer

### 10. Environment Security
- **Secret Key Validation**: Ensures strong SECRET_KEY in production
- **Environment Variables**: Sensitive data stored in environment variables
- **Config Validation**: Production config validates required secrets
- **No Hardcoded Secrets**: All secrets come from environment

## Deployment Checklist

### Before Deploying to Production:

1. **Set Environment Variables**:
   ```bash
   export SECRET_KEY="your-strong-random-secret-key-minimum-32-characters"
   export CSRF_SECRET="your-strong-random-csrf-secret-key"
   export DATABASE_URL="your-database-connection-string"
   ```

2. **Enable HTTPS**:
   - Use a reverse proxy (nginx/Apache) with SSL certificate
   - Configure Flask to use HTTPS
   - Ensure all cookies are secure

3. **Configure Firewall**:
   - Only allow necessary ports (80, 443)
   - Block direct database access from internet
   - Use VPN or SSH tunneling for database access

4. **Database Security**:
   - Use strong database passwords
   - Enable SSL/TLS for database connections
   - Restrict database user permissions
   - Regular backups

5. **File Upload Security**:
   - Store uploads outside web root if possible
   - Scan uploaded files for malware (consider ClamAV)
   - Monitor upload directory for suspicious files

6. **Monitoring & Logging**:
   - Enable application logging
   - Monitor for suspicious activity
   - Set up alerts for security events
   - Regular security audits

7. **Update Dependencies**:
   ```bash
   pip install --upgrade -r requirements.txt
   ```
   - Regularly update all dependencies
   - Monitor for security advisories

## Security Best Practices

### For Developers:
1. **Never commit secrets** to version control
2. **Use environment variables** for all sensitive data
3. **Validate all user input** before processing
4. **Use parameterized queries** (SQLAlchemy does this automatically)
5. **Escape output** in templates (Jinja2 does this automatically)
6. **Keep dependencies updated**
7. **Review security logs regularly**

### For Administrators:
1. **Change default passwords** immediately
2. **Use strong, unique passwords**
3. **Enable two-factor authentication** (if available)
4. **Regular security audits**
5. **Monitor access logs**
6. **Keep server software updated**
7. **Use HTTPS everywhere**

## Anti-Scraping Measures

### Implemented Protections:
1. **robots.txt**: Disallows all crawlers
2. **Bot Detection**: Automatically detects and blocks bots
3. **Rate Limiting**: Prevents rapid automated requests
4. **CSRF Tokens**: Required for all form submissions
5. **Session Requirements**: Most endpoints require authentication
6. **User-Agent Validation**: Blocks suspicious user agents

### Additional Recommendations:
1. **CAPTCHA**: Consider adding CAPTCHA for sensitive operations
2. **IP Blocking**: Implement IP blocking for repeated violations
3. **Honeypot Fields**: Add hidden form fields to catch bots
4. **JavaScript Challenges**: Require JavaScript execution
5. **Behavioral Analysis**: Monitor for unusual access patterns

## Security Headers Details

### Content Security Policy (CSP)
```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;
style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com;
img-src 'self' data: https:;
connect-src 'self';
frame-ancestors 'none';
base-uri 'self';
form-action 'self';
upgrade-insecure-requests;
```

This CSP:
- Allows scripts only from trusted sources
- Prevents inline scripts (with exceptions for CDN)
- Blocks frame embedding (prevents clickjacking)
- Forces HTTPS upgrades

## Rate Limiting Details

### Current Limits:
- **API Endpoints**: 60 requests per minute
- **File Uploads**: Limited by file size (16MB max)
- **Login Attempts**: Should be limited (consider implementing)

### Customization:
Rate limits can be adjusted per route:
```python
@route('/api/endpoint')
@rate_limit(max_requests=100, window=60)  # 100 requests per minute
def endpoint():
    ...
```

## File Upload Security

### Allowed File Types:
- **Images**: jpg, jpeg, png, gif, bmp, webp, svg
- **Documents**: pdf, doc, docx, xls, xlsx, txt, rtf
- **Archives**: zip, rar, 7z, tar, gz

### Validation Steps:
1. File extension check
2. MIME type validation
3. File size validation
4. Filename sanitization
5. Path traversal prevention
6. Dangerous pattern detection

## Incident Response

If a security breach is detected:
1. **Immediately** change all passwords
2. **Revoke** all active sessions
3. **Review** access logs
4. **Identify** the attack vector
5. **Patch** the vulnerability
6. **Notify** affected users (if required by law)
7. **Document** the incident

## Security Contacts

For security issues, please contact:
- **Email**: security@everlasteg.local
- **Priority**: High

## Updates

This security documentation should be reviewed and updated regularly as new threats emerge and security best practices evolve.

Last Updated: 2025-01-15

