import logging
from pathlib import Path
from cryptography.fernet import Fernet

log = logging.getLogger("builder.security")


class TokenVault:
    def __init__(self, data_dir: Path, env_key: str | None = None):
        key_file = data_dir / "fernet.key"
        key = None
        if env_key:
            try:
                Fernet(env_key.encode())
                key = env_key.encode()
            except ValueError:
                log.warning("FERNET_KEY is invalid; using persistent data/fernet.key instead")
        if key is None and key_file.exists():
            key = key_file.read_bytes().strip()
        if key is None:
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            log.info("Generated encryption key: %s", key_file)
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()
