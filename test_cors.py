import urllib.request

for url in ["https://gamma-api.polymarket.com/markets?limit=1", "https://clob.polymarket.com/book?token_id=20915769520649892253891152116892558509040947708579979357606346851624640476483"]:
    req = urllib.request.Request(url, headers={"Origin": "http://localhost:3000", "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            headers = dict(resp.getheaders())
            print(f"URL: {url.split('?')[0]}")
            print(f"  Access-Control-Allow-Origin: {headers.get('access-control-allow-origin', 'N/A')}")
    except Exception as e:
        print(f"Error {url}: {e}")
