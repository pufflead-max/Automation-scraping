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
    "hostOnly": false,
    "httpOnly": true,
    "name": "ar_debug",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": true,
    "storeId": "0",
    "value": "1",
    "id": 1
},
{
    "domain": ".facebook.com",
    "expirationDate": 1806409168.091581,
    "hostOnly": false,
    "httpOnly": false,
    "name": "c_user",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "61575526702971",
    "id": 2
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
    "id": 3
},
{
    "domain": ".facebook.com",
    "expirationDate": 1782649168.09166,
    "hostOnly": false,
    "httpOnly": true,
    "name": "fr",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "12nKUqWV4na5tbkWV.AWfUNrfPSA3hQZuhWauAki5d1HTyYPBKhkl_zlUOoiXi_ZmzSMc.BpympP..AAA.0.0.BpympP.AWct5C_X-xsQO-gMW_J-is_VgFw",
    "id": 4
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
    "id": 5
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
    "value": "C%7B%22t3%22%3A%5B%5D%2C%22utc3%22%3A1774873171051%2C%22v%22%3A1%7D",
    "id": 6
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
    "id": 7
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
    "id": 8
},
{
    "domain": ".facebook.com",
    "expirationDate": 1809433166.707415,
    "hostOnly": false,
    "httpOnly": true,
    "name": "sb",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "-Yi6afay1zEEotsLGNKYUKIM",
    "id": 9
},
{
    "domain": ".facebook.com",
    "expirationDate": 1775477970,
    "hostOnly": false,
    "httpOnly": false,
    "name": "wd",
    "path": "/",
    "sameSite": "lax",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "1920x966",
    "id": 10
},
{
    "domain": ".facebook.com",
    "expirationDate": 1806409168.091707,
    "hostOnly": false,
    "httpOnly": true,
    "name": "xs",
    "path": "/",
    "sameSite": "no_restriction",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "36%3AgDZlHY9eMWf94A%3A2%3A1774873165%3A-1%3A-1%3A%3AAcw8vVQ0Scx0axNKIP4mjPEYpOWNs2lXyaloBXWP-A",
    "id": 11
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
