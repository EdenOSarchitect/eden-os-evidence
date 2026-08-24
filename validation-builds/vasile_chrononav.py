#!/usr/bin/env python3
"""EDEN/Vasile ChronoNav multi-objective scheduler harness. Evidence class: SIMULATED."""
import argparse,json,random

def run(seed=19,n=800,horizon=300):
    rng=random.Random(seed)
    jobs=[{"id":i,"arrival":rng.randint(0,horizon-20),"duration":rng.randint(1,8),"energy":rng.uniform(.5,6),
           "utility":rng.uniform(.1,20),"deadline":rng.randint(5,horizon)} for i in range(n)]
    for j in jobs:
        j["deadline"]=max(j["deadline"],j["arrival"]+j["duration"])
    def sim(policy):
        t=0; done=set(); utility=energy=late=0.0
        while t<horizon:
            avail=[j for j in jobs if j["id"] not in done and j["arrival"]<=t]
            if not avail:
                t+=1; continue
            if policy=="edf":
                avail.sort(key=lambda j:j["deadline"])
            elif policy=="utility":
                avail.sort(key=lambda j:j["utility"],reverse=True)
            else:
                avail.sort(key=lambda j:(j["utility"]/(j["energy"]*j["duration"]),-(max(0,t+j["duration"]-j["deadline"]))),reverse=True)
            j=avail[0]; done.add(j["id"]); t+=j["duration"]; energy+=j["energy"]*j["duration"]
            if t<=j["deadline"]:
                utility+=j["utility"]
            else:
                late+=1
        return {"completed":len(done),"on_time_utility":utility,"energy_proxy":energy,"late_jobs":int(late),
                "objective_proxy":utility-0.05*energy-0.5*late}
    return {"evidence_class":"SIMULATED","claim_boundary":"Energy is a synthetic proxy, not electrical joules.",
            "seed":seed,"edf":sim("edf"),"utility_greedy":sim("utility"),"chrononav_candidate":sim("chrononav"),
            "falsification_rule":"ChronoNav fails this harness if its objective_proxy does not exceed both baselines."}
if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("--seed",type=int,default=19); a.add_argument("--jobs",type=int,default=800); a.add_argument("--horizon",type=int,default=300)
    x=a.parse_args(); print(json.dumps(run(x.seed,x.jobs,x.horizon),indent=2,sort_keys=True))
