from hashlib import sha256


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()
