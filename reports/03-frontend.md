# Modex-MH-Agent 前端静态逆向分析报告

- **目标应用**：`E:\02_Installers\DailyApps\Modex-MH-Agent`（Electron + React 桌面应用，「AI 数学建模竞赛智能体」）
- **分析对象**：`resources\app\dist\`（Vite 生产构建产物，无 sourcemap，全量 minified）
- **构建标识**：`build-info.json` → `{"branch":"release/intl","version":"2.1.2","display_version":"2.1.2","built_at":"2026-09-25T05:28:25.626Z"}`【直接提取】
- **源码清单**：`reports\build-inputs-paths.txt`（547 行 `sha256 路径`，其中 `web/frontend/src/**` 共 **138** 个文件）【直接提取】
- **分析方法**：自研 node 脚本对 bundle 做「括号感知字符串提取 + 结构化美化」（`tools\beautify.js`、`tools\fx2.js`、`tools\callsites3.js`、`tools\probe*.js`），再对美化产物做定点阅读。
- **标注约定**：【直接提取】= bundle 中原始字符串/代码可直接读到；【推断】= 有明确依据的推理；【推测】= 依据较弱。
- **证据格式**：所有结论均以 `[证据: <chunk 文件名>:<行号>（命中原文）]` 或表内「判定依据/关键字段」列给出 chunk 文件名与命中的原始字符串；行号对应 `beauty\*.pretty.js`（美化产物，与 `dist\assets\*.js` 一一对应）。置信度三档：`【直接提取】`（bundle 原文可直接读到）、`【推断】`（给依据）、`【推测】`。

---

## 1. 技术栈判定

| 层次 | 判定 | 版本 | 判定依据（原始字符串） |
|---|---|---|---|
| UI 框架 | **React** | **19.2.4** | `react-C0pe7UsM.pretty.js` 与 `index-BeImsYqE.pretty.js:6975` 出现字面量 `19.2.4`；`index` 含 `createRoot(document.getElementById('root')).render(...StrictMode...)`【直接提取】  [证据: react-C0pe7UsM.pretty.js, index-BeImsYqE.pretty.js] |
| React DOM | react-dom | 19.x（与 React 同版） | `index-BeImsYqE.pretty.js` 内 `e.createRoot=function(e,t){...}`、`unstable_scheduleCallback`、`inject(Rp)`（完整 reconciler）【直接提取】  [证据: index-BeImsYqE.pretty.js] |
| JSX 运行时 | react/jsx-runtime（`jsx-runtime-*.js` 内含 `jsxs/jsx` 与 react-router） | — | 所有 chunk 通过 `(0,M.jsx)()` / `(0,M.jsxs)()` 生成元素【直接提取】  [证据: 全部 chunk 的 jsx-runtime 导入（`import{a as r,...}from"./jsx-runtime-DriIcras.js"`）+ jsx-runtime-DriIcras.pretty.js] |
| 路由 | **React Router（数据路由 + `<Routes>/<Route>`）** | **7.x**（含 v8 预告 flag） | `jsx-runtime-DriIcras.pretty.js` 出现 ``future:a.v8_trailingSlashAwareDataRequests``、`routeModules`、`manifest`、`useViewTransitionState`、``"`useViewTransitionState` must be used within `react-router-dom`'s `RouterProvider`"``、`https://reactrouter.com/en/main/routers/picking-a-router`【直接提取】；`v8_*` 命名空间 flag 是 RR 7.9+ 的特征【推断】  [证据: jsx-runtime-DriIcras.pretty.js] |
| 状态管理 | **Zustand（v5 形态，被内联进 chunk）** | 无法读到版本号 | `workflowStore-DtYgz0OF.pretty.js:5-21` 是完整的 zustand 运行时：`setState/getState/getInitialState/subscribe` + `useSyncExternalStore(e.subscribe, ...)` + `useDebugValue(r)`；store 以 ``c((e,t)=>({...}))``（`create((set,get)=>...)`）签名创建【直接提取】。**未发现 Redux 用于业务层**（见下）  [证据: workflowStore-DtYgz0OF.pretty.js] |
| 构建工具 | **Vite** | 版本号未内嵌，判为 5+/6/7 形态 | `index-BeImsYqE.pretty.js:1` ``const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f\|\|(m.f=["assets/Dashboard-2mxANXyi.js",...])))``；`index.html` 使用 `type="module" crossorigin` + `modulepreload`；`L8881` 形如 ``z(`dashboard`,()=>i(()=>import(`./Dashboard-2mxANXyi.js`),__vite__mapDeps([0,1,2,3,4,5])))``；`__vite__mapDeps`（双下划线）为 Vite ≥4.3 命名【直接提取＋推断】  [证据: index-BeImsYqE.pretty.js, Dashboard-2mxANXyi.js] |
| CSS 框架 | **Tailwind CSS** | **v4.2.2** | `assets\index-mr3gZRQa.css`（251,502 字节）首行 `/*! tailwindcss v4.2.2 \| MIT License \| https://tailwindcss.com */`；文中含 `@layer properties`、`@supports ((-webkit-hyphens:none) and (not (margin-trim:inline)))` 等 v4 特征，共出现 174 个不同的 CSS 自定义属性名（绝大多数为 `--tw-*`），`bg-` 字面量 497 处【直接提取】  [证据: assets\index-mr3gZRQa.css（+ 8 个页面级 .css）] |
| 数学渲染 | **KaTeX** | **0.16.42** | `ArtifactLibrary-BPEftl07.pretty.js:10942` ``version:`0.16.42`,render:sh,renderToString:ch,ParseError:N,SETTINGS_SCHEMA:Rl``；`renderToString(d,{...t,displayMode:c,throwOnError:!0})`【直接提取】  [证据: ArtifactLibrary-BPEftl07.pretty.js] |
| Markdown 渲染 | **react-markdown（v9+）+ remark/rehype 插件链** | remark 插件与 rehype-katex | `ArtifactLibrary` 内 `hast-util-to-jsx-runtime`（`He="https://github.com/syntax-tree/hast-util-to-jsx-runtime"`）；``ho(e){let t=e.rehypePlugins\|\|lo,n=e.remarkPlugins\|\|lo,...Qa().use(ui).use(n).use(Ta,r).use(t)}``；`po=[{from:'astPlugins',id:'remove-buggy-html-in-markdown-parser'},{from:'plugins',id:'change-plugins-to-remarkplugins',to:'remarkPlugins'},{from:'renderers',id:'change-renderers-to-components',to:'components'},...]`（react-markdown 迁移表）；`rehype-katex` 插件（``source:`rehype-katex` `` + `Could not render math with KaTeX`）【直接提取】  [证据: ArtifactLibrary-BPEftl07.pretty.js:479962（react-markdown 调用点）, :131164/:131186（`ho` 插件装配）, :4114（迁移表）, :468238（rehype-katex）] |
| Markdown 解析内核 | micromark / mdast / hast（remark 生态） | — | `t.data('micromarkExtensions')`、`fromMarkdownExtensions`、`hast-util-to-jsx-runtime`【直接提取】  [证据: ArtifactLibrary-BPEftl07.pretty.js:97066/:97092（micromark↔mdast 适配）, :86838（mdast 构建）, :25158（hast→jsx）] |
| 图表 | **Recharts**（含其内部 react-redux/redux-toolkit/immer/reselect 依赖） | — | `WorkflowDetail-bN89YgNS.pretty.js` 出现 ``className:P(`recharts-surface`,o)``、``className:P(`recharts-layer`,r)``、``className:P(`recharts-symbols`,s)``、`BarChart/LineChart/ScatterChart`；同 chunk 含 `listenerMiddleware`（RTK）、`immer-nothing`/`immer-state`（immer）、`createSelector`/`withTypes`（reselect）——**这些是 Recharts 的传递依赖，切片名全是 Recharts 内部切片**（`chartLayout, legend, tooltip, zIndex, options, chartData, polarAxis, graphicalItems, cartesianAxis, brush, referenceElements, renderedTicks, errorBars, rootProps, polarOptions, eventSettings`），**不是业务 Redux**【直接提取＋推断】  [证据: WorkflowDetail-bN89YgNS.pretty.js] |
| LaTeX 编辑器 | **自研**（受控 `<textarea>` + 自研 diff/undo/run 状态机），**未使用 CodeMirror/Monaco** | — | `LatexEditor` 与 `index-mr3gZRQa.css` 中 `cm-editor/cm-content/monaco-editor` 命中数均为 **0**；编辑器逻辑为 `editorUndo.ts`（`modex.editor.undo:${id}`）、`editorLayout.ts`、`editorPayload.ts`、`editorUpload.ts` 等自研模块【直接提取；"未使用"为反证推断】  [证据: 全 27 chunk + 9 个 .css 对 `cm-editor\|cm-content\|monaco-editor` 命中数 = 0；LatexEditor-I1nsgpA4.pretty.js:320（自研 undo 状态机）] |
| UI 组件库 | **无第三方组件库**（无 antd/MUI/Radix/headlessui）；纯 Tailwind + 自研组件 + emoji 图标 | — | 全量 chunk 对 `antd\|@radix\|headlessui\|MuiBox` 的命中仅 `ant-` 类名 28 处（Tailwind 生成的普通类名，非 antd）；图标使用 emoji（`🏆 📱 🌍` 等）与内联 `<svg>`（`icons.svg` 未被引用）【直接提取＋推断】  [证据: 全 27 chunk 对 `antd\|@radix\|headlessui\|MuiBox` 命中仅 `ant-` 28 处；NewWorkflow-Ld6TEJjT.pretty.js:45387 起（emoji 图标表）] |
| 本地存储 | Web `localStorage` + `navigator.locks` + IndexedDB(推断) | — | `localStorage.setItem('MH Agent-theme', ...)`、`localStorage.getItem('mhagent_disclaimer_accepted')`、`localStorage.getItem('modex.chat.draft.v1:'+id)`、`localStorage.getItem('chat-outbox:v1:'+id)`、`localStorage.getItem('modex.editor.undo:'+id)`、`localStorage.getItem('modex-image-request:'+id)`、`localStorage.getItem('modex-native-checkout:'+...)`、`navigator.locks.request(...)`【直接提取】  [证据: index-BeImsYqE.js:232701（theme）/:315142（disclaimer）, ChatWorkbench-B0gSrHl3.js:1049（draft）, useWebSocket-DhwRyw4C.js:3057（outbox）, LatexEditor-I1nsgpA4.js:9822/:11035, Account-CFNFyFpM.js:12200（checkout）+ Account-CFNFyFpM.js:12826（navigator.locks）] |
| 桌面桥 | `window.electronAPI`（contextBridge） | — | `preload.js:6 contextBridge.exposeInMainWorld('electronAPI', {isDesktop:true, updater:{...}, pickFolder, latex:{getStatus,install}})`；前端 `window.electronAPI?.isDesktop && e.updater`【直接提取】  [证据: preload.js] |

**渲染进程加载来源**【直接提取，`asar\main.js`】：

- `const appOrigin = \`http://127.0.0.1:${actualPort}\``；`win.loadURL(appOrigin)`；`win.webContents` 权限白名单 `{ urls: ['http://127.0.0.1:'+port+'/*', 'ws://127.0.0.1:'+port+'/*'] }`
- ⇒ **前端所有 `fetch('/api/...')` 都是同源相对路径**，由本地 FastAPI/uvicorn 后端（`uvicorn.run("main:app", host="127.0.0.1", ...)`）同时托管 `dist` 静态文件与 `/api`，WebSocket 亦为同源 `/ws/...`。

### 1.1 明确排除的项  [证据: 全 27 个 assets\*.js 的字面量扫描 + index.html/build-info.json]

