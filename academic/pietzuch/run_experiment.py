import hashlib, json, os, platform, random, time

SEED=20260824
random.seed(SEED)
runner=os.getenv('EDEN_RUNNER_ID','unattributed')
token=os.getenv('EDEN_RUN_TOKEN','local')

def h(x): return hashlib.sha256(x).hexdigest()
def merkle(leaves):
    level=[h(x) for x in leaves]
    while len(level)>1:
        if len(level)%2: level.append(level[-1])
        level=[h((level[i]+level[i+1]).encode()) for i in range(0,len(level),2)]
    return level[0]

N=5000
payloads=[f'task:{i}:value:{random.random()}'.encode() for i in range(N)]
t0=time.perf_counter(); root=merkle(payloads); commit_s=time.perf_counter()-t0
# deterministic adversarial tamper test
sample=list(payloads[:200]); tampered=sample.copy(); tampered[73]=tampered[73]+b':tampered'
orig_root=merkle(sample); tampered_root=merkle(tampered)
false_accept=(orig_root==tampered_root)
# scheduling proxy
jobs=[]
for i in range(1000):
    cost=random.uniform(.1,5.0); utility=random.uniform(.1,20.0)
    jobs.append((utility,cost))
budget=500.0

def run(order):
    used=util=0.0; n=0
    for u,c in order:
        if used+c<=budget:
            used+=c; util+=u; n+=1
    return {'utility':util,'cost':used,'tasks':n}

fifo=run(jobs)
value=run(sorted(jobs,key=lambda x:x[0]/x[1],reverse=True))
out={'experiment':'pietzuch-dist-001','evidence_class':'SIMULATED / REPRODUCIBLE','runner_id':runner,'run_token':token,'seed':SEED,'timestamp_unix':int(time.time()),'platform':platform.platform(),'python':platform.python_version(),'provenance':{'tasks':N,'root':root,'commit_seconds':commit_s,'tasks_per_second':N/commit_s if commit_s else None,'tamper_detected':not false_accept,'false_accept':false_accept},'scheduling':{'fifo':fifo,'eden_value_proxy':value},'truth_boundary':'Local/synthetic distributed-systems proxy only; not a real cluster or independent validation unless externally executed and attributable.'}
print(json.dumps(out,indent=2,sort_keys=True))
