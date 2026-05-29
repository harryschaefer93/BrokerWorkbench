"""Temporary helper: get an ACR refresh token using IPv4-only socket resolution.

Workaround for Windows dual-stack bug where Python urllib3 fails with WinError 10048
on outbound to *.azurecr.io despite IPv4 connectivity being fine.

Usage:
    python scripts/acr_login_ipv4.py <acr-name>
Outputs the refresh token to stdout (suitable for piping to `docker login --password-stdin`).
"""

import socket
import sys

_orig_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [r for r in _orig_getaddrinfo(*a, **k) if r[0] == socket.AF_INET]

from azure.identity import AzureCliCredential  # noqa: E402
import requests  # noqa: E402

ACR_NAME = sys.argv[1] if len(sys.argv) > 1 else "acrbrokerworkbenchdev2qdxa3smrnc7a"
TENANT = "44e26be6-f73b-4438-8335-205b417d5b4d"

cred = AzureCliCredential()
arm_token = cred.get_token("https://management.azure.com/.default").token

acr_host = f"{ACR_NAME}.azurecr.io"
r = requests.post(
    f"https://{acr_host}/oauth2/exchange",
    data={
        "grant_type": "access_token",
        "service": acr_host,
        "tenant": TENANT,
        "access_token": arm_token,
    },
    timeout=30,
)
r.raise_for_status()
print(r.json()["refresh_token"])
