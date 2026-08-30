# EDEN Delivery Bundle

This directory turns the EDEN repository into one repeatable delivery workflow without changing the evidence class of any historical result.

## One command

On a normal development machine:

```bash
python delivery/run_all.py --package
```

On the validated Termux handset, while unplugged and reporting `DISCHARGING`:

```bash
python delivery/run_all.py --handset --package
```

The handset form runs the integrated software verification gate, SAT-001 deterministic simulation, EDEN-CORE-AB-001 and EDEN-CORE-AB-002, then creates one archive under `delivery/out/`.

## What the archive contains

The package builder gathers current EDEN Core, Refinery, ChronoNav, Chrysalis, Marble, Manifold, SAT-001, RF tooling, experiments, energy/GPU artifacts where present, documentation, and the launcher. It writes a file-by-file SHA-256 manifest, a delivery status record, the Git commit and branch, and the software verification result.

If `EDEN_DELIVERY_SIGNING_KEY` is set locally, the builder also writes `MANIFEST.hmac-sha256`. This is an HMAC authenticity check shared with whoever receives the secret; it is not public-key attestation and it is not independent validation.

Example:

```bash
export EDEN_DELIVERY_SIGNING_KEY="$(python - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
python delivery/run_all.py --handset --package
```

Keep that signing key private. Do not commit it to GitHub.

## Evidence boundary

`MEASURED`, `IMPLEMENTED`, `SIMULATED`, `MODELLED`, `PROPOSED`, and `INDEPENDENTLY_VALIDATED` remain distinct. Packaging, hashing, Marble verification, CI success, and HMAC authentication establish software/integrity properties only. They do not upgrade a physical or scientific claim to independent validation.

The physical energy figures produced by the handset experiments use Termux battery voltage/current integration and therefore remain on-device estimates rather than external power-meter measurements.

## Delivery gate

A package is suitable to hand to a technical evaluator when:

- required software tests pass;
- the archive SHA-256 is recorded;
- the manifest is present;
- each included experiment retains its own evidence boundary;
- physical handset results are included only when actually run on the handset;
- no claim of independent validation is made unless an external reproduction artifact is later added.