- **无 sourcemap**：`assets\` 下只有 `.js`/`.css`/字体（`KaTeX_*.woff2/woff/ttf`）与预览图片，无 `.map` 文件【直接提取】。
- **无 Monaco/CodeMirror**：见上。
- **无 axios**：所有网络请求都是 `fetch`（`globalThis.fetch`，`chatRequest-LRac2JB5.pretty.js:23`）【直接提取】。
- **Recharts 是唯一图表库**：`ArtifactLibrary` chunk 内 `recharts|echarts|d3.|chart.js` 命中为 0【直接提取】。

---

## 2. 页面与路由表

### 2.1 路由定义  [证据: index-BeImsYqE.pretty.js:8881（懒加载映射）, :9014-9042（<Route path> 表）, :9005（布局正则）]

懒加载映射（`z('name', ()=>import('./Xxx-HASH.js'), __vite__mapDeps([...]))`）：

| 懒加载 key | 页面源文件 | 产出 chunk |
|---|---|---|
| `dashboard` | `pages/Dashboard.tsx` | `Dashboard-2mxANXyi.js` |
| `new-workflow` | `pages/NewWorkflow.tsx` | `NewWorkflow-Ld6TEJjT.js` |
| `workflow-detail` | `pages/WorkflowDetail.tsx` | `WorkflowDetail-bN89YgNS.js` |
| `artifact-viewer` | `pages/ArtifactViewer.tsx` | `ArtifactViewer-DS3mPR9-.js` |
| `latex-editor` | `pages/LatexEditor.tsx` | `LatexEditor-I1nsgpA4.js` |
| `chat-workbench` | `pages/ChatWorkbench.tsx` | `ChatWorkbench-B0gSrHl3.js` |
| `settings` | `pages/Settings.tsx` | `Settings-D4EW1h0L.js` |
| `account` | `pages/Account.tsx` | `Account-CFNFyFpM.js` |
| `account-history` | `pages/AccountHistory.tsx` | `AccountHistory-DV1tVxrt.js` |

URL 路由表（`<Routes>` / `<Route path element>`）：

| URL | 页面 | 说明 |
|---|---|---|
| `/` | Dashboard | 工作流管理首页 |
| `/new` | NewWorkflow | 新建工作流 |
| `/workflow/:id` | WorkflowDetail | 自动流水线详情（步骤进度 / 检查点） |
| `/workflow/:id/artifact/*` | ArtifactViewer | 单工件全屏查看（`*` 为工件路径） |
| `/workflow/:id/editor` | LatexEditor | LaTeX/项目文件编辑器 |
| `/workflow/:id/chat` | ChatWorkbench | 协同聊天工作台 |
| `/settings` | Settings | 设置 |
| `/account` | Account | 账号 / 积分 / 充值 |
| `/account/history` | AccountHistory | 消费记录（New API 原生账单） |

**导航栏**【直接提取，`index:8909-8929`】：品牌 `Modex-MH-Agent` + `工作流`(`/`) + `新建`(`/new`) + 官网外链 `https://www.mingheng.xin/` + 主题切换 + 接入方式指示器 + `账号`(`/account`) + `设置`(`/settings`)。

**页面外壳逻辑**【直接提取，`index:9001-9055`】：按 pathname 正则切换布局类：

- `/^\/workflow\/[^/]+\/chat\/?$/` → `app-main-chat`（隐藏 footer）
- `/^\/workflow\/[^/]+\/artifact\//` → `app-main-artifact`
- `/^\/workflow\/[^/]+\/editor\/?$/` → `app-main-editor`
- `/^\/workflow\/[^/]+\/?$/` 或 `/` → `app-main-wide`

### 2.2 页面内子视图（chunk 名 + 清单文件名重建）

| 子视图 | 源文件 | 所属 chunk | 证据 |
|---|---|---|---|
| 工件库（分类/搜索/分页/批量） | `components/ArtifactLibrary.tsx`、`ArtifactCollection.tsx` | `ArtifactLibrary-*` | ``beginnerHint:`建议优先查看` ``、``collectionEndpoint:`` |
| Markdown 阅读器 | `components/MarkdownViewer.tsx` | `ArtifactLibrary-*` | `rehype-katex` 与 `components:{a,img}` 映射同处一个文件 |
| 纯文本预览 | `components/FileTextPreview.tsx` | `ArtifactLibrary-*` | 清单 + 预览类型分支 |
| 评分曲线 | `components/ScoreChart.tsx` | `WorkflowDetail-*` | `WorkflowDetail:427576` ``function vN({scores:e}){...children:`审稿分数曲线`}`` + Recharts `LineChart` |
| 步骤卡片 | `components/StepCard.tsx` | `WorkflowDetail-*` | `WorkflowDetail:84` `function te({...stepIndex, workflowStatus, onRerun, stepEffort, onSetEffort})` |
| 日志流 | `components/LogStream.tsx` | `WorkflowDetail-*` | `WorkflowDetail` 内 ``logs:ge`` 渲染 |
| 检查点弹窗 | `components/CheckpointModal.tsx` | `WorkflowDetail-*` | `WorkflowDetail:15098` `<se workflowId stepName checkpointType stepSkillName>` |
| 提案卡片 | `components/ProposalCard.tsx` | `ChatWorkbench-*` | `chat-card-body`、`item_kind/operation_kind` 渲染 |
| Fork 卡片 | `components/ForkCard.tsx` | `ChatWorkbench-*` | `forks`/`chooseFork` UI |
| 聊天历史面板 | `components/ChatHistoryPanel.tsx` | `ChatWorkbench-*` | `chat-history-scope-note` |
| 补丁审阅 | `components/PatchReviewDialog.tsx` | `PatchReviewDialog-*`（被 ChatWorkbench/WorkflowDetail 复用） | chunk 名 + `/patch-review-scale` |
| 充值/钱包 | `components/RechargeDialog.tsx`、`RechargeTerms.tsx`、`NewApiWallet.tsx` | `Account-*`、`newApiWallet-*` | `NativeBillingHistory`、`native-recharge-terms` |
| 模型目录 | `components/AccountModelCatalog.tsx` | `AccountModelCatalog-*` | `model-catalog-row` |
| 编辑器工作区/版本历史/Agent 历史 | `components/EditorWorkspace.tsx`、`EditorVersionHistory.tsx`、`EditorAgentHistory.tsx`、`EditorRunCard.tsx` | `LatexEditor-*` | `/ai-agent-history`、`/ai-agent-runs/{id}` |
| 更新通知 | `components/UpdateNotifier.tsx` | `index-*` | `window.electronAPI.updater.onUpdateAvailable` |
| 许可门禁 | `components/LicenseGate.tsx` | `index-*` | `/api/license/verify` |
| 免责声明门禁（全屏，非组件清单项，实际在 `App.tsx`） | `App.tsx` | `index-*` | `mhagent_disclaimer_accepted` |

---

## 3. 模块结构还原（138 个源文件）

来自 `reports\build-inputs-paths.txt` 全量枚举【直接提取】。**目录职责如下**。

```
web/frontend/src/
├── main.tsx            # 入口：createRoot(#root).render(<StrictMode><App/></StrictMode>)
├── App.tsx             # 根组件：Providers + 导航栏 + <Routes> + 免责声明门禁 + footer
├── index.css           # Tailwind v4 入口 + CSS 变量主题令牌
├── vite-env.d.ts
├── assets/             # react.svg, vite.svg（构建残留，未在产物中引用）
├── pages/ (10)         # 路由级页面（各对应一个懒加载 chunk）
│   Account.tsx, AccountHistory.tsx, ArtifactViewer.tsx, ChatWorkbench.tsx(+.css),
│   Dashboard.tsx, LatexEditor.tsx, NewWorkflow.tsx, Settings.tsx, WorkflowDetail.tsx
├── components/ (55)    # 页面内可复用 UI 组件（见下表分组）
├── hooks/ (10)         # 可复用 React hooks（副作用/订阅/取数）
│   useAccessMode.tsx, useAccountSession.ts, useCheckpointSession.ts, useClientConfig.ts,
│   useModalFocus.ts, useTailScroll.ts, useTheme.tsx, useWebSocket.ts,
│   useWorkbenchAccess.ts, useWorkflowSteps.ts
├── stores/ (2)         # Zustand store（全局状态）
│   chatStore.ts, workflowStore.ts
├── utils/ (47)         # 纯函数/无渲染逻辑：取数封装、校验、格式化、持久化
├── styles/ (6)         # 页面级独立 CSS（与 Tailwind 并存）
│   accountAccess.css, accountCredits.css, accountHistory.css,
│   accountStepModels.css, modelCatalog.css, newApiWallet.css
└── types/ (2)          # TypeScript 类型：index.ts（全局领域模型）, effort.ts（思考强度枚举）
```

### 3.1 components 分组（55 个）

- **工件/论文查看**：`ArtifactLibrary.tsx(+css)`、`ArtifactCollection.tsx`、`ArtifactViewer` 配套、`MarkdownViewer.tsx`、`FileTextPreview.tsx`、`ScoreChart.tsx`、`PatchReviewDialog.tsx`
- **聊天工作台**：`ChatAttachments.tsx(+css)`、`ChatHistoryPanel.tsx(+css)`、`ChatStageDetails.tsx(+css)`、`ChatTaskStatus.tsx`、`ChatBeginnerGuide.tsx`、`ChatProjectOverview.css`、`ProposalCard.tsx`、`ForkCard.tsx`
- **自动流水线**：`StepCard.tsx`、`CheckpointModal.tsx`、`LogStream.tsx`、`WorkflowPayerBadge.tsx`、`WorkflowParameterSettings.tsx`、`MathPromptRecipePanel.tsx`
- **LaTeX 编辑器**：`EditorWorkspace.tsx(+css)`、`EditorVersionHistory.tsx`、`EditorAgentHistory.tsx(+css)`、`EditorRunCard.tsx`、`EditorAccountModelPicker.tsx`
- **账号/计费**：`AccessModePanel.tsx`、`AccountAccessPanel.tsx`、`AccountCenterOperations.tsx`、`AccountImageSettings.tsx`、`AccountMessagesInference.tsx`、`AccountModelCatalog.tsx`、`AccountModelLink.tsx`、`AccountRecoveryForm.tsx`、`AccountStepModels.tsx`、`AccountTextInference.tsx`、`NewApiAccountAccess.tsx`、`NewApiSoftwareAccess.tsx`、`NewApiWallet.tsx`、`NativeBillingHistory.tsx`、`NativeRealnameAccess.tsx`、`RechargeDialog.tsx`、`RechargeTerms.tsx`、`KeyImageModelPicker.tsx`、`ModelContextSettings.tsx`
- **框架/壳层**：`RouteErrorBoundary.tsx`、`RouteScrollReset.tsx`、`UpdateNotifier.tsx`、`LicenseGate.tsx`、`ConfiguredExternalLink.tsx`

### 3.2 utils 分类（47 个）

- **取数/请求（7）**：`chatRequest.ts`（fetch+超时+abort 封装）、`clientConfig.ts`、`modelDiscovery.ts`、`artifacts.ts`、`accountAccess.ts`、`accountCenter.ts`、`accessMode.ts`
- **聊天（15）**：`chatComposer.ts`、`chatDraft.ts`、`chatOutbox.ts`、`chatHistory.ts`、`chatMessages.ts`、`chatMaterials.ts`、`chatErrors.ts`、`chatHandoff.ts`、`chatTaskFocus.ts`、`chatWorkflowProgress.ts`、`chatActivityTime.ts`、`chatProjectProfile.ts`、`workflowSocket.ts`、`workflowLogPresentation.ts`、`workflowProblemStatement.ts`
- **编辑器（11）**：`editorHistory.ts`、`editorImage.ts`、`editorLayout.ts`、`editorPayload.ts`、`editorRun.ts`、`editorSave.ts`、`editorUndo.ts`、`editorUpload.ts`、`editorWord.ts`、`unifiedDiff.ts`、`markdownCode.ts`
- **账号/计费/模型（8）**：`accountModelSelection.ts`、`accountPresentation.ts`、`nativeCheckout.ts`、`nativeReadCache.ts`、`modelContext.ts`、`workbenchAccess.ts`、`aiDisclosure.ts`、`mathPromptLibrary.ts`
- **通用（6）**：`lazyRoute.ts`、`logWindow.ts`、`scrollFollow.ts`、`checkpointClock.ts`、`filePresentation.ts`、`workflowCreation.ts`

### 3.3 chunk ↔ 源模块映射  [证据: 全 chunk 字面量唯一性矩阵，见 tools\_fx\homes.tsv]

| chunk | 归属源模块（决定性证据字符串） |
|---|---|
| `index-BeImsYqE.js` | `main.tsx`/`App.tsx`（`mhagent_disclaimer_accepted`、`WorkflowPayerBadge`路由外壳）、`hooks/useTheme.tsx`（`MH Agent-theme`）、`hooks/useClientConfig.ts`+`utils/clientConfig.ts`（`/api/client-config`）、`components/LicenseGate.tsx`（`/api/license/verify`）、`types/index.ts`；**并含 react-dom 19 与 FastAPI 文档外链** |
| `useAccessMode-CYwsqbbI.js` | `hooks/useAccessMode.tsx`（`/api/account/access-mode`）、`utils/accessMode.ts`（`modex-access-mode-changed`）、`utils/accountAccess.ts`（`class AccountRequestError`），含接入方式 React Context + 账号接口白名单 |
| `workflowStore-DtYgz0OF.js` | `stores/workflowStore.ts`（`fetchWorkflows`、``u=`/api` ``），内联 zustand 运行时 |
| `useWebSocket-DhwRyw4C.js` | `hooks/useWebSocket.ts`（`handleChatEvent`）、`stores/chatStore.ts`（`fetchRunEvents`）、`utils/chatOutbox.ts`（`chat-outbox:v1:`）、`utils/workflowSocket.ts` |
| `useTailScroll-BttpCSjs.js` / `scrollFollow-Be-o2lrP.js` | `hooks/useTailScroll.ts`、`utils/scrollFollow.ts`（独立小 chunk，被 3 处共享） |
| `effort-BoZu8WGp.js` | `types/effort.ts`（`low/medium/high/xhigh/max`） |
| `modelDiscovery-BRyakWgC.js` | `utils/modelDiscovery.ts`（`/api/settings/models/discover`） |
| `chatRequest-LRac2JB5.js` / `accountModelSelection-Ozwe5iJg.js` / `WorkflowPayerBadge-qKnYExmn.js` | 同名 utils/components 的共享小 chunk |
| `AccountMessagesInference-C-hk-by7.js` / `AccountModelCatalog-DdzyHjab.js` / `newApiWallet-BJVw6ude.js` / `PatchReviewDialog-CE7kb4Sp.js` | 对应同名组件的共享 chunk（被 Account / Settings 两处引用） |
| `ArtifactLibrary-BPEftl07.js` | `components/ArtifactLibrary.tsx`、`ArtifactCollection.tsx`、`MarkdownViewer.tsx`、`utils/artifacts.ts`；**并打包 react-markdown + micromark/mdast/hast + KaTeX 0.16.42** |
| `WorkflowDetail-bN89YgNS.js` | `pages/WorkflowDetail.tsx`、`components/StepCard.tsx`、`CheckpointModal.tsx`、`LogStream.tsx`、`ScoreChart.tsx`、`hooks/useCheckpointSession.ts`（`checkpoints/current`）、`utils/workflowLogPresentation.ts`；**并打包 Recharts（+RTK/immer/reselect）** |
| `ChatWorkbench-B0gSrHl3.js` | `pages/ChatWorkbench.tsx`、`ProposalCard.tsx`、`ForkCard.tsx`、`ChatHistoryPanel.tsx`、`utils/chatDraft.ts`（`modex.chat.draft.v1:`）等聊天组件 |
| `NewWorkflow-Ld6TEJjT.js` | `pages/NewWorkflow.tsx`、`MathPromptRecipePanel.tsx`、`WorkflowParameterSettings.tsx`、`hooks/useWorkflowSteps.ts`（`resolve-steps`）、`utils/mathPromptLibrary.ts`、`aiDisclosure.ts`、`workflowCreation.ts` |
| `LatexEditor-I1nsgpA4.js` | `pages/LatexEditor.tsx`、`EditorWorkspace.tsx`、`EditorAgentHistory.tsx`、`utils/editorUndo.ts`（`modex.editor.undo:`）、`editorImage.ts`（`modex-image-request:`） |
| `Settings-D4EW1h0L.js` | `pages/Settings.tsx`（`model_context_policies`）、`ModelContextSettings.tsx`、`AccountImageSettings.tsx`、`KeyImageModelPicker.tsx`、`AccountModelLink.tsx`、`AccountStepModels.tsx` |
| `Account-CFNFyFpM.js` | `pages/Account.tsx`（`native-wallet`）、`RechargeDialog.tsx`、`RechargeTerms.tsx`、`NativeBillingHistory.tsx`、`NativeRealnameAccess.tsx`、`NewApiAccountAccess.tsx`、`NewApiSoftwareAccess.tsx`、`AccountRecoveryForm.tsx`、`AccountCenterOperations.tsx`、`AccountTextInference.tsx`、`utils/nativeCheckout.ts`（`modex-native-checkout:`）、`nativeReadCache.ts` |
| `AccountHistory-DV1tVxrt.js` | `pages/AccountHistory.tsx`（`/api/account/native/wallet`） |
| `ArtifactViewer-DS3mPR9-.js` | `pages/ArtifactViewer.tsx`（`artifact-context/prompt/build`） |
| `Dashboard-2mxANXyi.js` | `pages/Dashboard.tsx`（引用 `workflowStore` 与 `NewWorkflow` 的常量） |

> ⚠️ 说明：**并非每个源文件都有独立 chunk**。Vite 只把「被 2 个以上 chunk 共享」或「路由懒加载入口」的模块拆成独立文件；其余组件被**内联合并**到其所属页面的 chunk 中。因此 27 个 `.js` chunk ≠ 138 个源文件。

---

## 4. API 调用面（核心交付物）

### 4.0 请求封装契约（复现时必须对齐）  [证据: useAccessMode-CYwsqbbI.pretty.js:114, chatRequest-LRac2JB5.pretty.js:1, ChatWorkbench-B0gSrHl3.pretty.js:988, Account-CFNFyFpM.pretty.js:401, newApiWallet-BJVw6ude.pretty.js:40, workflowStore-DtYgz0OF.pretty.js:37]

| 封装 | 位置 | 契约 |
|---|---|---|
| `fetch` 直调 | 全部 chunk | **相对同源路径**，无 baseURL、无自定义 header，`credentials` 默认同源 |
| `g(path, init, signal)` | `useAccessMode-CYwsqbbI.pretty.js:114-139` | 账号域专用：强制 `cache:'no-store'`、`credentials:'same-origin'`、`redirect:'error'`、30s 超时；**内含接口白名单校验**（见 4.0.1）；非 2xx 时抛 `AccountRequestError(code,status,retryAfter)` |
| `chatRequest` (`chatRequest-LRac2JB5.pretty.js:1-45`) | `utils/chatRequest.ts` | `(url, init, timeoutMs=20000)` → `AbortController` + `Promise.race`；超时文案「请求超时，操作结果尚未确认。请先同步任务状态，不要重复执行。」；返回 `{ok,status,json}` 轻量包装（**不抛 HTTP 错误**） |
| `Ve(url, signal, method='GET', body)` | `ChatWorkbench-B0gSrHl3.pretty.js:988` | ChatWorkbench 专用：`method` 为**第 3 个位置参数**；POST 超时 60s、其余 20s；非 2xx 抛错 |
| `H(path, body?, signal)` | `Account-CFNFyFpM.pretty.js:401` | **`/api/account/native/` + path**；`body===undefined` → GET，否则 → `POST` + JSON header/body |
| `v(path)` / `r(path, {}, signal)` | `newApiWallet-BJVw6ude.pretty.js:40` | New API 原生账单：GET 只读包装 |
| `u/n/t/e` (index) | `index-BeImsYqE.pretty.js:7444/7598` | 账号会话包装：`u(path, init, signal)`；`n(path, body)` = POST-JSON；`e.request(path, body)` 由上下文注入 |
| `workflowStore` 内联 fetch | `workflowStore-DtYgz0OF.pretty.js:37-307` | ``u=`/api` `` + 模板拼接；`fetchWorkflows` 失败静默降级，其余抛 `Error(detail)` |

#### 4.0.1 客户端接口白名单（安全相关，【直接提取】`useAccessMode-CYwsqbbI.pretty.js:116-117`）

`utils/accountAccess.ts` 的 `g()` 在发请求前用正则强校验路径，否则抛 `Error('无效的本地账号接口。')`。允许集合（原文正则，**等于后端账号路由的完整契约**）：

```
POST /^\/api\/account\/native\/(?:register|register-code|reset-email|login\/verify|software\/consent|checkout|orders\/mdx_[a-f0-9]{32}\/query)$/
GET  /^\/api\/account\/native\/usage\?start=\d{1,12}&end=\d{1,12}&model=(...){0,384}&cursor=[A-Za-z0-9_.-]{0,512}$/
GET|PUT /api/account/native/image-settings
GET  /^\/api\/account\/native\/(?:realname|software|wallet|(?:orders|adjustments|requests)\?page=[1-9][0-9]{0,4}|history\?page=[1-9][0-9]{0,4}&start=...&end=...&model=...)$/
GET  /^\/api\/account\/inference\/(?:capabilities|operations(?:\/[0-9a-f-]{36})?)$/
POST /api/account/inference/operations
GET  /^\/api\/account\/messages\/(?:capabilities|operations(?:\/[0-9a-f-]{36})?)$/
POST /api/account/messages/operations
PATCH /^\/api\/workflows\/[A-Za-z0-9_-]{1,128}\/steps\/[A-Za-z0-9_-]{1,128}\/account-model$/
PATCH /^\/api\/workflows\/[A-Za-z0-9_-]{1,128}\/steps\/[A-Za-z0-9_-]{1,128}\/effort$/
GET  /^\/api\/(?:account\/(?:status|login|logout|activate|access-mode|workbench-access|models|send-code|register|reset-password|bind-email|identity(?:\/withdraw)?|model-account|licenses\/(?:claim|[a-f0-9]{32}\/unbind)|logout-all)|license\/(?:status|verify))$/
```

### 4.1 端点全清单  [证据: tools\_fx\endpoint-map3.tsv（172 条调用点，含 HTTP method 与 body 类型）与 tools\_fx\path-normalized.tsv（171 条路径字面量）]

> 本清单共 **158 行 / 约 142 条唯一路径**（脚本对报告表格自动计数）。

> 下表「方法」列：读 `,{method:'X'}` 或封装器语义。标 `GET*` 表示调用点未显式给 method（fetch 默认为 GET）。`{id}`=workflow_id，`{mid}`=message id，`{p}`=工件路径。

#### A. 客户端配置与账号核心（`routers/client_config.py` / `routers/account.py` / `main.py`）

| 方法 | 端点 | 调用方（页面/模块） | 关键字段 / 备注 |
|---|---|---|---|
| GET | `/api/client-config` | App 全局 `useClientConfig` | 返回 `{revision, api_key_url, activation_url, expires_at}`；`expires_at` 到期自动转 `unavailable`；60s/30s 轮询 + focus/visibility 触发[证据: index:7378,index:246079] |
| POST | `/api/client-config/refresh` | 同上（`c?refresh:`） | 强制刷新 |
| GET | `/api/account/status` | App/LicenseGate | 账号状态轮询 |
| POST | `/api/account/access-mode` | Settings/Account 接入方式面板 | body `{mode}`；**GET 语义用 header `X-Modex-Mode-Read: identity`** |
| POST | `/api/account/login` | 登录表单 | 由 `/api/account/${e}` 模板生成 |
| POST | `/api/account/logout` | 退出 | 同上 |
| POST | `/api/account/register` | 注册 | 同日；body `{email,password,code}`[证据: index:8197] |
| POST | `/api/account/reset-password` | 重置密码 | |
| POST | `/api/account/bind-email` | 绑定邮箱 | |
| POST | `/api/account/send-code` | 验证码 | body `{email,purpose}`；响应 `{ok:true, retry_after_seconds}`；`ok!==true` 即视为「结果尚未确认」[证据: index:7598-7602] |
| GET | `/api/account/logout-all` | 账号中心 | 需二次确认弹窗文案「确认退出全部账号会话？」[证据: index:7979] |
| POST | `/api/account/activate` | LicenseGate | body `{license_id}`[证据: index:7469] |
| GET | `/api/account/identity` | 实名面板 | |
| POST | `/api/account/identity/withdraw` | 实名撤回 | 确认弹窗「确认撤回实名授权？」[证据: index:7983] |
| POST | `/api/account/workbench-access` | `useWorkbenchAccess` | 工作台准入 |
| GET | `/api/account/models` | 模型目录 | [证据: AccountModelCatalog:59] |
| GET | `/api/account/model-account` | 仅白名单出现 | 账号-模型关联开关 |
| POST | `/api/account/licenses/claim` | 领取软件授权 | [证据: index:7871] |
| POST | `/api/account/licenses/{32hex}/unbind` | 解绑设备 | 前缀校验 `/^[a-f0-9]{32}$/`；确认弹窗「确认解除设备绑定？」[证据: index:7973] |
| POST | `/api/license/verify` | LicenseGate | body `{license_key, machine_id:'CLIENT-PLACEHOLDER'}`[证据: index:8647] |
| GET | `/api/license/status` | 仅白名单出现 | |

#### B. 账号推理 / 消息通道（`routers/account_inference.py` / `routers/account_messages.py`）

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/account/inference/capabilities` | 推理能力 |
| GET | `/api/account/inference/operations/{uuid}` | 异步操作查询 |
| POST | `/api/account/inference/operations` | 发起异步操作 |
| GET | `/api/account/messages` | `AccountMessagesInference` 主列表 |
| GET | `/api/account/messages/capabilities` | NewWorkflow / WorkflowDetail 用于判断可用模型能力[证据: NewWorkflow:60,WorkflowDetail:95] |
| GET | `/api/account/messages/operations/{uuid}`、`POST /api/account/messages/operations` | 异步操作 |
| GET/PUT | `/api/account/native/image-settings` | 生图模型设置；GET 返回 `{account_id,mode_revision,model_id,effective_model,models[]}`；PUT body `{account_id,mode_revision,model_id}`[证据: Settings:78] |

#### C. New API 原生计费（`routers/newapi_account.py`，全部经 `H(path, body?, signal)` 打 `POST /api/account/native/*`）

| 方法 | 端点 | 响应关键字段 |
|---|---|---|
| GET | `/api/account/native/wallet` | `{account_id:'newapi:<int>', quota, used_quota, quota_per_point>0, payment_enabled, products[4], custom_amount?}`；`products[i].cny_fen` 必须为 `[1000,5000,10000,30000]` 且 `points=cny_fen/10`[证据: Account:412-414] |
| GET | `/api/account/native/usage?start&end&model&cursor` | `{account_id,items[],by_model[],summary{requests,quota,prompt_tokens,completion_tokens},total,next_cursor,filters{start,end,model},as_of}`；前端交叉校验 `Σby_model==summary`[证据: newApiWallet:172] |
| GET | `/api/account/native/orders?page=N` | `{account_id,total,items[{trade_no,...}]}`，`trade_no` 需 `/^[A-Za-z0-9_-]{1,128}$/` |
| GET | `/api/account/native/adjustments?page=N` | 额度调整 |
| GET | `/api/account/native/requests?page=N` | 调用明细 |
| GET | `/api/account/native/history?page=N&start&end&model` | 消费历史 |
| GET | `/api/account/native/realname` | `{verified,required,license_allowed,simulated,service_ready,consent_version,retry_after_seconds,name_masked,idcard_masked,mobile_masked,manual_access,policy{version,sha256,url,text},attempt{request_id,outcome},disclosure{provider_name,provider_contact,purpose,notice,published,policy_version,policy_digest}}`；`outcome∈{processing,uncertain,unknown}` 视为未确认[证据: index:7542-7575] |
| GET | `/api/account/native/software` | 软件授权状态（同 realname 结构 + `policy`） |
| POST | `/api/account/native/software/consent` | body 含 `{policy_digest, ...}`（`/consent` 后缀 + `consent_version`）[证据: index:8025] |
| POST | `/api/account/native/register` | 原生注册 |
| POST | `/api/account/native/register-code` | 发注册验证码 |
| POST | `/api/account/native/reset-email` | 重置邮箱 |
| POST | `/api/account/native/login/verify` | body `{challenge_id, code}`[证据: index:8191] |
| POST | `/api/account/native/checkout` | 发起充值订单（支付宝） |
| POST | `/api/account/native/orders/{mdx_32hex}/query` | 订单查询 |

**充值本地契约**[证据: Account:11863-12826]：`order_id` 必须 `/^mdx_[a-f0-9]{32}$/`；localStorage key 为 `modex-native-checkout:{newapi:<id>}:{cny_fen}`；用 `navigator.locks.request` 串行化；文案「1 元 = 10 积分，快捷套餐为 10 / 50 / 100 / 300 元」。

#### D. 设置（`routers/settings.py`）

| 方法 | 端点 | 关键字段 |
|---|---|---|
| GET | `/api/settings` | 返回 `{settings:{...}, presets:[...]}` |
| PUT | `/api/settings` | body `{settings:{...}}`；返回同结构[证据: Settings:219] |
| GET | `/api/settings/data-dir` | 数据目录 |
| PUT | `/api/settings/data-dir` | body `{data_dir}` |
| GET | `/api/settings/detect-claude` | 检测 Claude CLI |
| GET | `/api/settings/presets` | 预设列表；每项 `context_mode ∈ {auto,200k,1m,legacy}` |
| POST | `/api/settings/presets` | 新建；body `{name, model_id, api_key, ...}` |
| PUT | `/api/settings/presets/{id}` | 更新（`method: i?'PUT':'POST'`[证据: Settings:219]） |
| DELETE | `/api/settings/presets/{id}` | 删除 |
| POST | `/api/settings/test/{provider}` | 连通性测试（无 body） |
| POST | `/api/settings/models/discover` | body `{api_key, agent:'gpt_image', force_refresh:true}`；返回 `{models:[...]}`[证据: Settings:176,modelDiscovery] |

**`settings` 对象默认全集**【直接提取，`Settings-D4EW1h0L.pretty.js:219`，`k` 常量】：

```
executor_base_url, executor_api_key, executor_model_id('claude-opus-4-8'),
reviewer_base_url, reviewer_api_key, reviewer_model_id('claude-opus-4-8'),
minimax_api_key, minimax_group_id, gemini_api_key,
editor_ai_base_url, editor_ai_api_key, editor_ai_model_id('claude-opus-4-8'),
gpt_image_api_key, gpt_image_base_url, gpt_image_model_id('gpt-image-2'),
claude_bin('claude'), executor_preset_id, reviewer_preset_id, editor_ai_preset_id,
default_effort(''), model_context_policies('{}')
```

#### E. 工作流（`routers/workflows.py` + `stores/workflowStore.ts`）

| 方法 | 端点 | 调用点 / body |
|---|---|---|
| GET | `/api/workflows` | Dashboard 列表；失败静默（`catch{}`）[证据: workflowStore:44] |
| POST | `/api/workflows` | 新建；body `{template, title, params, enable_checkpoints}`[证据: workflowStore:101-107] |
| GET | `/api/workflows/{id}` | 详情；15s 超时 + AbortController；校验 `resp.id===id`[证据: workflowStore:75-81] |
| DELETE | `/api/workflows/{id}` | 删除 |
| POST | `/api/workflows/{id}/start` | 启动 |
| POST | `/api/workflows/{id}/resume` | body `{strategy}` |
| POST | `/api/workflows/{id}/pause` | 暂停 |
| POST | `/api/workflows/{id}/restart` | 重启（清空本地 logs） |
| PATCH | `/api/workflows/{id}/mode` | body `{chat_mode}` |
| POST | `/api/workflows/{id}/steps/{skill}/rerun` | 单步重跑 |
| PATCH | `/api/workflows/{id}/steps/{skill}/model` | body `{preset_id, rerun}` |
| PATCH | `/api/workflows/{id}/steps/{skill}/effort` | body `{effort, rerun}` |
| PATCH | `/api/workflows/{id}/steps/{skill}/account-model` | body `{model_id}`（WorkflowDetail 内联调用） |
| POST | `/api/workflows/{id}/checkpoints/resolve` | body `{action, data, checkpoint_id}`；12s 超时；响应必须 `status==='resolved'`[证据: workflowStore:290-307] |
| GET | `/api/workflows/{id}/checkpoints/current` | 检查点轮询；响应 `{active, checkpoint_id, remaining_seconds, step_name, resume_require, ...}`；缺 `remaining_seconds` 则提示「后端仍是旧版检查点逻辑」[证据: WorkflowDetail:15867] |
| GET | `/api/workflows/{id}/checkpoints/plan` | 方案确认 |
| PUT | `/api/workflows/{id}/checkpoints/plan` | body `{content, checkpoint_id}`[证据: WorkflowDetail:88] |
| GET | `/api/workflows/{id}/logs?limit=200&compact=true` | 日志流 |
| GET | `/api/workflows/{id}/export` / `?mode={mode}` | 单工作流导出（blob 下载，读 `Content-Disposition`） |
| POST | `/api/workflows/export-batch` | body `{ids:[...]}`，返回 zip[证据: Dashboard:35] |
| POST | `/api/workflows/import` | **FormData**（字段 `file`，仅接受 `.zip`）；响应 `{count, imported:[{title}]}`[证据: Dashboard:36] |

#### F. 工件（`routers/artifacts.py` / `routers/artifact_context.py`）

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/workflows/{id}/artifacts` | 工件集合（`collectionEndpoint`） |
| GET | `/api/workflows/{id}/artifacts?view=overview[&refresh=true]` | 概览视图（工件库/聊天页刷新用） |
| GET | `/api/workflows/{id}/artifacts/{path}` | 读工件；文本返回 `{content,...}`；`?raw=true` 取原始字节；`?preview=html` 用于 iframe 渲染（HTML/图表） |
| GET | `/api/workflows/{id}/artifacts/{path}#page=1&zoom=page-width&navpanes=0` | PDF iframe 片段参数 |
| POST | `/api/workflows/{id}/artifacts/upload` | **FormData**，字段 `files`（多文件）+ `target_dir=user_data`[证据: NewWorkflow:70,WorkflowDetail:103] |
| POST | `/api/workflows/{id}/artifacts/custom-requirements` | **FormData**（字段 `file`） |
| GET | `/api/workflows/{id}/artifacts/extract-status` | 解包/抽取进度 |
| GET | `/api/workflows/{id}/artifacts/ASSETS_INVENTORY.md` | 返回 `{content}`（资产清单）[证据: WorkflowDetail:15867] |
| GET | `/api/workflows/{id}/artifacts/ASSETS_CONFLICTS.md` | 返回 `{content}`（资产冲突） |
| GET | `/api/workflows/{id}/artifacts/PAPER_PLAN.md` | 论文计划 |
| GET | `/api/workflows/{id}/artifacts/paper%2FPAPER_IMPROVEMENT_LOG.md` | 论文改进日志（**路径已 URL 编码**） |
| GET | `/api/workflows/{id}/artifact-context/inspect/{path}` | 工件上下文探查（ArtifactViewer） |
| POST | `/api/workflows/{id}/artifact-context/prompt/build` | body `{path, instruction, action}`[证据: ArtifactViewer:18] |

#### G. 协同聊天（`routers/chat.py` / `chat_internal.py`，全部经 `chatStore`）

| 方法 | 端点 | body / 备注 |
|---|---|---|
| GET | `/api/workflows/{id}/chat` | 聊天基线 |
| POST | `/api/workflows/{id}/chat/session` | 开启会话（无 body，仅 `{method:'POST',signal}`） |
| DELETE | `/api/workflows/{id}/chat/session` | 关闭会话 |
| GET | `/api/workflows/{id}/chat/state` | 会话状态；返回 `session_alive` |
| GET | `/api/workflows/{id}/chat/config` | 协同配置 `{interaction_mode, model_preset_id, effort, project_brief}` |
| PATCH | `/api/workflows/{id}/chat/config` | 同上四字段[证据: useWebSocket:45] |
| GET | `/api/workflows/{id}/chat/messages{?limit/before}` | 历史分页（`full` 时带参） |
| POST | `/api/workflows/{id}/chat/say` | body `{text, turn_id, mode, focus_target, ...}`；`turn_id` 由 `crypto.randomUUID()`（退化 `turn-<ts>-<rand>`）生成[证据: useWebSocket:50] |
| POST | `/api/workflows/{id}/chat/messages/{mid}/confirm` | body `{force, front, revision}` |
| POST | `/api/workflows/{id}/chat/messages/{mid}/cancel` | 取消执行 |
| POST | `/api/workflows/{id}/chat/messages/{mid}/rollback` | 回滚局部改动 |
| PATCH | `/api/workflows/{id}/chat/messages/{mid}/proposal` | body `{instruction, revision, ...}`（编辑提案） |
| GET | `/api/workflows/{id}/chat/messages/{mid}/diff` | 单条消息 diff |
| POST | `/api/workflows/{id}/chat/messages/{mid}/resume-draft` | body `{revision, resolution...}`；20s 超时[证据: ChatWorkbench:21] |
| POST | `/api/workflows/{id}/chat/messages/{mid}/validation-proposal` | 只读校验提案 |
| GET | `/api/workflows/{id}/chat/messages/{mid}/events?after_sequence={n}&limit=80` | 运行事件增量拉取 |
| GET | `/api/workflows/{id}/chat/messages/{mid}/rollback-preview` | 回滚预览[证据: ChatWorkbench:27] |
| GET | `/api/workflows/{id}/chat/turns/{turn_id}` | 轮次查询 |
| GET | `/api/workflows/{id}/chat/queue` | 队列状态 `{busy, running, depth, waiting[]}` |
| POST | `/api/workflows/{id}/chat/queue` | 入队 |
| POST | `/api/workflows/{id}/chat/queue/{mid}/promote` | 插队 |
| GET | `/api/workflows/{id}/chat/forks?pending_only=false` | 分支（Fork）列表 |
| POST | `/api/workflows/{id}/chat/forks/{mid}/choose` | body `{choice, action(select/defer), expected_revision}` |
| GET | `/api/workflows/{id}/chat/decisions` | 决策列表 |
| POST | `/api/workflows/{id}/chat/decisions` | body `{topic, choice, rejected, ...}` |
| DELETE | `/api/workflows/{id}/chat/decisions/{id}` | 撤销决策 |
| GET | `/api/workflows/{id}/chat/materials` | 聊天素材[证据: ChatWorkbench:29] |
| POST | `/api/workflows/{id}/chat/stages/{skill}/accept` | body `{snapshot}`；60s 超时[证据: ChatWorkbench:30] |

#### H. 编辑器（`routers/editor.py` / `project_preview.py` / `docx_export.py`）

基址 `P = "/api/editor"`（`LatexEditor-I1nsgpA4.pretty.js:1190`），`{id}`=workflow_id。

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/editor/{id}` | 编辑器初始元数据 |
| GET | `/api/editor/{id}/files?view=overview[&refresh=true]` | 文件树/状态（**调用最频繁**） |
| GET | `/api/editor/{id}/files` | 文件集合（`collectionEndpoint`） |
| GET | `/api/editor/{id}/file?path={p}[&t={ts}]` | 读单文件 |
| GET | `/api/editor/{id}/pdf?t={ts}` | PDF 预览 |
| GET | `/api/editor/{id}/docx?{query}` | Word 预览 |
| GET | `/api/editor/{id}/docx-status` | Word 导出状态（`cache:'no-store'`） |
| POST | `/api/editor/{id}/compile` | body `{}`；返回 `{message, current_file, compile_log, request_id}`（`request_id` 需 `/^[A-Za-z0-9_-]{8,80}$/`）[证据: LatexEditor:148] |
| POST | `/api/editor/{id}/mode` | 编辑器模式切换 |
| GET | `/api/editor/{id}/stats` | 统计 |
| GET | `/api/editor/{id}/chat-history` | 编辑器侧聊天历史 |
| DELETE | `/api/editor/{id}/chat-history` | 清空历史 |
| POST | `/api/editor/{id}/upload?path={p}` | 上传 |
| POST | `/api/editor/{id}/create-file` | 新建文件 |
| POST | `/api/editor/{id}/drawio-export` | DrawIO 导出 |
| POST | `/api/editor/{id}/run-script` | 运行脚本 |
| POST | `/api/editor/{id}/run-script-stop` | 停止脚本 |
| POST | `/api/editor/{id}/image-check` | 图片校验 |
| GET | `/api/editor/{id}/describe-image?path={p}[&expected_sha256={h}]` | 图片描述（视觉） |
| GET | `/api/editor/{id}/file-preview-html?path={p}&revision={r}{&...}` | HTML 预览 |
| GET | `/api/editor/{id}/download?path={p}` | 下载 |
| POST | `/api/editor/{id}/serve` | body `{mode}` |
| DELETE | `/api/editor/{id}/serve[?kind={k}]` | 停止预览服务 |
| GET | `/api/editor/{id}/serve/status` | 预览服务状态 |
| POST | `/api/editor/{id}/ai-edit` | AI 局部改稿（`{method:'POST',headers:{...}}`，`LatexEditor:2161-2162`） |
| POST | `/api/editor/{id}/ai-agent` | 发起编辑器 Agent 运行；body 为 JSON；**响应为 SSE 事件流**，读 `X-Editor-Run-Id` 响应头（见 §5.5） |
| POST | `/api/editor/{id}/ai-agent-apply` | 应用 Agent 结果（`LatexEditor:2265-2266`） |
| GET | `/api/editor/{id}/ai-agent-check?log_offset={n}&run_id={r}` | 轮询运行日志 / 恢复（`?request_id=` 亦可） |
| POST | `/api/editor/{id}/ai-agent-stop?run_id={r}`（或 `?request_id={r}`） | 安全停止；响应 `{running, state}`；失败文案「停止未确认」「未能确认停止，任务可能仍在后台执行。」（`LatexEditor:2013-2024`） |
| POST | `/api/editor/{id}/ai-agent-discard?run_id={r}` | 丢弃草稿（`LatexEditor:2341-2342`） |
| GET | `/api/editor/{id}/ai-agent-runs?limit=20&before={c}` | 运行历史分页 |
| GET | `/api/editor/{id}/ai-agent-runs/{run_id}` | 单次运行详情 |
| POST | `/api/editor/{id}/ai-agent-undo?version_id={v}` | 撤回版本（`version_id` 需 `/^[a-f0-9]{32}$/`）[证据: LatexEditor:320] |
| GET | `/api/editor/{id}/ai-agent-history` | 版本历史 `{versions[]}` |
| GET | `/api/editor/{id}/ai-agent-version/{version_id}` | 版本 diff `{version_id, diffs[]}` |
| GET | `/api/editor/{id}/model-options` | 可选模型 |
| POST | `/api/editor/{id}/generate-image` | body `{...,request_id}`（`request_id` 先落 localStorage，失败可恢复）[证据: LatexEditor:396] |
| GET | `/api/editor/{id}/image-requests/{request_id}` | 生图结果查询 |

#### I. 预览与模板（`routers/palette_preview.py` / `style_preview.py` / 模板解析）

| 方法 | 端点 | 参数 |
|---|---|---|
| GET | `/api/palette-preview?colors={csv}` | 配色预览 PNG（`#4477AA,#EE6677,...`） |
| GET | `/api/style-preview?frame=&grid=&lw=&font=&legend=&bg=` | 版式预览 PNG |
| POST | `/api/templates/{template}/resolve-steps` | body 为工作流参数对象；`signal` + 15s 超时[证据: NewWorkflow:59] |
| GET | `{backend.url}/docs` | FastAPI 交互文档外链（「API文档」链接） |

#### J. 非前端调用但存在于后端的端点（交叉证据）

- `POST /api/health/update`（`asar\main.js:1265`，主进程调用）
- 全部 `routers/*.pyd` 中的路由模块名（`account, account_inference, account_messages, artifacts, artifact_context, chat, chat_internal, checkpoints, client_config, cli_gateway, docx_export, editor, newapi_account, palette_preview, project_preview, settings, style_preview, workflows, ws`），与前端调用面一一对应【直接提取：`reports\build-inputs-paths.txt` 与 `strings\routers__*.strings.txt`】。

### 4.2 外部端点与出站 URL  [证据: tools\_fx\external-urls.txt（node 全量扫描 21 条，去 W3C/XML 命名空间后为下表）]

| URL | 出现位置 | 用途 |
|---|---|---|
| `https://www.mingheng.xin/` | `index-*` | 导航栏「官网」外链 |
| `https://bill.mingheng.xin` | `useAccessMode-*` | New API 账户站点白名单（`account_site===此值才保留`） |
| `https://license.mingheng.xin/privacy` | `Account-*` | 隐私政策外链 |
| `https://openapi.alipay.com` | `Account-*` | 支付宝支付地址**前缀校验**（另有 `location.username/password/hash` 校验，见 `Account:17224`「支付地址校验失败。」） |
| `https://embed.diagrams.net/?embed=1&proto=json&spin=1&libraries=1&noExitBtn=1&saveAndExit=0` | `LatexEditor-*` | DrawIO 嵌入式编辑器 iframe |
| `https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html` | `ChatWorkbench-*` | 美赛（MCM/ICM）官方说明外链 |
| `https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html` | `NewWorkflow-*` | 美赛官方规则外链（AI 使用记录合规依据） |
| `https://react.dev/errors/`、`https://reactrouter.com/...`、`https://redux-toolkit.js.org/Errors`、`https://github.com/ungap/url-search-params`、`https://github.com/syntax-tree/hast-util-to-jsx-runtime`、`https://bit.ly/3cXEKWf` | vendor | 第三方库错误链接（非业务） |
| `http://localhost` | `jsx-runtime-*` | 开发期 base URL 兜底（生产不生效） |

> 【推断】`bill.mingheng.xin` + `openapi.alipay.com` + `license.mingheng.xin` 三者共同构成本产品的外网信任面：模型/账单在 New API 站点，支付走支付宝，授权走 license 服务。

---

## 5. WebSocket 协议

### 5.1 连接与心跳  [证据: useWebSocket-DhwRyw4C.pretty.js:901-1015（重连/心跳/唤醒）, :984（WS URL）]

- **URL**：`` `${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/${encodeURIComponent(workflowId)}` `` ⇒ 即 `ws://127.0.0.1:<port>/ws/{workflow_id}`，与后端 `routers/ws.py` 的 `ws_endpoint`/`ConnectionManager` 对应[证据: useWebSocket:984；strings\routers__ws... 含 ws.ConnectionManager.connect/disconnect/broadcast/pong、ws.ws_endpoint、workflow_id]
- **心跳**：客户端每 10s 发送**纯文本** `` `ping` ``；服务端回 `` `pong` ``；客户端收到 `pong` 时不派发事件（`t.data!=='pong' && e.onMessage(...)`）；任意消息都会刷新 `lastMessageAt`
- **超时**：连接中超过 20s 未 open → 重连；OPEN 后 60s 无消息 → 重连
- **退避**：`Math.min(1000*2**Math.min(n,5), 30000) * (0.8 + random*0.2)`，成功后 n 归零
- **唤醒**：`window.online` 与 `document.visibilitychange`（visible）触发 `wake()`；若 OPEN 且 <60s 空闲则仅回调 `onOpen()`（相当于重新同步），否则重建连接
- **onOpen 侧同步动作**：`chatStore.fetchMessages({full:true})` → 对 `status==='running'` 的消息 `fetchRunEvents(id,0)` → `fetchState()` → `fetchQueue()`；`workflowStore.fetchWorkflow(id)`

### 5.2 消息信封与分发  [证据: useWebSocket-DhwRyw4C.pretty.js:996-1004]

```jsonc
{ "type": "<string>", "workflow_id": "<id>", /* 其余按 type 而定 */ }
```

分发规则：`workflow_id` 不匹配当前工作流则丢弃；`type.startsWith('chat_')` → `chatStore.handleChatEvent`，否则 → `workflowStore.handleWsEvent`。

### 5.3 工作流事件  [证据: workflowStore-DtYgz0OF.pretty.js:323-452（handleWsEvent 全分支）]

| type | 字段 | 前端状态效果 |
|---|---|---|
| `step_progress` | `step, phase, log, workflow_id` | 追加日志 `[step] log`；`phase==='preparing_content'` 时把当前步标记为「准备 Skill」 |
| `step_started` | `step` | 该步 `running`，前一个 `running` 步置 `completed`，`current_step=step` |
| `step_skipped` | `step` | 该步 `completed`（日志「已完成，跳过」） |
| `step_completed` | `step, result_summary, missing_files[], output_files[]` | 该步 `completed`，合并 `output_files`；`missing_files` 输出告警 |
| `step_failed` | `step, error` | 该步 `failed` + `error_message` |
| `checkpoint_hit` | `step, checkpoint_type, checkpoint_id, display_name, primary_output_file, primary_output_content` | 工作流 `paused`，该步 `waiting_checkpoint`；写入 `checkpointPreview/DisplayName/Id` |
| `workflow_started` | — | 状态 `running` |
| `workflow_paused` | `message` | `paused`；运行中步回退 `pending`；日志 `[暂停诊断] message` |
| `workflow_license_required` | `reason, error` | `paused`；`reason==='content_network_unavailable'` 或 error 匹配 `/(CAPSULE\|LICENSE)_(NETWORK_ERROR\|SERVICE_UNAVAILABLE)/` 时提示「网络等待」，否则「授权暂停」 |
| `workflow_completed` / `workflow_failed` / `workflow_stopped` | — | 置对应终态并重新 `fetchWorkflow` |

### 5.4 聊天事件  [证据: useWebSocket-DhwRyw4C.pretty.js:746-870（handleChatEvent 全分支）]

| type | 关键字段 | 效果 |
|---|---|---|
| `chat_reply_progress` | `turn_id, progress_message, elapsed_seconds, idle_seconds` | 更新「正在处理本轮对话 · 已用时 X」 |
| `chat_progress` | `message_id, run_id, progress{version,phase,message,health,last_activity_at,recent[]}, progress_phase, progress_message` | 100ms 节流写入消息 progress |
| `chat_run_event` | `message_id, event{sequence, run_id, type, ...}` | 合并到 `message.run_events`；序号跳空时触发 `fetchRunEvents` 补拉 |
| `chat_proposal` | `message_id, turn_id, item_kind, skill, instruction, source_skill, operation_kind, eta_minutes, outputs[], missing_deps[], proposal_revision, execution_scope, focus_target, model_preset_id, effort, target_paths[], input_paths[], target_sections{}, raw_text` | 新增/更新 `status:'proposed'` 的助手消息 |
| `chat_started` | `message_id, status, state_revision, run_id` | 消息 `running`；重拉消息 + run events + 队列 + 状态 |
| `chat_done` | `message_id, status, state_revision, run_id, quality_status, summary, outputs, source_skill, operation_kind, diffs, version_id, rollback_available, progress_phase, progress_message, progress, completed_at` | 消息 `done` + 结果/补丁/质量信息 |
| `chat_failed` / `chat_cancelled` | 同上 + `error` | 消息 `failed` / `cancelled` |
| `chat_rollback` | `message_id, summary` | 消息标记 `rolled_back_at`，清除 `rollback_available` |
| `chat_forks` | — | 触发 `fetchForks()` |
| `chat_runtime` | `message_id, model_used, effort` | 回写实际使用的模型/强度 |
| `chat_stale` | `message_id` | 消息 `stale`（前提已变化）+ `fetchState()` |

**运行事件（`chat_run_event.event.type`）枚举**【直接提取，`ChatWorkbench:8615` 的 `ge` 映射表】：
`run_started, phase_started, source_opened, fact_extracted, artifact_started, artifact_updated, calculation_started, validation_started, validation_passed, artifact_created, run_waiting, run_failed, run_completed`
（后端侧同名：`chat_run_events.RunEventTracker.run_started/start_phase/source_started/source_progress/source_finished/feed/validation_started/validation_finished/terminal`[证据: strings\_merged_strings.txt:5589-5610]）

### 5.5 编辑器 Agent 的 SSE 事件流（非 WebSocket，独立的第二套实时通道）  [证据: LatexEditor-I1nsgpA4.pretty.js:93-116（le）, :164-203（ge 解析器）, :2082-2090（事件类型）, :62-63（合并规则）]

除 `/ws/{workflow_id}` 外，LaTeX 编辑器的 AI Agent 使用 **fetch + `ReadableStream` 手写 SSE 解析**：

- **请求**（【直接提取】`LatexEditor:93-116` `le(e,t,n,r=15e3)`）：``fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(t),signal})``，外部 signal 桥接 + 15s 首包超时，返回 `{response, close}`
- **响应头**：``o = t.headers.get('X-Editor-Run-Id')`` —— 编辑器 Agent 的 run id 从**响应头**而非 body 取得
- **解析器**（【直接提取】`LatexEditor:164-203` `ge(stream, cb, timeout=30s)`）：`response.body.getReader()` + `TextDecoder(stream:true)`；按 `\n\n` 切分事件块，取 `data:` 行拼接后 `JSON.parse`；**每次 read 有 30s 超时**，超时报「事件连接长时间无响应，正在恢复后台状态」；无 `body` 时报「没有收到任务事件流」
- **事件类型**：`progress | log | heartbeat | result`（【直接提取】`LatexEditor:2087`）；`type==='result'` 即终止流
- **断线恢复语义**：`ai-agent` 请求失败时**不新建任务**，而是用同一个请求编号重试并提示「连接中断，正在用同一个请求编号恢复；不会重复启动任务」；并配合 `GET /ai-agent-check?run_id=` 做状态回填（`state:'unknown'`）
- **合并规则**（【直接提取】`LatexEditor:62-63`）：`heartbeat` 在连接后 10s 内不得覆盖已有状态；`progress` 有 `sequence` 时按序号单调递增合并

---

## 6. 状态管理结构

两个 Zustand store（均以 `create((set,get)=>({...}))` 内联形态出现）。

### 6.1 `stores/workflowStore.ts`  [证据: workflowStore-DtYgz0OF.js（导出 `p as t`）, :37-39（state）, :39-452（28 个 action）]

**state**【直接提取，`workflowStore-DtYgz0OF.pretty.js:37-39`】

```
workflows: []            // 列表
current: null            // 当前工作流详情（含 steps[]）
logs: {}                 // { [workflowId]: string[] }，单条截断 2000 字、总 200KB、最多 500 条
loading: false
detailError: null
checkpointPreview: null  // {file, content}
checkpointDisplayName: null
checkpointId: null
```

**actions**：`fetchWorkflows(quiet?)`、`fetchWorkflow(id)`、`createWorkflow(template,title,params,enableCheckpoints)`、`startWorkflow(id)`、`resumeWorkflow(id,strategy)`、`pauseWorkflow(id)`、`restartWorkflow(id)`、`deleteWorkflow(id)`、`rerunStep(id,skillName)`、`setWorkflowMode(id,chatMode)`、`patchStepModel(id,skill,presetId,rerun)`、`patchStepEffort(id,skill,effort,rerun)`、`resolveCheckpoint(id,action,data,checkpointId)`、`addLog(id,line)`、`addHistoryLogs(id,lines)`、`handleWsEvent(event)`

**关键派生字段**（写死在 action 里）：`status ∈ {pending,running,paused,completed,failed}`（前端显式写出的 5 个；`workflow_stopped` 事件只清空检查点预览并重新拉取详情，未显式写入新状态值）；step 对象含 `skill_name, display_name, status, checkpoint_type, error_message, recovery_phase, recovery_message, output_files[], started_at, completed_at, resume_error_code, resume_session_id`。

### 6.2 `stores/chatStore.ts`  [证据: useWebSocket-DhwRyw4C.js（导出 `K as r`）, :146-160（state）, :160-899（28 个 action）]

**state**【直接提取，`useWebSocket-DhwRyw4C.pretty.js:158-160`】

```
workflowId, sessionId, messages[], state, audit, queue, config, configSaving,
forks[], forkOps{}, hasMoreBefore, loadingOlder, messageOps{},
opening, sending, replyTurnId, replyProgress, stopping, stopUnconfirmed,
error, errorInfo, sessionAlive
```

**actions**（28 个，【直接提取】）：

```
loadWorkspace, openSession, closeSession, say, stopResponse, confirm, editProposal,
fetchConfig, patchConfig, fetchQueue, promote, cancel, rollbackPatch, validateOutputs,
addDecision, rejected, revokeDecision, fetchForks, chooseFork, fetchMessages,
fetchRunEvents, loadOlder, fetchState, handleChatEvent, startPolling, stopPolling,
clearError, reset
```

**消息对象字段**（由 `chat_proposal` / `chat_done` 写入，【直接提取】）：`id, session_id, role, content, intent, status, confirmed, turn_id, client_turn_id, item_kind, skill_name, instruction, source_skill, operation_kind, execution_scope, focus_target, model_preset_id, effort, model_used, eta_minutes, outputs[], missing_deps[], target_paths[], input_paths[], target_sections{}, proposal_revision, run_id, run_events[], quality_status, error_message, result_summary, result_outputs, diffs, version_id, rollback_available, progress{version,phase,message,health,last_activity_at,recent[]}, progress_phase, progress_message, message_phase, artifact_state, rolled_back_at, started_at, completed_at, created_at`

**消息状态枚举**【直接提取，`ChatWorkbench:140967`】：`proposed(等待确认), queued(已确认·排队中), running(正在执行), done(已完成), failed(未完成), interrupted(已中断), cancelled(已取消), stale(前提已变化)`

**生命周期**：`startPolling` 仅在队列忙或有未完成消息时运行（`W(e)` 判定：存在 `pending/queued/running` 消息 或 `queue.busy/running/depth>0/waiting.length`），否则自动 `stopPolling`；页面不可见时跳过轮询。

### 6.3 React Context（非 store 的全局态）  [证据: index-BeImsYqE.pretty.js:232701（Theme）, useAccessMode-CYwsqbbI.pretty.js:272-316（AccessMode）, index:246079（ClientConfig）]

- **ThemeContext**（`hooks/useTheme.tsx`）：`{theme, setTheme, toggle, customColors, setCustomColors}`；`theme ∈ {warm, light, green, custom}`，默认 `warm`，写 `<html data-theme>` 与 localStorage `MH Agent-theme` / `MH Agent-custom-colors`[证据: index:232701]
- **AccessModeContext**（`hooks/useAccessMode.tsx`）：`{status, loading, busy, error, refresh, select}`；派发全局事件 `modex-access-mode-changed`；GET 时带 header `X-Modex-Mode-Read: identity`[证据: useAccessMode:159,273-316]
- **ClientConfig**（`hooks/useClientConfig.ts`）：`{status:'idle'|'loading'|'ready'|'unavailable', config, message}`[证据: index:246079]

---

## 7. UI 层面的业务特征（数模竞赛智能体）

### 7.1 赛题模板目录  [证据: NewWorkflow-Ld6TEJjT.pretty.js:45387 起（常量 `Te`）；条目数由 node 计数 `value:`comp_*`` = 22]

每条模板含 `{value, icon, label, desc, time, lang, pages, stars, group}`，`desc` 即流水线。

- **竞赛模板（`comp_*`，共 22 个，脚本精确计数）**：`comp_tianfu`(天府杯), `comp_certcup`(认证杯), `comp_certcup_en`, `comp_mathorcup`(MathorCup), `comp_teddy`(泰迪杯), `comp_huadong`(华东杯), `comp_huazhong`(华中杯), `comp_wuyi`(五一杯), `comp_zhongqing`(中青杯), `comp_yangtze`(长三角), `comp_stats`(统计建模大赛), `comp_shuwei`(数维杯), `comp_shuwei_en`, `comp_diangong`(电工杯), `comp_liaoning`(辽宁省/东三省), `comp_apmcm_zh`(亚太赛中文), `comp_apmcm`(亚太 APMCM), `comp_shenzhen`(深圳杯), `comp_huashu`(华数杯), `comp_cumcm`(国赛 CUMCM), `comp_huawei`(华为杯), `comp_mcm`(美赛 MCM/ICM)；`desc` 统一为「赛题分析 → 建模 → 编程 → 图表 → 论文 → 编译」（`group:'en'` 的英文条目为 `Analysis → Modeling → Code → Figures → Paper → Compile`），每条另带 `time`(月份)、`pages`(目标页数)、`stars`(1–5)、`group`[证据: NewWorkflow-Ld6TEJjT.pretty.js:45387 起，node 计数 value:\comp_*_\ 命中 22]
- **学术模板（`category:'academic'`，5 条）**：`thesis_proposal`(开题报告), `literature_review`(文献综述), `course_paper`(课程论文), `course_report`(课程报告), `humanities_paper`（另有 `paper_writing`/`paper_writing_zh`/`nature_writing`/`full_pipeline` 出现在 `br` 分支判定数组中）
- **科研模板（`category:'research'`，4 条）**：含 `idea_discovery`、`experiment_bridge` 等；`N()` 中另见 `grad_project`、`copyright_material`、`patent_disclosure`、`auto_review`[证据: ChatWorkbench:6130 的 N() 与 NewWorkflow:54553 的 br/[...] 数组]
- 全页 `value:` 字面量共 63 个（含配色/版式/输出格式等枚举）
- 本地资源预览：`/palette_preview/{name}.png`（30 个配色预览图）与 `/style_preview/{name}.png`（6 个版式预览图）

### 7.2 新建工作流参数契约（POST `/api/workflows` 的 `params`）

【直接提取，`NewWorkflow:56843-65877`】

`template`, `title`, `enable_checkpoints`, `language`, `output_format`(docx/latex/markdown), `flowchart_engine`(drawio/html), `enable_comp_review`, `skip_report`, `skip_figures`, `skip_analysis`, `skip_drawio`, `skip_improvement_loop`, `format_text`, `template_file`(=`user_data/{name}`), `template_files[]`, `project_type`(fullstack/frontend/cli/script), `tech_frontend/tech_backend/tech_db/tech_lang`, `custom_requirements`, `data_fig_style`, `style_custom`, `figure_style`, `validation_mode`(strict/fast), `min_tables`, `min_models`, `max_rounds`, `target_score`, `max_pages`, `competition`。

**学术诚信门禁（AI 使用记录）**[证据: NewWorkflow:13454-13508]：

- `w(e){ return e==='comp_cumcm' }`（国赛专属校验）
- 校验文案：「请先确认所填 AI 使用记录真实、完整，并已由参赛队人工核验」「请填写 1–5 条真实 AI 工具记录」；记录项含 `provider_id` 等字段，与 `utils/aiDisclosure.ts`、`oe`（provider 列表）对应
- 配色/版式随机化说明文案：「同一篇内统一、不同篇各不相同，像不同的人画的，最大程度降低雷同、避免被识别」

### 7.3 图表配色与版式（`DATA_FIG_PALETTES` / `DATA_FIG_STYLES` 导出）

- **30 套配色**（每套 7–8 色，如 `elegant #7AAEC8...#A8C4D8`、`okabe_ito`、`tol_muted`、`tol_vibrant`、`nord`、`morandi`、`sunburst`、`ocean`、`journal`、`pastel`、`earth_forest`、`peacock`、`aurora`、`vivid_bold`、`mint_lav` 等）[证据: NewWorkflow:19854]
- **6 套版式**：`clean_open`(清爽开放·左下轴线无网格)、`soft_grid`(柔和网格)、`framed_journal`(框线期刊·四面边框朝内刻度)、`minimal_bare`(极简无框)、`bold_edge`(粗描边)、`crisp_dark`(清晰深轴)；每套含 `scene`/`feats` 说明（如 framed_journal → 「SCI 投稿 / 审稿人熟悉的严谨风」）[证据: NewWorkflow:23134-24176]
- **版式参数**：`frame∈{open,journal}`、`grid∈{none,y,both}`、`lw∈{thin,mid,thick}`、`font∈{small,medium,large}`、`legend∈{...,noframe}`、`bg∈{white,graytint}`；默认 `{frame:'open',grid:'none',lw:'mid',font:'medium',legend:'noframe',bg:'white'}`

