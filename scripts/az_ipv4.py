"""Run `az` commands with IPv4-only socket resolution to dodge the Windows
WinError 10048 dual-stack bug.

Usage:
    python scripts/az_ipv4.py acr build -r <acr> -t <tag> -f <Dockerfile> <ctx> --no-logs
"""
import runpy
import socket
import sys

_orig = socket.getaddrinfo
socket.getaddrinfo = (
    lambda *a, **k: [r for r in _orig(*a, **k) if r[0] == socket.AF_INET]
)

# Shift our wrapper out of argv so azure.cli sees its real args
sys.argv = ["az"] + sys.argv[1:]
runpy.run_module("azure.cli", run_name="__main__")
