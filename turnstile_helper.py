"""
Cloudflare Turnstile Helper
Handles Turnstile CAPTCHA verification
"""
import requests
import logging
from flask import current_app


def verify_turnstile_token(token, remote_ip=None):
    """
    Verify a Cloudflare Turnstile token
    
    Args:
        token: The Turnstile token from the client
        remote_ip: Optional client IP address for additional verification
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not token:
        return False, "Turnstile token is missing"
    
    # Get Turnstile secret key from config
    secret_key = current_app.config.get('TURNSTILE_SECRET_KEY')
    
    if not secret_key:
        logging.warning("TURNSTILE_SECRET_KEY not configured, skipping verification")
        return True, None  # Allow if not configured (for development)
    
    # Prepare verification request
    verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    
    data = {
        'secret': secret_key,
        'response': token
    }
    
    if remote_ip:
        data['remoteip'] = remote_ip
    
    try:
        # Make verification request
        response = requests.post(verify_url, data=data, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('success'):
            return True, None
        else:
            error_codes = result.get('error-codes', [])
            error_message = ', '.join(error_codes) if error_codes else 'Verification failed'
            logging.warning(f"Turnstile verification failed: {error_message}")
            return False, error_message
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Turnstile verification request failed: {str(e)}")
        # In case of network error, allow the request (fail open for availability)
        # In production, you might want to fail closed
        return True, None
    except Exception as e:
        logging.error(f"Turnstile verification error: {str(e)}")
        return False, f"Verification error: {str(e)}"

