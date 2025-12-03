#!/usr/bin/env python3
"""
NY Times Cookie Extraction Helper
Run this in your browser console to get cookies
"""

# JavaScript code to run in browser console
BROWSER_CONSOLE_CODE = """
// Run this in your browser console while logged into NY Times
function extractNYTimesCookies() {
    const cookies = document.cookie.split(';').map(cookie => {
        const [name, value] = cookie.trim().split('=');
        return {
            name: name,
            value: value,
            domain: '.nytimes.com',
            path: '/',
            secure: true,
            httpOnly: false
        };
    }).filter(cookie => 
        cookie.name.startsWith('nyt') || 
        cookie.name.includes('auth') || 
        cookie.name.includes('session')
    );
    
    console.log('Copy this cookie data:');
    console.log(JSON.stringify(cookies, null, 2));
    return cookies;
}

extractNYTimesCookies();
"""

def create_cookie_template():
    """Create a template for manual cookie entry"""
    template = """
# NY Times Cookies Template
# Replace the values with your actual cookie data

NYTIMES_COOKIES = [
    {
        'name': 'nyt-a',
        'value': 'PASTE_YOUR_NYT_A_VALUE_HERE',
        'domain': '.nytimes.com',
        'path': '/',
        'secure': True,
        'httpOnly': True
    },
    {
        'name': 'nyt-s', 
        'value': 'PASTE_YOUR_NYT_S_VALUE_HERE',
        'domain': '.nytimes.com',
        'path': '/',
        'secure': True,
        'httpOnly': False
    },
    {
        'name': 'NYT-S',
        'value': 'PASTE_YOUR_NYT_S_CAPS_VALUE_HERE',
        'domain': '.nytimes.com',
        'path': '/',
        'secure': True,
        'httpOnly': False
    }
]
"""
    
    with open('/app/nytimes_cookies_template.py', 'w') as f:
        f.write(template)
    
    print("Cookie template created at /app/nytimes_cookies_template.py")
    print("\nTo extract cookies:")
    print("1. Open NY Times in browser and log in")
    print("2. Press F12 → Console tab")
    print("3. Paste this code:")
    print(BROWSER_CONSOLE_CODE)
    print("4. Copy the output and update the template")

if __name__ == "__main__":
    create_cookie_template()