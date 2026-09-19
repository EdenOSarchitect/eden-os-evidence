#!/usr/bin/env python3
import argparse, hashlib, json, math, random, statistics, time, uuid
from collections import Counter
from pathlib import Path

EXP="EDEN-AZURE-WORKLOAD-ANALYTICS-001"

def canon(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(x): return "sha256:"+hashlib.sha256(x if isinstance(x,bytes) else canon(x)).hexdigest()

def make_trace(n, seed=20260901):
    r=random.Random(seed)
    hot=[f"tenant-{i:03d}" for i in range(40)]
    trace=[]
    for i in range(n):
        if i and r.random()<0.58:
            base=trace[r.randrange(max(1,len(trace)//2), len(trace))] if len(trace)>2 else trace[0]
            trace.append(base)
            continue
        tenant=r.choice(hot)
        events=[]
        for j in range(64):
            v=((i+1)*(j+7)*2654435761) & 0xffffffff
            events.append({"ts":1700000000+j,"kind":["read","write","infer","cache"][v%4],"value":v%10000,"tenant":tenant})
        trace.append(canon({"tenant":tenant,"events":events}))
    return trace

def analytics(blob, rounds):
    obj=json.loads(blob)
    counts=Counter(); total=0; mx=0
    for _ in range(rounds):
        for e in obj["events"]:
            counts[e["kind"]]+=1; total+=e["value"]; mx=max(mx,e["value"])
        total=(total*1103515245+12345)&0x7fffffff
    out={"tenant":obj["tenant"],"counts":dict(sorted(counts.items())),"score":total,"max":mx}
    return out

def run(trace, rounds, seed):
    cache={}; eden_cache={}; rows=[]; order_rng=random.Random(seed)
    unique=len({hashlib.sha256(x).digest() for x in trace}); observed_reuse=1-unique/len(trace)
    for idx,blob in enumerate(trace):
        key=sha(blob); arm_order=["CONTROL","CACHE","EDEN"]; order_rng.shuffle(arm_order); per={}
        for arm in arm_order:
            c0=time.process_time_ns(); w0=time.perf_counter_ns(); reused=False
            if arm=="CONTROL":
                out=analytics(blob,rounds)
            elif arm=="CACHE":
                if key in cache: out=cache[key]; reused=True
                else: out=analytics(blob,rounds); cache[key]=out
            else:
                rec=eden_cache.get(key)
                if rec is not None:
                    if rec["proof"]!=sha({"input":key,"output":rec["output"]}): raise RuntimeError("EDEN integrity failure")
                    out=rec["output"]; reused=True
                else:
                    out=analytics(blob,rounds)
                    rec={"output":out}; rec["proof"]=sha({"input":key,"output":out}); eden_cache[key]=rec
                _evidence=sha({"experiment":EXP,"request":idx,"input":key,"output":sha(out),"reused":reused})
            cpu=(time.process_time_ns()-c0)/1e6; wall=(time.perf_counter_ns()-w0)/1e6
            per[arm]={"cpu_ms":cpu,"wall_ms":wall,"reused":reused,"output_commitment":sha(out)}
        eq=len({per[a]["output_commitment"] for a in per})==1
        rows.append({"index":idx,"order":arm_order,"equivalent":eq,"arms":per})
        if (idx+1)%500==0: print(f"{idx+1:,}/{len(trace):,}",flush=True)
    return rows, observed_reuse

def summarize(rows):
    out={}
    for arm in ["CONTROL","CACHE","EDEN"]:
        cpu=[r["arms"][arm]["cpu_ms"] for r in rows]; wall=[r["arms"][arm]["wall_ms"] for r in rows]
        out[arm]={"cpu_total_s":sum(cpu)/1000,"wall_total_s":sum(wall)/1000,"cpu_mean_ms":statistics.mean(cpu),"wall_mean_ms":statistics.mean(wall),"reuse_hits":sum(r["arms"][arm]["reused"] for r in rows)}
    out["all_outputs_equivalent"]=all(r["equivalent"] for r in rows)
    out["paired_eden_minus_control_cpu_ms_mean"]=statistics.mean(r["arms"]["EDEN"]["cpu_ms"]-r["arms"]["CONTROL"]["cpu_ms"] for r in rows)
    out["paired_eden_minus_cache_cpu_ms_mean"]=statistics.mean(r["arms"]["EDEN"]["cpu_ms"]-r["arms"]["CACHE"]["cpu_ms"] for r in rows)
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--requests",type=int,default=2500); ap.add_argument("--rounds",type=int,default=80); ap.add_argument("--seed",type=int,default=20260901); ap.add_argument("--environment",default="AZURE_VM"); ap.add_argument("--output-dir",default="experiments/eden-azure-workload-analytics-001/results"); a=ap.parse_args()
    trace=make_trace(a.requests,a.seed); trace_commit=sha([sha(x) for x in trace]); rid=str(uuid.uuid4())
    print("="*78); print(" EDEN AZURE ANALYTICS WORKLOAD — INTERLEAVED"); print(" "+EXP); print("="*78); print(f"Run ID: {rid}\nRequests: {a.requests:,}\nRounds/request: {a.rounds}\nTrace commitment: {trace_commit}")
    rows,reuse=run(trace,a.rounds,a.seed+99); s=summarize(rows)
    report={"experiment":EXP,"evidence_class":"MEASURED_HOST_PROCESS_INTERLEAVED","environment":a.environment,"run_id":rid,"configuration":vars(a),"trace_commitment":trace_commit,"observed_exact_reuse_fraction":reuse,"summary":s,"truth_boundary":{"measured":["paired process CPU/wall timing","observed exact duplicate fraction","exact output equivalence"],"not_claimed":["Azure billing savings","datacentre energy savings","production workload generality"]}}
    report["report_commitment"]=sha(report); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); f=out/f"{EXP}-{rid[:8]}.json"; f.write_text(json.dumps(report,indent=2,sort_keys=True))
    c=s["CONTROL"]["cpu_total_s"]; e=s["EDEN"]["cpu_total_s"]; k=s["CACHE"]["cpu_total_s"]
    print("\n"+"="*78+"\n RESULTS\n"+"="*78); print(f"OBSERVED EXACT REUSE: {reuse:.2%}"); print("OUTPUT EQUIVALENCE:","PASS" if s["all_outputs_equivalent"] else "FAIL"); print(f"CONTROL CPU: {c:.6f}s"); print(f"CACHE CPU:   {k:.6f}s"); print(f"EDEN CPU:    {e:.6f}s"); print(f"EDEN CPU reduction vs CONTROL: {(1-e/c)*100:.2f}%"); print(f"EDEN CPU delta vs CACHE:       {(e/k-1)*100:+.2f}%"); print(f"Paired EDEN-CONTROL CPU: {s['paired_eden_minus_control_cpu_ms_mean']:+.4f} ms/request"); print(f"Paired EDEN-CACHE CPU:   {s['paired_eden_minus_cache_cpu_ms_mean']:+.4f} ms/request"); print("REPORT COMMITMENT:",report["report_commitment"]); print("SAVED:",f)

if __name__=="__main__": main()
