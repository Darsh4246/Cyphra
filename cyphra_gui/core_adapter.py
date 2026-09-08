"""A small compatibility layer around the Cyphra cryptography core.

The core package is developed separately from the UI.  No crypto code belongs
in this module: it only discovers and normalises the public functions exposed
by a core implementation.  Supported function names are deliberately
conventional (``encrypt_file``, ``decrypt_file``, ``hash_file``,
``hash_text`` and ``compare_hash``), while the adapter also accepts a module
object in tests or from an embedding application.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import secrets
import string
from pathlib import Path
from typing import Any, Callable, Iterable


class CoreUnavailableError(RuntimeError):
    """Raised when an encryption operation is requested before the core exists."""


class OperationCancelled(RuntimeError):
    """Raised by an adapter when a worker cancellation request is observed."""


CIPHER_METADATA = {
    "AES-256-GCM": {
        "id": 0,
        "name": "AES-256-GCM",
        "title": "AES-256-GCM · Galois/Counter Mode",
        "tag": "NIST Standard · Hardware Accelerated",
        "badge_color": "#10b981",
        "key_size": "256 bits (32 bytes)",
        "auth_tag": "128 bits (16 bytes)",
        "where_used": "TLS 1.3, OpenSSH, BitLocker, Google Cloud KMS, Apple FileVault, AWS S3",
        "description": "NIST FIPS 197 standard authenticated cipher. Uses AES-NI CPU hardware acceleration for ultra-high throughput while providing cryptographic AEAD integrity protection.",
        "security": "Military-grade 256-bit key space. Highly recommended standard for secure file and directory archives.",
    },
    "ChaCha20-Poly1305": {
        "id": 1,
        "name": "ChaCha20-Poly1305",
        "title": "ChaCha20-Poly1305 · Bernstein Stream Cipher",
        "tag": "High Assurance · Timing-Attack Immune",
        "badge_color": "#38bdf8",
        "key_size": "256 bits (32 bytes)",
        "auth_tag": "128 bits (16 bytes Poly1305)",
        "where_used": "WireGuard VPN, Signal Protocol, Android disk encryption, OpenSSH, Cloudflare",
        "description": "High-assurance authenticated stream cipher designed by Daniel J. Bernstein (RFC 8439). Provides mathematical immunity to CPU cache-timing side-channel attacks and maximum speed on systems lacking hardware AES.",
        "security": "Provable security bounds with Poly1305 one-time authenticator. The modern choice for mobile and privacy-first networks.",
    },
    "AES-256-GCM-SIV": {
        "id": 2,
        "name": "AES-256-GCM-SIV",
        "title": "AES-256-GCM-SIV · Synthetic IV Nonce-Misuse Resistant",
        "tag": "RFC 8452 · Misuse Resistant",
        "badge_color": "#818cf8",
        "key_size": "256 bits (32 bytes)",
        "auth_tag": "128 bits (16 bytes)",
        "where_used": "Google Key Management, modern distributed databases, high-availability clouds",
        "description": "Defined in RFC 8452 (CFRG / Gueron, Langley, Lindell). Designed specifically to be robust against nonce reuse: even if a random nonce is accidentally repeated, confidentiality and integrity remain uncompromised.",
        "security": "Synthetic Initialization Vector (SIV) mode. Unsurpassed resiliency for mission-critical archiving.",
    },
}

KDF_METADATA = {
    "Argon2id": {
        "id": 1,
        "name": "Argon2id",
        "title": "Argon2id · Password Hashing Competition Winner",
        "tag": "Memory-Hard · GPU/ASIC Immune",
        "badge_color": "#10b981",
        "memory": "64 MB RAM per hash",
        "iterations": "3 time iterations · 4 threads",
        "where_used": "KeePassXC, Bitwarden, Linux LUKS2 disk encryption, 1Password",
        "description": "The undisputed state of the art in password-based key derivation (RFC 9106). Employs memory-hardness to prevent attackers from using GPU or custom ASIC mining clusters to brute-force passphrases.",
        "security": "Maximum resistance to both side-channel timing attacks and massively parallel hardware attacks.",
    },
    "PBKDF2-HMAC-SHA256": {
        "id": 0,
        "name": "PBKDF2-HMAC-SHA256",
        "title": "PBKDF2 · Password-Based Key Derivation 2",
        "tag": "FIPS 140-2 Compliant · Universal Standard",
        "badge_color": "#38bdf8",
        "memory": "Minimal (< 1 MB)",
        "iterations": "600,000 rounds (OWASP 2025+ recommendation)",
        "where_used": "Apple iOS Keychain, WPA2/WPA3 Wi-Fi, OpenSSL, Windows DPAPI",
        "description": "The globally recognized NIST SP 800-132 standard. Applies 600,000 chained cryptographic HMAC-SHA256 operations to drastically slow down dictionary attacks while maintaining universal compatibility.",
        "security": "Standard computational work factor; compliant with corporate and government security standards.",
    },
    "Scrypt": {
        "id": 2,
        "name": "Scrypt",
        "title": "Scrypt · Sequential Memory-Hard KDF",
        "tag": "Colin Percival · Memory-Hard",
        "badge_color": "#f59e0b",
        "memory": "32 MB RAM (N=32768, r=8, p=1)",
        "iterations": "Sequential memory iterations",
        "where_used": "Tarsnap online backups, cryptocurrency key storage (Litecoin), FreeBSD",
        "description": "Designed by Colin Percival (IETF RFC 7914) to require large amounts of RAM for each password guess. Forcing high RAM usage renders custom FPGA and ASIC cracking hardware prohibitively expensive.",
        "security": "Proven memory-hard security track record over 15+ years of cryptanalysis.",
    },
}

HASH_METADATA = {
    "SHA-256": {
        "name": "SHA-256",
        "algorithm": "sha256",
        "bits": 256,
        "hex_len": 64,
        "family": "SHA-2 (NIST FIPS 180-4)",
        "status": "Cryptographically Secure",
        "badge_color": "#10b981",
        "where_used": "Bitcoin blockchain, TLS/SSL certificates, Linux package repositories, Git 2.28+",
        "description": "The global standard cryptographic hash. Produces a 256-bit digest resistant to collision and pre-image attacks. The gold standard for software download verification.",
    },
    "SHA-512": {
        "name": "SHA-512",
        "algorithm": "sha512",
        "bits": 512,
        "hex_len": 128,
        "family": "SHA-2 (NIST FIPS 180-4)",
        "status": "Maximum Security",
        "badge_color": "#10b981",
        "where_used": "OpenPGP key signatures, Debian/Ubuntu package verification, Unix shadow passwords",
        "description": "512-bit digest optimized for 64-bit CPU architectures. Highly efficient on modern desktop processors while providing 256 bits of collision resistance.",
    },
    "SHA3-256": {
        "name": "SHA3-256",
        "algorithm": "sha3_256",
        "bits": 256,
        "hex_len": 64,
        "family": "SHA-3 Keccak (NIST FIPS 202)",
        "status": "Next-Gen Standard",
        "badge_color": "#06b6d4",
        "where_used": "Ethereum blockchain (Keccak), Post-Quantum cryptographic signature suites",
        "description": "Winner of the NIST hash competition. Based on the Keccak sponge construction, mathematically distinct from the Merkle-Damgård structure of SHA-1 and SHA-2.",
    },
    "SHA3-512": {
        "name": "SHA3-512",
        "algorithm": "sha3_512",
        "bits": 512,
        "hex_len": 128,
        "family": "SHA-3 Keccak (NIST FIPS 202)",
        "status": "Maximum Next-Gen Security",
        "badge_color": "#06b6d4",
        "where_used": "High-security military and government digital signatures, quantum-resistant archiving",
        "description": "The largest digest size in the SHA-3 family. Uses a 1600-bit internal permutation state to guarantee complete immunity against length extension attacks.",
    },
    "BLAKE2b": {
        "name": "BLAKE2b",
        "algorithm": "blake2b",
        "bits": 512,
        "hex_len": 128,
        "family": "BLAKE2 (RFC 7693)",
        "status": "Ultra-Fast & Secure",
        "badge_color": "#3b82f6",
        "where_used": "WireGuard VPN, Argon2 internal hashing, Zcash cryptocurrency, Arch Linux pacman",
        "description": "Extremely fast cryptographic hash function that is faster than MD5 on 64-bit platforms, yet provides security equal to or higher than SHA-3.",
    },
    "BLAKE2s": {
        "name": "BLAKE2s",
        "algorithm": "blake2s",
        "bits": 256,
        "hex_len": 64,
        "family": "BLAKE2 (RFC 7693)",
        "status": "Ultra-Fast 256-bit",
        "badge_color": "#3b82f6",
        "where_used": "WireGuard cookie authentication, IoT devices, 32-bit embedded microcontrollers",
        "description": "Optimized 256-bit variant of BLAKE2 tailored for 8-to-32-bit platforms and high-speed packet verification.",
    },
    "SHA-384": {
        "name": "SHA-384",
        "algorithm": "sha384",
        "bits": 384,
        "hex_len": 96,
        "family": "SHA-2 (NIST FIPS 180-4)",
        "status": "CNSA / Suite B Standard",
        "badge_color": "#818cf8",
        "where_used": "US National Security Agency (NSA) Suite B and CNSA top-secret classified communications",
        "description": "Truncated variant of SHA-512 with distinct initial state constants, designed to provide 192 bits of security against quantum and classical collision attacks.",
    },
    "SHA-224": {
        "name": "SHA-224",
        "algorithm": "sha224",
        "bits": 224,
        "hex_len": 56,
        "family": "SHA-2 (NIST FIPS 180-4)",
        "status": "224-bit Legacy Match",
        "badge_color": "#a855f7",
        "where_used": "2-Key Triple-DES security matching, legacy TLS cipher suites",
        "description": "224-bit truncated SHA-2 variant matched to 112 bits of security strength for backward compatibility with 2-key 3DES systems.",
    },
    "MD5": {
        "name": "MD5",
        "algorithm": "md5",
        "bits": 128,
        "hex_len": 32,
        "family": "MD5 (RFC 1321)",
        "status": "Legacy / Checksum Only (Insecure for Security)",
        "badge_color": "#f43f5e",
        "where_used": "Legacy ISO file verification, old CD-ROM images, retro software checksums, rsync quick checks",
        "description": "128-bit legacy digest. Cryptographically broken (collision attacks demonstrated since 2004). Provided ONLY for verifying old download checksums and archive integrity.",
    },
    "SHA-1": {
        "name": "SHA-1",
        "algorithm": "sha1",
        "bits": 160,
        "hex_len": 40,
        "family": "SHA-1 (NIST FIPS 180-1)",
        "status": "Legacy / Checksum Only (Insecure for Security)",
        "badge_color": "#f59e0b",
        "where_used": "Git legacy commit SHAs, older BitTorrent v1 torrent infohashes, older SSL certificates",
        "description": "160-bit legacy digest. Vulnerable to chosen-prefix collision attacks (SHAttered attack). Provided for verifying Git commit hashes and legacy archives.",
    },
}


_CORE_MODULES = (
    "cyphra",
    "cyphra_core",
    "cyphra.crypto",
    "cyphra.core",
    "crypto_core",
    "core.crypto",
)


def _load_core(module: Any = None) -> Any:
    if module is not None:
        return module
    for module_name in _CORE_MODULES:
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    return None


def _find(core: Any, names: Iterable[str]) -> Callable[..., Any] | None:
    if core is None:
        return None
    for name in names:
        function = getattr(core, name, None)
        if callable(function):
            return function
    return None


def _call(function: Callable[..., Any], **kwargs: Any) -> Any:
    """Call a core function while accommodating small signature variations."""
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return function(**kwargs)
    accepted = {
        key: value for key, value in kwargs.items()
        if key in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
    }
    return function(**accepted)


def _progress_callback(progress: Callable[[int], None] | None) -> Callable[..., None] | None:
    """Accept both ``progress(percent)`` and ``progress(done, total)`` cores."""
    if progress is None:
        return None

    def report(*values: Any) -> None:
        if not values:
            return
        if len(values) > 1 and values[1]:
            progress(min(100, int(values[0] * 100 / values[1])))
        else:
            value = values[0]
            progress(int(value if isinstance(value, (int, float)) else 0))

    return report


class CryptoAdapter:
    """Normalised facade used by the GUI workers.

    ``core_module`` is optional so applications can inject the real core and
    tests can supply a deterministic fake without importing implementation
    files.  File operations require a core function; hashing has a safe
    hashlib fallback to keep the Hash screen useful independently.
    """

    def __init__(self, core_module: Any = None) -> None:
        self.core = _load_core(core_module)

    @property
    def available(self) -> bool:
        return self.core is not None

    def _required(self, names: Iterable[str]) -> Callable[..., Any]:
        function = _find(self.core, names)
        if function is None:
            joined = ", ".join(names)
            raise CoreUnavailableError(
                f"Cyphra core is not available (expected one of: {joined})"
            )
        return function

    @staticmethod
    def _check_cancel(cancel_event: Any = None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled("Operation cancelled")

    def encrypt_file(
        self,
        source: str | Path,
        destination: str | Path,
        password: str,
        progress: Callable[[int], None] | None = None,
        cancel_event: Any = None,
        cipher_id: int = 0,
        kdf_id: int = 0,
    ) -> Any:
        self._check_cancel(cancel_event)
        source_path = Path(source)
        if source_path.is_dir():
            vault = getattr(self.core, "Vault", None)
            function = getattr(vault, "create", None)
            if function is None:
                raise CoreUnavailableError("Cyphra Vault support is not available")
            result = _call(
                function,
                source=source_path,
                destination=str(destination),
                password=password,
                progress=_progress_callback(progress),
                cancellation=cancel_event,
                cipher_id=cipher_id,
                kdf_id=kdf_id,
            )
            self._check_cancel(cancel_event)
            return result
        function = _find(self.core, ("encrypt_file", "encrypt"))
        if function is None and self.core is not None:
            image = getattr(self.core, "Image", None)
            function = getattr(image, "encrypt", None)
        if function is None:
            function = self._required(("encrypt_file", "encrypt"))
        result = _call(
            function,
            input_path=str(source),
            source=str(source),
            output_path=str(destination),
            destination=str(destination),
            password=password,
            progress_callback=_progress_callback(progress),
            progress=_progress_callback(progress),
            cancel_event=cancel_event,
            cancellation=cancel_event,
            cipher_id=cipher_id,
            kdf_id=kdf_id,
        )
        self._check_cancel(cancel_event)
        return result

    def decrypt_file(
        self,
        source: str | Path,
        destination: str | Path,
        password: str,
        progress: Callable[[int], None] | None = None,
        cancel_event: Any = None,
        overwrite: bool = True,
        **_kwargs: Any,
    ) -> Any:
        self._check_cancel(cancel_event)
        source_path = Path(source)
        if source_path.suffix.lower() == ".cyphra-vault":
            vault = getattr(self.core, "Vault", None)
            function = getattr(vault, "extract", None)
            if function is None:
                raise CoreUnavailableError("Cyphra Vault support is not available")

            dest_path = Path(destination)
            vault_name = source_path.name.removesuffix(".cyphra-vault")

            # Always extract into a dedicated folder named after the vault:
            # If destination is an existing directory and not already named vault_name, extract into destination / vault_name
            if dest_path.is_dir() and dest_path.name != vault_name:
                dest_path = dest_path / vault_name

            dest_path.mkdir(parents=True, exist_ok=True)

            result = _call(
                function,
                source=source_path,
                destination=str(dest_path),
                password=password,
                progress=_progress_callback(progress),
                cancellation=cancel_event,
                overwrite=overwrite,
            )
            self._check_cancel(cancel_event)
            return str(dest_path)
        function = _find(self.core, ("decrypt_file", "decrypt"))
        if function is None and self.core is not None:
            image = getattr(self.core, "Image", None)
            function = getattr(image, "decrypt", None)
        if function is None:
            function = self._required(("decrypt_file", "decrypt"))
        result = _call(
            function,
            input_path=str(source),
            source=str(source),
            output_path=str(destination),
            destination=str(destination),
            password=password,
            progress_callback=_progress_callback(progress),
            progress=_progress_callback(progress),
            cancel_event=cancel_event,
            cancellation=cancel_event,
        )
        self._check_cancel(cancel_event)
        return result

    def hash_text(self, text: str, algorithm: str = "SHA-256", key: str = "") -> str:
        algo_name = algorithm.strip()
        meta = HASH_METADATA.get(algo_name)
        raw_algo = meta["algorithm"] if meta else algo_name.replace("-", "").lower()

        if key:
            import hmac
            return hmac.new(key.encode("utf-8"), text.encode("utf-8"), raw_algo).hexdigest()

        function = _find(self.core, ("hash_text", "hash_string", "digest_text"))
        if function is not None:
            return str(_call(function, text=text, data=text, algorithm=algorithm))
        digest = hashlib.new(raw_algo)
        digest.update(text.encode("utf-8"))
        return digest.hexdigest()

    def hash_file(
        self,
        source: str | Path,
        algorithm: str = "SHA-256",
        key: str = "",
        progress: Callable[[int], None] | None = None,
    ) -> str:
        algo_name = algorithm.strip()
        meta = HASH_METADATA.get(algo_name)
        raw_algo = meta["algorithm"] if meta else algo_name.replace("-", "").lower()
        path = Path(source)
        size = max(path.stat().st_size, 1)
        read = 0

        if key:
            import hmac
            mac = hmac.new(key.encode("utf-8"), b"", raw_algo)
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    mac.update(chunk)
                    read += len(chunk)
                    if progress:
                        progress(min(100, int(read * 100 / size)))
            return mac.hexdigest()

        function = _find(self.core, ("hash_file", "digest_file"))
        if function is not None:
            return str(_call(
                function,
                input_path=str(source),
                source=str(source),
                algorithm=algorithm,
                progress_callback=progress,
                progress=progress,
            ))
        digest = hashlib.new(raw_algo)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                read += len(chunk)
                if progress:
                    progress(min(100, int(read * 100 / size)))
        return digest.hexdigest()

    def compare_hash(self, actual: str, expected: str) -> bool:
        function = _find(self.core, ("compare_hash", "verify_hash", "hash_matches"))
        if function is not None:
            return bool(_call(function, actual=actual, expected=expected, left=actual, right=expected))
        return secrets.compare_digest(actual.strip().casefold(), expected.strip().casefold())


def generate_password(length: int = 24, symbols: bool = True) -> str:
    """Generate a password using the system CSPRNG, never ``random``."""
    if length < 8:
        raise ValueError("Password length must be at least 8 characters")
    alphabet = string.ascii_letters + string.digits
    if symbols:
        alphabet += "!@#$%^&*()-_=+[]{}:,.?"
    return "".join(secrets.choice(alphabet) for _ in range(length))
