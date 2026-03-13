"""
AES-256-GCM decryption — matches nextjs-frontend/src/lib/encryption.ts format.

Input format: "iv_hex:authTag_hex:ciphertext_hex"
Key: 64-char hex string from ENCRYPTION_KEY env var (32 bytes).
"""

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def decrypt(encrypted: str, key_hex: str) -> str:
    parts = encrypted.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid encrypted format. Expected iv:authTag:ciphertext")

    iv = bytes.fromhex(parts[0])
    auth_tag = bytes.fromhex(parts[1])
    ciphertext = bytes.fromhex(parts[2])

    key = bytes.fromhex(key_hex)
    aesgcm = AESGCM(key)

    # AESGCM expects ciphertext + authTag concatenated
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    return plaintext.decode("utf-8")
