import requests, os

p_server = os.getenv("PROXY_SERVER")
p_user = os.getenv("PROXY_USER")
p_pass = os.getenv("PROXY_PASS")

# Force US location
p_user_us = f"{p_user}-country-us"

proxy_url = f"http://{p_user_us}:{p_pass}@{p_server}"
proxies = {"http": proxy_url, "https": proxy_url}

print(f"DEBUG: Testing BrightData vs Nextdoor...")
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    res = requests.get("https://nextdoor.com/search/?query=plumbing", proxies=proxies, timeout=30, verify=False)
    print(f"Status Code: {res.status_code}")
    print(f"Response Snippet (first 500 chars):")
    print("-" * 30)
    print(res.text[:500])
    print("-" * 30)
         
except Exception as e:
    print(f"❌ Proxy Error: {e}")
