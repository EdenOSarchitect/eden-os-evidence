import json, os, random, statistics, platform, time

SEED=20260824
random.seed(SEED)
runner=os.getenv('EDEN_RUNNER_ID','unattributed')
token=os.getenv('EDEN_RUN_TOKEN','local')

policies=['fifo','edf','throughput_greedy','eden_value']
results={p:[] for p in policies}
for _ in range(1000):
    jobs=[]
    for i in range(40):
        size=random.randint(50,500)
        utility=random.uniform(0.5,10.0)
        deadline=random.randint(2,20)
        capacity=random.randint(100,700)
        jobs.append({'size':size,'utility':utility,'deadline':deadline,'capacity':capacity,'idx':i})
    orders={
      'fifo':jobs,
      'edf':sorted(jobs,key=lambda x:x['deadline']),
      'throughput_greedy':sorted(jobs,key=lambda x:x['size']),
      'eden_value':sorted(jobs,key=lambda x:(x['utility']/x['size']),reverse=True)
    }
    budget=5000
    for p,order in orders.items():
        used=0; util=0.0; hit=0
        for j in order:
            if used+j['size']<=budget:
                used+=j['size']; util+=j['utility']; hit+=1
        results[p].append({'utility':util,'bytes':used,'jobs':hit})
summary={}
for p,rows in results.items():
    summary[p]={k:statistics.mean(r[k] for r in rows) for k in ['utility','bytes','jobs']}
out={'experiment':'tafazolli-ntn-001','evidence_class':'SIMULATED / REPRODUCIBLE','runner_id':runner,'run_token':token,'seed':SEED,'timestamp_unix':int(time.time()),'platform':platform.platform(),'python':platform.python_version(),'summary':summary,'truth_boundary':'No physical RF/6G/NTN claim. Independent validation requires attributable external execution and preserved environment metadata.'}
print(json.dumps(out,indent=2,sort_keys=True))
