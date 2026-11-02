"""Validate gateway configuration and an exclusive loopback bind; starts no service."""
import socket
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.gateway import config


def main():
    try:
        _, _, _, gateway_port, _ = config()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', gateway_port))
    except (ValueError, OSError):
        print('Preflight failed: invalid configuration or loopback port unavailable.', file=sys.stderr)
        return 2
    print('Configuration and loopback bind checked; this does not reserve the port or verify backend or HTTPS ingress.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
