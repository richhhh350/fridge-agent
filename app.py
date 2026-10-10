import json, math, os, sqlite3, uuid
import deepseek
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'fridge.sqlite3'
# Starter values are approximate demonstration data, editable from food labels.
SEEDS = [
 ('egg','鸡蛋','生，可食部分',143,12.6,9.5,0.7,200),
 ('rice','米饭','熟',130,2.7,0.3,28.2,400),
 ('tomato','番茄','生',18,0.9,0.2,3.9,350),
 ('onion','洋葱','生',40,1.1,0.1,9.3,150),
 ('chicken','鸡胸肉','生，去皮',120,22.5,2.6,0,300),
 ('broccoli','西兰花','生',34,2.8,0.4,6.6,300),
 ('oil','食用油','烹调投入量',884,0,100,0,100),
 ('soy','酱油','液体',53,8.1,0.6,4.9,100)]

@contextmanager
def conn():
    c=sqlite3.connect(DB, timeout=15); c.row_factory=sqlite3.Row
    try:
        with c: yield c
    finally:
        c.close()

def init():
    with conn() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS foods(id TEXT PRIMARY KEY,name TEXT,state TEXT,kcal REAL,p REAL,f REAL,c REAL,stock REAL,expiry TEXT,source TEXT); CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,payload TEXT,committed INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS meals(id TEXT PRIMARY KEY,created TEXT,payload TEXT);')
        if not c.execute('SELECT 1 FROM foods LIMIT 1').fetchone():
            c.executemany('INSERT INTO foods VALUES(?,?,?,?,?,?,?,?,?,?)',[(*f,'','内置演示估算值；请按包装标签校准') for f in SEEDS])

def number(v, low=0, high=100000):
    if isinstance(v,bool): raise ValueError('数值格式错误')
    x=float(v)
    if not math.isfinite(x) or not low<=x<=high: raise ValueError('数值超出允许范围')
    return x

def foods():
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM foods ORDER BY name')]

def calculate(items, servings=1):
    servings=number(servings,0.1,100)
    if not isinstance(items,list) or not 1<=len(items)<=30: raise ValueError('需要 1 至 30 项食材')
    catalog={x['id']:x for x in foods()}; totals=dict.fromkeys(['kcal','p','f','c'],0.0); rows=[]; seen=set()
    for item in items:
        key=item['id']
        if key in seen: raise ValueError('食材重复，请合并重量')
        seen.add(key)
        if key not in catalog: raise ValueError('未知食材，请先添加营养数据')
        food=catalog[key]; grams=number(item['grams'],0.1,10000)
        row={'id':key,'name':food['name'],'state':food['state'],'grams':grams,'source':food['source'],'missing':round(max(0,grams-food['stock']),2)}
        for k in totals:
            if food[k] is None: raise ValueError('缺少营养数据：'+food['name'])
            val=grams*food[k]/100; totals[k]+=val; row[k]=round(val,2)
        rows.append(row)
    return {'items':rows,'servings':servings,'total':{k:round(v,2) for k,v in totals.items()},'per_serving':{k:round(v/servings,2) for k,v in totals.items()}}

def save_food(d):
    name=str(d['name']).strip()[:60]; state=str(d['state']).strip()[:60]; source=str(d['source']).strip()[:240]
    if not name or not state or not source: raise ValueError('名称、生熟状态和数据来源必填')
    vals=[number(d[k],0,1000 if k=='kcal' else 100) for k in ['kcal','p','f','c']]
    expiry=d.get('expiry','')
    if expiry: datetime.strptime(expiry,'%Y-%m-%d')
    key=d.get('id') or uuid.uuid4().hex
    with conn() as c: c.execute('INSERT INTO foods VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,state=excluded.state,kcal=excluded.kcal,p=excluded.p,f=excluded.f,c=excluded.c,stock=excluded.stock,expiry=excluded.expiry,source=excluded.source',(key,name,state,*vals,number(d['stock']),expiry,source))
    return {'ok':True}

