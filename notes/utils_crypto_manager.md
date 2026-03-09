# file: src/utils/crypto_manager.py

## 1. File Overview
**Purpose**: **Security & Compliance Module**.
**Role**: Handles AES-256 encryption for patient data at rest.
**Compliance**: Essential for HIPAA (USA) and GDPR (EU) requirements. It ensures that if the laptop is stolen, the JSON logs cannot be read without the key.

## 2. Code Breakdown

### Initialization (Lines 15-18)
-   **Key Loading**: Tries to load `config/secret.key`.
-   **Generation**: If the key is missing (first run), it generates a new Fernet key and saves it.

### Fernet Encryption (Lines 32-38)
-   **Algorithm**: Fernet (Symmetric Encryption). It uses AES-128 with HMAC-SHA256 for integrity.
-   **Methods**:
    -   `encrypt_data(str) -> bytes`: Takes a JSON string, returns garbled bytes.
    -   `decrypt_data(bytes) -> str`: Reverses the process.

## 3. Data Flow
1.  **DataLogger** creates a JSON string of the session.
2.  **CryptoManager** encrypts it.
3.  **File System** stores the `.enc` file.
4.  **Load History**: Reads bytes -> Decrypts -> Returns JSON.

## 4. Design Decisions
-   **Symmetric Key**: We use a single key (Symmetric) because the data is local. We don't need Public/Private keys (Asymmetric) unless we start sending data to a server.
-   **File-Based Key**: The key is stored in `config/secret.key`.
    -   **Pros**: Simple.
    -   **Cons**: If the user deletes this file, ALL patient history is lost forever.

## 5. How to Modify
-   **Rotate Key**: Delete `secret.key`. The app will generate a new one. (Warning: Old files will become unreadable).

## 6. Limitations
-   **Key Management**: There is no "Password Protection" for the key itself. If a hacker gets root access to the laptop, they can read `secret.key` and decrypt the data.
-   **Performance**: Encrypting large video files (if we stored them) would be slow. Currently, we only encrypt the JSON metadata.

## 7. Future Improvements
-   **Password Deriviation**: Ask the doctor for a password at startup, and use `PBKDF2` to derive the encryption key. This way, the key is never stored on disk.
