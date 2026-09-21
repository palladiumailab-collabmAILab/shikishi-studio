"""Generate a high-entropy Shikishi Studio LAN authentication token."""

import secrets

if __name__ == "__main__":
    print(secrets.token_urlsafe(32))
