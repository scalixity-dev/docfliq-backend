from passlib.context import CryptContext

context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return context.verify(plain, hashed)
