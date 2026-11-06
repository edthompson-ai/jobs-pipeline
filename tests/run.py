"""Test entry point used by `make test`.

Blocks all outbound network connections for the whole run, so any test that
accidentally reaches for a real API fails loudly instead of spending money.
"""
import os
import socket
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("network access is disabled during tests")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover("tests", top_level_dir=ROOT)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