### 7.4 步骤（Skill）中文映射  [证据: ChatWorkbench-B0gSrHl3.pretty.js:6130（常量 `ue` 与 `fe` 重活步骤集合）]

```
comp-prob-analysis   赛题分析            comp-stats-topic     选题与数据规划
comp-modeling        建模求解            comp-code             编程实现
paper-figure         图表生成            nature-figure         Nature 风格图表
paper-figure-html    流程图/架构图        paper-figure-drawio   DrawIO 图
comp-review          逻辑复核            comp-paper-zh         论文撰写（中）
comp-paper-en        论文撰写（英）        comp-paper-zh-docx    Word 论文撰写（中）
comp-paper-en-docx   Word 论文撰写（英）   comp-compile-zh       编译检查（中）
comp-compile-en      编译检查（英）        auto-paper-improvement-loop  论文改进循环
docx-format-check    Word 格式检查        docx-export           导出 Word
format-profile       解析格式要求          docx-template-map     识别 Word 模板
editor-agent         局部改稿            quality-check         质量体检
```

另有"重活"步骤集合 `fe=new Set(['paper-figure','nature-figure','comp-review','comp-paper-*','docx-*','comp-compile-*','docx-export','auto-paper-improvement-loop','paper-compile','paper-compile-zh','dev-selfcheck'])`【同处】。

