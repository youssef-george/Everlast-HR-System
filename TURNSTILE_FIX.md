# Fixing Cloudflare Turnstile Error 110200

## Problem
Error 110200 means your Turnstile site key is not configured for the domain you're using.

## Solution

### Step 1: Go to Cloudflare Dashboard
1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Navigate to **Turnstile** section
3. Find your site key: `0x4AAAAAACAhO6remiAiUqI9`

### Step 2: Update Domain Settings
1. Click on your Turnstile site
2. In the **Domains** section, add:
   - `hr.everlastdashboard.com`
   - `everlastdashboard.com` (if you want it to work on the main domain too)
3. Save the changes

### Step 3: Wait for Propagation
- Changes usually take effect within a few minutes
- Clear your browser cache
- Refresh the login page

## Alternative: Use Test Keys (For Development Only)

If you want to test without domain restrictions, you can use Cloudflare's test keys:

**Test Site Key (always passes):**
```
1x00000000000000000000AA
```

**Test Secret Key (always passes):**
```
1x0000000000000000000000000000000AA
```

⚠️ **Warning:** Test keys should ONLY be used for development/testing. They don't provide real bot protection.

## Verify Fix

After updating the domain:
1. Clear browser cache
2. Refresh the login page
3. Check browser console - error 110200 should be gone
4. The Turnstile widget should appear and work correctly

