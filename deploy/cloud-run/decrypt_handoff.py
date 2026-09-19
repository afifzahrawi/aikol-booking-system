"""Decrypt a one-time administrator handoff token supplied through environment variables."""

import os
import sys

from cryptography.fernet import Fernet, InvalidToken


def main() -> int:
    try:
        key = os.environ["AIKOL_HANDOFF_KEY"].encode()
        token = os.environ["AIKOL_HANDOFF_TOKEN"].encode()
        password = Fernet(key).decrypt(token).decode()
    except (KeyError, ValueError, InvalidToken):
        print("Invalid or unavailable administrator handoff token.", file=sys.stderr)
        return 1

    print(password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
