# EDEN Neural Interface — Encrypted Manifold Ingress

Status: **IMPLEMENTED connector/gate research design.** No live Neuralink device connection, physiological interpretation, or independent security validation is claimed.

## Required path

External source -> `manifold_encrypt.py` -> encrypted transport/frame -> `manifold_gate.py` -> verified local handoff -> `open_connector.py`

`open_connector.py` does not accept direct TCP or plaintext ingress.

## Manifold v2 security properties

`MANIFOLD-AUTH-001` upgrades the ingress frame to protocol version 2.

- AES-256-GCM authenticated encryption.
- Fresh 96-bit random nonce per frame.
- Canonical AEAD associated data binds:
  - Manifold identifier;
  - protocol version;
  - algorithm;
  - sender-supplied `source` label;
  - `session_id`;
  - monotonic `sequence` number.
- A changed source/session/sequence/version is rejected rather than silently being written into provenance.
- Replay and out-of-order sequence numbers are rejected per source/session pair.
- Replay state is persisted locally and corrupted replay state fails closed.
- The provenance head is cross-checked with the last Marble log entry. A corrupt/missing/mismatched head fails closed rather than silently starting a new chain.
- Invalid authentication tags, malformed frames, invalid nonces and wrong protocol identifiers are rejected.
- The open connector recomputes SHA-256 on the decrypted payload before recording provenance.

### Identity boundary

The source label is now **cryptographically bound to the frame under the configured Manifold key**. That means the label cannot be altered in transit without authentication failure. It does **not** independently prove that the real-world device is the named vendor/device; external hardware identity would require a separate attestation/credential mechanism.

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
rm -rf /tmp/eden-manifold-proof
mkdir -p /tmp/eden-manifold-proof

printf '%s\n' '{"example":"input"}' \
  | python neural-interface/manifold_encrypt.py \
      --key-file ~/.eden/keys/neural-manifold.key \
      --source test-source \
      --session-id local-proof-001 \
  | python neural-interface/manifold_gate.py \
      --key-file ~/.eden/keys/neural-manifold.key \
      --marble-log /tmp/eden-manifold-proof/marbles.jsonl \
      --head-file /tmp/eden-manifold-proof/head.json \
      --replay-state /tmp/eden-manifold-proof/replay.json \
  | python neural-interface/open_connector.py
```

This proves only that the local encryption/authentication/provenance path functions. It does not prove a Neuralink connection, neural measurement, vendor identity, physiological meaning, medical validity, or deployment security.

## MANIFOLD-AUTH-001 regression test

```bash
python -m pip install cryptography
python neural-interface/test_manifold_auth.py
```

The test suite checks rejection of tampered:

- source label;
- session identifier;
- sequence;
- protocol version;
- AAD;
- nonce;
- ciphertext;
- replayed/out-of-order frames;
- corrupt/missing/mismatched provenance heads;
- corrupt replay state.

A passing local/CI test demonstrates software behavior for those test cases only. It is not independent penetration testing or formal cryptographic verification.

## Real source integration

For real external ingress, encryption should occur at the source process or as close to the source boundary as technically possible. If an upstream device/API cannot produce EDEN Manifold frames itself, an authorized adapter should receive the vendor stream locally and immediately wrap each record with `manifold_encrypt.py` before EDEN transport.

For stronger device provenance, add externally verifiable device/session attestation and bind its identifier or certificate fingerprint into the authenticated metadata. Manifold v2 currently authenticates possession of the configured shared key plus frame integrity/confidentiality; it does not establish hardware identity by itself.
