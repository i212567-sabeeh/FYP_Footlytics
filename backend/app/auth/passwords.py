from functools import lru_cache
from secrets import token_urlsafe

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hasher.verify(password, hashed_password)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """Unknown accounts still perform password verification to limit timing leaks."""
    return hash_password(token_urlsafe(32))
