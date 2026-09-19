# PR #19 evidence review

## Initial implementation weaknesses

| Area | Initial state | Evidence risk | Resolution |
|---|---|---|---|
| RSS | `RUSAGE_SELF.ru_maxrss` reused in one process | Later arms inherited earlier high-water marks | Each arm now runs in a fresh child process |
| CPU scope | Process CPU not described precisely | Could be mistaken for server-only or Azure CPU | Explicitly labelled as load generator plus service |
| Teardown | Server shutdown was inside timing window | Fixed polling delay distorted wall/throughput | Window ends after final response |
| Arm order | Always CONTROL, CACHE, EDEN | Thermal/background drift systematically favored later arms | Seeded order is randomized and recorded |
| Repetition | One run silently presented as decisive | No uncertainty or significance basis | Single-run limitation is explicit in truth boundary |
| Concurrent misses | Lookup and compute were not atomic | Duplicate executions could be miscounted | Per-key single-flight miss coordination |
| CACHE fairness | CACHE misses created EDEN-like proof hashes | Understated EDEN's assurance overhead | CACHE stores only the conventional value |
| EDEN assurance | Only key/value proof checked on hits | Policy and provenance were not bound | Input, output, policy, provenance and record are bound |
| Verification | Hit verification not fully accounted | Assurance claim was weakly observable | Attempts, passes, failures and CPU time recorded |
| Payload parity | EDEN returned extra metadata | Biased response bytes and latency | Identical semantic HTTP response for every arm |
| Output equality | Rows sorted by value | Did not commit request-ordered behavior | Results are reconstructed by request ordinal |
| Bytes | Generic request/response byte labels | Could imply HTTP/TCP wire bytes | Labelled application bodies; protocol overhead excluded |
| Environment | User label selected Azure evidence class | Any host could self-label as Azure | Azure class requires Microsoft DMI vendor signal |
| External evidence | File was merely hashed | Could imply correlation or interpretation | Explicitly attached, uninterpreted and not time-aligned |
| Reproducibility | Minimal command only | Host/commit/order preservation incomplete | Azure runbook and committed configuration |
| Regression protection | No tests or CI | Claims could regress unnoticed | Unit, concurrency, smoke and truth-boundary CI checks |

## Primary pilot interpretation

The meaningful comparisons are:

1. **CACHE versus CONTROL:** benefit of conventional exact reuse.
2. **EDEN versus CONTROL:** net benefit of verified reuse.
3. **EDEN versus CACHE:** incremental cost of EDEN assurance.

A credible result requires output equivalence, exact execution accounting, zero
failed requests, zero verification failures and equal application payload
bytes. CPU reduction, throughput gain and latency changes must be reported even
when unfavorable.

## Residual limitations

The chosen primary design has one long run per arm. Seeded random ordering
reduces systematic order selection but does not counterbalance it. The result
therefore has no confidence interval, no statistical-significance claim and
remains vulnerable to time, thermal and noisy-neighbor drift.

The deterministic workload is a controlled application kernel served over real
HTTP on loopback. It is not evidence of production-workload generality. CPU and
RSS cover the combined service/load-generator child process, not an isolated
server or Azure platform counter. Application body bytes exclude headers and
TCP/IP framing. Azure billing, energy, carbon and platform utilization remain
outside the harness unless independently measured and separately interpreted.

## Promotion gate

Do not describe a run as pilot evidence unless the JSON report, terminal log,
exact Git commit, VM SKU/region/image, Python version, effective VM price and
any external telemetry are preserved together. Independent validation remains
`NOT_PERFORMED` until an external party reproduces the committed procedure.
