import hashlib
import os
import secrets

def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC with SHA-256 and a random salt.
    Format of output: 'salt_hex:hash_hex'
    """
    salt = os.urandom(16)
    db_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}:{db_hash.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies a password against its PBKDF2-HMAC hashed counterpart.
    """
    try:
        if not hashed_password or ":" not in hashed_password:
            return False
        salt_hex, hash_hex = hashed_password.split(':')
        salt = bytes.fromhex(salt_hex)
        db_hash = bytes.fromhex(hash_hex)
        test_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return test_hash == db_hash
    except Exception:
        return False


def generate_session_token() -> str:
    """
    Generates a secure random token string for refresh tokens.
    """
    return secrets.token_urlsafe(32)


def generate_token_id() -> int:
    """
    Generates a secure random 63-bit positive integer
    suitable for use as a primary key in PostgreSQL BigInt (access_token_id).
    """
    return secrets.randbits(63)
