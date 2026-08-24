#!/usr/bin/env python3
"""EDEN/Vural NTN orchestration validation harness. Evidence class: SIMULATED."""
import argparse, json, random

def run(seed=7, windows=200, packets=400):
    rng = random.Random(seed)
    jobs = []
    for i in range(packets):
        size = rng.randint(1, 12)
        value = rng.uniform(0.1, 10.0)
        deadline = rng.randint(10, windows)
        jobs.append({"id": i, "size": size, "value": value, "deadline": deadline})

    capacities = [rng.randint(8, 35) for _ in range(windows)]
    losses = [rng.uniform(0.0, 0.18) for _ in range(windows)]

    def simulate(policy):
        pending = [dict(j) for j in jobs]
        delivered_value = 0.0
        delivered = 0
        used = 0
        for t, cap in enumerate(capacities, start=1):
            if policy == "fifo":
                pending.sort(key=lambda j: j["id"])
            else:
                pending.sort(key=lambda j: (j["value"]/j["size"], -j["deadline"]), reverse=True)
            budget = cap
            next_pending = []
            for j in pending:
                if j["deadline"] < t:
                    continue
                if j["size"] <= budget:
                    budget -= j["size"]
                    used += j["size"]
                    if rng.random() >= losses[t-1]:
                        delivered += 1
                        delivered_value += j["value"]
                    else:
                        next_pending.append(j)
                else:
                    next_pending.append(j)
            pending = next_pending
        return {"delivered_packets": delivered, "delivered_value": delivered_value, "bytes_units_sent": used}

    rng_state = rng.getstate()
    fifo = simulate("fifo")
    rng.setstate(rng_state)
    eden = simulate("eden")
    return {
        "evidence_class":"SIMULATED",
        "claim_boundary":"No physical RF or satellite link is measured by this harness.",
        "seed":seed, "windows":windows, "packets":packets,
        "baseline_fifo":fifo, "eden_value_aware":eden,
        "delta_delivered_value":eden["delivered_value"]-fifo["delivered_value"],
        "pass_condition":"EDEN is not considered advantageous unless delivered_value exceeds FIFO on the same trace."
    }

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=int,default=7)
    p.add_argument("--windows",type=int,default=200)
    p.add_argument("--packets",type=int,default=400)
    a=p.parse_args()
    print(json.dumps(run(a.seed,a.windows,a.packets),indent=2,sort_keys=True))