### 7.5 工作流详情：步骤进度与检查点确认

- **步骤状态色板**[证据: WorkflowDetail:68-82]：`pending 待执行`、`running 执行中`(脉冲点)、`waiting_checkpoint 等待输入`、`completed 已完成`、`failed 失败`、`skipped 跳过`；附加态「准备 Skill」（`recovery_phase==='preparing_content'`）、「等待核验 / 已暂停」（`check_unavailable`/`quality_attention`）
- **进度**：`已完成步数/总步数*100`；`resume_error_code==='ACCOUNT_MODEL_REFUSED' && resume_session_id` 时展示特殊的「继续」流程[证据: WorkflowDetail:14918]
- **检查点类型**【直接提取，`WorkflowDetail:514`,`:31380`,`:15867`】：`approve`（兜底默认值 ``checkpointType: Be.checkpoint_type||`approve` ``）、`idea_select`、`feedback`、`assets_resolve`（共 4 个在 bundle 中可直接读到的取值）
- **检查点弹窗交互**[证据: WorkflowDetail:514,:31380]：
  - 按钮「确认继续」（`idea_select` 时为「自动选择并继续」，有编辑时「保存并继续」）/「提交修改意见」/「停止」/「继续执行并恢复检查点」
  - 文案：`idea_select`「请选择要继续深入的 Idea，或让系统自动选择」；`approve`+大纲「请查看生成的大纲，可以直接编辑后继续」；`approve`「请确认当前步骤的结果，或提供修改意见」；`feedback`「请查看审稿结果，提供修改意见或停止循环」；`assets_resolve`「资产之间检测到不一致, 请选择处理策略后继续」
  - 冲突策略选项 `conflict_resolution_strategy`（默认 `use_user_results`）
  - `allow_feedback===false` 时提示「恢复轮次仅支持确认或停止」
  - 倒计时基于 `/checkpoints/current` 的 `remaining_seconds`（本地 `performance.now()` 插值，1s 刷新）