def demo(target,feedback):
    light='少油' in feedback or '清淡' in feedback
    protein='蛋白' in feedback
    recipes=[('番茄鸡蛋炒饭',[('rice',200),('egg',100),('tomato',150),('onion',30),('oil',4 if light else 8),('soy',5)],['番茄、洋葱切小块；鸡蛋打散。','用列出的食用油炒熟鸡蛋，加入蔬菜翻炒。','加入熟米饭和酱油，翻炒至充分热透。']),('鸡胸西兰花饭',[('rice',200),('chicken',180 if protein else 130),('broccoli',160),('oil',4 if light else 8),('soy',8)],['鸡胸肉切小块，西兰花洗净切块。','西兰花煮熟；使用列出的食用油将鸡肉充分炒熟。','加入西兰花和酱油翻炒，与热透的米饭一起装盘。'])]
    idx=1 if protein or '换' in feedback else 0
    title,items,steps=recipes[idx]
    factor=target/calculate([{'id':i,'grams':g} for i,g in items])['total']['kcal']
    return {'title':title,'servings':1,'minutes':20,'items':[{'id':i,'grams':round(g*factor,1)} for i,g in items],'steps':steps,'note':'模板演示：支持“少油 / 清淡 / 高蛋白 / 换一个”，其他自由文本需接入模型。'}

