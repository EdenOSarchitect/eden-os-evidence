# EDEN External Run / Termux Ping Protocol

Purpose: provide a transparent, auditable signal that an external party executed an EDEN academic harness.

This is NOT covert telemetry. Nothing is transmitted automatically by the experiment harness.

## Runner workflow
1. Clone/fork the repository.
2. Set non-secret labels:
```bash
export EDEN_RUNNER_ID="institution-or-lab-label"
export EDEN_RUN_TOKEN="experiment-run-label"
```
3. Run the relevant experiment and save JSON in `results/external/`.
4. Add an environment manifest containing OS, Python version, architecture, hardware description where the runner is comfortable disclosing it, commit SHA, exact command and UTC timestamp.
5. Submit a pull request titled:

`EDEN-EXT-RUN <experiment-id> <runner-label>`

## Termux example
```bash
pkg install git python -y
git clone https://github.com/EdenOSarchitect/eden-os-evidence.git
cd eden-os-evidence
mkdir -p results/external
export EDEN_RUNNER_ID="external-lab"
export EDEN_RUN_TOKEN="tafazolli-ntn-001"
python academic/tafazolli/run_experiment.py > results/external/tafazolli-ntn-001.json
python - <<'PY' > results/external/environment.json
import json,platform,subprocess,time
try: sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
except Exception: sha=None
print(json.dumps({'utc_unix':int(time.time()),'platform':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),'git_commit':sha},indent=2))
PY
```

The runner may then commit these files to their fork/branch and open the PR.

## Classification rule
A PR is a RUN SIGNAL only. It becomes INDEPENDENTLY VALIDATED only after identity/provenance, environment, methodology, outputs and any deviations are reviewed. A successful CI run by itself is not independent validation.

## Privacy
Do not include usernames, local paths, serial numbers, IP addresses, Wi-Fi identifiers, Android IDs, phone numbers or secrets in submitted manifests. `EDEN_RUNNER_ID` and `EDEN_RUN_TOKEN` are public labels, not credentials.
