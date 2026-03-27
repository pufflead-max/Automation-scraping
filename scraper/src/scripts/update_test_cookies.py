import sys
import os
import json

# Add src to path so we can import user_credential_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_credential_manager import UserCredentialManager
from dotenv import load_dotenv

def main():
    load_dotenv()
    
    cookies = json.loads("""
[
{
    "domain": ".facebook.com",
    "expirationDate": 1806127666.057401,
    "hostOnly": false,
    "httpOnly": false,
    "name": "c_user",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "61578516027016",
    "id": 1
},
{
    "domain": ".facebook.com",
    "expirationDate": 1808390776.853632,
    "hostOnly": false,
    "httpOnly": true,
    "name": "datr",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "eIK6aWmR_wwBqsXxH0-1iOKW",
    "id": 2
},
{
    "domain": ".facebook.com",
    "expirationDate": 1782367666.057462,
    "hostOnly": false,
    "httpOnly": true,
    "name": "fr",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "1XlDaSaYDEPxC7Eyf.AWdIMgRlGG0tDemzAJxLd8LrXCWpniBUYkFolxrzUBW6kE1CyiQ.Bpxh6x..AAA.0.0.Bpxh6x.AWdo_AjiOskCVLqWBJcIIQ2JEUE",
    "id": 3
},
{
    "domain": ".facebook.com",
    "expirationDate": 1775021942.686196,
    "hostOnly": false,
    "httpOnly": false,
    "name": "locale",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "en_GB",
    "id": 4
},
{
    "domain": ".facebook.com",
    "hostOnly": false,
    "httpOnly": false,
    "name": "presence",
    "path": "/",
    "sameSite": "unspecified",
    "secure": true,
    "session": true,
    "storeId": "0",
    "value": "C%7B%22t3%22%3A%5B%5D%2C%22utc3%22%3A1774591669091%2C%22v%22%3A1%7D",
    "id": 5
},
{
    "domain": ".facebook.com",
    "expirationDate": 1808392442.685121,
    "hostOnly": false,
    "httpOnly": true,
    "name": "ps_l",
    "path": "/",
    "sameSite": "lax",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "1",
    "id": 6
},
{
    "domain": ".facebook.com",
    "expirationDate": 1808392442.685208,
    "hostOnly": false,
    "httpOnly": true,
    "name": "ps_n",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "1",
    "id": 7
},
{
    "domain": ".facebook.com",
    "expirationDate": 1809092994.417559,
    "hostOnly": false,
    "httpOnly": true,
    "name": "sb",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "-Yi6afay1zEEotsLGNKYUKIM",
    "id": 8
},
{
    "domain": ".facebook.com",
    "expirationDate": 1775196468,
    "hostOnly": false,
    "httpOnly": false,
    "name": "wd",
    "path": "/",
    "sameSite": "lax",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "1920x966",
    "id": 9
},
{
    "domain": ".facebook.com",
    "expirationDate": 1806127666.057492,
    "hostOnly": false,
    "httpOnly": true,
    "name": "xs",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "41%3AaGipM06eoSjYDA%3A2%3A1774532992%3A-1%3A-1%3A%3AAcyMMd-RcutGk8PE-RVET8O9-L4HEp_pL-tKQGye2A",
    "id": 10
}
]
""")

    target_email = os.getenv("FACEBOOK_EMAIL", "anirudh@lnwebworks.com")
    print(f"Update cookies for user: {target_email} for platform 'facebook'")
    manager = UserCredentialManager()
    success = manager.save_cookies(user_email=target_email, platform="facebook", cookies=cookies)
    
    if success:
        print("Successfully updated facebook cookies in MongoDB (user_cookies).")
    else:
        print("Failed to update cookies.")

if __name__ == "__main__":
    main()
