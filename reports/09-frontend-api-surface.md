# 前端 bundle 提取的 API 面（确定性脚本产出）

来源：`resources/app/dist/assets/*.js`（Vite minified，无 sourcemap）。

> **为什么用前端而不是后端**：编译后的后端在 import 期即触发守卫
> （`RuntimeInspectionUnavailable: 完整性验证或运行时约束未通过，未执行任何能力`），
> 带外导入被拒绝；且 FastAPI 路由字面量未被 Cython 保留为可检索常量。
> 前端必须调用每一个端点，因此它是当前最可靠的路由来源。

## A. 后端 API 路径（92 条）

| 资源域 | 条数 | 路径 |
|---|---|---|
| `account` | 22 | `/api/account/${e}`<br>`/api/account/access-mode`<br>`/api/account/activate`<br>`/api/account/identity`<br>`/api/account/identity/withdraw`<br>`/api/account/inference`<br>`/api/account/inference/operations`<br>`/api/account/licenses/${e.id}/unbind`<br>`/api/account/licenses/claim`<br>`/api/account/logout-all`<br>`/api/account/messages`<br>`/api/account/messages/capabilities`<br>`/api/account/messages/operations`<br>`/api/account/models`<br>`/api/account/native/`<br>`/api/account/native/image-settings`<br>…（共 22） |
| `client-config` | 2 | `/api/client-config`<br>`/api/client-config/refresh` |
| `editor` | 7 | `/api/editor`<br>`/api/editor/${encodeURIComponent(e)}`<br>`/api/editor/${encodeURIComponent(e)}/ai-agent-history`<br>`/api/editor/${encodeURIComponent(e)}/ai-agent-version/${t}`<br>`/api/editor/${encodeURIComponent(e)}/generate-image`<br>`/api/editor/${encodeURIComponent(e)}/image-requests/${encodeURIComponent(t)}`<br>`/api/editor/${encodeURIComponent(e)}/model-options` |
| `license` | 2 | `/api/license/`<br>`/api/license/verify` |
| `settings` | 8 | `/api/settings`<br>`/api/settings/data-dir`<br>`/api/settings/detect-claude`<br>`/api/settings/models/discover`<br>`/api/settings/presets`<br>`/api/settings/presets/${R.id}`<br>`/api/settings/presets/${e.id}`<br>`/api/settings/test/${e}` |
| `templates` | 1 | `/api/templates/${encodeURIComponent(t)}/resolve-steps` |
| `workflows` | 50 | `/api/workflows/${a}/chat/forks/${n}/choose`<br>`/api/workflows/${a}/chat/messages/${r}/confirm`<br>`/api/workflows/${e[0]}/export`<br>`/api/workflows/${encodeURIComponent(e)}/artifact-context/inspect/${r}`<br>`/api/workflows/${encodeURIComponent(e)}/artifact-context/prompt/build`<br>`/api/workflows/${encodeURIComponent(e)}/artifacts`<br>`/api/workflows/${encodeURIComponent(e)}/artifacts/${r}`<br>`/api/workflows/${encodeURIComponent(e)}/artifacts/${t.split(`<br>`/api/workflows/${encodeURIComponent(e)}/artifacts/upload`<br>`/api/workflows/${encodeURIComponent(e)}/chat`<br>`/api/workflows/${encodeURIComponent(e)}/chat/materials`<br>`/api/workflows/${encodeURIComponent(e)}/chat/stages/${encodeURIComponent(t.skill)}/accept`<br>`/api/workflows/${encodeURIComponent(t)}/artifacts`<br>`/api/workflows/${encodeURIComponent(y)}/artifacts/${e.split(`<br>`/api/workflows/${e}/artifacts`<br>`/api/workflows/${e}/artifacts/${encodeURIComponent(r)}`<br>…（共 50） |

## B. WebSocket / 实时通道（0 条）


## C. 前端路由路径（0 条，React Router 线索）


## D. 外部端点（9 条）

- `https://bill.mingheng.xin`
- `https://embed.diagrams.net/?embed=1&proto=json&spin=1&libraries=1&noExitBtn=1&saveAndExit=0`
- `https://github.com/syntax-tree/hast-util-to-jsx-runtime`
- `https://license.mingheng.xin/privacy`
- `https://openapi.alipay.com`
- `https://react.dev/errors/`
- `https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html`
- `https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html`
- `https://www.mingheng.xin/`

## E. 各 chunk 的 API 调用密度

| chunk | API 路径数 |
|---|---|
| `WorkflowDetail-bN89YgNS.js` | 18 |
| `useWebSocket-DhwRyw4C.js` | 17 |
| `index-BeImsYqE.js` | 16 |
| `NewWorkflow-Ld6TEJjT.js` | 8 |
| `Settings-D4EW1h0L.js` | 8 |
| `LatexEditor-I1nsgpA4.js` | 7 |
| `ChatWorkbench-B0gSrHl3.js` | 6 |
| `useAccessMode-CYwsqbbI.js` | 5 |
| `ArtifactViewer-DS3mPR9-.js` | 4 |
| `Dashboard-2mxANXyi.js` | 3 |
| `Account-CFNFyFpM.js` | 2 |
| `AccountHistory-DV1tVxrt.js` | 1 |
| `AccountMessagesInference-C-hk-by7.js` | 1 |
| `AccountModelCatalog-DdzyHjab.js` | 1 |
| `PatchReviewDialog-CE7kb4Sp.js` | 1 |
| `modelDiscovery-BRyakWgC.js` | 1 |
| `newApiWallet-BJVw6ude.js` | 1 |

