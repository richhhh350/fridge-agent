"""DeepSeek connection and local-only configuration, using the standard library."""
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path
from threading import Lock

CONFIG_PATH = Path(__file__).resolve().parent / '.local-model.json'
LOCK = Lock()
DEFAULT_BASE = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-flash'


def settings():
    with LOCK:
        try:
            local = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except FileNotFoundError:
            local = {}
        except (ValueError, OSError):
            raise ValueError('本地模型配置无法读取，请检查 .local-model.json') from None
    generic = bool(os.environ.get('FRIDGE_API_BASE'))
    key = os.environ.get('FRIDGE_API_KEY') if generic else os.environ.get('DEEPSEEK_API_KEY')
    model = os.environ.get('FRIDGE_MODEL') if generic else os.environ.get('DEEPSEEK_MODEL')
    return {
        'base': (os.environ.get('FRIDGE_API_BASE') or DEFAULT_BASE).rstrip('/'),
        'key': (key or ('' if generic else local.get('key', ''))).strip(),
        'model': (model or (DEFAULT_MODEL if generic else local.get('model', DEFAULT_MODEL))).strip(),
        'provider': 'compatible' if generic else 'deepseek',
        'environment_key': bool(key),
    }


def public_settings():
    cfg = settings()
    return {'provider': cfg['provider'], 'model': cfg['model'], 'configured': bool(cfg['key']),
            'environment_key': cfg['environment_key']}


def save_settings(data):
    if os.environ.get('FRIDGE_API_BASE'):
        raise ValueError('当前使用 FRIDGE_API_BASE 环境配置；请移除该环境变量后重启，再使用 DeepSeek 配置入口')
    if os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('密钥由环境变量管理，请在本机环境中修改后重启')
    key = str(data.get('key', '')).strip()
    model = str(data.get('model', DEFAULT_MODEL)).strip()
    if not model or len(model)>100 or any(c.isspace() for c in model):
        raise ValueError('请填写有效的模型名称')
    if not key or len(key)>512 or any(c.isspace() for c in key):
        raise ValueError('请填写有效的 API 密钥，不要包含空格或换行')
    with LOCK:
        temp = CONFIG_PATH.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps({'key':key,'model':model}),encoding='utf-8')
            try: temp.chmod(0o600)
            except OSError: pass
            temp.replace(CONFIG_PATH)
        finally:
            if temp.exists(): temp.unlink()
    return {'ok':True, **public_settings()}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, payload=None):
    cfg=settings()
    if not cfg['key']:
        raise ValueError('请先在 DeepSeek 设置中填写 API 密钥')
    if not cfg['base'].startswith('https://') and not cfg['base'].startswith(('http://127.0.0.1:', 'http://localhost:')):
        raise ValueError('API 地址须使用 HTTPS 或本机 HTTP')
    req=urllib.request.Request(cfg['base']+path,
        data=None if payload is None else json.dumps(payload).encode('utf-8'),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+cfg['key']})
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        reasons={400:'请求或模型参数无效',401:'API 密钥无效',402:'账户余额不足',403:'账户没有访问权限',404:'模型或接口不存在',429:'请求过于频繁，请稍后再试',500:'模型服务暂时异常',503:'模型服务繁忙，请稍后再试'}
        raise ValueError(reasons.get(e.code,'模型请求失败')+'（HTTP '+str(e.code)+'）') from None
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        raise ValueError('无法连接模型服务或请求超时，请检查网络后重试') from None
    except (ValueError, TypeError):
        raise ValueError('模型服务返回了无效数据，请稍后重试') from None


def test_connection(_=None):
    result=request('/models')
    models=[x.get('id') for x in result.get('data',[]) if isinstance(x,dict)]
    if settings()['model'] not in models:
        raise ValueError('连接成功，但当前模型不在可用列表中。可用模型：'+', '.join(str(x) for x in models)[:500])
    return {'ok':True,'message':'连接成功，当前模型可用。菜单生成会消耗 API 额度。'}