- **暂停确认弹窗**（一次性，localStorage `mhagent_pause_warning_seen`）：「暂停会立即终止本地进程。但 Anthropic 服务端已发出的 API 请求会继续生成响应（约 1-3 分钟），token 仍会计费——这是 Anthropic API 的原生行为」[证据: WorkflowDetail:442683]

### 7.6 工件库与论文产出

- **分类（8 类）**【直接提取，`ArtifactLibrary:486239` 常量 `Pg`】：`final 最终成果`、`report 分析与报告`、`figure 论文图表`、`result 结果数据与表格`、`section 论文分章节稿`、`input 题目与原始数据`、`technical 代码与计算文件`、`other 其他文件`；每类含 `hint` 与 `beginnerHint`（新手引导）；排序权重 `final>report>figure>input>section>technical>other`
- **文件名 → 中文含义映射**[证据: 同处，常量 Ig]：`problem_statement.md 赛题原文与补充说明`、`problem_analysis.md 赛题分析报告`、`modeling_report.md 建模方案报告`、`modeling_precheck.json 建模预检查结果`、`code_report.md 代码实现报告`、`result_analysis.md 结果分析报告`、`paper_outline.md 论文结构大纲`、`review_report.md 论文审阅报告`、`delivery_report.md 交付检查报告`、`main.pdf 最终论文（PDF）`、`main.docx 最终论文（Word）`、`main.tex 论文主稿（LaTeX）`、`main.md 论文主稿（Markdown）`、`ai工具使用详情.pdf AI 工具使用详情（独立支撑材料）`
- **优先级排序**（`Qg`）：`main.docx 1000 > paper/main.docx 980 > ai工具使用详情.pdf 970 > paper/main.tex 950 > main.pdf 940 > problem_analysis.md 900 > modeling_report.md 880 > result_analysis.md 860 > 分类权重 800/700/600/400/300/200/100`
- **渲染矩阵**【直接提取】：Markdown → `react-markdown`（`prose prose-invert prose-sm`）+ `rehype-katex`；`img` 若指向本地 `.pdf` 则自动降级为 `<iframe>`（`height:70vh`），图片加载失败渲染「🖼️ 图片加载失败」占位；纯文本 → `FileTextPreview`；PDF → `<iframe src="/api/workflows/{id}/artifacts/{path}#page=1&zoom=page-width&navpanes=0">`；HTML → `?preview=html` + `sandbox="allow-same-origin"`；二进制 → `/artifacts/{path}?raw=true` 下载
- **KaTeX 配置**：``rehypePlugins:[[pg,{throwOnError:false,errorColor:'#888888',strict:false,maxExpand:100}]]``[证据: ArtifactLibrary:479962]