def model_plan(target,feedback,previous):
    config=deepseek.settings(); model=config['model']
    tool_defs=[{'type':'function','function':{'name':'get_inventory','description':'查看库存及每100克营养、生熟状态、来源、日期','parameters':{'type':'object','properties':{},'additionalProperties':False}}},{'type':'function','function':{'name':'calculate_nutrition','description':'按数据库计算整道菜和每份营养及缺少食材。每次改用量必须重新调用。','parameters':{'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'grams':{'type':'number'}},'required':['id','grams']}},'servings':{'type':'number'}},'required':['items','servings']}}}]
    system='你是中文冰箱菜单助手。必须先查询库存，再调用营养计算工具。只使用库存数据库中存在的食材ID，包括油和酱料；可列出需采购数量。优先使用用户记录的较早日期食材，但不判断食用安全。尊重用户忌口和要求，无法满足请解释。营养不可凭空估算；以工具计算为准。目标为每份热量，允许10%偏差。最多5轮工具交互。最终只输出JSON对象：title,servings(人数),minutes,items([{id,grams}]整锅用量),steps(字符串数组),note。不要输出markdown。'
    messages=[{'role':'system','content':system},{'role':'user','content':json.dumps({'target_kcal_per_serving':target,'request':feedback,'previous_plan':previous},ensure_ascii=False)}]; trace=[]; calculated=False
    for _ in range(6):
        payload={'model':model,'messages':messages,'tools':tool_defs,'temperature':0.4}
        if config['provider']=='deepseek': payload['thinking']={'type':'disabled'}
        result=deepseek.request('/chat/completions',payload)
        try: msg=result['choices'][0]['message']
        except (KeyError,IndexError,TypeError): raise ValueError('模型没有返回有效回复，请重试') from None
        messages.append({k:msg[k] for k in ['role','content','tool_calls','reasoning_content'] if k in msg})
        calls=msg.get('tool_calls',[])
        if not calls:
            if not calculated: raise ValueError('模型未调用营养计算工具，请重试')
            raw=msg.get('content','').strip()
            if raw.startswith('```'): raw=raw.split('\n',1)[1].rsplit('```',1)[0]
            return json.loads(raw),trace
        if len(calls)>8: raise ValueError('模型一次调用工具过多')
        for call in calls:
            name=call['function']['name']
            try:
                args=json.loads(call['function']['arguments'])
                if name=='get_inventory': result=foods()
                elif name=='calculate_nutrition': result=calculate(args['items'],args.get('servings',1)); calculated=True
                else: raise ValueError('未知工具')
                trace.append(name)
            except (ValueError,KeyError,TypeError) as e: result={'error':str(e)}
            messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(result,ensure_ascii=False)})
    raise ValueError('模型达到6轮上限，请简化要求重试')

def plan(d):
    target=number(d.get('target',600),100,3000); feedback=str(d.get('feedback',''))[:3000]; mode=d.get('mode','demo')
    previous=None
    if d.get('previous_id'):
        with conn() as c:
            row=c.execute('SELECT payload FROM plans WHERE id=?',(d['previous_id'],)).fetchone()
            if row: previous=json.loads(row[0])
    raw,trace=model_plan(target,feedback,previous) if mode=='ai' else (demo(target,feedback),['模板选择','calculate_nutrition'])
    result=calculate(raw['items'],raw.get('servings',1))
    if not isinstance(raw['steps'],list) or not raw['steps'] or not all(isinstance(x,str) for x in raw['steps']): raise ValueError('模型返回的步骤格式不正确')
    result.update(id=uuid.uuid4().hex,title=str(raw['title'])[:100],steps=raw['steps'][:20],note=str(raw.get('note',''))[:1500],minutes=number(raw.get('minutes',20),1,600),target=target,mode=mode,trace=trace)
    result['deviation']=round(result['per_serving']['kcal']-target,1)
    with conn() as c: c.execute('INSERT INTO plans(id,payload) VALUES(?,?)',(result['id'],json.dumps(result,ensure_ascii=False)))
    return result

def commit(d):
    fraction=number(d.get('fraction',1),0.01,1)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT payload,committed FROM plans WHERE id=?',(d['id'],)).fetchone()
        if not row: raise ValueError('菜单不存在')
        if row[1]: raise ValueError('这份菜单已经记录过，请勿重复提交')
        p=json.loads(row[0]); current={x['id']:x['stock'] for x in c.execute('SELECT id,stock FROM foods')}
        for item in p['items']:
            if current.get(item['id'],0)+1e-6<item['grams']: raise ValueError(item['name']+'库存不足，请补充库存后再确认烹饪')
        for item in p['items']: c.execute('UPDATE foods SET stock=stock-? WHERE id=?',(item['grams'],item['id']))
        record={'title':p['title'],'fraction':fraction,'nutrition':{k:round(v*fraction,2) for k,v in p['total'].items()},'plan':p}
        c.execute('INSERT INTO meals VALUES(?,?,?)',(p['id'],datetime.now().astimezone().isoformat(),json.dumps(record,ensure_ascii=False)))
        c.execute('UPDATE plans SET committed=1 WHERE id=?',(p['id'],))
    return {'ok':True}

def state():
    with conn() as c: meals=[{'id':r['id'],'created':r['created'],**json.loads(r['payload'])} for r in c.execute('SELECT * FROM meals ORDER BY created DESC')]
    today=datetime.now().astimezone().date().isoformat()
    totals={k:round(sum(m['nutrition'][k] for m in meals if m['created'][:10]==today),2) for k in ['kcal','p','f','c']}
    return {'foods':foods(),'meals':meals,'today':totals,'ai_ready':deepseek.public_settings()['configured'],'model_config':deepseek.public_settings()}

class Handler(BaseHTTPRequestHandler):
    def send_json(self,data,status=200):
        b=json.dumps(data,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.headers.get('Host') not in {'127.0.0.1:8765','localhost:8765'}: return self.send_json({'error':'不允许的主机'},403)
        if self.path=='/api/state': return self.send_json(state())
        assets={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        if self.path not in assets: return self.send_json({'error':'未找到'},404)
        path=ROOT/assets[self.path]; b=path.read_bytes(); self.send_response(200); self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[path.suffix[1:]]); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        if self.headers.get('Host') not in {'127.0.0.1:8765','localhost:8765'}: return self.send_json({'error':'不允许的主机'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://127.0.0.1:8765','http://localhost:8765'}: return self.send_json({'error':'不允许跨站请求'},403)
        try:
            length=int(self.headers.get('Content-Length',0))
            if length<1 or length>50000: raise ValueError('请求大小不合法')
            if not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError('请求必须为JSON')
            d=json.loads(self.rfile.read(length)); routes={'/api/model-config':deepseek.save_settings,'/api/model-test':deepseek.test_connection,'/api/food':save_food,'/api/plan':plan,'/api/commit':commit,'/api/calculate':lambda d:calculate(d['items'],d.get('servings',1))}
            if self.path not in routes: return self.send_json({'error':'未找到'},404)
            self.send_json(routes[self.path](d))
        except (ValueError,KeyError,TypeError,OverflowError) as e: self.send_json({'error':str(e)},400)
        except Exception: self.send_json({'error':'操作失败，请检查模型服务连接或本地数据文件'},500)

if __name__=='__main__':
    init(); print('Fridge Agent: http://127.0.0.1:8765',flush=True); ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
