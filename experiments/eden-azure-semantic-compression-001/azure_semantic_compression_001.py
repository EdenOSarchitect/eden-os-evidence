#!/usr/bin/env python3
import argparse, hashlib, json, random, statistics, time, zlib
from pathlib import Path

RUN_ID = "EDEN-AZURE-SEMANTIC-COMPRESSION-001"
OUTDIR = Path(__file__).resolve().parent / "results"
OUTDIR.mkdir(parents=True, exist_ok=True)

SERVICES = ["auth","billing","search","orders","profile","recommendations","telemetry","storage"]
REGIONS = ["uksouth","ukwest","westeurope","northeurope"]
LEVELS = ["INFO","WARN","ERROR"]
EVENTS = ["request_ok","cache_hit","timeout","retry","quota_check","write_ok","read_ok","validation_ok"]
TEMPLATES = [
    "service={service} region={region} event={event} level={level} tenant={tenant} request completed with status={status}",
    "tenant={tenant} service={service} observed {event} in {region}; status={status}; level={level}",
    "{level} {service}/{region}: {event} tenant={tenant} status={status}",
]

def canon(x):
    return json.dumps(x, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()

def sha(b): return "sha256:" + hashlib.sha256(b).hexdigest()

def make_trace(n, seed):
    r = random.Random(seed)
    rows=[]
    for i in range(n):
        service=r.choice(SERVICES); region=r.choice(REGIONS); level=r.choices(LEVELS,[0.84,0.11,0.05])[0]
        event=r.choice(EVENTS); tenant=f"tenant-{r.randrange(1,101):03d}"; status=200 if level=="INFO" else (429 if level=="WARN" else 500)
        msg=r.choice(TEMPLATES).format(service=service,region=region,event=event,level=level,tenant=tenant,status=status)
        rows.append({
            "id": i,
            "ts_ms": 1760000000000+i*7,
            "service":service,"region":region,"level":level,"event":event,"tenant":tenant,"status":status,
            "message":msg,
            "trace_id": hashlib.sha256(f"trace:{seed}:{i}".encode()).hexdigest(),
            "span_id": hashlib.sha256(f"span:{seed}:{i}".encode()).hexdigest()[:16],
            "sdk":"eden-benchmark-agent/1.0.0",
            "schema":"telemetry.event.v1"
        })
    return rows

def eden_pack(rows, keep_message=False):
    # Semantic representation: dictionary-code repeated categorical values and retain fields
    # required by the declared query suite. message can optionally be retained.
    dicts={
        "service":sorted({x["service"] for x in rows}), "region":sorted({x["region"] for x in rows}),
        "level":sorted({x["level"] for x in rows}), "event":sorted({x["event"] for x in rows}),
        "tenant":sorted({x["tenant"] for x in rows}),
    }
    ix={k:{v:i for i,v in enumerate(vals)} for k,vals in dicts.items()}
    packed=[]
    for x in rows:
        a=[x["id"],x["ts_ms"],ix["service"][x["service"]],ix["region"][x["region"]],ix["level"][x["level"]],ix["event"][x["event"]],ix["tenant"][x["tenant"]],x["status"]]
        if keep_message: a.append(x["message"])
        packed.append(a)
    return {"v":1,"dict":dicts,"base_fields":["id","ts_ms","service","region","level","event","tenant","status"] + (["message"] if keep_message else []),"rows":packed}

def unpack(p):
    d=p["dict"]; out=[]; has_msg="message" in p["base_fields"]
    for a in p["rows"]:
        x={"id":a[0],"ts_ms":a[1],"service":d["service"][a[2]],"region":d["region"][a[3]],"level":d["level"][a[4]],"event":d["event"][a[5]],"tenant":d["tenant"][a[6]],"status":a[7]}
        if has_msg: x["message"]=a[8]
        out.append(x)
    return out

def semantics(rows):
    # Predeclared application semantics. This is the quality boundary, not byte identity.
    by_level={k:0 for k in LEVELS}; by_service={k:0 for k in SERVICES}; by_region={k:0 for k in REGIONS}
    errors_by_service={k:0 for k in SERVICES}; tenant_fail={}
    status_sum=0
    for x in rows:
        by_level[x["level"]]+=1; by_service[x["service"]]+=1; by_region[x["region"]]+=1; status_sum += x["status"]
        if x["status"] >= 400:
            errors_by_service[x["service"]]+=1; tenant_fail[x["tenant"]]=tenant_fail.get(x["tenant"],0)+1
    top_fail=sorted(tenant_fail.items(), key=lambda kv:(-kv[1],kv[0]))[:20]
    return {"n":len(rows),"by_level":by_level,"by_service":by_service,"by_region":by_region,"errors_by_service":errors_by_service,"top_failed_tenants":top_fail,"status_sum":status_sum}

def score(a,b):
    # Exact equality of every declared semantic output => 1.0, otherwise fieldwise fraction.
    if a==b: return 1.0
    keys=list(a.keys()); return sum(a.get(k)==b.get(k) for k in keys)/len(keys)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--records",type=int,default=100000)
    ap.add_argument("--seed",type=int,default=20260901)
    ap.add_argument("--quality-threshold",type=float,default=1.0)
    ap.add_argument("--environment",default="AZURE_VM")
    args=ap.parse_args()

    t0=time.process_time(); rows=make_trace(args.records,args.seed); gen_cpu=time.process_time()-t0
    raw=canon(rows); baseline_sem=semantics(rows)

    trials=[]
    for mode,keep_msg in [("EDEN_TASK_SEMANTIC",False),("EDEN_MESSAGE_PRESERVING",True)]:
        t=time.process_time(); packed=eden_pack(rows,keep_msg); pack_cpu=time.process_time()-t
        enc=canon(packed)
        t=time.process_time(); restored=unpack(packed); unpack_cpu=time.process_time()-t
        q=score(baseline_sem, semantics(restored))
        trials.append({
            "mode":mode,"bytes":len(enc),"compressed_bytes_zlib":len(zlib.compress(enc,9)),
            "semantic_reduction_pct":100*(1-len(enc)/len(raw)),
            "semantic_plus_zlib_reduction_pct":100*(1-len(zlib.compress(enc,9))/len(raw)),
            "quality":q,"threshold":args.quality_threshold,"threshold_pass":q>=args.quality_threshold,
            "pack_cpu_s":pack_cpu,"unpack_cpu_s":unpack_cpu,"commitment":sha(enc)
        })

    raw_z=zlib.compress(raw,9)
    eligible=[x for x in trials if x["threshold_pass"]]
    best=max(eligible,key=lambda x:x["semantic_reduction_pct"]) if eligible else None
    report={
        "run_id":RUN_ID,"environment":args.environment,"records":args.records,"seed":args.seed,
        "evidence_class":"MEASURED_HOST_PROCESS_AND_BYTES","quality_boundary":"EXACT_DECLARED_QUERY_SUITE",
        "quality_threshold":args.quality_threshold,"raw_bytes":len(raw),"raw_zlib_bytes":len(raw_z),
        "conventional_zlib_reduction_pct":100*(1-len(raw_z)/len(raw)),"trace_commitment":sha(raw),
        "generation_cpu_s":gen_cpu,"trials":trials,"best_threshold_passing_mode":best["mode"] if best else None,
        "best_semantic_reduction_pct":best["semantic_reduction_pct"] if best else None,
        "truth_boundary":"Semantic reduction is measured against the declared analytics semantics; it is not lossless source compression. zlib is the conventional byte-compression comparator. No network, Azure bill, datacentre-energy, or universal semantic-compression claim is made."
    }
    report_commitment=sha(canon(report)); report["report_commitment"]=report_commitment
    out=OUTDIR/f"{RUN_ID}-{report_commitment.split(':')[1][:8]}.json"; out.write_bytes(canon(report)+b"\n")

    print("="*78); print(" EDEN AZURE SEMANTIC COMPRESSION 001"); print("="*78)
    print(f"Records:                    {args.records:,}")
    print(f"Raw bytes:                  {len(raw):,}")
    print(f"Conventional zlib bytes:    {len(raw_z):,}")
    print(f"Conventional zlib reduction:{100*(1-len(raw_z)/len(raw)):8.2f}%")
    print(f"Quality threshold:          {args.quality_threshold:.6f}")
    for x in trials:
        print("-")
        print(f"Mode:                       {x['mode']}")
        print(f"EDEN bytes:                 {x['bytes']:,}")
        print(f"EDEN semantic reduction:    {x['semantic_reduction_pct']:8.2f}%")
        print(f"EDEN + zlib reduction:      {x['semantic_plus_zlib_reduction_pct']:8.2f}%")
        print(f"Semantic quality:           {x['quality']:.6f}")
        print(f"THRESHOLD:                  {'PASS' if x['threshold_pass'] else 'FAIL'}")
        print(f"Pack CPU:                   {x['pack_cpu_s']:.6f}s")
        print(f"Unpack CPU:                 {x['unpack_cpu_s']:.6f}s")
    print("="*78)
    print(f"BEST THRESHOLD-PASS MODE:   {report['best_threshold_passing_mode']}")
    print(f"BEST SEMANTIC REDUCTION:    {report['best_semantic_reduction_pct']:.2f}%" if best else "BEST SEMANTIC REDUCTION:    NONE")
    print(f"TRACE COMMITMENT:           {report['trace_commitment']}")
    print(f"REPORT COMMITMENT:          {report_commitment}")
    print(f"SAVED:                      {out}")

if __name__=="__main__": main()