### 7.7 聊天工作台（协同模式）

- **交互方式 `interaction_mode`（4 档）**【直接提取，`ChatWorkbench:148842`、`ChatWorkbench:140967` 常量 `on`】：
  - `auto 智能判断（推荐）`「聊天直接回答；需要执行或改文件时先让你确认」
  - `conversation 只聊天`「只讨论和解释，不运行步骤，也不修改文件」
  - `focused 小范围任务`「只处理你指定的部分，不展开整个工作流」
  - `full 完整步骤`「按当前项目阶段完整执行一次，适合正式产出」
- **操作类型 `operation_kind`（6 种）**【直接提取，`ChatWorkbench:11337`、`:52554` 常量 `Ue`】：`run_step 执行流程阶段`、`patch 局部修改`、`focused_run 聚焦执行`、`research 聚焦研究`、`validate 只读检查`、`repair 质量修复`（`Ue` 标签表：「修改指定内容 / 生成指定成果 / 查证与资料整理 / 执行流程阶段 / 检查与修复 / 检查现有结果」）
- **执行范围 `execution_scope`**：`full` | `focused`（focused 时需填「唯一目标」`focus_target`）
- **进度阶段 `progress.phase`**【直接提取，`ChatWorkbench:8615` 常量 `pe`】：`preparing 准备运行环境`、`reading 读取与核对资料`、`reasoning 分析当前任务`、`writing 写入任务产物`、`checking 执行验证与检查`、`completed 任务已完成`、`waiting 等待执行条件`、`failed 任务执行失败`、`cancelled 任务已中断`、`interrupted 任务异常中断`
- **工具动作分类**（`me`）：`read 阅读 / search 检索 / write 生成 / edit 修改 / compute 计算 / coordinate 协作 / reason 分析`（`he` 为 1 字缩写：文/查/写/改/算/合/思）
- **本地返修预算文案**：「内容检查失败时，在同一范围内最多自动返修 3 轮；返修预算 120 分钟。连续无进展、版本冲突或检查工具不可用时停止，不会自动扩大任务」
- **范围免责文案**：「本次仅覆盖确认范围，不代表整阶段或整篇论文已经完成。文件与语法检查不等同于模型正确、数值可靠或可直接提交。」
- **会话/队列/分支**：`/chat/session` 生命周期、`/chat/queue`（含 `promote` 插队）、`/chat/forks`（Fork 卡片选择 `select/defer`，带 `expected_revision` 乐观并发）、`/chat/decisions`（决策记录增删）、消息级 diff / rollback / rollback-preview / validation-proposal
- **草稿与发件箱**：`localStorage['modex.chat.draft.v1:{workflowId}']`（上限 100k 字符）、`localStorage['chat-outbox:v1:{workflowId}']`（`turn_id` 需 `/^[A-Za-z0-9_-]{8,80}$/`，用于断线重发幂等）

