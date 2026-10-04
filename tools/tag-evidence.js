// Add explicit [证据: ...] tags to load-bearing headings + insert a legend. Deterministic, exact-match only.
const fs = require('fs');
const P = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/03-frontend.md';
let s = fs.readFileSync(P, 'utf8');
const before = s;

const HEAD = [
  ['### 1.1 明确排除的项', '### 1.1 明确排除的项  [证据: 全 27 个 assets\\*.js 的字面量扫描 + index.html/build-info.json]'],
  ['### 2.1 路由定义（【直接提取】，`index-BeImsYqE.pretty.js:8881` 与 `L9014-L9042`）',
   '### 2.1 路由定义  [证据: index-BeImsYqE.pretty.js:8881（懒加载映射）, :9014-9042（<Route path> 表）, :9005（布局正则）]'],
  ['### 3.3 chunk ↔ 源模块映射（【直接提取】：以「唯一特征字符串只出现在某 chunk」判定）',
   '### 3.3 chunk ↔ 源模块映射  [证据: 全 chunk 字面量唯一性矩阵，见 tools\\_fx\\homes.tsv]'],
  ['### 4.0 请求封装契约（复现时必须对齐）',
   '### 4.0 请求封装契约（复现时必须对齐）  [证据: useAccessMode-CYwsqbbI.pretty.js:114, chatRequest-LRac2JB5.pretty.js:1, ChatWorkbench-B0gSrHl3.pretty.js:988, Account-CFNFyFpM.pretty.js:401, newApiWallet-BJVw6ude.pretty.js:40, workflowStore-DtYgz0OF.pretty.js:37]'],
  ['### 4.1 端点全清单', '### 4.1 端点全清单  [证据: tools\\_fx\\endpoint-map3.tsv（172 条调用点，含 HTTP method 与 body 类型）与 tools\\_fx\\path-normalized.tsv（171 条路径字面量）]'],
  ['### 4.2 外部端点与出站 URL（`node` 全量扫描 21 条，去命名空间后如下）',
   '### 4.2 外部端点与出站 URL  [证据: tools\\_fx\\external-urls.txt（node 全量扫描 21 条，去 W3C/XML 命名空间后为下表）]'],
  ['### 5.1 连接与心跳（【直接提取】`useWebSocket-DhwRyw4C.pretty.js:901-1015`）',
   '### 5.1 连接与心跳  [证据: useWebSocket-DhwRyw4C.pretty.js:901-1015（重连/心跳/唤醒）, :984（WS URL）]'],
  ['### 5.2 消息信封与分发（【直接提取】`useWebSocket:996-1004`）',
   '### 5.2 消息信封与分发  [证据: useWebSocket-DhwRyw4C.pretty.js:996-1004]'],
  ['### 5.3 工作流事件（consumed by `workflowStore.handleWsEvent`，【直接提取】`workflowStore:323-452`）',
   '### 5.3 工作流事件  [证据: workflowStore-DtYgz0OF.pretty.js:323-452（handleWsEvent 全分支）]'],
  ['### 5.4 聊天事件（consumed by `chatStore.handleChatEvent`，【直接提取】`useWebSocket:746-870`）',
   '### 5.4 聊天事件  [证据: useWebSocket-DhwRyw4C.pretty.js:746-870（handleChatEvent 全分支）]'],
  ['### 5.5 编辑器 Agent 的 SSE 事件流（**非 WebSocket，独立的第二套实时通道**）',
   '### 5.5 编辑器 Agent 的 SSE 事件流（非 WebSocket，独立的第二套实时通道）  [证据: LatexEditor-I1nsgpA4.pretty.js:93-116（le）, :164-203（ge 解析器）, :2082-2090（事件类型）, :62-63（合并规则）]'],
  ['### 6.1 `stores/workflowStore.ts`（chunk `workflowStore-DtYgz0OF.js`，导出 `p as t`，hook 名 `useWorkflowStore`）',
   '### 6.1 `stores/workflowStore.ts`  [证据: workflowStore-DtYgz0OF.js（导出 `p as t`）, :37-39（state）, :39-452（28 个 action）]'],
  ['### 6.2 `stores/chatStore.ts`（chunk `useWebSocket-DhwRyw4C.js`，导出 `K as r`，hook 名 `useChatStore`）',
   '### 6.2 `stores/chatStore.ts`  [证据: useWebSocket-DhwRyw4C.js（导出 `K as r`）, :146-160（state）, :160-899（28 个 action）]'],
  ['### 6.3 React Context（非 store 的全局态）',
   '### 6.3 React Context（非 store 的全局态）  [证据: index-BeImsYqE.pretty.js:232701（Theme）, useAccessMode-CYwsqbbI.pretty.js:272-316（AccessMode）, index:246079（ClientConfig）]'],
  ['### 7.1 赛题模板目录（`pages/NewWorkflow.tsx`，常量 `Te`，【直接提取】`NewWorkflow-Ld6TEJjT.pretty.js:45387` 起）',
   '### 7.1 赛题模板目录  [证据: NewWorkflow-Ld6TEJjT.pretty.js:45387 起（常量 `Te`）；条目数由 node 计数 `value:`comp_*`` = 22]'],
  ['### 7.4 步骤（Skill）中文映射（【直接提取】`ChatWorkbench-B0gSrHl3.pretty.js:6130` 常量 `ue`）',
   '### 7.4 步骤（Skill）中文映射  [证据: ChatWorkbench-B0gSrHl3.pretty.js:6130（常量 `ue` 与 `fe` 重活步骤集合）]'],
];

let applied = 0, missed = [];
for (const [from, to] of HEAD) {
  if (s.includes(from)) { s = s.replace(from, to); applied++; }
  else missed.push(from);
}

// legend right after the 标注约定 bullet
const legendAnchor = '- **标注约定**：';
const legend = '- **证据格式**：所有结论均以 `[证据: <chunk 文件名>:<行号>（命中原文）]` 或表内「判定依据/关键字段」列给出 chunk 文件名与命中的原始字符串；行号对应 `beauty\\*.pretty.js`（美化产物，与 `dist\\assets\\*.js` 一一对应）。置信度三档：`【直接提取】`（bundle 原文可直接读到）、`【推断】`（给依据）、`【推测】`。\n';
if (!s.includes('**证据格式**：')) {
  const i = s.indexOf(legendAnchor);
  const j = s.indexOf('\n', i);
  s = s.slice(0, j + 1) + legend + s.slice(j + 1);
}

fs.writeFileSync(P, s, 'utf8');
console.log('headings tagged:', applied, '/', HEAD.length);
if (missed.length) console.log('MISSED:\n' + missed.join('\n'));
console.log('legend inserted:', s.includes('**证据格式**：'));
console.log('bytes', before.length, '->', s.length);
