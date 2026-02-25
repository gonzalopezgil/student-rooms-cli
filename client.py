"""
client.py — Backwards-compatibility shim.
The YugoClient has moved to providers/yugo.py.
"""
from providers.yugo import YugoClient, find_by_name  # noqa: F401