### 7.8 LaTeX / 项目编辑器

- **编译与预览**：`POST /api/editor/{id}/compile`（返回 `compile_log`）；`serve` / `serve/status` 起停本地预览服务（`kind` 参数区分）；Word 预览 `docx-status`
- **AI 局部改稿（editor agent）**：版本状态机 `state ∈ {queued,running,checking,exporting,publishing,stopping,completed,needs_attention,failed,interrupted,cancelled,undone,discarded}`；中文标签「排队中/正在处理/正在检查/正在导出/正在发布/正在安全停止/已完成/需要处理/未完成/已中断/已停止/已撤销/草稿已放弃」[证据: LatexEditor:320，ChatWorkbench:22978 同表]
- **撤回幂等**：`localStorage['modex.editor.undo:{editorId}']` 存 `version_id`，两次撤回不一致时报「另一次撤回结果尚未确认，请先重试那次撤回；不会撤回不同版本」[证据: LatexEditor:320]
- **生图幂等**：`localStorage['modex-image-request:{editorId}']` 存 `request_id`，重复发起报「已有待确认的生图请求，请先查询结果」[证据: LatexEditor:11984]
- **Word/LaTeX 工具链**：设置页含 `claude_bin`；`/api/editor/{id}/docx*`、`docx-status`、`drawio-export`、`editorWord.ts`、`editorUpload.ts`；编译步前置校验会提示「仍然现在就跑（编译步可能失败）· 取消：先去设置页安装 LaTeX」[证据: NewWorkflow:66 附近文案]

