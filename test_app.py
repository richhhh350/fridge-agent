import unittest, tempfile, pathlib, json
from unittest.mock import patch
import app

class FridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=app.DB; app.DB=pathlib.Path(self.tmp.name)/'test.sqlite3'; app.init()
    def tearDown(self):
        app.DB=self.old; self.tmp.cleanup()
    def test_calories_and_servings(self):
        n=app.calculate([{'id':'rice','grams':200},{'id':'oil','grams':10}],2)
        self.assertAlmostEqual(n['total']['kcal'],348.4); self.assertAlmostEqual(n['per_serving']['kcal'],174.2)
    def test_reject_bad_nutrition(self):
        for items in [[{'id':'unknown','grams':10}],[{'id':'rice','grams':-1}],[{'id':'rice','grams':float('nan')}],[{'id':'rice','grams':1},{'id':'rice','grams':2}]]:
            with self.assertRaises(ValueError): app.calculate(items)
    def test_half_eaten_full_stock_deduction_and_duplicate(self):
        p=app.plan({'target':500}); before={f['id']:f['stock'] for f in app.foods()}
        app.commit({'id':p['id'],'fraction':0.5}); after={f['id']:f['stock'] for f in app.foods()}
        for i in p['items']: self.assertAlmostEqual(before[i['id']]-after[i['id']],i['grams'])
        self.assertAlmostEqual(app.state()['today']['kcal'],round(p['total']['kcal']/2,2))
        with self.assertRaises(ValueError): app.commit({'id':p['id']})
    def test_insufficient_stock_is_atomic(self):
        p=app.plan({'target':3000}); before=app.foods()
        with self.assertRaises(ValueError): app.commit({'id':p['id']})
        self.assertEqual(before,app.foods()); self.assertEqual(app.state()['meals'],[])
    def test_food_validation_and_persistence(self):
        f=app.foods()[0]; f['stock']=123; app.save_food(f); self.assertEqual(app.foods()[0]['stock'],123)
        f['kcal']='nan'
        with self.assertRaises(ValueError): app.save_food(f)
    def test_target_and_feedback(self):
        p=app.plan({'target':600,'feedback':'高蛋白，少油'})
        self.assertLess(abs(p['deviation']),2); self.assertIn('鸡胸',p['title'])
    def test_agent_loop(self):
        class Response:
            def __init__(self,m): self.value=json.dumps({'choices':[{'message':m}]}).encode()
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self): return self.value
        def tool(name,args,id): return {'id':id,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}
        recipe=app.demo(600,''); messages=[{'role':'assistant','tool_calls':[tool('get_inventory',{},'a')]},{'role':'assistant','tool_calls':[tool('calculate_nutrition',{'items':recipe['items'],'servings':1},'b')]},{'role':'assistant','content':json.dumps(recipe)}]
        with patch.dict(app.os.environ,{'FRIDGE_API_BASE':'https://example.invalid/v1','FRIDGE_MODEL':'test'}),patch('deepseek.request',side_effect=[{'choices':[{'message':m}]} for m in messages]):
            p=app.plan({'mode':'ai','target':600}); self.assertEqual(p['trace'],['get_inventory','calculate_nutrition']); self.assertLess(abs(p['deviation']),2)

if __name__=='__main__': unittest.main()
