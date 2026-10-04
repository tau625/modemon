# 后端规格恢复（内省法）

## 关键突破

**运行期守卫只拦截顶层 `main` 模块**（它在导入时执行完整性校验）。
**叶子模块可以正常导入**，且 Cython 完整保留了大量可内省对象。

| 可内省对象 | 是否可用 |
|---|---|
| 模块 docstring | ✅ 且本项目的 docstring **就是设计文档** |
| 类名 / 基类 / 是否异常类 | ✅ |
| **方法名与函数签名**（含**类型标注**） | ✅ 见下方样例 |
| dataclass **字段名/类型/默认值** | ✅ |
| 异常类的 **`code` 默认值**（错误码常量） | ✅ |
| 模块级常量 / 正则 / 集合 | ✅ |
| **函数体实现** | ❌ 仍是原生机器码 |

⇒ 这把「照符号表猜测重写」提升为「**照接口规格复现**」。

## 恢复统计

| 指标 | 数量 |
|---|---|
| 尝试导入的模块 | 162 |
| 成功导入 | **159** |
| 失败（守卫/依赖/副作用） | 3 |
| 有 docstring 的模块 | **158**（共 35,819 字符） |
| 恢复出的**类** | **422** |
| 恢复出的**异常类**（含错误码） | **132** |
| 恢复出的 **dataclass 字段** | **330** |
| 恢复出的**类方法** | **6194** |
| 恢复出的**模块级函数** | **1719** |
| 其中有**可用签名**的 | **7077** |
| 有 docstring 的函数 | 795 |
| 有 docstring 的方法 | 1284 |
| 恢复出的模块级常量 | 271 |

## 导入失败的模块（3）

- `main` — RuntimeInspectionUnavailable: 网关验证组件完整性检查未通过；未执行该组件，请使用官方安装包修复
- `routers.client_config` — RuntimeInspectionUnavailable: 网关验证组件完整性检查未通过；未执行该组件，请使用官方安装包修复
- `services.client_gateway_config` — RuntimeInspectionUnavailable: 网关验证组件完整性检查未通过；未执行该组件，请使用官方安装包修复

## 样例：模块 docstring（本项目 docstring 即设计文档）

### `config`

```
MH Agent 路径配置 — 同时支持开发模式和桌面打包模式。

桌面打包模式检测：环境变量 MH_DESKTOP=1 或 desktop/runtime/ 目录存在。
打包后目录结构：
    install_dir/
    ├── resources/app/          ← Electron asar 解压后的应用目录
    │   ├── main.js
    │   ├── backend/            ← Python 后端
    │   ├── dist/               ← 前端构建产物
    │   ├── tools/              ← 工具目录
    │   └── templates/          ← 模板目录
    │   （正式包不含 skills/；受保护 Skill 从签名 Capsule 获取）
    ├── runtime/
    │   ├── python/             ← 内嵌 Python
    │   ├── node/               ← 内嵌 Node.js + Claude CLI
    │   └── texlive/            ← 内嵌 TinyTeX
    └── MHAgent.exe

用户数据目录（%APPDATA%/MHAgent/）：
    ├── db/aris.db
    └── workspaces/
```

### `routers.account_messages`

```
Desktop v2 facade; task identities are reconstructed by the trusted client, not HTTP.
```

### `routers.chat`

```
对话工作台对外接口（给前端用，走正常的控制 token 鉴权）。

与 chat_internal.py 的区别：
  · chat_internal 给 MCP 子进程用，走短票，只有 propose/deps/state 三个动作
  · 本文件给前端用，走标准 desktop 控制 token（中间件已经管了）

⛔ 确认闸落在这里：POST /confirm 之前 confirmed_at 是 NULL，
   执行接口第一件事就是查它 —— 不能只靠前端不显示按钮。
```

### `routers.chat_internal`

