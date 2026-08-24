#!/usr/bin/env python3
"""EDEN/Macdonald constrained orbital-compute scheduling harness. Evidence class: SIMULATED."""
import argparse, json, random

def run(seed=11, tasks=500, slots=240):
    rng=random.Random(seed)
    work=[{"id":i,"cpu":rng.randint(1,8),"power":rng.uniform(.5,5.0),"bytes":rng.randint(1,20),
           "value":rng.uniform(.1,15.0),"deadline":rng.randint(5,slots)} for i in range(tasks)]
    contacts={t:rng.randint(0,25) if rng.random()<.35 else 0 for t in range(1,slots+1)}
    power={t:rng.uniform(8,22) for t in range(1,slots+1)}
    def sim(policy):
        pending=[dict(x) for x in work]; returned=0.0; done=0; energy=0.0; tx=0
        for t in range(1,slots+1):
            if policy=="fifo":
                pending.sort(key=lambda x:x["id"])
            else:
                pending.sort(key=lambda x:(x["value"]/(x["power"]+0.25*x["bytes"]),-x["deadline"]),reverse=True)
            pwr=power[t]; link=contacts[t]; keep=[]
            for x in pending:
                if x["deadline"]<t:
                    continue
                if x["power"]<=pwr and x["bytes"]<=link:
                    pwr-=x["power"]; link-=x["bytes"]; energy+=x["power"]; tx+=x["bytes"]; done+=1; returned+=x["value"]
                else:
                    keep.append(x)
            pending=keep
        return {"completed":done,"mission_value_returned":returned,"energy_proxy_units":energy,"transmit_units":tx}
    return {"evidence_class":"SIMULATED","claim_boundary":"Power values are model units, not joules; contacts are synthetic.",
            "seed":seed,"baseline_fifo":sim("fifo"),"eden_value_per_resource":sim("eden"),
            "pass_condition":"Compare mission_value_returned under identical synthetic power/contact traces."}
if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("--seed",type=int,default=11); a.add_argument("--tasks",type=int,default=500); a.add_argument("--slots",type=int,default=240)
    x=a.parse_args(); print(json.dumps(run(x.seed,x.tasks,x.slots),indent=2,sort_keys=True))
