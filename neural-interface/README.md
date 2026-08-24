# EDEN Neural Interface — Encrypted Manifold Ingress

Status: IMPLEMENTED connector/gate design. No live Neuralink device connection is claimed.

## Required path

External source -> `manifold_encrypt.py` -> encrypted transport/frame -> `manifold_gate.py` -> verified local handoff -> `open_connector.py`

`open_connector.py` no longer accepts direct TCP or plaintext ingress.

## Cryptography

- AES-256-GCM authenticated encryption
- Fresh 96-bit random nonce per frame
- Fixed protocol AAD: `EDEN-MANIFOLD-NI-v1`
- 32-byte key loaded from a local key file
- Invalid authentication tags, malformed frames and wrong protocol identifiers are dropped
- The open connector recomputes SHA-256 on the decrypted payload before recording provenance

## Termux setup

```bash
pkg install python
python -m pip install cryptography
mkdir -p ~/.eden/keys
python - <<'PY'
import os, base64
p=os.path.expanduser('~/.eden/keys/neural-manifold.key')
open(p,'wb').write(base64.b64encode(os.urandom(32)))
os.chmod(p,0o600)
print(p)
PY
```

Never commit the key file.

## Local proof-of-path

```bash
printf '%s\n' '{"example":"input"}' \
  | python neural-interface/manifold_encrypt.py --key-file ~/.eden/keys/neural-manifold.key --source test-source \
  | python neural-interface/manifold_gate.py --key-file ~/.eden/keys/neural-manifold.key \
  | python neural-interface/open_connector.py
```

This proves only that the encryption/authentication path functions locally. It does not prove a Neuralink connection, neural measurement, vendor identity, or medical validity.

## Real source integration

For real external ingress, encryption should occur at the source process or as close to the source boundary as technically possible. If the upstream device/API cannot produce EDEN Manifold frames itself, an adapter should receive the vendor-authorized stream locally and immediately wrap each record with `manifold_encrypt.py` before any EDEN transport.

The cryptographic layer authenticates possession of the configured Manifold key and integrity/confidentiality of the frame. It does not by itself authenticate that the originating hardware is a Neuralink device.
