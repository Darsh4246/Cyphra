# Cyphra

Cyphra is a local-first encrypted container application. It has a
GUI-independent Python core and a PySide6 desktop interface. The core handles
single-file payloads (`Image`) and streamed encrypted directories (`Vault`).
The GUI calls that core through small adapters, so the binary format and
security checks do not need to be duplicated in the interface.

## Architecture

```
cyphra/             Container API, cryptography, framing, and path safety
cyphra_gui/         PySide6 windows, pages, workers, and core adapter
main.py             Compatibility launcher for the GUI
tests/              Pytest coverage for the public container behaviour
```

`Image` is the API for one payload and `Vault` is the API for a directory tree.
Both APIs accept filesystem paths, binary streams, or bytes where appropriate.
They also expose progress callbacks and cancellation hooks for responsive
frontends.

```python
from cyphra import Image, Vault

Image.encrypt(
    "photo.jpg",
    "photo.cyphra",
    password="use-a-long-passphrase",
    metadata={"original_name": "photo.jpg"},
)
Image.decrypt("photo.cyphra", "photo.jpg", password="use-a-long-passphrase")

Vault.create(
    "documents",
    "documents.cyphra-vault",
    password="use-a-long-passphrase",
)
Vault.extract(
    "documents.cyphra-vault",
    "restored",
    password="use-a-long-passphrase",
)
```

## Security model

* Each container gets a cryptographically random 16-byte salt and 12-byte
  nonce.
* Passwords derive a 256-bit AES key with PBKDF2-HMAC-SHA256 using 600,000
  iterations by default.
* AES-256-GCM authenticates the header and every encrypted record. A wrong
  password, changed ciphertext, or changed authenticated header raises
  `AuthenticationError` (malformed framing raises `FormatError`).
* Metadata is inside the encrypted stream; names, sizes, and image metadata are
  not written in plaintext.
* Vault extraction validates normalized relative paths and refuses absolute
  paths, `..` traversal, and symbolic-link traversal. Failed extraction
  removes files created during that operation.

Cyphra protects data at rest when the password remains secret. It does not
protect a running, unlocked process, recover a forgotten password, hide file
existence or container size, or provide remote backup. Keep independent
backups of important containers.

## Container format

Every container begins with a fixed binary header containing the `CYPhRA`
magic/version, kind (`Image` or `Vault`), PBKDF2 iteration count, salt, nonce,
and reserved fields. The header is authenticated as AES-GCM additional
authenticated data.

The decrypted payload is a length-delimited record stream:

* An image contains metadata, one or more data records, and an end marker.
* A vault contains metadata, directory/file records, file data records, and
  end markers. Paths use UTF-8 and POSIX separators, preserving Unicode names,
  empty directories, empty files, and nested directories.

The stream design bounds metadata, path, and record sizes and avoids loading a
whole vault into memory. Authentication is checked before the operation
returns, and malformed or trailing records are rejected.

## Workflows

### Desktop GUI

Install the package and run:

```powershell
python -m cyphra_gui
```

Choose an image or vault workflow, select the input/output paths, enter the
password, and use the progress/cancel controls. The GUI is optional; the
`cyphra` package can be embedded in another application or used from a script.

### Python API

`Image.encrypt`/`Image.decrypt` handle a file or bytes. `Vault.create`,
`Vault.extract`, and `Vault.list` create, restore, and inspect a directory
container. `CryptoService` provides aliases suitable for GUI workers, and
`CancellationToken` is a thread-safe cancellation object.

## Requirements and installation

* Python 3.10 or newer
* `cryptography >= 41`
* `PySide6 >= 6.5` for the desktop GUI
* `pytest` for the test suite

The runtime dependencies are declared in `pyproject.toml`. Create a virtual
environment and install the package:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
```

For a headless/container-only installation, `cryptography` is sufficient for
the core, but installing the project also installs the GUI dependency.

## Testing and building

Run the complete test suite from the repository root:

```powershell
python -m pytest -q
```

The package build uses the standard PEP 517 backend:

```powershell
python -m pip install build
python -m build
```

The wheel contains both `cyphra` and `cyphra_gui`. `python main.py` is also
available as a source-tree compatibility launcher.

## PyInstaller guidance

PyInstaller can package the GUI entry point after installing the project in the
same environment:

```powershell
python -m pip install pyinstaller
pyinstaller --name Cyphra --windowed --paths . main.py
```

If a platform-specific PySide6 plugin is not collected automatically, rebuild
with its normal Qt collection options (for example,
`--collect-all PySide6`) or add the missing plugin to a `.spec` file. Build
on each target operating system, test the resulting executable on a clean
machine, and distribute the generated `dist/Cyphra` directory (or the
one-file artifact). PyInstaller does not change the encryption format or
remove the need for a strong password.
