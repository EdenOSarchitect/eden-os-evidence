#!/usr/bin/env python3
"""EDEN/Simeonidou information-aware programmable-network harness. Evidence class: SIMULATED."""
import argparse,json,random,statistics

def run(seed=29,flows=600,steps=250):
    rng=random.Random(seed)
    items=[{"id":i,"size":rng.randint(1,10),"utility":rng.uniform(.1,12),"latency_budget":rng.randint(5,80)} for i in range(flows)]
    capacity=[rng.randint(12,45) for _ in range(steps)]
    loss=[rng.uniform(0,.12) for _ in range(steps)]
    def sim(policy):
        q=[dict(x,age=0) for x in items]; utility=0.0; delivered=0; expired=0; latency=[]
        for t in range(steps):
            for x in q:
                x["age"]+=1
            alive=[]
            for x in q:
                if x["age"]>x["latency_budget"]:
                    expired+=1
                else:
                    alive.append(x)
            q=alive
            if policy=="fifo":
                q.sort(key=lambda x:x["id"])
            else:
                q.sort(key=lambda x:(x["utility"]/x["size"])/(1+x["age"]/max(1,x["latency_budget"])),reverse=True)
            cap=capacity[t]; nxt=[]
            for x in q:
                if x["size"]<=cap:
                    cap-=x["size"]
                    if rng.random()>=loss[t]:
                        delivered+=1; utility+=x["utility"]; latency.append(x["age"])
                    else:
                        nxt.append(x)
                else:
                    nxt.append(x)
            q=nxt
        return {"delivered":delivered,"application_utility":utility,"expired":expired,
                "mean_delivery_age":statistics.mean(latency) if latency else None}
    state=rng.getstate(); fifo=sim("fifo"); rng.setstate(state); eden=sim("eden")
    return {"evidence_class":"SIMULATED","claim_boundary":"Synthetic programmable-network workload; no live Bristol infrastructure is represented.",
            "seed":seed,"fifo":fifo,"eden_information_aware":eden,
            "falsification_rule":"Report a negative result when EDEN does not improve application_utility under the same trace."}
if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("--seed",type=int,default=29); a.add_argument("--flows",type=int,default=600); a.add_argument("--steps",type=int,default=250)
    x=a.parse_args(); print(json.dumps(run(x.seed,x.flows,x.steps),indent=2,sort_keys=True))
