#!/usr/bin/env python3
import argparse, hashlib, json, random, statistics, time, uuid
from pathlib import Path

EXP='EDEN-TERMUX-INTERLEAVED-001'
ARMS=('CONTROL','CACHE','EDEN')

def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def sha(x): return 'sha256:'+hashlib.sha256(x if isinstance(x,bytes) else canon(x)).hexdigest()
def work(seed,iters):
    x=(seed*2654435761)&0xffffffff
    for i in range(iters):
        x^=(x<<13)&0xffffffff; x^=x>>17; x^=(x<<5)&0xffffffff; x=(x+i*17)&0xffffffff
    return x

def make_requests(n,reuse):
    unique=max(1,n-int(round(n*reuse))); seq=list(range(1,unique+1)); i=0
    while len(seq)<n: seq.append(seq[i%unique]); i+=1
    return seq[:n]

def pct(xs,p):
    s=sorted(xs); return s[min(len(s)-1,int((len(s)-1)*p))]

class Arm:
    def __init__(self,name,iters): self.name=name; self.iters=iters; self.cache={}; self.hits=0; self.full=0
    def run(self,seed):
        key=sha({'seed':seed,'iterations':self.iters})
        if self.name in ('CACHE','EDEN') and key in self.cache:
            rec=self.cache[key]; self.hits+=1
            if self.name=='EDEN' and rec['proof']!=sha({'key':key,'value':rec['value']}): raise RuntimeError('integrity failure')
            value=rec['value']
        else:
            value=work(seed,self.iters); self.full+=1
            if self.name in ('CACHE','EDEN'):
                self.cache[key]={'value':value,'proof':sha({'key':key,'value':value})}
        if self.name=='EDEN':
            _=sha({'input':key,'output':sha({'seed':seed,'value':value}),'reused':key in self.cache})
        return value

def one_case(n,iters,reuse,seed):
    seq=make_requests(n,reuse); states={a:Arm(a,iters) for a in ARMS}; rows=[]
    for i,s in enumerate(seq):
        order=list(ARMS); random.Random(seed+i*1000003+int(reuse*10000)).shuffle(order)
        vals={}
        for a in order:
            c0=time.thread_time_ns(); w0=time.perf_counter_ns(); v=states[a].run(s); c=(time.thread_time_ns()-c0)/1e9; w=(time.perf_counter_ns()-w0)/1e9
            vals[a]=v; rows.append({'i':i,'seed':s,'arm':a,'cpu_s':c,'wall_s':w,'value':v,'order':order})
        if len(set(vals.values()))!=1: raise RuntimeError(f'output mismatch at request {i}')
    out={}
    for a in ARMS:
        rs=[r for r in rows if r['arm']==a]; cp=[r['cpu_s'] for r in rs]; wa=[r['wall_s'] for r in rs]
        out[a]={'cpu_seconds':sum(cp),'wall_seconds':sum(wa),'cpu_mean_ms':statistics.mean(cp)*1000,'cpu_p95_ms':pct(cp,.95)*1000,'wall_mean_ms':statistics.mean(wa)*1000,'wall_p95_ms':pct(wa,.95)*1000,'reuse_hits':states[a].hits,'full_executions':states[a].full}
    paired=[]
    for i in range(n):
        d={r['arm']:r for r in rows if r['i']==i}
        paired.append({'i':i,'eden_minus_control_cpu_ms':(d['EDEN']['cpu_s']-d['CONTROL']['cpu_s'])*1000,'eden_minus_cache_cpu_ms':(d['EDEN']['cpu_s']-d['CACHE']['cpu_s'])*1000})
    emc=statistics.mean(x['eden_minus_control_cpu_ms'] for x in paired); emk=statistics.mean(x['eden_minus_cache_cpu_ms'] for x in paired)
    zero_check=None
    if reuse==0:
        rel=(out['EDEN']['cpu_seconds']/out['CONTROL']['cpu_seconds']-1)*100
        zero_check={'eden_vs_control_cpu_pct':rel,'status':'PASS_EXPECTED_OVERHEAD' if rel>=0 else 'INVESTIGATE_NEGATIVE_DELTA'}
    return {'reuse_target':reuse,'observed_reuse':states['EDEN'].hits/n,'arms':out,'paired_mean_eden_minus_control_cpu_ms':emc,'paired_mean_eden_minus_cache_cpu_ms':emk,'output_equivalence':True,'zero_reuse_invariant':zero_check}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--requests',type=int,default=600); p.add_argument('--iterations',type=int,default=30000); p.add_argument('--reuse',type=float,nargs='+',default=[0,.5]); p.add_argument('--seed',type=int,default=1729); p.add_argument('--output-dir',default='experiments/eden-termux-interleaved-001/results'); a=p.parse_args()
    rid=str(uuid.uuid4()); print('='*72); print(EXP); print('Per-request randomized interleaving: CONTROL / CACHE / EDEN'); print('='*72)
    cases=[]
    for r in a.reuse:
        print(f'Running reuse {r:.0%}...',flush=True); c=one_case(a.requests,a.iterations,r,a.seed); cases.append(c)
        print(f"CONTROL CPU {c['arms']['CONTROL']['cpu_seconds']:.3f}s | CACHE {c['arms']['CACHE']['cpu_seconds']:.3f}s | EDEN {c['arms']['EDEN']['cpu_seconds']:.3f}s")
        print(f"paired EDEN-CONTROL {c['paired_mean_eden_minus_control_cpu_ms']:+.3f} ms/request | EDEN-CACHE {c['paired_mean_eden_minus_cache_cpu_ms']:+.3f} ms/request")
        if c['zero_reuse_invariant']: print('0% invariant:',c['zero_reuse_invariant']['status'],f"({c['zero_reuse_invariant']['eden_vs_control_cpu_pct']:+.2f}%)")
    report={'experiment':EXP,'run_id':rid,'evidence_class':'MEASURED_TERMUX_THREAD_CPU_INTERLEAVED','config':vars(a),'cases':cases,'truth_boundary':{'measured':'same-process per-request randomized interleaved thread CPU/wall time','not_measured':['device joules','Azure billing','GPU performance']}}
    report['report_commitment']=sha(report); d=Path(a.output_dir); d.mkdir(parents=True,exist_ok=True); f=d/f'{EXP}-{rid[:8]}.json'; f.write_text(json.dumps(report,indent=2,sort_keys=True)); print('OUTPUT EQUIVALENCE: PASS'); print('REPORT COMMITMENT:',report['report_commitment']); print('SAVED:',f)
if __name__=='__main__': main()
