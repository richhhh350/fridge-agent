# 冰箱有戏 · Fridge Agent

一个轻量的本地吃饭助手：管理冰箱食材，用 DeepSeek 规划菜单，由程序计算卡路里和三大营养素，再按实际食用比例记录饮食。

**Python 标准库 + SQLite + 原生 HTML/CSS/JavaScript，零第三方运行依赖。**

## 快速开始

需要 Python 3.10 或以上。

```bash
git clone https://github.com/richhhh350/fridge-agent.git
cd fridge-agent
python app.py
```

打开 **http://127.0.0.1:8765/**。Windows 可双击 `start.bat`。

无需密钥也可使用模板演示。首次启动包含演示库存，实际使用前请替换为自己的食材和营养数据。

## 接入 DeepSeek

1. 在 [DeepSeek 平台](https://platform.deepseek.com/api_keys) 创建 API Key。
2. 打开网页，展开「连接 DeepSeek」。
3. 输入密钥和模型名，点击「保存到本机」。默认模型为 `deepseek-flash`，可以修改。
4. 点击「测试连接」，成功后使用「DeepSeek Agent」模式生成菜单。

网页保存立即生效，无需重启。连接测试只查询模型列表；实际生成菜单会消耗你的 API 额度。配置接口不把密钥返回给网页，页面也不使用 localStorage 存储密钥。

**密钥以明文保存在本机 `.local-model.json` 中**，不要分享这个文件。它、数据库和 `.env` 都已加入 `.gitignore`。程序仅绑定 `127.0.0.1`，不适合直接部署公网。

也可通过环境变量配置（优先于本地文件）：

```powershell
$env:DEEPSEEK_API_KEY="你的密钥"
$env:DEEPSEEK_MODEL="deepseek-flash"
python app.py
```

macOS / Linux：

```bash
export DEEPSEEK_API_KEY="你的密钥"
export DEEPSEEK_MODEL="deepseek-flash"
python app.py
```

程序不会自动加载 `.env`。如需其他兼容服务，可设置 `FRIDGE_API_BASE`、`FRIDGE_API_KEY` 和 `FRIDGE_MODEL`，随后重启。使用这组环境变量时，网页 DeepSeek 配置不会覆盖它们。

接口依据：[DeepSeek 首次调用](https://api-docs.deepseek.com/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。默认请求 `https://api.deepseek.com/chat/completions`，采用非思考模式，并兼容返回的 `reasoning_content`。

## Agent 如何工作

```text
用户提出目标与偏好
  → DeepSeek 查询库存 get_inventory
  → 给出食材用量，调用 calculate_nutrition
  → 根据结果调整菜单
  → 后端重新校验与计算
  → 用户确认做完后，扣减库存并记录实际摄入
```

最多 6 次模型请求，每次网络超时为 60 秒。模型仅有读取和计算工具，不能直接修改库存。调用失败会明确提示，不会偷偷换成模板答案。

使用大模型模式时，库存、营养数据、用户要求和上一份菜单会发送给所配置的模型服务。

## 已实现

- 食材新增与编辑：生熟状态、可食重量、参考日期、每 100 克营养和数据来源。
- DeepSeek 自然语言菜单与反馈：反馈时携带上一份菜单。
- 卡路里、蛋白质、脂肪、碳水计算：包括已列出的油和酱料。
- 显示每份和整锅营养、目标差值及缺料购物清单。
- 做完后扣除整锅用料；根据吃掉的比例记录摄入。
- 防止重复确认；库存不足时整个事务回滚。
- SQLite 持久保存，今日营养汇总按本机日期。
- 中文响应式界面、键盘焦点样式及减少动画支持。

## 数据与功能边界

- 内置营养是明确标记的演示估算值，没有逐项权威来源；实际使用前请按食品包装或可靠成分表校准。
- 重量为可食部分克数；生重和熟重需分别建档。未知营养值不能当作零。
- 模板模式只有两套菜单，识别「少油 / 清淡 / 高蛋白 / 换一个」；自由语言使用 DeepSeek 模式。
- 营养为估算，烹调损耗和吸油差异未建模；本工具不提供医学营养或食材安全判断。
- 尚无跨会话口味记忆；剩菜不会自动入库。
- 页面刷新后需要重新生成当前菜单，已记录饮食仍会保留。
- DeepSeek 集成已通过模拟请求与工具循环测试；真实密钥和账户额度需由使用者提供，并在本机验证。

## 测试

```bash
python -m unittest discover -v
```

14 项测试覆盖营养计算、份量、输入校验、库存事务、重复确认、模拟工具调用、密钥隔离、配置优先级、请求格式及错误提示。GitHub Actions 在 Windows 和 Linux 上运行这些测试。

## 项目结构

| 文件 | 用途 |
|---|---|
| `app.py` | 本地 HTTP 服务、Agent 循环、营养工具、SQLite |
| `deepseek.py` | API 请求、本地密钥配置、模型连接测试 |
| `index.html` / `style.css` / `app.js` | 中文网页界面 |
| `test_app.py` / `test_deepseek.py` | 自动化测试 |
| `fridge.sqlite3` | 私人库存与饮食记录，启动后创建，不提交 |
| `.local-model.json` | 本地密钥配置，不提交 |

视觉设计使用 [Taste Skill](https://github.com/Leonxlnx/taste-skill) 的 `high-end-visual-design` 指导，插画以 CSS 绘制，不请求外部字体或图片。
