"""Check ACR for a specific image tag using IPv4-only socket workaround."""

import socket
import sys

_orig = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [r for r in _orig(*a, **k) if r[0] == socket.AF_INET]

from azure.identity import AzureCliCredential  # noqa: E402
import requests  # noqa: E402

ACR = sys.argv[1] if len(sys.argv) > 1 else "acrbrokerworkbenchdevwnwtqzj2xcdts"
REPO = sys.argv[2] if len(sys.argv) > 2 else "brokerworkbench-backend"
TARGET = sys.argv[3] if len(sys.argv) > 3 else "backend-handoff-df3691d"
TENANT = "44e26be6-f73b-4438-8335-205b417d5b4d"
HOST = f"{ACR}.azurecr.io"

cred = AzureCliCredential()
arm = cred.get_token("https://management.azure.com/.default").token

r = requests.post(
    f"https://{HOST}/oauth2/exchange",
    data={"grant_type": "access_token", "service": HOST, "tenant": TENANT, "access_token": arm},
    timeout=30,
)
r.raise_for_status()
refresh = r.json()["refresh_token"]

r2 = requests.post(
    f"https://{HOST}/oauth2/token",
    data={
        "grant_type": "refresh_token",
        "service": HOST,
        "scope": f"repository:{REPO}:pull",
        "refresh_token": refresh,
    },
    timeout=30,
)
r2.raise_for_status()
acc = r2.json()["access_token"]

r3 = requests.get(
    f"https://{HOST}/acr/v1/{REPO}/_tags?n=100&orderby=timedesc",
    headers={"Authorization": f"Bearer {acc}"},
    timeout=30,
)
r3.raise_for_status()
tags = r3.json().get("tags", [])

print(f"Total tags in {REPO}: {len(tags)}")
match = [t for t in tags if t.get("name") == TARGET]
if match:
    t = match[0]
    print(f"FOUND target tag: {TARGET}")
    print(f"  digest:    {t.get('digest', '')}")
    print(f"  created:   {t.get('createdTime', '')}")
    print(f"  updated:   {t.get('lastUpdateTime', '')}")
else:
    print(f"NOT FOUND: {TARGET}")
    print("Most recent 10 tags:")
    for t in tags[:10]:
        name = t.get("name", "")
        created = t.get("createdTime", "")
        print(f"  {name}  created={created}")
