import urllib.request
import sys

try:
    with urllib.request.urlopen("http://localhost:8080/api/data", timeout=3) as resp:
        print("Status code:", resp.status)
        data = resp.read().decode("utf-8")
        print("Data preview:", data[:150])
except Exception as e:
    print("Connection failed:", e)
