"""Hash an opaque demo token without placing it in shell history."""

import getpass
import sys

from mneme.core.security import token_sha256


def hash_nonempty_token(raw_token: str) -> str:
    """Return a token digest while refusing an accidental empty secret."""
    if not raw_token:
        raise ValueError("Demo token must not be empty")
    return token_sha256(raw_token)


def main() -> None:
    """Read a hidden token and print only its safe SHA-256 digest."""
    raw_token = getpass.getpass("Demo token: ")
    try:
        digest = hash_nonempty_token(raw_token)
    except ValueError as exception:
        print(str(exception), file=sys.stderr)
        raise SystemExit(2) from None
    print(digest)


if __name__ == "__main__":
    main()
