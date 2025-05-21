from cryptography.fernet import Fernet
from .config import settings
import base64

# Ensure the APP_SECRET_KEY is a valid Fernet key (URL-safe base64-encoded 32-byte key)
# For simplicity, we'll assume settings.APP_SECRET_KEY is already in this format.
# In a real app, you might generate one if not set or validate its format.
# For example, to generate a key: Fernet.generate_key().decode()
# For this setup, we expect APP_SECRET_KEY to be the direct Fernet key string.

try:
    # The key must be url-safe base64 encoded
    key = settings.APP_SECRET_KEY.encode()
    # Validate if the key is 32 bytes url-safe base64-encoded
    if len(base64.urlsafe_b64decode(key)) != 32:
        raise ValueError("APP_SECRET_KEY must be a URL-safe base64-encoded 32-byte key.")
    cipher_suite = Fernet(key)
except Exception as e:
    # Handle cases where the key might be malformed or not set,
    # though Pydantic should ensure it's set.
    # For a production system, you'd want robust error handling or startup failure here.
    print(f"Error initializing Fernet cipher suite: {e}")
    print("Ensure APP_SECRET_KEY is a valid URL-safe base64-encoded 32-byte key.")
    # Fallback or raise - for now, let it raise if key is truly bad
    # For development, you might use a default key, but NOT for production.
    # Example: key = Fernet.generate_key()
    # cipher_suite = Fernet(key)
    # print(f"WARNING: Using a dynamically generated APP_SECRET_KEY: {key.decode()}")
    raise ValueError(f"Invalid APP_SECRET_KEY for Fernet: {e}")


def encrypt_api_key(api_key: str) -> str:
    """Encrypts an API key."""
    if not api_key:
        return ""
    encrypted_text = cipher_suite.encrypt(api_key.encode())
    return encrypted_text.decode()

def decrypt_api_key(encrypted_api_key: str) -> str:
    """Decrypts an API key."""
    if not encrypted_api_key:
        return ""
    decrypted_text = cipher_suite.decrypt(encrypted_api_key.encode())
    return decrypted_text.decode()
