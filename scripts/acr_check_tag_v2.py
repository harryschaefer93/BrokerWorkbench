"""Check ACR for a specific tag via standard v2 Docker Registry API."""

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

# Use catalog scope to list repos
r2 = requests.post(
    f"https://{HOST}/oauth2/token",
    data={
        "grant_type": "refresh_token",
        "service": HOST,
        "scope": f"repository:{REPO}:pull registry:catalog:*",
        "refresh_token": refresh,
    },
    timeout=30,
)
r2.raise_for_status()
acc = r2.json()["access_token"]
headers = {"Authorization": f"Bearer {acc}"}

# v2 catalog
print("--- /v2/_catalog ---")
rc = requests.get(f"https://{HOST}/v2/_catalog", headers=headers, timeout=30)
print(f"  status={rc.status_code}  body={rc.text[:500]}")

# v2 tags list
print(f"--- /v2/{REPO}/tags/list ---")
rt = requests.get(f"https://{HOST}/v2/{REPO}/tags/list", headers=headers, timeout=30)
print(f"  status={rt.status_code}")
if rt.status_code == 200:
    tags = rt.json().get("tags", []) or []
    print(f"  total tags: {len(tags)}")
    if TARGET in tags:
        print(f"  FOUND target: {TARGET}")
    else:
        print(f"  NOT FOUND: {TARGET}")
        print(f"  recent (last 10): {sorted(tags)[-10:]}")
else:
    print(f"  body={rt.text[:500]}")

# Manifest check (most authoritative)
print(f"--- /v2/{REPO}/manifests/{TARGET} ---")
rm = requests.head(
    f"https://{HOST}/v2/{REPO}/manifests/{TARGET}",
    headers={**headers, "Accept": "application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json"},
    timeout=30,
)
print(f"  status={rm.status_code}  digest={rm.headers.get('Docker-Content-Digest','')}")
