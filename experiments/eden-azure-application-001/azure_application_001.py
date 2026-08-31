#!/usr/bin/env python3
"""EDEN-AZURE-APPLICATION-001

Real HTTP application benchmark for CONTROL vs conventional CACHE vs EDEN.
Measures application-level resource/capacity metrics and can attach external
Azure telemetry/billing evidence. It does not claim Azure billing or energy
savings unless such evidence is supplied separately.
"""
import argparse, hashlib, json, os, resource, statistics, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EXP="EDEN-AZURE-APPLICATION-001"

def canonical(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(x): return "sha256:"+hashlib.sha256(x if isinstance(x,bytes) else canonical(x)).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()

def work(seed,iters):
    x=(seed*2654435761)&0xffffffff
    for i in range(iters):
        x^=(x<<13)&0xffffffff; x^=x>>17; x^=(x<<5)&0xffffffff; x=(x+i*17)&0xffffffff
    return x

def requests(n,reuse):
    unique=max(1,n-int(round(n*reuse))); a=list(range(1,unique+1)); i=0
    while len(a)<n: a.append(a[i%unique]); i+=1
    return a[:n]

class State:
    def __init__(self,mode,iters): self.mode=mode; self.iters=iters; self.cache={}; self.lock=threading.Lock(); self.full=0; self.hits=0
    def eval(self,seed):
        desc={"workload":"http-deterministic-xorshift-v1","seed":seed,"iterations":self.iters}; key=sha(desc)
        if self.mode in ("CACHE","EDEN"):
            with self.lock:
                rec=self.cache.get(key)
            if rec is not None:
                if self.mode=="EDEN" and sha({"key":key,"value":rec["value"]})!=rec["proof"]: raise RuntimeError("integrity failure")
                with self.lock: self.hits+=1
                value=rec["value"]
            else:
                value=work(seed,self.iters)
                rec={"value":value,"proof":sha({"key":key,"value":value})}
                with self.lock: self.cache[key]=rec; self.full+=1
        else:
            value=work(seed,self.iters)
            with self.lock: self.full+=1
        out={"seed":seed,"value":value}
        if self.mode=="EDEN":
            out["eden"]={"input_commitment":key,"output_commitment":sha({"seed":seed,"value":value}),"integrity":"VERIFIED"}
        return out

class Handler(BaseHTTPRequestHandler):
    state=None
    def do_POST(self):
        if self.path!="/process": self.send_error(404); return
        try:
            n=int(self.headers.get("Content-Length","0")); obj=json.loads(self.rfile.read(n)); out=self.state.eval(int(obj["seed"])); body=canonical(out)
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as e:
            body=canonical({"error":str(e)}); self.send_response(500); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass

def percentile(xs,p):
    if not xs:return 0.0
    s=sorted(xs); return s[min(len(s)-1,max(0,int((len(s)-1)*p)))]

def post(host,port,seed):
    import http.client
    b=canonical({"seed":seed}); t=time.perf_counter_ns(); c=http.client.HTTPConnection(host,port,timeout=120); c.request("POST","/process",body=b,headers={"Content-Type":"application/json"}); r=c.getresponse(); data=r.read(); c.close(); dt=(time.perf_counter_ns()-t)/1e9
    if r.status!=200: raise RuntimeError(data.decode())
    obj=json.loads(data); return seed,obj["value"],dt,len(b),len(data)

def arm(mode,seeds,iters,concurrency):
    state=State(mode,iters); Handler.state=state; srv=ThreadingHTTPServer(("127.0.0.1",0),Handler); port=srv.server_address[1]; th=threading.Thread(target=srv.serve_forever,daemon=True); th.start()
    cpu0=time.process_time_ns(); wall0=time.perf_counter_ns(); started=utc(); rows=[]
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        fs=[ex.submit(post,"127.0.0.1",port,s) for s in seeds]
        for f in as_completed(fs): rows.append(f.result())
    wall=(time.perf_counter_ns()-wall0)/1e9; cpu=(time.process_time_ns()-cpu0)/1e9; completed=utc(); srv.shutdown(); srv.server_close()
    rows.sort(key=lambda x:(x[0],x[1])); l=[x[2] for x in rows]
    outputs=[{"seed":x[0],"value":x[1]} for x in rows]
    return {"mode":mode,"started_utc":started,"completed_utc":completed,"cpu_seconds":cpu,"wall_seconds":wall,"successful_requests":len(rows),"full_executions":state.full,"reuse_hits":state.hits,"p50_latency_ms":statistics.median(l)*1000,"p95_latency_ms":percentile(l,.95)*1000,"p99_latency_ms":percentile(l,.99)*1000,"requests_per_second":len(rows)/wall,"successful_outputs_per_vm_hour":len(rows)/wall*3600,"max_rss_kb":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"request_bytes":sum(x[3] for x in rows),"response_bytes":sum(x[4] for x in rows),"semantic_output_commitment":sha(outputs)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--requests",type=int,default=3000); ap.add_argument("--iterations",type=int,default=30000); ap.add_argument("--reuse",type=float,default=.5); ap.add_argument("--concurrency",type=int,default=8); ap.add_argument("--environment",default="AZURE_VM"); ap.add_argument("--vm-hour-cost",type=float); ap.add_argument("--external-evidence"); ap.add_argument("--output-dir",default="experiments/eden-azure-application-001/results"); a=ap.parse_args()
    if not(0<=a.reuse<1) or a.requests<1 or a.iterations<1 or a.concurrency<1: raise SystemExit("invalid arguments")
    rid=str(uuid.uuid4()); seq=requests(a.requests,a.reuse); reqc=sha({"requests":seq,"iterations":a.iterations,"reuse":a.reuse}); order=["CONTROL","CACHE","EDEN"]
    print("="*78); print(" EDEN AZURE REAL HTTP APPLICATION BENCHMARK"); print(" "+EXP); print("="*78); print(f"Run ID: {rid}\nRequests/arm: {a.requests:,}\nReuse: {a.reuse:.2%}\nConcurrency: {a.concurrency}\nRequest commitment: {reqc}")
    arms={}
    for m in order:
        print(f"\nRunning {m}...",flush=True); arms[m]=arm(m,seq,a.iterations,a.concurrency); x=arms[m]; print(f"{m}: CPU {x['cpu_seconds']:.3f}s | wall {x['wall_seconds']:.3f}s | p95 {x['p95_latency_ms']:.2f}ms | {x['requests_per_second']:.2f} req/s")
    eq=len({x["semantic_output_commitment"] for x in arms.values()})==1
    def red(x,y): return (1-y/x)*100 if x else 0
    def gain(x,y): return (y/x-1)*100 if x else 0
    cmp={"output_equivalence":eq,"eden_cpu_reduction_vs_control_pct":red(arms['CONTROL']['cpu_seconds'],arms['EDEN']['cpu_seconds']),"eden_cpu_delta_vs_cache_pct":gain(arms['CACHE']['cpu_seconds'],arms['EDEN']['cpu_seconds']),"eden_capacity_gain_vs_control_pct":gain(arms['CONTROL']['successful_outputs_per_vm_hour'],arms['EDEN']['successful_outputs_per_vm_hour']),"eden_p95_latency_delta_vs_control_pct":gain(arms['CONTROL']['p95_latency_ms'],arms['EDEN']['p95_latency_ms'])}
    economics={"status":"MODELLED_FROM_VM_HOUR_PRICE" if a.vm_hour_cost is not None else "NOT_CALCULATED"}
    if a.vm_hour_cost is not None:
        for m,x in arms.items(): economics[m]={"modelled_cost_per_million_successful_outputs":a.vm_hour_cost/(x['successful_outputs_per_vm_hour']/1_000_000)}
    ext=None
    if a.external_evidence:
        p=Path(a.external_evidence); ext={"path":str(p),"sha256":sha(p.read_bytes()),"note":"External Azure telemetry/billing attachment; interpretation remains separate from self-measured process metrics."}
    report={"experiment":EXP,"evidence_class":"MEASURED_AZURE_VM_HTTP_APPLICATION_HOST_METRICS","environment":a.environment,"run_id":rid,"configuration":vars(a),"request_commitment":reqc,"arms":arms,"comparison":cmp,"economics":economics,"external_azure_evidence":ext,"truth_boundary":{"measured":["HTTP application CPU/wall/latency/throughput","reuse/full executions","semantic output equivalence"],"not_measured_without_external_evidence":["Azure datacentre energy","actual Azure invoice savings","independent validation"]}}
    report["report_commitment"]=sha(report); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); f=out/f"{EXP}-{rid[:8]}.json"; f.write_text(json.dumps(report,indent=2,sort_keys=True))
    print("\n"+"="*78+"\n RESULTS\n"+"="*78); print("OUTPUT EQUIVALENCE:","PASS" if eq else "FAIL"); print(f"EDEN CPU REDUCTION vs CONTROL: {cmp['eden_cpu_reduction_vs_control_pct']:.2f}%"); print(f"EDEN CPU DELTA vs CACHE:       {cmp['eden_cpu_delta_vs_cache_pct']:+.2f}%"); print(f"EDEN CAPACITY GAIN:            {cmp['eden_capacity_gain_vs_control_pct']:.2f}%"); print(f"EDEN p95 LATENCY DELTA:        {cmp['eden_p95_latency_delta_vs_control_pct']:+.2f}%"); print("REPORT COMMITMENT:",report['report_commitment']); print("SAVED:",f)
if __name__=="__main__": main()
