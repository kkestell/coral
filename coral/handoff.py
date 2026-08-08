"""The encrypted API-key handoff between the resolve and review jobs."""

from cryptography.fernet import Fernet, InvalidToken


def encryption_key(value: str) -> str:
    """Validate the caller's Fernet key and return it."""
    try:
        Fernet(value.encode())
    except ValueError as error:
        raise RuntimeError("CORAL_KEY_ENCRYPTION_KEY must be a valid Fernet key.") from error
    return value


def encrypt(key: str, plaintext: str) -> str:
    """Encrypt one API key into the one-line token that crosses jobs."""
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def decrypt(key: str, token: str) -> str:
    """Authenticate and decrypt the token in the receiving runner process."""
    try:
        return Fernet(key.encode()).decrypt(token.encode()).decode()
    except InvalidToken as error:
        raise RuntimeError(
            "The encrypted OpenRouter API key and CORAL_KEY_ENCRYPTION_KEY do not match."
        ) from error


def review_key(plain: str, token: str, key: str) -> str:
    """Select the plain path or open the encrypted path for review."""
    if plain and token:
        raise RuntimeError("Coral received both a plain and an encrypted OpenRouter API key.")
    if plain:
        return plain
    if not token:
        raise RuntimeError("Coral received neither a plain nor an encrypted OpenRouter API key.")
    return decrypt(encryption_key(key), token)
