#!/usr/bin/env python3
"""EDEN/Evans satellite-network testbed trace adapter.
With --trace, evaluates a measured link trace supplied by the experimenter.
Without --trace, uses a clearly-labelled synthetic trace.
"""
import argparse,csv,json,random

def load_trace(path,seed=23,n=180):
    if path:
        rows=[]
        with open(path,newline="",encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append({"capacity":float(r["capacity"]), "loss":float(r.get("loss",0)), "latency_ms":float(r.get("latency_ms",0))})
        return rows,"MEASURED-TRACE-INPUT"
    rng=random.Random(seed)
    return [{"capacity":rng.randint(5,30),"loss":rng.uniform(0,.2),"latency_ms":rng.uniform(20,250)} for _ in range(n)],"SIMULATED"

def run(trace_path=None,seed=23):
    trace,cls=load_trace(trace_path,seed)
    rng=random.Random(seed)
    packets=[{"id":i,"size":rng.randint(1,8),"value":rng.uniform(.1,10)} for i in range(450)]
    def sim(policy):
        pending=[dict(p) for p in packets]; val=0.0; delivered=0; sent=0
        for row in trace:
            cap=row["capacity"]
            pending.sort(key=(lambda p:p["id"]) if policy=="fifo" else (lambda p:p["value"]/p["size"]), reverse=(policy!="fifo"))
            nxt=[]
            for p in pending:
                if p["size"]<=cap:
                    cap-=p["size"]; sent+=p["size"]
                    if rng.random()>=row["loss"]:
                        val+=p["value"]; delivered+=1
                    else:
                        nxt.append(p)
                else:
                    nxt.append(p)
            pending=nxt
        return {"delivered":delivered,"application_value":val,"sent_units":sent}
    state=rng.getstate(); fifo=sim("fifo"); rng.setstate(state); eden=sim("eden")
    return {"evidence_class":cls,"trace_rows":len(trace),
            "claim_boundary":"A measured trace is still not an EDEN-controlled RF test; it is trace replay unless integrated with live testbed I/O.",
            "fifo":fifo,"eden_value_aware":eden,"delta_application_value":eden["application_value"]-fifo["application_value"],
            "trace_csv_columns":["capacity","loss","latency_ms"]}
if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("--trace"); a.add_argument("--seed",type=int,default=23)
    x=a.parse_args(); print(json.dumps(run(x.trace,x.seed),indent=2,sort_keys=True))
