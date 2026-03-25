from cryptography.fernet import Fernet
import os


def get_fernet():
    key = os.environ.get('FERNET_KEY')
    if not key:
        raise ValueError('FERNET_KEY not set')
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return get_fernet().decrypt(ciphertext.encode()).decode()
