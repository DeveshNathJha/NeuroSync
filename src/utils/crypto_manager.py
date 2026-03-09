import os
from cryptography.fernet import Fernet
from config.settings import settings
from src.utils.logger import logger

class CryptoManager:
    """
    ENTERPRISE SECURITY MODULE (HIPAA COMPLIANT)
    --------------------------------------------
    Manages encryption keys and secures sensitive patient data at rest.
    Arguments:
        key_path: Path to the .key file. 
    """
    
    def __init__(self, key_path: str = "config/secret.key"):
        self.key_path = key_path
        self.key = self._load_or_generate_key()
        self.cipher = Fernet(self.key)

    def _load_or_generate_key(self) -> bytes:
        """Loads existing key or generates a new one if missing."""
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as key_file:
                return key_file.read()
        else:
            logger.warning("No encryption key found. Generating new master key.")
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as key_file:
                key_file.write(key)
            return key

    def encrypt_data(self, data: str) -> bytes:
        """Encrypts a string payload."""
        return self.cipher.encrypt(data.encode())

    def decrypt_data(self, encrypted_data: bytes) -> str:
        """Decrypts a bytes payload."""
        return self.cipher.decrypt(encrypted_data).decode()
