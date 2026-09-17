# Contributing and independent reproduction

Thank you for checking EDEN's claims. Small, reproducible contributions are especially useful.

1. Run the [quickstart](docs/QUICKSTART.md) or choose an experiment from the [evidence map](docs/EVIDENCE_MAP.md).
2. Record the exact commit, command, Python version, machine/OS, workload inputs, output report and any errors. Redact secrets and personal data before sharing traces.
3. Open an issue with your result, including neutral or negative outcomes. State what was measured and what was inferred. Distinguish simulated, modelled, host-measured and externally reproduced evidence.
4. For code changes, keep the comparator and EDEN arms on equivalent input streams, check output equality, and document verification overhead and truth boundaries. Open a pull request with the command used to check it.

Useful first contributions: rerun the three-arm comparison on another system; review a benchmark's conventional-cache comparator; supply an anonymized reusable workload; improve the clarity of the evidence map.

Please report potential security issues privately to the repository owner rather than posting exploit details in an issue. Project contact: [edenrefinery.com](https://edenrefinery.com/).
