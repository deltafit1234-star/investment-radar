
import requests
r = requests.get(
    "https://huggingface.co/api/models",
    params={"sort": "trending", "limit": 5},
    headers={"User-Agent": "InvestmentRadar/1.0"},
    timeout=15
)
print(f"status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"count: {len(data)}")
    for m in data[:3]:
        print(f"  - {m.get('id', m.get('modelId', '?'))} | dl: {m.get('downloads', '?')}")
else:
    print(r.text[:300])
