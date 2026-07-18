# Agent runtime `py311-stdlib-v1`

- Python: `3.11.11`
- Third-party packages: none
- Entrypoint: `main.py:agent`
- Strategy mount: `/strategy` (read-only)
- Writable path: `/tmp` tmpfs only

Runtime dependencies are immutable per image tag. Adding libraries creates a new runtime image version; existing strategy versions continue to reference their original image.

## Expert runtime `py311-torch251-v1`

- Inherits the same Python base image and isolation contract.
- Adds PyTorch `2.5.1`, matching the audited producer v69 source runtime.
- Uses a separate immutable image reference; stdlib strategies do not inherit Torch.
