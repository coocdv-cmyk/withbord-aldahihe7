import struct,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
def inspect(p):
    with p.open('rb') as f:
        def num(fmt): return struct.unpack('<'+fmt,f.read(struct.calcsize('<'+fmt)))[0]
        def string(keep=True):
            n=num('Q')
            if keep: return f.read(n).decode('utf-8',errors='replace')
            f.seek(n,1)
        def val(t,keep=True):
            fmts={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
            if t in fmts: return num(fmts[t])
            if t==8: return string(keep)
            if t==9:
                subtype=num('I'); n=num('Q')
                if subtype in fmts: f.seek(struct.calcsize('<'+fmts[subtype])*n,1)
                else:
                    for _ in range(n): val(subtype,False)
                return {'array_type':subtype,'length':n}
            raise ValueError(t)
        magic=f.read(4); version=num('I'); tensors=num('Q'); count=num('Q'); meta={}
        for _ in range(count):
            key=string(); t=num('I'); keep=key.startswith('general.') or key.endswith(('.block_count','.embedding_length','.context_length'))
            value=val(t,keep)
            if keep: meta[key]=value
        return {'file':str(p),'magic':magic.decode(),'gguf_version':version,'tensors':tensors,'bytes':p.stat().st_size,'metadata':meta}
out=[inspect(p) for p in (BASE.parent/'studio/models').glob('*.gguf')]
(BASE/'MODEL-IDENTITY.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=True,indent=2))