```
给 MCP server 子进程用的窄权限接口。

⛔ 为什么单独一个 router、单独一套鉴权：
   main.py 的注释写着「不把 Electron 控制 token 或 License Lease 交给子进程」。
   MCP server 是 Claude CLI 派生的子进程，要回调后端建提议记录 —— 但绝不能给它
   MODEX_CONTROL_TOKEN，那等于把整个后端 API 的钥匙（含 /api/settings 里的真实
   API Key）交出去。所以走独立短票 + 路径白名单，照 /v1/messages 的 CLI 代理模式。

⛔ 本文件下的接口有三条铁律，破了任意一条就等于开后门：
   1. 只暴露提议、依赖、状态和受控公开产物读取，不提供任意路径文件工具
   2. 任何响应都不含配置、密钥、settings 内容
   3. 每个接口第一行就 authorize()，同时核 session_id 和 workflow_id
```

### `routers.checkpoints`

```
Human checkpoint status and identity-bound decisions; never restart a task implicitly.
```

### `routers.editor`

```
LaTeX 在线编辑器 API — 文件读写 + 编译 + AI 辅助修改

支持两种工作流模式：
- LaTeX 模式（output_format=pdf 或科研类）：编辑 .tex/.bib/.py，编译用 xelatex 输出 PDF
- Markdown/Word 模式（output_format=docx 或学术写作类）：编辑 .md/.py，导出用 docx-cn-engine 输出 .docx

模式由工作流的 template + params.output_format 自动判断。
```

### `routers.palette_preview`

```
数据图配色 即时预览 —— 给前端自定义取色返回真 matplotlib 多图型 PNG。
GET /api/palette-preview?colors=#4477AA,#EE6677,...  → image/png
校验：2–8 个合法 hex；非法/越界返回 400。渲染用 Agg，线程安全（每次新 figure）。
```

### `routers.project_preview`

```
一句话生成项目 —— 本地预览服务 API。

端点(挂在 /api/editor 前缀下，与在线编辑器同源)：
- POST   /api/editor/{wf_id}/serve       启动服务(body: {mode: frontend|backend|both})
- DELETE /api/editor/{wf_id}/serve       停止服务(query: kind 可选)
- GET    /api/editor/{wf_id}/serve/status 查状态

只对「一句话生成项目」(template=grad_project)且已产出 code/ 的工作流可用。
命令白名单式启动(见 project_server._build_cmd)，不执行任意命令。
```

### `routers.style_preview`

```
数据图版式 即时预览 —— 给前端「高级自定义」返回真 matplotlib 样图 PNG。
GET /api/style-preview?frame=journal&grid=both&lw=thick&font=large&legend=framed&bg=graytint → image/png

★ 核心保证「预览 = 实际出图」：本接口不自己实现版式逻辑，而是加载【真正的 plot_utils】，
  monkey-patch 它的 marker 读取函数返回用户所选档位，再调它的 setup_style —— 与工作流实际
  出图跑的是同一份代码、同一个 _knobs_from_custom 映射，零同步风险。
```

### `services._preview_proxy`

```
预览反向代理前端服务器(纯标准库，无第三方依赖)。

用途：当全栈项目的**后端没有同源托管前端**时，用它起前端，实现"同源"：
- 托管 --dir 下的前端静态文件(纯 HTML 或 build 产物)。
- 所有 /api/* 请求**反向代理**到 --backend-port(后端进程)，透传方法/头/体/状态码。
这样前端里 `fetch("/api/...")` 的相对路径请求就能打到后端，避免 http.server 404。

由 project_server.py 作为子进程拉起：
  python _preview_proxy.py --dir <前端目录> --port <本服务端口>       --backend-port <后端端口> [--bind 127.0.0.1]
```

### `services.access_mode`

```
Desktop execution identity, separate from editable personal-Key settings.

This is a client safety boundary, not a replacement for server authorization.
Account inference stays fail-closed until the metered server relay is available.
```

### `services.account_center`

```
Strict local facade for License account self-service; no legacy Portal tokens.

Inputs are never persisted or logged. Identity checks and email sends are explicit
user actions and never retried here. Real eligibility remains server-authoritative.
```