### 7.9 账号、计费与钱包

- **接入方式 `mode`**：`key`（MHcoding Key / 激活码）| `account`（Modex 账号 + 积分）；`AccessModeProvider` 全局指示器文案「确认接入中 / 接入待确认 / 查看接入方式与费用归属」
- **账户页分区**【直接提取，`Account:20700-25600`】：`MODEX 积分 / 我的积分` 卡片（`native-wallet`）、`充值记录`（orders）、`消费明细列表`（usage，含「调用明细 / 按模型汇总」两个 tab）、`清除本地记录缓存`、`充值说明与退款规则`（`RechargeTerms`）
- **计费契约**：`1 元 = 10 积分`；快捷套餐 `10/50/100/300 元`；`quota_per_point`；显示换算 `quota / quotaPerPoint`；`生图按张计费，不换算为 Token`；`数据时间 as_of`
- **本地读缓存**：`nativeReadCache.ts`（key 形如 `wallet:{scope}` / `usage:{account_id}:{params}`），TTL 300s（`p(n,o,3e5,a)`）；「本地记录缓存已清除，服务端账单和待付款订单不受影响」
- **模型目录**[证据: AccountModelCatalog:59,127]：分类 tab「文本与推理 / 图像生成」（`billing_kind==='image'`）；每行展示 上下文窗口（`context_window` Token）、价格（`native` 时「动态计价」或「{unit_price} 积分 / 张」，`max_reserved` 时「以任务报价为准」，否则「价格配置中，暂不可用」）；`disabled_reason ∈ {QUOTE_EXPIRED, MODEL_PRICE_NOT_CONFIGURED}`；`catalog_source ∈ {native-messages-v2, newapi-direct}`；`billing_source==='newapi'`；`price_version` 为 64 位 hex
- **实名/软件授权**：`NativeRealnameAccess`（掩码字段 `name_masked/idcard_masked/mobile_masked`、`manual_access`、`consent_version`、`simulated` 模拟认证）、`NewApiSoftwareAccess`（`software/consent`）
- **错误码字典**：`utils/accountAccess.ts` 内含 60+ 个错误码 → 中文文案映射（如 `WORKFLOW_PAYER_CHANGED`「这个工作流属于另一接入方式或账户。请切回原账户继续，系统不会自动改用另一套额度。」、`ACCOUNT_QUOTE_EXPIRED`、`ACCOUNT_TLS_FAILED`…）[证据: useAccessMode:108]

### 7.10 平台与合规

- **免责/版权门禁**：首启全屏弹窗，`localStorage['mhagent_disclaimer_accepted']`；文案含「AI 生成的内容可能存在错误…用户应对最终提交的论文内容负全部责任」「用户应遵守所在学校和竞赛组委会的学术诚信规定」；页脚「Modex-MH-Agent v2.1.2 | 仅供学习交流使用」
- **接入方式运行时提示**（`Ke` 组件）：`/account` 与 `/account/history` 之外，或 `mode==='key'`，或 `mode==='account' && inference_enabled` 时不显示；否则显示「接入方式尚未确认，模型调用暂不可用。」
- **更新通知**：`window.electronAPI.updater.onUpdateAvailable/onUpdateProgress` + `checkNow/startDownload/applyAndRestart/abort/skipVersion/getCached`（`components/UpdateNotifier.tsx`）
- **模型强度 `effort`**（`types/effort.ts`）：`low/medium/high/xhigh/max`；文案「low · 最省，简单任务 / medium · 平衡 / high · 默认，复杂推理 / xhigh · 长周期编码/建模 / max · 最高能力，最贵」；`xhigh` 对不支持模型（`opus-4-6/4.6/4-5/4.5/sonnet-4-6/4.6`）降级为 high 并提示[证据: effort-BoZu8WGp.pretty.js:1-13]

---

## 8. 复现要点与红线（红方视角）

1. **必须实现的后端端点：报告内端点表共 158 行，去重后约 142 条唯一路径**（含同路径的多种方法）。全部为**同源相对路径**，前缀 `/api`（编辑器为 `/api/editor`，WS 为 `/ws/{workflow_id}`）。前端**不做鉴权头**（除 `X-Modex-Mode-Read: identity`），依赖本地回环 + Electron 侧端口白名单 `http://127.0.0.1:{port}/*`、`ws://127.0.0.1:{port}/*`。
2. **错误契约**：`{detail: string | {message, code}}`；账号域额外有 `code` + `retry_after_seconds`/`Retry-After`（前端据此做错误码→文案映射）。检查点 resolve 必须回 `{status:'resolved'}`，`/checkpoints/current` 必须回 `remaining_seconds`，否则前端判定"后端版本不匹配"。
3. **乐观并发**：提案编辑/检查点 resolve/分支选择均带 `revision`/`expected_revision`/`checkpoint_id`；前端在修订号不匹配时拒绝写入并重新同步（`proposal_revision`、`state_revision`）。
4. **幂等键**：聊天用客户端生成的 `turn_id`（写入 outbox 供重发）、生图用 `request_id`、撤回用 `version_id` —— 复现时这些字段是去重/恢复的关键。
5. **前端白名单会拦截非法路径**（`无效的本地账号接口。`），因此扩展端点需同时改前端封装；反之，若目标是"伪造后端"，必须原样实现白名单内的所有路径，否则账号面板会直接报错。
6. **两条实时通道都要实现**：WebSocket `/ws/{workflow_id}`（工作流 + 聊天）**和** 编辑器 Agent 的 SSE（`POST /api/editor/{id}/ai-agent` + `X-Editor-Run-Id` 响应头 + `data:` 分帧 + `progress/log/heartbeat/result`）。缺任一都会导致对应页面功能不可用。
7. **本地资源依赖**：`/palette_preview/{name}.png`、`/style_preview/{name}.png`、`/logo.svg`、`/favicon.svg`、`/support-wechat.png` 以及 KaTeX 字体（`KaTeX_*.woff2/woff/ttf`，共 60 个文件）需随静态托管提供；Electron 侧另有 `katex-assets/auto-render.min.js` + `katex.min.js` + `katex.embedded.css` 供主进程使用。

---

## 9. 方法与局限

**做了什么**：对 27 个 `.js` bundle（合计约 2.6 MB minified）做 tokenizer 级美化（`tools\beautify.js`，正确处理字符串/模板/正则/注释），再以「括号感知字符串提取」获得 220 条路径字面量、172 条调用点（含 HTTP method 上下文），并对关键 chunk 定点阅读获取 store/事件/常量表。

**未能确定的项（不臆造）**：

- **Vite / zustand / react-markdown / react-router 的精确版本号**：bundle 未内嵌 `package.json` 版本；仅 React(19.2.4)、Tailwind(4.2.2)、KaTeX(0.16.42) 有字面量版本。
- **`routers/ws.py` 之外的后端事件字面量表**：`.pyd` 的 strings dump 以符号名为主，未包含 Cython 内联的字符串常量；本文 WS 事件表以前端消费端为准（这是最可靠的来源）。
- **`utils/` 中若干工具的精确行为**（如 `mathPromptLibrary.ts` 的配方全集、`unifiedDiff.ts` 的 diff 算法细节、`workflowCreation.ts` 的默认参数合并顺序）未逐行展开；仅在需要处（参数名、字段名）取了证据。
- **未验证运行时行为**：本报告为纯静态分析，所有"效果/状态流转"结论均来自代码路径推断，未实际运行应用验证。

**工作区产物**（分析脚手架，非交付物；`reports\` 下只有本文件为本次交付）：

```
E:\02_Installers\DailyApps\Modex-MH-Agent-RE\tools\           # beautify.js / fx2.js / fx3.js / callsites3.js / probe*.js / home-map.js / literals.js / exturls.js / count-te.js
E:\02_Installers\DailyApps\Modex-MH-Agent-RE\tools\_fx\       # apis.tsv / path-normalized.tsv / endpoint-map3.tsv / callsites3.txt / probe*.txt / homes.tsv / literals.txt / external-urls.txt
E:\02_Installers\DailyApps\Modex-MH-Agent-RE\beauty\          # 27 个 *.pretty.js（美化后可读产物，可复现全部结论）
```
