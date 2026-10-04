# Modex-MH-Agent 桌面主进程与安全防护体系 —— 逆向工程分析报告

> 目标：`Modex-MH-Agent` v2.1.2（Electron + 内嵌 Python 后端）桌面端主进程、preload 暴露面、
> 自动更新、运行时完整性校验、Electron 加固，以及红队视角下的可利用性与影响面评估。
> 分析方式：**纯静态分析**。未修改任何目标文件，未实施任何攻击，未运行目标程序。

> **文档结构**：正文 §0–§7 + 附录 A–D 为第一轮分析；**附录 E–G 为 2026-10-02 的第二次独立复核补充**
> （新增：主 EXE 无 Authenticode 签名且本机对非提权用户可写 → 信任链可整体替换；
> CSP 不可静态提取的原因定位为 Cython 字符串压缩；供应链 547/147 统计；`modemon` 借鉴清单）。
> 附录 E–G **不覆盖、不修改**前文结论，仅做补充与证据升级。

---

## 0. 分析基线与证据来源

### 0.1 受检标的

| 项 | 值 | 证据 |
|---|---|---|
| 产品名 | `modex-mh-agent`，显示名 `Modex-MH-Agent`，作者「明珩科技」 | [证据: `asar/package.json:2-7`] |
| 版本 | `2.1.2` | [证据: `asar/package.json:3`] |
| 安装根 | `E:\02_Installers\DailyApps\Modex-MH-Agent\` | [证据: 目录枚举] |
| 主程序 | `Modex-MH-Agent.exe` 188,753,408 字节 | [证据: 目录枚举] |
| 代码容器 1 | `resources/app.asar` 889,727 字节（Electron 主进程代码） | [证据: 目录枚举 + 清单 `runtime_files`] |
| 代码容器 2 | `resources/app/` 实体目录（后端 .pyd / 前端 dist / tools / 3 个 security 模块 / `update-helper.js`） | [证据: 目录枚举] |

### 0.2 关键结构性发现（贯穿全文）

**本产品的应用程序被拆成两个互相独立、信任根不同的代码容器：**

1. **`resources/app.asar`** —— 装着 `main.js` / `preload.js` / `updater.js` / `capture.js` /
   `security/` 全部 18 个模块 / `katex-assets` / `icon.ico` / `package.json` / `updater-config.json`。
   它由 **Electron 自身的 ASAR 完整性机制**保护（见 5.1 的 fuse #4/#5），
   并在签名清单里作为**单个文件** `resources/app.asar`（sha256 已锁）被校验。
   [证据: `asar/` 目录枚举；`runtime-integrity-manifest.json` 的 `runtime_files` 含 `resources/app.asar`]
2. **`resources/app/`** —— 只有 6 项：`backend/`、`dist/`、`security/`、`templates/`、`tools/`、
   `update-helper.js`。它由**自研 Ed25519 签名清单**逐文件保护（1498 条）。
   [证据: `E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app` 目录枚举]

`resources/app/security/` 下**只有 3 个模块**：`release-trust.js`、`update-security.js`、
`update-transaction.js`（外加 manifest 与 sig 两个文件）。
其余 15 个 security 模块只存在于 asar 内。
[证据: `resources/app/security` 目录枚举]

### 0.3 证据链闭合性验证（本次实测）

以下结论均为本次**实机核算**结果，非推测：

| 检查项 | 结果 | 命令/脚本 |
|---|---|---|
| 磁盘文件数 vs 清单条数 | 磁盘 1498 / 清单 1498，**缺失 0，多余 0** | `reports/_fx/verify-install-tree.js` |
| 逐文件 sha256 复算 | 1498 个文件全部 **MATCH**，不一致 0 | 同上 |
| `runtime_files`（关键运行时闭包）存在性+尺寸 | 27,752 / 27,752 全部一致，异常 0 | 同上 |
| 13 个 `CRITICAL_RUNTIME_FILES` 逐一哈希 | 全部 **MATCH**（含 `app.asar`、`python.exe`、`libcrypto-3.dll`、`_ssl.pyd`、`claude.exe`、`pandoc.exe`） | 同上 |
| Ed25519 签名独立验签 | **true**（用 `release-trust.js` 内固化的公钥 + `canonicalJson` 复算） | `node -e ...crypto.verify` |
| Electron fuse 线（从 exe 内读出） | `version=1 length=8 wire=01001101`，与代码内 `EXPECTED_FUSE_WIRE_V1` 一致 | `reports/_fx/read-fuses.js` |

**签名验签原文（本机 Node v24.20.0 复算）**：

```
key type: ed25519
canonical bytes: 5001244
signature verifies: true
```

[证据: 本次执行 `crypto.verify(null, canonicalJson(manifest), pubkey, sig)` 返回 `true`；
公钥取自 `asar/security/release-trust.js:9`；签名取自
`resources/app/security/runtime-integrity-manifest.sig.json:4`]

### 0.4 签名清单规模统计（脚本统计，未整篇读入）

统计脚本：`reports/_fx/manifest-stats.js`，输出：`reports/_fx/manifest-stats.txt`（2.23 MB）。

**顶层元数据** [证据: `resources/app/security/runtime-integrity-manifest.json` 由脚本解析]

| 字段 | 值 |
|---|---|
| 原始大小 | 5,995,780 字节（5.72 MB） |
| `schema_version` | `2` |
| `key_id` | `intl-update-2026-08-a` |
| `channel` | `intl` |
| `version` | `2.1.2` |
| `generated_at` | `2026-09-25T05:33:35.075Z` |
| `files` 条数 / 总字节 | **1498** / 50,634,523 B（48.3 MB） |
| `runtime_files` 条数 / 总字节 | **27,752** / 4,482,380,831 B（**4274.7 MB**） |

**`files`（`resources/app` 树）目录分布**

| 顶层目录 | 文件数 | 字节 |
|---|---|---|
| `tools/` | 1164 | 11.33 MB |
| `backend/` | 186 | 29.07 MB |
| `dist/` | 135 | 7.84 MB |
| `templates/` | 9 | 0.01 MB |
| `security/` | 3 | 0.02 MB |
| `(根)` | 1（`update-helper.js`） | 0.004 MB |

**`files` 扩展名分布（前 6）**：`.ts` 637 / `.js` 335 / `.pyd` 157 / `.md` 60 / `.pyc` 52 / `.json` 51
[证据: `reports/_fx/manifest-stats.txt` "files by extension"]

**`runtime_files`（关键运行时闭包）分布**

| 顶层 | 文件数 | 字节 |
|---|---|---|
| `runtime/` | 27751 | 4273.88 MB |
| `resources/` | 1（`app.asar`） | 0.85 MB |

扩展名：`.py` 26678（380 MB）、`.pyd` 762（847 MB）、`.dll` 196（2241 MB）、
`.exe` 107（786 MB）、`.zip` 3、`.so` 2、`.asar` 1、`._pth` 1、`.pth` 1、`.whl` 1。
[证据: `reports/_fx/manifest-stats.txt` "runtime_files by extension"]

**结论**：`runtime_files` 中 **96% 是 `runtime/python/Lib/site-packages/**` 下的 `.py` 文件**，
即「关键运行时闭包」实际覆盖的是整个 Python 标准库 + site-packages 树，而非仅 13 个关键文件。
这一点直接决定了第 4 节与第 6 节的启动开销与缺口评估。

### 0.5 标注约定

- `【直接提取】`：源码/文件/脚本输出中可直接读到的字面事实。
- `【推断】`：由多个直接提取事实按确定性逻辑推得，逻辑链在文中给出。
- `【推测】`：证据不足，仅为可能性判断，明确标注不确定性。
- 所有结论附 `[证据: 文件:行号]` 或原文引用。行号基于本报告使用的解包副本
  （`Modex-MH-Agent-RE\asar\*` 与安装目录 `resources\app\*`）。

---

## 1. 启动全链路

### 1.1 总览时序

```
Modex-MH-Agent.exe 进程启动
  │
  ├─[P0] 禁用的启动开关检查          main.js:23-31   （app.isPackaged 才执行）
  │
  ├─[P1] --mh-capture 截图模式分流    main.js:40-43   （命中即 return，跳过 P2..P9）
  │
  ├─[P2] 隔离开发实例配置             main.js:45-52   （dev-isolation）
  │
  ├─[P3] 单实例锁                     main.js:54-58   （requestSingleInstanceLock）
  │
  ├─[P4] 用户存储初始化 / 全新安装     main.js:78-89   （fresh-start + user-storage）
  │      └ 失败 → 挂起为 storageStartupError，延后到 ready 后交互式恢复
  │
  ├─[P5] app.on('ready')              main.js:1123-1134
  │      └ 启动状态窗 StartupStatus.show()（data: URL + 严格 CSP）
  │
  └─[P6] openApplication()            main.js:999-1121
         ├─ 6.1 建托盘                                   :1000
         ├─ 6.2 等残留更新 helper 退出 + 事务回滚         :1003-1014
         ├─ 6.3 签名清单完整性校验（app 树 + 运行时闭包）:1016-1027
         ├─ 6.4 关键运行时文件存在性/尺寸自检             :1029-1036
         ├─ 6.5 Python 解释器注入自检                     :1038-1044
         ├─ 6.6 资料位置校验 / 交互式恢复                 :1046-1066
         ├─ 6.7 MiKTeX 非阻塞探测                         :1068-1076
         ├─ 6.8 生成后端控制令牌                          :1084
         ├─ 6.9 签名更新配置校验 + 检查更新               :1086-1096
         ├─ 6.10 清理历史泄露源码残留                     :1098-1103
         ├─ 6.11 选端口 + spawn Python 后端               :1105-1108
         ├─ 6.12 健康检查（带 OS 归属核验）               :1109
         └─ 6.13 建主窗口并加载前端                       :1113
```

### 1.2 P0 禁用启动开关（生产模式）

【直接提取】打包产物启动时，第一个动作就是拒绝调试/注入类开关：

```js
// main.js:23-31
if (app.isPackaged) {
  try {
    require('./security/electron-launch-policy').enforceProductionLaunchPolicy(app.commandLine, process.argv);
  } catch (error) {
    console.error(`[Security] ${error.message}`);
    app.exit(78);
    return;
  }
}
```

`FORBIDDEN_PRODUCTION_SWITCHES` 共 22 项，含 `remote-debugging-port`、`remote-debugging-pipe`、
`load-extension`、`browser-subprocess-path`、`renderer-cmd-prefix`、`js-flags`、`inspect*`、
`disable-web-security`、`allow-file-access-from-files`、`ignore-certificate-errors`、`no-sandbox`、
`disable-gpu-sandbox` 等。[证据: `asar/security/electron-launch-policy.js:7-28`]

匹配只用 `process.argv`，**刻意不用** `commandLine.hasSwitch()`：

```js
// electron-launch-policy.js:41-44
// Only argv identifies caller-supplied switches. commandLine.hasSwitch()
// also exposes switches Electron/Chromium inserted internally and caused a
// false positive on an otherwise clean packaged launch.
return FORBIDDEN_PRODUCTION_SWITCHES.filter(name => argvNames.has(name));
```

命中后先 `commandLine.removeSwitch(name)` 再抛错，`app.exit(78)` 是 fail-closed 退出码。
[证据: `asar/security/electron-launch-policy.js:47-54`；`asar/main.js:28`]

### 1.3 P1 `--mh-capture` 截图模式（高危旁路，详见 6.3）

```js
// main.js:33-43（原文注释）
// ⛔⛔ 截图模式分流（必须在最前，early return）
// 后端会以子进程调用本 exe: `主程序.exe --mh-capture <config.json>` 来给网页截图。
// 检测到该参数时，只跑截图逻辑(capture.js)然后退出，绝不启动正常应用
// (不加载 updater / 不校验 license / 不起后端 / 不建主窗口 / 不建托盘)。
if (process.argv.includes('--mh-capture')) {
  require('./capture').runCaptureMode();
  return;
}
```

该分支在 `dev-isolation`、单实例锁、全部完整性校验**之前**执行并 `return`。
[证据: `asar/main.js:40-43`]。截图窗口参数见 5.4。

### 1.4 P2 隔离开发实例

【直接提取】`configureIsolatedDev(app, __dirname)` 仅在 argv 出现
`--modex-isolated-dev-root=` 或 `--modex-isolated-dev-resume-root=` 时激活；
无参数时会**主动删除**三个可能残留的环境变量：

```js
// dev-isolation.js:162-167
const argumentsFound = argv.filter(arg => arg.startsWith('--modex-isolated-dev'));
if (!argumentsFound.length) {
  for (const key of KEYS) delete env[key];
  return null;
}
```
`KEYS = ['MODEX_DEV_ISOLATED','MODEX_DEV_PROFILE_ROOT','MODEX_DEV_FRONTEND_DIST']`
[证据: `asar/security/dev-isolation.js:9`]

打包版**拒绝**该参数：`if (app.isPackaged) throw new Error('正式安装版不接受隔离开发参数');`
[证据: `asar/security/dev-isolation.js:168`]

初始化失败 → 弹框 + `app.exit(78)`。[证据: `asar/main.js:48-51`]

### 1.5 P3 单实例锁

```js
// main.js:54-58
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) { app.quit(); return; }
```

第二实例被唤醒时只做两件事：把已有窗口带到前台 + 处理「全新安装 token 尚未启用」提示。
[证据: `asar/main.js:288-299`]

【直接提取】**单实例锁不足以做互斥**，这一点在 Python 侧的 `instance_guard` 里被明确记录：

> 「单实例锁只挡同一个 appId，国内版 + 国际版是两个 appId，而它们默认共用
> `%APPDATA%\MHAgent` 这同一个数据目录，所以这个竞态是真会发生的。」
> 「只会静默地把结果搅乱。必须在进程层面互斥。」
> [证据: `reports/cjk-strings-from-pyd.md:773,776`（`instance_guard.cp311-win_amd64.pyd` 段落）]

### 1.6 P4 用户存储初始化与全新安装

#### 1.6.1 全新安装 token（`fresh-start.js`）

- 参数格式：`--fresh-install=<uuid-v4>`，**只接受一个小写 hex UUID**，重复出现直接报错。
  [证据: `asar/security/fresh-start.js:7-16`]
- 幂等凭据：`%APPDATA%\MHAgent\fresh-install-receipts\<token>.json`，两阶段
  `prepared → complete`。[证据: `asar/security/fresh-start.js:24-25,53-65`]
- **所有权约束**：新资料目录必须位于 `%APPDATA%\ModexData` 之下（用 `isInside` 校验），
  且不能等于该基目录本身。[证据: `asar/security/fresh-start.js:58-61`]
- **CAS 写入**：`replacePointer` 比较「预期指针原字节」，不一致即拒绝覆盖，并用
  `fsync` + 同目录 `rename` 原子替换。[证据: `asar/security/user-storage.js:42-63`]
- 中断恢复：若 receipt 处于 `prepared`，会用 `previous_pointer_sha256` 或
  `fresh_install_id` 双重确认没有被别的操作改过，否则拒绝。
  [证据: `asar/security/fresh-start.js:42-48`]

#### 1.6.2 数据目录解析（`user-storage.js`）

`configureUserStorage(app, installDir)` 的顺序：
[证据: `asar/security/user-storage.js:111-148`]

1. `defaultDir = %APPDATA%\MHAgent`（:112）
2. `repairUnusedRoot(defaultDir, installDir)`：仅当指针指向**盘符根**、盘符根存在、
   不在安装目录内、且根目录和 defaultDir **都没有历史标记**
   （`db` / `workspaces` / `claude-workflow-sessions-v1` / `security`）时，
   才创建 `ModexData` 并改写指针。（:72-88, :65-70）
3. `resolveDataDirectory`：三条硬拒绝
   - 资料位于程序安装目录内 → 抛错（:94-96）
   - 资料位置是磁盘根且未确认为完整原库 → 抛错（:101-103）
   - 指针存在但目录不存在/不是目录 → 抛错，并明示「不会在 C 盘另建空库」（:105-107）
   - 完整原库判定 = `db/aris.db` 是文件且 16 字节头等于 `SQLite format 3\0`，
     `workspaces` 是目录，且两者 canonical 后都落在目录内。（:29-40）
4. 目录布局与 `app.setPath`：`sessionData=desktopRoot/desktop-profile`、`temp`、`logs`、
   `crashDumps`；旧 profile 的 `Local Storage / Session Storage / IndexedDB /
   Preferences / Cookies / Network` 按需复制，若指针里 `profile_policy === 'fresh'` 则**不导入**。
   （:118-140）
5. 环境变量重定向：`TEMP/TMP/TMPDIR`、`XDG_CACHE_HOME`、`MPLCONFIGDIR`、`PIP_CACHE_DIR`、
   `npm_config_cache`、`HF_HOME`、`TORCH_HOME`。（:141-146）

**注意**：`app.setPath('sessionData', ...)` 必须在 `ready` 之前完成，所以 P4 放在
`app.on('ready')` 之外；失败时错误被挂起、延后到 ready 后走交互式恢复（见 1.11）。
[证据: `asar/main.js:84-88`；`asar/security/user-storage.js:124-128` 注释]

### 1.7 6.2 更新事务恢复（先于一切代码加载）

```js
// main.js:1003-1014
// 上次更新若在断电/进程崩溃时停在提交中，必须先从完整备份恢复，再加载后端。
const installDir = path.dirname(process.resourcesPath);
await waitForActiveUpdateHelper(installDir);
const recovery = await recoverInterruptedUpdate(installDir, path.join(installDir, '.app.bak'));
```
- `waitForActiveUpdateHelper`（:972-995）：读 `<installDir>\.app.update.lock` 的 `{pid, started_at}`；
  - pid 不合法 / 进程已死 / `started_at` 超过 10 分钟 → 直接删锁继续；
  - 否则最多等 60 秒，仍存活则抛「安全更新仍在提交，请稍后重新启动程序」→ 走 `failStartup`。
- `recoverInterruptedUpdate`（`update-transaction.js:143-170`）：journal 状态必须是
  `backup_complete` 才回滚；对每个 entry 重新做 `resolveWithin` 边界校验后按逆序还原，
  写回 `status: 'recovered_on_startup'`。

### 1.8 6.3 签名清单完整性校验

```js
// main.js:116-122
return await verifyRuntimeTree(
  APP_ROOT, manifest, signature, PINNED_UPDATE_PUBLIC_KEYS,
  { channel: cfg.channel, version: currentVersion,
    installRoot: path.dirname(process.resourcesPath), requireRuntimeClosure: true },
);
```
`APP_ROOT = <installRoot>\resources\app`（:91），`installRoot` 为 `process.resourcesPath` 的父目录。
校验前先做文件尺寸门禁：清单与签名必须是 32 B ~ 32 MiB 的普通文件。
[证据: `asar/main.js:107-112`]

失败后果：`failStartup('程序文件不完整或校验未通过', ...)`，**不 spawn 后端、不建主窗口**。
[证据: `asar/main.js:1023-1027`]

详细机制见第 4 节。

### 1.9 6.4 / 6.5 关键运行时自检与解释器注入自检

**6.4 `verifyRuntime()`** —— 只做「存在性 + 尺寸窗口」，属可用性保护而非密码学校验：
[证据: `asar/main.js:132-159`]

| 文件 | 最小 | 最大 |
|---|---|---|
| `runtime\python\python.exe` | 50 KiB | 500 KiB |
| `runtime\python\python311.dll` | 1 MiB | — |
| `runtime\python\python311.zip` | 1 MiB | — |
| `runtime\node\node.exe` | 10 MiB | — |

失败弹窗的文案专门针对「杀软误报隔离」，并**明确劝阻用户关闭防护或加排除项**。
[证据: `asar/main.js:165-190`]

**6.5 `detectPythonInjection()`** —— fail-closed 拒绝 `sitecustomize.py` / `usercustomize.py`：

```js
// main.js:204-222（原文注释节选）
// 内嵌 Python 打包时启用了 site 机制（build.ps1 反注释 ._pth 的 import site）。
// 这意味着 site-packages 里若出现 sitecustomize.py / usercustomize.py，解释器会在
// 后端任何 .pyd（skill_crypto / license_guard 等）import 之前自动执行它 —— 攻击者
// 借此可在解密逻辑加载前 monkeypatch AESGCM.decrypt 等边界，dump 明文与 DEK。
// 这两个文件在正常发行包里【绝不存在】，出现即视为注入，fail-closed 拒绝启动。
const suspectDirs = [ path.join(PY_DIR,'Lib','site-packages'), PY_DIR ];
const suspectNames = ['sitecustomize.py', 'usercustomize.py'];
```
[证据: `asar/main.js:204-222`]

【推断】该检查只覆盖 2 个目录 × 2 个精确文件名，本身很窄；其有效性完全依赖
`runtime-integrity.js` 把 `runtime/python/**/*.py` 全部纳入哈希闭包
（`.py` 命中 `PYTHON_EXECUTABLE` 正则）——任何多出来的 `.py` 都会让清单计数不符而拒启动。
详见 6.3-G8。

### 1.10 6.6 资料位置校验与交互式恢复

```js
// main.js:1047-1066
startupStatus.set('storage', '检查资料位置，保留已有工作区');
if (!storageStartupError && userStorage?.legacyRoot) {
  await require('./security/storage-recovery').validateLibrary(PYTHON_EXE, userStorage.dataDir, userStorage.dataDir);
}
if (storageStartupError) {
  const restored = await require('./security/storage-recovery').recoverStorageLocation({...});
  if (restored) app.relaunch();
  isQuitting = true; app.quit(); return;
}
```

`validateLibrary` 用 `python.exe -I -S -X utf8 -c <脚本>` 子进程，参数以 **JSON 走 stdin**
（不拼字符串代码），脚本只读打开 SQLite（`?mode=ro` + `PRAGMA query_only=ON`），
比较 `workflows.id` 集合；工作流 id 还必须是 `[A-Za-z0-9_-]+`。
[证据: `asar/security/storage-recovery.js:9-41,43-66`]

`recoverStorageLocation` 是 4 选项对话框（选择已有资料 / 恢复磁盘后重试 / 全新开始 / 暂时退出），
每次选择都重新校验：不能是盘符根、不能在安装目录内、必须有 `db/aris.db` + `workspaces`、
必须通过 Python 只读校验、写入前 CAS 校验指针未变。
[证据: `asar/security/storage-recovery.js:72-118`]

### 1.11 6.8~6.11 令牌、更新门禁与后端拉起

```js
// main.js:1084
backendControlToken = crypto.randomBytes(32).toString('base64url');
```
【直接提取】256 位随机、base64url 编码。

```js
// main.js:1089-1096
const updateResult = await initUpdater();
mandatoryUpdateRequired = Boolean(updateResult && updateResult.hasUpdate && updateResult.mandatory);
} catch (e) {
  failStartup('安全更新配置错误', `程序缺少有效的更新签名信任配置，已停止启动。\n${e.message}`);
```
即：**更新信任配置无效 = 拒绝启动**（fail-closed）。[证据: `asar/main.js:1086-1096`]

### 1.12 端口如何选定

**默认端口硬编码 `18088`** [证据: `asar/main.js:101`]

**端口禁区** [证据: `asar/main.js:313-327`]

```js
// ⛔ 预览服务（毕设工作流跑用户项目的 dev server）独占的端口段，主后端绝不能进。
//   必须与 web/backend/services/project_server.py 的 PORT_RANGE_START/END 保持一致。
const RESERVED_PORT_START = 19000;
const RESERVED_PORT_END   = 19100;   // 不含
```
原文解释了后果：预览服务的 `cleanup_port_range()` 会 taskkill 整段占用者，
主后端若绑到 19000-19100 就会在启动过程中**杀掉自己**，表现为「后端起来又立刻死」。
[证据: `asar/main.js:313-322`]

**选端口算法 `findAvailablePort(startPort, maxTries=10)`** [证据: `asar/main.js:329-367`]
1. `isPortAvailable` = `net.createServer().listen(port,'127.0.0.1')` 成功即空闲（:303-311）。
2. 禁区端口**跳过但不消耗尝试次数**：`port = RESERVED_PORT_END; continue;`
   原文说明了不这么写会「十次全被跳过，一个端口都没真探测过」（:330-339）。
3. 兜底 1：在 `startPort+100 .. +300` 范围再找一个真的可用端口（:349-359）。
4. 兜底 2：全找不到 → 回退默认端口或原端口（但**绝不回禁区/非法端口**），
   交给 uvicorn 报错、stderr 被捕获展示（:360-366）。

**已删除的危险逻辑**（保留为注释，是很好的工程证据）：

```js
// main.js:345-348
// ⛔ 这里曾经有一段「netstat 查出占用 startPort 的 pid 全部 taskkill」。已删除，原因：
//   它不判断那进程是不是自家的 —— 18088 若被用户别的软件占着就会被误杀。
//   自家孤儿后端现在由 Python 侧的 instance_guard 精确回收（按 pid 文件 + 进程
//   创建时间比对，还要确认它的父进程确实已经死了），比按端口盲杀既准又安全。
```

**何时选**：不在 `openApplication` 里提前选，而是**紧贴 spawn 选**：

```js
// main.js:581-594
async function startBackend(fromPort = PORT) {
  // ⛔ 挑端口紧贴 spawn，把"探测到可用"与"真正 bind"之间的空窗压到最小。
  if (isQuitting) return;
  actualPort = await findAvailablePort(fromPort);
  if (isQuitting) return;   // findAvailablePort 里有 await，期间用户可能已经点了退出
```
[证据: `asar/main.js:581-594`；`asar/main.js:1078-1083` 原注释说明原先提前挑端口的空窗问题]

**bind 失败自动换端口重试** [证据: `asar/main.js:760-785`]

```js
const bindFailed = /10048|10013|address already in use|Only one usage of each socket|error while attempting to bind/i.test(tail);
if (bindFailed && backendPortRetries < MAX_PORT_RETRIES) {
  backendPortRetries++;                 // MAX_PORT_RETRIES = 3
  const from = actualPort + 1;
  backendExited = false; backendGeneration++; pythonProcess = null;
  startupStatus?.set('backend', `端口冲突，正在重试启动（${backendPortRetries}/${MAX_PORT_RETRIES}）`);
  startBackend(from).catch(...);
  return;
}
```
原文还特别说明**不要**在这里加宽泛的 `permission denied`：那多半是杀软拦文件，
换端口解决不了，只会白试 3 次。[证据: `asar/main.js:766-768`]

### 1.13 环境变量如何传递

**第一步：白名单式剔除** [证据: `asar/security/backend-environment.js:5-16`]

```js
const UNSAFE = new Set([
  'PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT','PYTHONBREAKPOINT','PYTHONUSERBASE',
  'PYTHONHTTPSVERIFY','ELECTRON_RUN_AS_NODE','NODE_OPTIONS','NODE_PATH','NODE_EXTRA_CA_CERTS',
  'NODE_TLS_REJECT_UNAUTHORIZED','SSL_CERT_FILE','SSL_CERT_DIR','SSLKEYLOGFILE','REQUESTS_CA_BUNDLE',
  'CURL_CA_BUNDLE','OPENSSL_CONF','OPENSSL_CONF_INCLUDE','OPENSSL_MODULES',
]);
```
原文注释明确其边界：「This only cleans the child copy. Preserve the user's actual shell and
proxy routing; TLS must authenticate the destination with the system trust store.」

**第二步：注入受控变量** [证据: `asar/main.js:660-680`]

| 变量 | 值 | 作用 |
|---|---|---|
| `MH_DESKTOP` | `1` | 桌面模式标识 |
| `MODEX_PACKAGED` | `1`/`0` | 打包态 |
| `API_PORT` | `String(actualPort)` | 实际端口 |
| `PYTHONDONTWRITEBYTECODE` | `1` | 不生成 .pyc |
| `LANG` / `LC_ALL` | `en_US.UTF-8` | 编码 |
| `PYTHONIOENCODING` / `PYTHONUTF8` | `utf-8` / `1` | 编码 |
| `MODEX_MANDATORY_UPDATE_REQUIRED` | `1`/`0` | 强制更新时后端做 API 门禁 |
| `MODEX_CLIENT_VERSION` | 来自 `package.json` | 版本上报 |
| `MODEX_CONTROL_TOKEN` | 256 位随机 | 控制令牌 |
| `MODEX_PARENT_PID` | `String(process.pid)` | **父进程看护** |

父进程看护的必要性（原注释）：
> 「Windows 上 spawn 的子进程不随父进程死，而 killBackend() 只挂在 before-quit 上 ——
> 任务管理器结束进程、关机超时被强杀、Electron 自己崩溃，这三种都走不到它。没有看护，
> 后端就变成孤儿一直霸着端口……而且两个后端会同时 resume 同一个工作流。」
> [证据: `asar/main.js:673-679`]

**第三步：PATH 前置** [证据: `asar/main.js:682-716`]
依次拼接：`runtime\node`、捆绑 TeX 目录、Git Bash 的 `bin`+`cmd`
（同时设 `CLAUDE_CODE_GIT_BASH_PATH`）、Python 所在目录 + `Scripts`，
最终 `env.PATH = extraPaths.join(';') + ';' + env.PATH`。

**第四步：解释器隔离启动**（打包态）[证据: `asar/main.js:599-613`]

```js
const isolatedBootstrap = [
  'import sys',
  'sys.path.insert(0, sys.argv[1])',
  'import uvicorn',
  'uvicorn.run("main:app", host="127.0.0.1", port=int(sys.argv[2]), log_level="info")',
].join(';');
pythonArgs = ['-I', '-B', '-X', 'utf8', '-c', isolatedBootstrap, BACKEND_DIR, String(actualPort)];
```
原注释：「Packaged backend runs in Python isolated mode. This ignores user site, PYTHONPATH
and sitecustomize-style startup injection while retaining the bundled site-packages needed by
FastAPI/scientific tools.」[证据: `asar/main.js:601-603`]

**开发态解析真实解释器**（避免 `py.exe` / Store launcher 再 fork 出别的 PID）：
[证据: `asar/main.js:642-656`]

```js
// A py.exe / Windows Store launcher may create another PID. Resolve the
// interpreter before giving any backend control token to a child, then
// spawn Python directly so OS listener ownership can match that exact PID.
const probeArgs = [ ...(basename==='py.exe' ? ['-3'] : []), '-I','-B','-c','import sys; print(sys.executable)'];
const probeEnv = {};   // 仅白名单 7 个变量
for (const name of ['SystemRoot','WINDIR','PATH','PATHEXT','LOCALAPPDATA','APPDATA','USERPROFILE']) ...
const resolvedPython = execFileSync(pythonPath, probeArgs, {env: probeEnv, ..., timeout:10000}).trim();
if (!path.isAbsolute(resolvedPython) || /[\r\n\0]/.test(resolvedPython) || !fs.statSync(resolvedPython).isFile())
  throw new Error('无法确认开发版 Python 实际程序位置，请检查 Python 安装');
```

**spawn 参数**：`cwd: BACKEND_DIR`、`stdio: ['ignore','pipe','pipe']`、`windowsHide: true`。
[证据: `asar/main.js:721-726`]

### 1.14 健康检查：带操作系统级归属核验

这是本产品桌面侧**最有价值的安全设计之一**，值得单独说明。

`waitForBackend()` 默认参数：`timeoutMs=180000`、`intervalMs=500`、`requestTimeoutMs=2000`。
[证据: `asar/security/backend-health.js:48-49`]

**核验层次**：
1. **轮询前**：`verifyOwner({port, pid})` → 调 `netstat.exe -ano -p tcp`（只读、超时 3 s、
   `maxBuffer` 8 MB），解析 TCP 表，要求
   - 该端口存在 `peerAddress==='0.0.0.0' && peerPort===0` 的 LISTENING 行，
   - 且**所有**该端口的 listener 行 PID 都等于我们的 PID。
   [证据: `asar/security/backend-port-owner.js:22-34,36-52`]
2. **建连后、写任何 HTTP 字节之前**：`guardedAgent` 在 `socket.once('connect')` 里再次核验
   - `sameBackend(expected, current())`（port/pid/generation 三元组未变）
   - `socket.remoteAddress === '127.0.0.1'`、`socket.remotePort === expected.port`
   - `verifyOwner({port, pid, clientPort: socket.localPort})` —— 要求存在
     `port + peerAddress==='127.0.0.1' + peerPort===clientPort` 的**唯一**连接行且 PID 匹配
   - 超时 5 s
   [证据: `asar/security/backend-health.js:13-45`]
3. **响应内容**：`statusCode===200` 且 JSON `{status:'ok', desktop:true}`，且
   `sameBackend` 在响应结束时仍然成立。[证据: `asar/security/backend-health.js:98-105`]

代码注释直接点明动机：
> "Hand the socket to HTTP only AFTER the OS confirms the accepted connection's PID.
> No HTTP header, including the control token, is written before this."
> [证据: `asar/security/backend-health.js:11-12`]

`backend-port-owner.js` 文件头同样声明：「Never identify a backend by its HTTP response,
kill a port occupant, pass a control token to a helper, or print netstat output.」
[证据: `asar/security/backend-port-owner.js:1-3`]

**超时与取消**：
- 硬超时 180 s，报「后端启动超过等待时限，未向未知进程发送控制令牌；已保留诊断，请重试启动」
- 250 ms 粒度的状态轮询，检测 `quitting` / `exited` 时立即失败
[证据: `asar/security/backend-health.js:63-68`]

### 1.15 失败分类与恢复

后端进程 `exit` 处理器的分类逻辑 [证据: `asar/main.js:752-825`]：

| 判据（stderr 尾 40 行） | 分类 | 用户提示 | 恢复动作 |
|---|---|---|---|
| `/10048\|10013\|address already in use\|.../` | 端口冲突 | **不弹框** | 自动 `actualPort+1` 重试，最多 3 次（:769-785） |
| 含 `MODEX_BACKEND_ALREADY_RUNNING` | 已在运行 | 「软件已在运行」+ 指引去托盘，**不附 traceback** | 无（提示用户） |
| `nativeStartupFailure()` 命中 | Windows 应用控制策略 / 原生组件加载失败 | 专门中文提示 + 事件 ID 3077/3089 指引 | 无（引导修复安装） |
| `/ModuleNotFoundError\|ImportError\|No module named/` | 组件缺失 | 「后端组件缺失或损坏」 | 无 |
| `/PermissionError\|Access is denied\|拒绝访问/` | 权限/占用 | 「权限或文件被占用」 | 无 |
| 其他 | 未知 | 「请把下面的错误信息发给技术支持」 | 无 |

`nativeStartupFailure` 的两条规则 [证据: `asar/security/backend-startup-error.js:5,15`]：
- `应用程序控制策略|application control policy|blocked by group/security policy|winerror 1260`
  → `WINDOWS_APPLICATION_CONTROL_BLOCKED`
- `DLL load failed|winerror 126|winerror 193` → `NATIVE_RUNTIME_LOAD_FAILED`

**进程错误** 单独处理：`child.on('error')` → `failStartup('后端未能启动', ...)`。
[证据: `asar/main.js:733-737`]

**统一失败出口 `failStartup`** [证据: `asar/main.js:273-286`]
```js
function failStartup(message, detail = '') {
  if (isQuitting || startupFailed) return;
  startupFailed = true; backendExitReported = true; backendExited = true;
  killBackend();
  if (startupStatus && !startupStatus.finished) { startupStatus.fail('failed', message, detail); return; }
  dialog.showErrorBox(message, require('./security/startup-status').safeDetail(detail));
}
```
注意 `failStartup` **先杀后端**，且用 `startupFailed` 做幂等，避免「崩溃框 + 超时框」重复弹。

**启动状态窗 `StartupStatus`** [证据: `asar/security/startup-status.js`]
- 独立 `BrowserWindow`，`contextIsolation: true, nodeIntegration: false, sandbox: true`
  （:52-57）
- 内容用 `data:text/html` URL 加载，内嵌严格 CSP：
  `default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none';
  img-src 'none'; base-uri 'none'; form-action 'none'`（:23）
- 原文注释：「This shell never loads backend code, a preload, network resources or scripts.」
  （:3-4）
- `setWindowOpenHandler` 一律 deny；`will-navigate` 一律 `preventDefault`，
  只识别 `modex-startup://copy` 与 `modex-startup://quit` 两个自定义 URL。（:59-65）
- `safeDetail` 对诊断文本做密钥脱敏：PEM 块、`sk-xxx`、`Bearer xxx`、
  `api_key|password|secret|token|authorization` 赋值，并截断到 12000 字符。（:8-14）
- 每次 `set()` 都把 `report()` 写入 `<logDir>\startup-latest.json`；写失败不阻断。
  （:76-89）

---

## 2. preload 暴露面

### 2.1 源码（全文仅 70 行，已完整读取）

`resources/app.asar → preload.js`

```js
// preload.js:4-6
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('electronAPI', {
  isDesktop: true,
  platform: process.platform,
  ...
});
```
[证据: `asar/preload.js:1-70`]

### 2.2 暴露的 API 结构

顶层键 `electronAPI` 含 4 个成员：

| 成员 | 类型 | 说明 |
|---|---|---|
| `isDesktop` | 常量 `true` | 前端用来判断运行在桌面壳里 [证据: `asar/preload.js:7`] |
| `platform` | `process.platform` 快照 | 静态字符串 [证据: `asar/preload.js:8`] |
| `updater` | 对象，7 个方法 | 自动更新控制面 [证据: `asar/preload.js:13-45`] |
| `pickFolder` | 函数 | 原生选目录对话框 [证据: `asar/preload.js:51`] |
| `latex` | 对象，3 个方法 | MiKTeX 状态/安装 [证据: `asar/preload.js:56-69`] |

`updater` 的 7 个方法：`checkNow`、`startDownload`、`applyAndRestart`、`abort`、
`skipVersion(version)`、`getCached`，以及 2 个事件订阅器 `onUpdateAvailable(cb)`、
`onProgress(cb)`。`latex` 的 3 个：`getStatus`、`install`、`onInstallProgress(cb)`。

事件订阅器都返回**取消订阅函数**：
```js
// preload.js:33-37
onUpdateAvailable: (cb) => {
  const handler = (_e, info) => cb(info);
  ipcRenderer.on('update-available', handler);
  return () => ipcRenderer.removeListener('update-available', handler);
},
```
[证据: `asar/preload.js:33-44`]

### 2.3 完整 IPC 通道名清单

**A. 渲染进程 → 主进程（`ipcRenderer.invoke` / `ipcMain.handle`）共 9 条** [证据: `asar/main.js:1244,1276,1310,1318,1329,1336,1347,1365,1375`]

| # | 通道名 | 发起方 | 主进程处理器 | 参数 | 返回值 |
|---|---|---|---|---|---|
| 1 | `updater:check-now` | preload:15 | main.js:1336 | 无 | `publicUpdateInfo(result)` |
| 2 | `updater:start-download` | preload:18 | main.js:1244 | 无 | `{ok}` 或 `{ok:false,error}` |
| 3 | `updater:apply-and-restart` | preload:21 | main.js:1276 | 无 | `{ok}`/`{ok:false,cancelled}`/`{ok:false,error}` |
| 4 | `updater:abort` | preload:24 | main.js:1310 | 无 | `{ok}` 或 `{ok:false,error}` |
| 5 | `updater:skip-version` | preload:27 | main.js:1318 | `version`（**未校验类型/长度**） | `{ok}` 或 `{ok:false,error}` |
| 6 | `updater:get-cached` | preload:30 | main.js:1329 | 无 | `publicUpdateInfo(_lastCheck)` |
| 7 | `dialog:pick-folder` | preload:51 | main.js:1347 | 无 | `{canceled, path}` |
| 8 | `latex:get-status` | preload:58 | main.js:1365 | 无 | `{state,hasXelatex,miktexDir,installerAvailable}` |
| 9 | `latex:install` | preload:61 | main.js:1375 | 无 | `{ok,state,message}` |

**B. 主进程 → 渲染进程（`webContents.send` / `ipcRenderer.on`）共 3 条** [证据: `asar/main.js:1202,1233,1252,1379`]

| # | 通道名 | 发送方 | 载荷 |
|---|---|---|---|
| 10 | `update-available` | main.js:1202（启动后）、main.js:1233（前端加载完成后补发缓存） | `publicUpdateInfo`（**不含** manifest 与 signature） |
| 11 | `update-progress` | main.js:1252 | `{current,total,file}` |
| 12 | `latex-install-progress` | main.js:1379 | 一行日志字符串 |

**C. 不存在其它通道。** 全仓 grep `ipcMain.(handle|on|handleOnce|once)` 只命中上述 9 处，
`ipcRenderer.(invoke|send|on|sendSync)` 只命中 preload.js 的 12 处。
[证据: 对 `asar/` 全目录 grep 上述模式，共 23 条命中，全部列于上表]

**重要**：`publicUpdateInfo` 是显式投影，**不会**把 `manifest` / `signature` 交给渲染进程：
```js
// main.js:1219-1228
return { hasUpdate: true, version, changelog, fileCount, kind, totalSize,
         mandatory: Boolean(result.mandatory), minimumSupportedVersion };
```
[证据: `asar/main.js:1217-1229`]

### 2.4 参数校验情况

**共用的强制门禁 `assertTrustedRenderer`** [证据: `asar/main.js:1236-1241`]

```js
function assertTrustedRenderer(event) {
  const url = event?.senderFrame?.url || event?.sender?.getURL?.() || '';
  let trusted = false;
  try { trusted = new URL(url).origin === `http://127.0.0.1:${actualPort}`; } catch {}
  if (!trusted) throw new Error('untrusted renderer IPC request');
}
```
9 个 handler **全部**把它作为第一行调用（main.js:1245,1277,1311,1319,1330,1337,1348,1366,1376）。
`event.senderFrame` 为 `null`（如 iframe 已销毁）时退化为空串 → 不匹配 → 抛错。判定基于
**origin 精确相等**，不用 `startsWith`，也不受路径/查询串影响。

**逐个通道的参数校验**：

| 通道 | 校验 | 证据 |
|---|---|---|
| `updater:skip-version` | **无任何校验**：`version` 直接透传给 `updater.skipVersion(version)`，后者仅检查「mandatory 不可跳过」，然后 `state.skipped_version = version; this._saveState(state)`（`fs.writeFileSync(statePath, JSON.stringify(state))`） | `main.js:1318-1326`；`updater.js:641-648,168-175` |
| 其余 8 条 | 无入参，或入参在更深层校验（如 `updater.downloadUpdate` 先 `verifyManifest`，`updateBarrier` 结果被 `JSON.parse` + 状态码检查） | `main.js:1244-1259,1263-1275` |
| `latex:install` | 用模块级 `_latexInstalling` 布尔量做重入保护 | `main.js:1374-1378` |
| `updater:apply-and-restart` | 用 `updateApplyActive` 布尔量防重入；失败路径会 `updateBarrier('release')` 释放后端门禁 | `main.js:1262,1279-1280,1293-1297` |

【直接提取】`updater:skip-version` 是唯一存在「未校验入参 + 落盘」组合的通道，
但落盘目标仅 `updater-state.json`，且 JSON 序列化会转义，不构成注入。
影响面评估见 6.3-G14。

### 2.5 `nodeIntegration` / `contextIsolation` / `sandbox` 设置

**主窗口** [证据: `asar/main.js:861-866`]

```js
webPreferences: {
  preload: path.join(__dirname, 'preload.js'),
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
},
```
三项都是安全值。`show: false` 直到 `did-finish-load` 才 `win.show()`。
[证据: `asar/main.js:867,910-916`]

**另外两个窗口都没有 preload，因此都没有 `electronAPI`：**
- 启动状态窗：`webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true }`
  [证据: `asar/security/startup-status.js:56`]
- 截图窗：`nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true,
  allowRunningInsecureContent: false, webviewTag: false, navigateOnDragDrop: false`
  [证据: `asar/capture.js:687-697`]

### 2.6 主窗口的其余防护

**（1）控制令牌由主进程注入请求头，渲染进程拿不到** [证据: `asar/main.js:870-878`]

```js
const appOrigin = `http://127.0.0.1:${actualPort}`;
// Token 只存在于 Electron 主进程和后端环境；renderer JS/localStorage 都拿不到。
mainWindow.webContents.session.webRequest.onBeforeSendHeaders(
  { urls: [`${appOrigin}/*`, `ws://127.0.0.1:${actualPort}/*`] },
  (details, callback) => {
    details.requestHeaders['X-Modex-Control'] = backendControlToken;
    callback({ requestHeaders: details.requestHeaders });
  },
);
```
作用域限定为 `appOrigin/*` 与同端口 ws，不会外泄到第三方源。

**（2）外部链接** [证据: `asar/main.js:881-898`]
- `setWindowOpenHandler`：一律 `{action:'deny'}`；仅当协议为 `https:` 才
  `shell.openExternal`。
- `will-navigate`：origin 不等于 `appOrigin` 就 `preventDefault`，同样只对 `https:` 放行外部打开。

**（3）崩溃/加载失败兜底** [证据: `asar/main.js:902-921`]
`render-process-gone`、`did-fail-load`（忽略 `-3`/ERR_ABORTED）、60 秒加载超时，
任一触发即 `failStartup`。加载前先 `session.clearCache()`。

**（4）关闭即最小化到托盘** [证据: `asar/main.js:924-933`]
若托盘不存在则**不劫持关闭**，直接 `isQuitting = true; app.quit()`，避免出现无入口的后台进程。

### 2.7 越权与注入面评估（结论先行）

| 维度 | 判断 | 依据 |
|---|---|---|
| 原生 `require`/Node 逃逸 | **无** | `contextIsolation:true` + `nodeIntegration:false` + `sandbox:true`，三窗一致 [证据: `main.js:861-866`；`startup-status.js:56`；`capture.js:687-697`] |
| 通道面 | **极小**（9 invoke + 3 send），无文件读写、无 shell、无任意 URL 通道 | 全仓 grep 结果见 2.3 |
| 调用方身份校验 | **有**，origin 精确匹配 + 9/9 覆盖 | `main.js:1236-1241` 及各 handler 首行 |
| 参数校验 | **基本缺失**，但通道本身无危险参数（唯一带参通道落盘无注入） | `main.js:1318-1326` |
| **信任锚强度** | **弱**：信任锚 = 「能向 `http://127.0.0.1:<port>` 提交请求且 origin 为该值的 frame」。该 origin 正是**后端自己托管的整个前端 + 用户产物** | `main.js:1239` + `main.js:920`（`loadURL(appOrigin)`） |
| **纵深防御** | **缺失**：主窗口**没有 CSP** | `resources/app/dist/index.html` 无 CSP meta（全文 22 行，已读）；`asar/` 全目录 grep `Content-Security-Policy` 仅命中 `startup-status.js:23`；**无** `session.webRequest.onHeadersReceived` 注入 |

【推断】**结论**：preload 暴露面在「Electron 配置」维度上是合格的（最小通道集 + 三隔离 +
origin 校验 + 令牌不下发））。真正的弱点在**信任锚的语义**：被信任的 origin 与
「后端托管的全部内容（含前端 bundle 与用户/工作流产出的可预览产物）」同源。因此
**任何**同源 HTML/JS 注入一旦成立，即等价于获得全部 `electronAPI` 能力。
由于主窗口无 CSP，浏览器层没有任何兜底。
可利用性与影响面在 6.3-G4 展开。

---

## 3. 更新机制

### 3.1 参与模块与职责

| 模块 | 位置 | 职责 |
|---|---|---|
| `updater.js` (655 行) | asar 内 | 检查/下载/校验/触发安装状态机 |
| `security/update-security.js` (221 行) | **asar + `resources/app` 双份** | 清单 schema 校验、路径规范化、canonical JSON、Ed25519 验签、版本与回滚策略 |
| `security/update-transaction.js` (249 行) | **双份** | 事务化落盘、备份、journal、回滚、启动恢复 |
| `security/release-trust.js` (44 行) | **双份** | 固化信任根（server / channel / 公钥 / epoch 下限） |
| `security/update-network.js` (69 行) | asar 内 | Chromium `net` 传输封装（双隔离 session、system/direct 代理回退） |
| `security/installer-update.js` (77 行) | asar 内 | 完整安装包的 Authenticode 校验与提权启动 |
| `update-helper.js` (97 行) | **`resources/app/` 根** | 父进程退出后独立完成事务提交并重启主程序 |
| `updater-config.json` (12 行) | asar 内 | 运行期可读的更新配置 |

`resources/app` 下的 3 个 security 模块与 asar 内的同名模块**逐字节相同**，
可用哈希链证明：

| 文件 | 签名清单中的 sha256 | `build-inputs-paths.txt` 中 `desktop/security/` 同名源文件 sha256 |
|---|---|---|
| `security/release-trust.js` | `f9cbd1ebc6a4c088c0bb9f95685af07fc22176b97f1803472e85023c7b471ac4` | `f9cbd1ebc6a4c088c0bb9f95685af07fc22176b97f1803472e85023c7b471ac4` |
| `security/update-security.js` | `567239f801b6aebb2d955a113df9a2cdde65ded120aa4ee560af5dd666263cb9` | `567239f801b6aebb2d955a113df9a2cdde65ded120aa4ee560af5dd666263cb9` |
| `security/update-transaction.js` | `8bbf1beba0bd655889fe4091fa03e4564290c65374daf225dd1968bf0aa31bb7` | `8bbf1beba0bd655889fe4091fa03e4564290c65374daf225dd1968bf0aa31bb7` |

[证据: 左侧来自本机 Node 脚本读取 `runtime-integrity-manifest.json` 得到的 3 条记录
（脚本 `reports/_fx/manifest-stats.js` 输出 + `verify-install-tree.js` 复算一致）；
右侧来自 `reports/build-inputs-paths.txt:540`（release-trust.js）、`:173`（update-security.js）、
`:289`（update-transaction.js）] 【直接提取】

### 3.2 信任根：编译期固化，不信任本地文件

```js
// asar/security/release-trust.js:3-10
// Public release roots are intentionally compiled into both the Electron code
// container and runtime_guard.pyd.  They are not secrets; their job is to make
// a local JSON edit insufficient to replace the signer, channel, or endpoints.
const PINNED_CHANNEL = 'intl';
const PINNED_UPDATE_SERVER = 'https://up.mingheng.xin';
const PINNED_UPDATE_PUBLIC_KEYS = Object.freeze({
  'intl-update-2026-08-a': 'MCowBQYDK2VwAyEA5lJ+a3h3WfVpwLII4q5KBOtl+RD2lp3WISJxtDGoyMY=',
});
```
[证据: `asar/security/release-trust.js:3-10`]

`assertPinnedUpdateConfig(cfg)` 强制四件事 [证据: `asar/security/release-trust.js:12-37`]：
1. `config.channel === 'intl'`
2. `config.server_url === 'https://up.mingheng.xin'`
3. `update_public_keys` 的**键集合完全相等**（数量与逐项名），且每个键的值**逐字符相同**
4. `Number.isSafeInteger(config.security_epoch) && config.security_epoch >= 2`

绑定到启动路径：`_loadUpdateConfig()` 末尾无条件调用 `assertPinnedUpdateConfig(cfg)`。
[证据: `asar/main.js:1142-1167`，调用点 `:1165`]

【直接提取】该函数在启动的两个位置被触发：
- `verifyPackagedAppIntegrity()` 内（`main.js:115`）——即**完整性校验期间**
- `initUpdater()` 内（`main.js:1175`）——即**更新检查期间**

【推断】**所以：只要 `updater-config.json` 被删除或被改写（channel / server / 公钥 /
epoch 任一不符），`_loadUpdateConfig` 抛错 → `initUpdater` 抛错 → `main.js:1092-1095`
走 `failStartup('安全更新配置错误')` → 后端不启动、主界面不打开。**
这是一个真实的 fail-closed 语义，而不是「忽略配置继续跑」。

`updater-config.json` 实际内容与固化值一致：
`server_url=https://up.mingheng.xin`、`channel=intl`、`security_epoch=2`、
`full_installer_updates=true`、公钥表 1 项，且键名与固化值一致。
[证据: `asar/updater-config.json:1-12`]

配置里的自我说明：「客户端只包含 Ed25519 公钥；对应私钥保存在本机 gitignored
`_local-secrets`，正式采用前必须完成离线备份和权限审计」。
[证据: `asar/updater-config.json:11`]

### 3.3 更新元数据来源

【直接提取】URL 只有两条，由 `full_installer_updates` 开关决定：

```js
// updater.js:341-342
const manifestPath = this.config.full_installer_updates
  ? `/channels/${this.config.channel}/installer.bundle.json`
  : '/manifest.bundle.json';
const bundle = await this._fetchJson(this._url(manifestPath, true), 6 * 1024 * 1024);
```

本发行版 `full_installer_updates: true`（`updater-config.json:7`，并在 `main.js:1192`
透传给 `Updater`），因此**实际只走 `GET https://up.mingheng.xin/channels/intl/installer.bundle.json?_t=<ts>`**。

**bundle 结构强制**：必须是对象、键集合精确为 `manifest,signature`：
```js
// updater.js:343-348
if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)
    || Object.keys(bundle).sort().join(',') !== 'manifest,signature') {
  throw new Error('invalid signed manifest bundle');
}
manifest = bundle.manifest; signature = bundle.signature;
verifyManifest(manifest, signature, this.config.update_public_keys);
```
原注释：「manifest 与签名放在同一个原子 bundle，避免发布两文件之间的短暂错配。」
[证据: `asar/updater.js:340-348`]

**Origin 强绑定**：`_url()` 要求相对路径以 `/` 开头，且解析后 origin 必须等于
`this.updateOrigin` 且协议为 `https:`；构造函数还拒绝带用户名/密码/非根 pathname 的 URL。
[证据: `asar/updater.js:116-120,160-166`]；`_fetchJson` / `_downloadFile` 各自再校验一次
（`updater.js:182-186, 222-226`）。

**大小与超时**：manifest 上限 5 MiB（`_fetchJson` 默认）/ 6 MiB（bundle 调用点），
超时 10 s；下载超时 60 s。[证据: `asar/updater.js:180,216,306`]

### 3.4 清单校验（schema 2 / schema 3）

`validateManifest(manifest)` [证据: `asar/security/update-security.js:83-163`]：

- **字段白名单**：只允许 `schema_version, key_id, channel, version, minimum_supported_version,
  mandatory, security_epoch, sequence, released_at, changelog, files, deleted_files, installer`；
  出现任何未知字段即抛错（:88-95）
- `schema_version ∈ {2,3}`（:96）；`key_id` 匹配 `/^[A-Za-z0-9._-]{1,80}$/`（:97）
- `channel ∈ {intl, cn}`（:98）
- `version` / `minimum_supported_version` 必须是严格的 `X.Y.Z` 数值语义版本（:69-81,99-100）
- `security_epoch >= 1`、`sequence >= 1`、`released_at` 可解析、`changelog <= 20000` 字符
  （:102-111）
- `minimum_supported_version <= version`（:112）
- **schema 3 专属**：
  - 禁止携带 `files` / `deleted_files`（:114）
  - `installer` 键集合必须精确为 `path,publisher,sha256,size`（:116）
  - `path` 必须精确等于 `/downloads/<channel>/<version>/Modex-MH-Agent-Setup-<version>.exe`
    —— 注释「installer path must be immutable and version-bound」（:117-118）
  - `sha256` 64 位小写 hex、`size` 为正安全整数且 ≤ 4 GiB、`publisher` 非空且无控制字符
    （:119-121）
- **schema 2 专属**：`files` 1..20000 条，每条键集合精确为 `rel,sha256,size`；
  路径经 `normalizeRelativePath`（拒 `\`、`\0`、`:`、前导 `/`、`.`/`..` 段、NFC 规范化）；
  **大小写不敏感查重**；sha256 64 hex；单文件 ≤ 512 MiB；总量 ≤ 4 GiB（:125-151）
- `deleted_files` 同样规范化、查重、且不能与 `files` 冲突（:152-161）
- **`modex-mh-agent.exe` 与 `resources/app.asar` 只允许完整安装器更新** [证据: `update-security.js:17-24,139-141,155-157`]

```js
// update-security.js:13-20（原文注释）
// Electron 的 EmbeddedAsarIntegrityValidation 把 app.asar 的 SHA-256 写进主
// EXE。两者不是可独立提交的普通文件；逐文件增量替换在断电窗口内会形成一对
// 不匹配的文件，而且 Electron 会在 main.js / JS 恢复逻辑运行前直接终止。
const FULL_INSTALLER_ONLY_PATHS = new Set(['modex-mh-agent.exe', 'resources/app.asar']);
```

**签名验证 `verifyManifest`** [证据: `asar/security/update-security.js:174-186`]
- `signatureRecord.schema_version === 1`
- `signatureRecord.key_id === manifest.key_id`
- 公钥必须存在于传入的 `update_public_keys` 中
- 签名长度必须为 **64 字节**
- `crypto.verify(null, canonicalJson(manifest), key, sig)`，且 `publicKeyFromSpkiB64`
  强制 `asymmetricKeyType === 'ed25519'`（:165-172）

`canonicalJson` 是本项目自实现的决定性序列化：对象键 `sort()`、数字必须是安全整数
（拒绝浮点）、字符串用 `JSON.stringify`、数组按序。[证据: `update-security.js:26-40`]

### 3.5 回滚与降级防护

```js
// update-security.js:199-207
function evaluateUpdatePolicy(manifest, local) {
  if (manifest.channel !== local.channel) throw new Error('update channel mismatch');
  if (manifest.security_epoch < local.securityEpoch) throw new Error('security epoch rollback');
  if (manifest.sequence < local.highestSequence) throw new Error('update sequence rollback');
  const belowMinimum = compareVersions(local.version, manifest.minimum_supported_version) < 0;
  const newer = compareVersions(manifest.version, local.version) > 0;
  const mandatory = Boolean(manifest.mandatory || belowMinimum || manifest.security_epoch > local.securityEpoch);
  return { newer, belowMinimum, mandatory };
}
```
[证据: `asar/security/update-security.js:199-207`]

调用点传入的 `local` 值取「配置值与状态文件值的最大值」：
```js
// updater.js:370-375
const policy = evaluateUpdatePolicy(manifest, {
  channel: this.config.channel,
  version: effectiveVersion,
  securityEpoch: Math.max(this.config.security_epoch || 1, state.security_epoch || 1),
  highestSequence: Math.max(state.highest_sequence || 0, state.highest_seen_sequence || 0),
});
```
`security_epoch` 提升本身即触发强制更新（`manifest.security_epoch > local.securityEpoch
→ mandatory`）。[证据: `asar/security/update-security.js:205`]

### 3.6 离线降级路径（缓存的上一次已签名清单）

```js
// updater.js:349-366（原文注释节选）
// 网络被阻断时仍执行最后一次已验证策略，防止用 hosts/代理屏蔽强制更新。
} catch (e) {
  const stat = fs.statSync(this.signedManifestCachePath);
  if (!stat.isFile() || stat.size > 6 * 1024 * 1024) throw new Error('invalid signed manifest cache');
  const cached = JSON.parse(fs.readFileSync(this.signedManifestCachePath, 'utf8'));
  verifyManifest(cached.manifest, cached.signature, this.config.update_public_keys);   // ← 同样验签
  manifest = cached.manifest; signature = cached.signature;
} catch (cacheError) {
  return { hasUpdate: false, reason: `signed manifest unavailable: ...`, securityError: true };
}
```
[证据: `asar/updater.js:349-366`]

缓存路径：`<userData>\last-signed-installer-update.json`（`full_installer_updates` 为 true 时）
或 `last-signed-update.json`。[证据: `asar/updater.js:107`]
**缓存不再是可信的例外**：读取后仍必须通过 `verifyManifest`。[证据: `updater.js:355`]

### 3.7 下载与校验流程

**schema 3（本发行版实际路径）** [证据: `asar/updater.js:536-567`]

1. 缓存命中判定：`<installerCacheDir>\<version>-<sha256>.exe` 存在、是普通文件、
   非符号链接、尺寸相符、且 `hashFile()` 复算相符 → 跳过下载（:541-542）
2. 否则 `_downloadFile(_url(artifact.path), target, artifact.sha256, artifact.size, cb)`，
   **最多 3 次**，退避 1 s / 2 s（:545-558）
3. 下载完成后 `inspectInstaller(target, { sha256, publisher })`（:562）

**`_downloadFile` 的完整性控制** [证据: `asar/updater.js:220-308`]
- 目标先写 `<dest>.tmp`，`fs.createWriteStream(tmpPath, { flags: 'wx' })`（:229,235）
- 若 `.tmp` 已存在，先 lstat 确认是普通文件且非符号链接才 unlink（:230-234）
- 流量上限 `Math.max(expectedSize*2, 1MiB)`，超限即 fail（:265,269-272）
- 流式 sha256（:236,273）
- `finish` → 关闭文件句柄 → **先比大小、再比 sha256**，全部通过才 `renameSync(tmp, dest)`
  （:279-298）
- 失败路径保证：「不要释放调用方直到清理完成。快速重试的新 .tmp 不能被上一次下载的
  延迟回调删掉」（:246-251）
- URL origin 二次校验（:222-226）

**schema 2（本发行版被禁用，仅作对照）** [证据: `asar/updater.js:456-525`]
- 先 `verifyManifest(updateInfo.manifest, updateInfo.signature, ...)`（:458）
- 再对每个 `changedFiles` 元素**回查签名清单**：`authorized.get(file.rel)` 必须存在且
  sha256 与 size 完全一致，否则「下载文件与签名清单不一致」（:460-464）
- 检测残留 `.app.update.lock` / `.apply-request.json` 存在则拒绝下载（:465-468）
- 文件 URL 内容寻址：`/files/<sha256 前 2 位>/<sha256>.bin`（:485）
- 每个文件最多 3 次重试（:489-509）
- 收尾把 manifest 与签名写入 staging 并**再验一次签**（:514-522）

### 3.8 完整安装包（schema 3）的额外信任检查

`inspectInstaller` 通过 **PowerShell** 执行固定脚本（`-NoProfile -NonInteractive
-EncodedCommand <base64(utf16le)>`），路径与期望值经**环境变量**传入，不拼接代码。
[证据: `asar/security/installer-update.js:53-60`]

`VERIFY_SCRIPT` 的检查项 [证据: `installer-update.js:28-52`]：

| 检查 | 实现 | 失败信息 |
|---|---|---|
| 文件必须是普通文件、非重解析点 | `$f.PSIsContainer -or ($f.Attributes -band ReparsePoint)` | `Unsafe installer file` |
| SHA-256 一致（若传入） | `Get-FileHash -Algorithm SHA256` 小写比较 | `Installer hash changed` |
| **Authenticode 必须 Valid** | `Get-AuthenticodeSignature` 的 `$s.Status.ToString() -ne 'Valid'` | `Installer must have a valid timestamped Windows signature` |
| **必须同时有签名证书与时间戳证书** | `-not $s.SignerCertificate -or -not $s.TimeStamperCertificate` | 同上 |
| 发布者 Subject 精确匹配 | `$s.SignerCertificate.Subject -cne $env:MODEX_INSTALLER_PUBLISHER` | `Installer publisher mismatch` |
| 启动 | `Start-Process -FilePath $f.FullName -Verb RunAs -PassThru -WindowStyle Normal` | 取消 UAC → 「未能启动安装器（可能取消了管理员授权），原程序保持运行。」 |

非启动模式下有 45 s 超时（`launch` 模式不设超时）[证据: `installer-update.js:62`]。
`assertSafeDirectory` 会向上遍历到根，拒绝任何一层是符号链接，再 `mkdir -p`。
[证据: `installer-update.js:14-26`]

### 3.9 事务化安装与回滚

#### 3.9.1 触发链

```js
// main.js:1276-1307（关键行）
ipcMain.handle('updater:apply-and-restart', async (event) => {
  assertTrustedRenderer(event);
  if (!updater) return { ok:false, error:'updater not initialized' };
  if (updateApplyActive) return { ok:false, error:'正在准备安装，请勿重复点击' };
  updateApplyActive = true;
  const mainExePath = process.execPath;
  if (updater._lastCheck?.kind === 'full_installer') {
    const answer = await dialog.showMessageBox(mainWindow, {... '请确认编辑器中的修改已经保存。' ...});
    if (answer.response !== 1) { updateApplyActive = false; return { ok:false, cancelled:true }; }
    await updateBarrier('prepare');          // POST /api/health/update {action:'prepare'}
    await updater.launchFullInstaller();
  } else { await updater.applyUpdateAndRestart(mainExePath); }
  isQuitting = true; killBackend();
  setTimeout(() => { app.quit(); }, 800);
  return { ok: true };
});
```
[证据: `asar/main.js:1276-1307`]

`updateBarrier` 向后端 `POST /api/health/update`（带 `X-Modex-Control` 令牌），
15 s 超时，非 200 抛后端返回的 `detail` —— 后端据此阻止「有任务在跑时安装更新」。
[证据: `asar/main.js:1263-1275`]

#### 3.9.2 事务 helper 的启动（schema 2 路径）

```js
// updater.js:594-627
const helperScript = path.join(this.appDir, 'update-helper.js');   // resources/app/update-helper.js
helperNode = prepareUpdateHelperNode(path.join(this.runtimeDir,'node','node.exe'), this.helperHostDir);
fs.writeFileSync(requestPath, JSON.stringify({
  schema_version: 1, install_dir, staging_dir, backup_dir, state_path, main_exe, parent_pid: process.pid,
}), { flag: 'wx', mode: 0o600 });
const child = spawn(helperNode, [helperScript, '--request', requestPath], {
  detached: true, stdio: 'ignore', windowsHide: true, env: sanitizedNodeEnvironment(),
});
child.once('error', reject);
child.once('spawn', () => { child.unref(); resolve(); });
```
[证据: `asar/updater.js:594-627`]

- `prepareUpdateHelperNode` 把 `runtime\node\node.exe` **复制**到
  `<cache>\update-helper-host\node-update-helper-<pid>-<12hex>.exe`（`COPYFILE_EXCL`），
  复制后复算 sha256 必须相同，否则删除并抛错。命名为的是让启动后能识别并清理陈旧副本。
  [证据: `asar/updater.js:66-96`；清理规则 `UPDATE_HELPER_NODE_PATTERN` `:47`，清理逻辑 `:127-147`]
- 环境变量脱敏：删除 `ELECTRON_RUN_AS_NODE`、`NODE_OPTIONS`、`NODE_PATH`、
  `NODE_EXTRA_CA_CERTS`。[证据: `asar/updater.js:53-64`]
- 注释点明「Confirm OS process creation before main.js exits. An ENOENT/EACCES on spawn
  must leave the old application running and retryable.」（:612-613）

#### 3.9.3 helper 的请求校验与提交

[证据: `E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\update-helper.js:39-88`]

```js
function validateRequest(request, requestPath) {
  if (!request || request.schema_version !== 1 || !Number.isSafeInteger(request.parent_pid) || request.parent_pid < 1)
    throw new Error('invalid update apply request');
  if (stagingDir !== path.join(installDir, '.app.update')) throw new Error('unexpected staging directory');
  if (backupDir  !== path.join(installDir, '.app.bak'))     throw new Error('unexpected backup directory');
  if (path.resolve(requestPath) !== path.join(stagingDir, '.apply-request.json')) throw new Error('unexpected request path');
  const exeRelative = path.relative(installDir, mainExe);
  if (!exeRelative || exeRelative.startsWith('..') || path.isAbsolute(exeRelative)) throw new Error('main executable escapes install root');
}
```
随后：
1. 抢 `.app.update.lock`（`fs.promises.open(lockPath,'wx',0o600)`），写入 `{pid, started_at}` 并 `sync()`
   （:59-62）
2. 读 `.manifest.json`（≤5 MiB）与 `.manifest.sig.json`（:64-65）
3. `waitForParentExit(parent_pid, 60000)`：250 ms 轮询 `process.kill(pid,0)`；超时抛
   「parent application did not exit; update aborted safely」（:31-37,66）
4. `applySignedUpdate({ ..., publicKeys: PINNED_UPDATE_PUBLIC_KEYS, manifest, signature, statePath })`
   —— **信任根来自 `release-trust.js` 的固化常量，不读配置文件**（:67-75，import 见 :9）
5. 成功 → 整体删除 staging（:76）
6. 失败 → 写 `<backupDir>\update-error.log`（含 ISO 时间戳与完整 stack）（:77-80）
7. `finally` → 删 `.apply-request.json`、关锁句柄、删锁（:81-86）
8. 最后 `spawn(mainExe, [], {detached:true, stdio:'ignore', windowsHide:true}).unref()` 重启（:87）

#### 3.9.4 落盘事务 `applySignedUpdate`

[证据: `asar/security/update-transaction.js:172-237`]

| 阶段 | 行为 | 行号 |
|---|---|---|
| 0 验签 | `verifyManifest(manifest, signature, publicKeys)` | :183 |
| 1 计划 | `buildApplyPlan`：逐条 `resolveWithin` + `assertNoSymlinkPath`；本地已相符则跳过；否则要求 staging 副本的 sha256+size 相符，否则抛「required staged file missing or invalid」；`deleted_files` 要求目标是普通文件、非符号链接，否则拒绝删除 | :76-103 |
| 2 备份 | `rm -rf backupDir` → 逐条复制原文件到 `backupDir/<rel>`（`COPYFILE_EXCL`）；已存在的目标若为符号链接或非文件 → 「unsafe existing target」 | :192-208 |
| 3 journal | `atomicWriteJson(transaction.json, {status:'backup_complete', entries, version})` | :209 |
| 4 应用 | 按 `applyPriority` **升序**处理 changed：业务文件(0) → preload/package.json(70) → `security/update-*`(80) → `updater.js`/`update-helper.js`(90) → `main.js`(100) | :213,133-141 |
| 5 写入 | `copyVerified`：校验源 → 复制到 `<dest>.modex-new-<pid>`（`COPYFILE_EXCL`）→ 复算 tmp 哈希 → **`rm dest` → `rename tmp dest`** | :59-74,216 |
| 6 删除 | `deleted_files` 逐个 `rm(force)` | :218 |
| 7 全树复核 | `verifyInstalledTree`：清单中每个文件重算哈希必须相符；每个"签名删除"必须确实不存在 | :219,105-119 |
| 8 提交 | journal → `committed`；写 `statePath`：`{installed_version, security_epoch, highest_sequence, committed_at}` | :220-228 |
| 9 失败 | `restoreBackup`（逆序：先 `rm target`，若 `existed` 则从备份复制回来）→ journal → `rolled_back`（含 error 字符串）→ 重新抛出 | :230-236,121-131 |

`applyPriority` 的注释说明了排序动机：「保证旧启动链尽可能一直可用：业务文件先替换，
更新器启动链最后替换，main.js 最后落盘。」[证据: `update-transaction.js:134`]

#### 3.9.5 失败恢复总表

| 故障点 | 恢复机制 | 证据 |
|---|---|---|
| 下载中断/超时/哈希不符 | 删除 `.tmp` 后重试（≤3 次，1 s/2 s 退避） | `updater.js:487-509` |
| 下载中磁盘满/无权限 | 立即停止重试并给出专门中文提示（`ENOSPC` / `EACCES,EPERM,EROFS`） | `updater.js:445-449,503,555` |
| 下载期间用户取消 | `abortDownload()` 置 `aborted` 并 `destroy(new Error('aborted'))` | `updater.js:527-530` |
| 提交过程抛错 | `restoreBackup` 全量回滚 + journal `rolled_back` + `update-error.log` | `update-transaction.js:230-236`；`update-helper.js:77-80` |
| 提交中途断电/被强杀 | 下次启动 `recoverInterruptedUpdate` 按 `backup_complete` journal 回滚 | `main.js:1008`；`update-transaction.js:143-170` |
| helper 正在提交时用户又启动程序 | `waitForActiveUpdateHelper` 最多等 60 s；锁超过 10 分钟或 PID 已死则视为陈旧并删除 | `main.js:972-995` |
| 强制更新被 aborts | `updater:abort` 显式拒绝：`mandatory update cannot be aborted` | `main.js:1312` |
| 用户想跳过强制更新 | `skipVersion` 抛 `mandatory security updates cannot be skipped` | `updater.js:641-644` |
| 离线且无缓存 | 返回 `hasUpdate:false` + `securityError:true`；`initUpdater` 见 `securityError` 后的分支见 6.3-G6 | `updater.js:358-365`；`main.js:1206-1213` |

---

## 4. 运行时完整性校验

### 4.1 清单文件与常量

```js
// asar/security/runtime-integrity.js:8-14
const MANIFEST_NAME  = 'security/runtime-integrity-manifest.json';
const SIGNATURE_NAME = 'security/runtime-integrity-manifest.sig.json';
const EXCLUDED = new Set([MANIFEST_NAME, SIGNATURE_NAME]);
const MAX_FILES = 20000;
const MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024;
const MAX_RUNTIME_FILES = 100000;
const MAX_RUNTIME_BYTES = 8 * 1024 * 1024 * 1024;
```
[证据: `asar/security/runtime-integrity.js:8-14`]

签名文件实体（小文件，全文）：
```json
// resources/app/security/runtime-integrity-manifest.sig.json:1-5
{ "key_id": "intl-update-2026-08-a", "algorithm": "Ed25519",
  "signature": "TfbEhg4rUW+irQV5AIg13tCttkqQHZ5iAWolPEtk+kpKs0QjJ9qAyUwq+3cImO3DuQbKzykIftEF6yA1l+dDBw==" }
```
[证据: `resources/app/security/runtime-integrity-manifest.sig.json:1-5`]

### 4.2 清单如何加载与验签

**加载**：`main.js` 先做尺寸门禁，再 `JSON.parse`：
```js
// main.js:105-114
const manifestPath  = path.join(APP_ROOT, ...RUNTIME_MANIFEST_NAME.split('/'));
const signaturePath = path.join(APP_ROOT, ...RUNTIME_SIGNATURE_NAME.split('/'));
for (const target of [manifestPath, signaturePath]) {
  const stat = fs.statSync(target);
  if (!stat.isFile() || stat.size < 32 || stat.size > 32 * 1024 * 1024) {
    throw new Error(`应用完整性文件无效: ${path.basename(target)}`);
  }
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const signature = JSON.parse(fs.readFileSync(signaturePath, 'utf8'));
```
[证据: `asar/main.js:103-114`]

**清单结构强校验 `validateRuntimeManifest`** [证据: `asar/security/runtime-integrity.js:251-268`]

| 校验 | 规则 |
|---|---|
| 顶层键集合 | 必须**精确等于** `channel,files,generated_at,key_id,runtime_files,schema_version,version` |
| `schema_version` | ∈ {1, 2} |
| `key_id` | `/^[A-Za-z0-9._-]{1,80}$/` |
| `channel` | `/^(intl\|cn)$/` |
| `version` | `/^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/` |
| `generated_at` | 可被 `Date.parse` |
| `files` | 1..20000 条，每条键集合精确为 `rel,sha256,size`，**必须已按 rel 升序排列**（`rel.localeCompare(previous,'en') <= 0` 即报错），大小写不敏感不可重复，sha256 64 位小写 hex，总量 ≤ 2 GiB |
| `files` 自签名禁止 | `manifest.files.some(f => EXCLUDED.has(f.rel))` → 「runtime manifest cannot sign itself」 |
| `runtime_files` | 允许为空，≤100000 条，总量 ≤ 8 GiB |
| **schema 2 额外要求** | `CRITICAL_RUNTIME_FILES` 的 13 条必须**全部**出现在 `runtime_files` 中，否则「critical runtime baseline incomplete」 |

**路径规范化 `normalizeRel`** [证据: `runtime-integrity.js:65-75`]
拒绝 `\`、`\0`-`\x1f`、`:<>"|?*`，拒绝任一段以 `.`/空格结尾或匹配 `~\d+(\.|$)`
（即 Windows 8.3 短名），要求 `path.posix.normalize(v) === v`、不以 `/` 开头、
不是 `..`/`../` 开头。

**验签 `verifyRuntimeSignature`** [证据: `runtime-integrity.js:281-292`]
```js
validateRuntimeManifest(manifest);
if (!signatureRecord || Object.keys(signatureRecord).sort().join(',') !== 'algorithm,key_id,signature')
  throw new Error('runtime signature record invalid');
if (signatureRecord.algorithm !== 'Ed25519' || signatureRecord.key_id !== manifest.key_id)
  throw new Error('runtime signature metadata mismatch');
const publicB64 = publicKeys && publicKeys[manifest.key_id];
if (typeof publicB64 !== 'string' || !publicB64) throw new Error('runtime integrity public key missing');
const signature = Buffer.from(signatureRecord.signature || '', 'base64');
if (signature.length !== 64) throw new Error('runtime integrity signature length invalid');
if (!crypto.verify(null, Buffer.from(canonicalJson(manifest), 'utf8'), publicKeyFromSpkiB64(publicB64), signature))
  throw new Error('runtime integrity signature verification failed');
```
签名覆盖的是**整份清单的 canonical JSON**（含 27752 条 runtime_files 记录），
`canonicalJson` 与更新模块共用同一实现（`runtime-integrity.js:6` import 自 `update-security`）。

**本次实测**：该签名对本机 `resources/app` 上的清单验签通过。
[证据: 0.3 节的 `signature verifies: true`；canonical JSON 长度 5,001,244 字节]

### 4.3 覆盖范围

`verifyRuntimeTree(rootDir, manifest, signatureRecord, publicKeys, expected)` 分两段比对。
[证据: `asar/security/runtime-integrity.js:310-352`]

**第一段：`expected.applicationRoot = APP_ROOT = <installRoot>\resources\app`**
（`main.js:91,116-122`）

`listRuntimeFiles(APP_ROOT)` 递归枚举（**拒绝任何符号链接**、拒绝非常规目录/文件），
排除清单与签名自身，逐文件 `lstat` + `sha256File`，要求与 `manifest.files` **按序逐条**
（`rel` / `size` / `sha256` 三者全等），且**数量必须相等**。
[证据: `runtime-integrity.js:87-119,317-325`]

实测覆盖（0.4 节统计）：**1498 个文件 / 48.3 MB**，分布为
`tools/` 1164、`backend/` 186、`dist/` 135、`templates/` 9、`security/` 3、根 1（`update-helper.js`）。

【推断】由此可知：**前端 `dist/`、全部后端 `.pyd`、`tools/`（含 node_modules）、
`templates/`、以及更新事务/信任/清单三个 security 模块 + `update-helper.js` 都在
硬哈希覆盖内**；而 Electron 主进程代码（`main.js`/`preload.js`/`updater.js`/`capture.js`/
其余 15 个 security 模块）位于 asar 内，由 `resources/app.asar` 这一条
（0.85 MB、sha256 已锁）间接覆盖。

**第二段：关键运行时闭包**

```js
// runtime-integrity.js:167-193（listPythonRuntimeClosure）
const selected = new Set(CRITICAL_RUNTIME_FILES);
// 走 runtime/python，凡命中 PYTHON_EXECUTABLE 的普通文件都纳入
} else if (PYTHON_EXECUTABLE.test(rel)) { selected.add(rel); }
```
`PYTHON_EXECUTABLE = /(?:\.(?:py|pyw|pyd|dll|exe|zip|egg|whl|pth|_pth|so)(?:\.\d+)*|\/pyvenv\.cfg)$/i`
[证据: `runtime-integrity.js:29`]

`CRITICAL_RUNTIME_FILES` 共 13 条，且带有明确的安全论证注释：
[证据: `runtime-integrity.js:30-49`]

| 条目 | 注释结论 |
|---|---|
| `resources/app.asar` | Electron 主进程代码容器 |
| `runtime/python/python.exe` / `python311.dll` / `python311.zip` | 解释器本体 |
| `runtime/python/python311._pth` | 「解释器启动配置：._pth 里任何 `import xxx` 行会在后端任何 .pyd 之前执行，篡改它即可在解密逻辑加载前注入 hook。锁哈希 → 改一字节即 fail-closed 拒启动。」 |
| `runtime/python/libcrypto-3.dll` / `libssl-3.dll` / `_hashlib.pyd` / `_ssl.pyd` | 「加密实现的真正落点：AES-GCM 最终由 OpenSSL(libcrypto) 执行……不锁这些，攻击者可直接掉包 libcrypto-3.dll 在解密处 dump 明文，绕过所有 .pyd/ASAR/Fuse 校验。」 |
| `runtime/node/node.exe` | Node 运行时 |
| `runtime/node/node_modules/@anthropic-ai/claude-code/bin/claude.exe` | Claude CLI |
| `runtime/git/bin/bash.exe` | Git Bash |
| `runtime/pandoc/pandoc.exe` | 文档转换 |

实际纳入的闭包规模（0.4 节）：**27,752 个文件 / 4274.7 MB**，
其中 `runtime/python/Lib/site-packages/**` 的 `.py` 有 26,678 个（380 MB），
`.dll` 196 个（2241 MB），`.pyd` 762 个（847 MB），`.exe` 107 个（786 MB）。

**易变产物豁免** [证据: `runtime-integrity.js:15-27`]
```js
function isVolatileRuntimeArtifact(rel) {
  const normalized = rel.replace(/\\/g, '/');
  return normalized.split('/').includes('__pycache__') || /\.(?:pyc|pyo)$/i.test(normalized);
}
```
原注释说明：这些是 Python 首次 import 后生成的缓存，文件头含解释器/版本元信息，
字节会随启动与安装而合法变化，因此排除在签名闭包之外；
但 `resources/app/backend` 下的 `.pyc` 仍被视为受保护的应用文件，规则**只在枚举
`runtime/python` 时生效**，并且同时按路径（`__pycache__` 目录）与扩展名判定。（:16-22）

清单侧同样过滤（兼容旧清单）：`listSelectedFiles` 会先 `.filter(rel => !isVolatileRuntimeArtifact(rel))`。
[证据: `runtime-integrity.js:126-130`]

主动清理在启动早期同步执行（见 4.5 与 `main.js:574`）：
`cleanupVolatileRuntimeArtifacts(rootDir)` 递归删除 `__pycache__` 目录与 `.pyc/.pyo`，
**从不跟随或删除符号链接**。[证据: `runtime-integrity.js:195-231`]

### 4.4 校验时机

【直接提取】校验在启动流程中**恰好执行一次**，位置在 `openApplication()` 内，
**更新事务恢复之后、任何后端进程与任何应用前端代码启动之前**：

```js
// main.js:1016-1027
// 更新恢复完成后、任何后端/应用前端代码启动前（无脚本启动提示窗除外），验证 resources/app 的
// Ed25519 签名清单。新增、删除、替换文件或目录链接全部 fail closed。
if (isQuitting) return;
startupStatus.set('integrity', '核对程序与内置运行环境，请稍候');
try {
  const integrity = await verifyPackagedAppIntegrity();
  console.log(`[Integrity] verified ${integrity.files} app files (${integrity.bytes} bytes)`);
} catch (error) {
  console.error('[Integrity] packaged app verification failed:', error);
  failStartup('程序文件不完整或校验未通过', `未加载不完整组件。请保留诊断、核对安装日志；不需要先卸载或删除工作区。\n\n${error.message}`);
  return;
}
```
[证据: `asar/main.js:1016-1027`]

**Dev 模式跳过**：`verifyPackagedAppIntegrity()` 第一行 `if (IS_DEV) return {files:0,bytes:0,skipped:true};`
[证据: `asar/main.js:104`]

**schema 门禁**：`requireRuntimeClosure: true` 要求 `manifest.schema_version === 2`，否则
「runtime closure manifest required; install a current full release」。
[证据: `main.js:121`；`runtime-integrity.js:312-314`]

**版本与通道绑定**：`expected.channel` / `expected.version` 分别取自 `updater-config.json`
与 `package.json`，与清单不符即拒。[证据: `main.js:115-121`；`runtime-integrity.js:315-316`]

【直接提取】全仓 grep `verifyRuntimeTree` 只有 2 处：定义（`runtime-integrity.js:310`）
与唯一调用（`main.js:116`）。**更新完成后没有二次校验**，运行期也没有周期性复核。

### 4.5 校验开销（本次实测）

| 项目 | 值 | 依据 |
|---|---|---|
| 需哈希的应用树 | 1498 文件 / 48.3 MB | 0.4 节统计 |
| 需哈希的运行时闭包 | 27,752 文件 / 4274.7 MB | 0.4 节统计 |
| 本机 SHA-256 吞吐 | **1188.3 MB/s**（545.4 MB / 0.46 s，热缓存） | 本次 `node crypto` 实测 |
| 纯吞吐外推下限 | 4323 MB ÷ 1188.3 MB/s ≈ **3.6 s** | 同上 |
| 实际开销影响因素 | 27,752 次独立 open/read/close（`sha256File` 每次 `createReadStream`）、并发上限 4、冷缓存、HDD 随机寻道 | `runtime-integrity.js:77-85,134-162` |

并发被刻意限制为 4 个 worker，注释说明原因：「Bound concurrent IO/memory.
Scientific wheels contain multi-hundred-MB DLLs.」[证据: `runtime-integrity.js:133-135`]

【推断】热缓存 SSD 上校验约 4-10 秒；机械盘冷缓存下，27752 次随机文件打开的寻道成本
可能把这一步拉到分钟级。这是**每次启动都付出**的固定成本。这解释了为什么产品需要一个
独立的「启动状态窗」来兜住等待体验（`startup-status.js:3-4` 的注释也印证了这一意图）。

### 4.6 失败后果

| 失败点 | 后果 | 证据 |
|---|---|---|
| 清单/签名文件缺失、非普通文件、或尺寸 <32 B / >32 MiB | `throw` → `failStartup('程序文件不完整或校验未通过')` | `main.js:107-112,1023-1027` |
| 清单结构/字段/路径/排序不合法 | 同上 | `runtime-integrity.js:251-268` |
| 签名不匹配 / key_id 不在信任表 / 签名长度 ≠ 64 | 同上 | `runtime-integrity.js:281-292` |
| `schema_version !== 2` | 「runtime closure manifest required」 | `runtime-integrity.js:312-314` |
| channel / version 与本地配置不符 | 同上 | `runtime-integrity.js:315-316` |
| 应用树有任何新增 / 缺失 / 改动 / 目录链接 | 「runtime integrity file count mismatch」或「runtime integrity mismatch: &lt;rel&gt;」 | `runtime-integrity.js:318-325,99,111` |
| 运行时闭包有任何新增 / 缺失 / 改动 | 「critical runtime file count mismatch」或「critical runtime integrity mismatch: &lt;rel&gt;」 | `runtime-integrity.js:335-342,146,148,175` |
| 超过文件数/字节上限 | 「runtime integrity file limit exceeded」等 | `runtime-integrity.js:104-108,153,176` |

统一后果：`failStartup(...)` → `killBackend()` + 启动状态窗显示「未加载不完整组件」→
**后端不启动、主界面不打开**。属于 fail-closed。
[证据: `main.js:273-286,1023-1027`]

---

### 4.7 与运行时实测日志的核对（含对附录 A 相位归属的修正）

主控在同一时间窗内取得了现场运行时日志
`%APPDATA%\ModexData\library-aJL7Wi\logs\startup-latest.json`
（该文件由产品自身的 `StartupStatus.persist()` 写入，见 `startup-status.js:84-89`），
并在附录 A 中列出 8 个阶段。

【直接提取】`elapsed_ms` 的语义是 `Date.now() - this.started`（`startup-status.js:78`），
即**自 `ready` 起的绝对累计毫秒**；每个阶段文本是在该阶段**动作开始前**写入的
（对照 `main.js:1019` 先 `set('integrity')`、`:1021` 才 `await verifyPackagedAppIntegrity()`）。
因此：**相邻两条 `set()` 的 `elapsed_ms` 之差 = 前一个阶段的实际耗时**。

按此规则重新计算（数据取自附录 A 表格）：

| 阶段 | 累计 elapsed_ms（起点→终点） | **该阶段实际耗时** | 该阶段包含的动作 |
|---|---|---|---|
| `update_recovery` | 0 → 251 | 251 ms | 托盘 + 等 helper + 事务回滚（`main.js:1000-1008`） |
| `integrity` | 251 → 255 | 4 ms | 仅写入阶段文案 |
| **`integrity` 校验本体** | **255 → 879,658** | **879,403 ms ≈ 14.66 分钟** | `verifyPackagedAppIntegrity()` + `verifyRuntime()` + `detectPythonInjection()`（`main.js:1019-1044`） |
| `storage` | 879,658 → 883,277 | **3,619 ms** | 资料位置校验（`main.js:1047-1052`） |
| `runtime` | 883,277 → 883,965 | 688 ms | `ensureMiKTeX()`（`main.js:1069-1076`） |
| `updates` | 883,965 → 911,978 | 28,013 ms | `initUpdater()` 联网检查（`main.js:1088-1096`） |
| `backend` | 911,978 → 1,015,491 | 103,513 ms | `startBackend()` + `waitForBackend()`（`main.js:1107-1109`） |
| `frontend` | 1,015,491 → 1,024,525 | 9,034 ms | `createWindow()` + 加载前端（`main.js:1112-1113`） |
| `ready` | 1,024,525 | — | 合计 **≈ 17.08 分钟** |

**结论（修正附录 A 第 2 条）**：

- 附录 A 把「14.7 分钟」记在 `storage` 阶段、并据此推断「`integrity` 仅 255 ms 完成，
  很可能并未真正完成全量校验」——按上述相位归属规则，**这个归因是反的**：
  4 ms 是写入文案的耗时，**879.4 秒全部是完整性校验本身**；`storage` 阶段只有 3.6 秒。
  [证据: `main.js:1019`（先 set 后 await）与 `startup-status.js:78`（elapsed 语义）]
- 因此**并非「未校验」**，而是**确实做了全量校验，只是慢得多**。
- 与 4.5 节的对照：本次热缓存实测吞吐 1188.3 MB/s ⇒ 纯吞吐外推 ≈ 3.6 s；
  现场实际 879.4 s ⇒ **有效吞吐约 4.86 MB/s**（4273.9 MB ÷ 879.4 s）。
  两者相差约 240 倍。差异来源符合 4.5 节的预判：**冷缓存 + 27,752 次独立
  open/read/close 的寻道成本 + 并发上限 4**。热缓存 1188 MB/s 是把大文件整体读入内存的
  顺序吞吐，不能代表本场景。【推断】
- 【直接提取】这同时说明：**`schema_version 2` 的「运行时闭包」不是纸面声明，
  而是在每次启动时真实核算的**——第 4.3 节的 27,752 条覆盖范围是实际执行范围。
- 代价是产品**每次冷启动要花约 15 分钟卡在完整性校验上**（占 17 分钟总启动时间的 86%）。
  这是蓝方**最大的可用性缺陷**，并在 6.3-G1 中作为 TOCTOU 讨论的另一面同时成立：
  校验极慢 ⇒ 校验与实际使用之间的时间窗极大（≈ 十几分钟到数小时）。

---

## 5. Electron 加固

### 5.1 `electron-fuses.js`：设置了哪些 fuse

【直接提取】打包期调用 `flipFuses`，并**强制要求全部 fuse 都被显式指定**：

```js
// asar/security/electron-fuses.js:38-51
await flipFuses(path.resolve(executablePath), {
  version: FuseVersion.V1,
  strictlyRequireAllFuses: true,
  [FuseV1Options.RunAsNode]: false,
  [FuseV1Options.EnableCookieEncryption]: true,
  [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
  [FuseV1Options.EnableNodeCliInspectArguments]: false,
  [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
  [FuseV1Options.OnlyLoadAppFromAsar]: true,
  // The package does not ship browser_v8_context_snapshot.bin.
  [FuseV1Options.LoadBrowserProcessSpecificV8Snapshot]: false,
  // The renderer still loads its static application through file://.
  [FuseV1Options.GrantFileProtocolExtraPrivileges]: true,
});
```
[证据: `asar/security/electron-fuses.js:38-51`]

**版本锁**：代码把期望的 fuse 线固化为常量，并解释原因：

```js
// electron-fuses.js:6-9
const FUSE_SENTINEL = Buffer.from('dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX', 'ascii');
// Electron 33 has eight V1 fuses. Keep this exact so an Electron upgrade that
// adds a fuse fails the build until the new security decision is reviewed.
const EXPECTED_FUSE_WIRE_V1 = '01001101';
```
[证据: `asar/security/electron-fuses.js:6-9`]

`hardenElectronExecutable` 结尾自校验，不符即抛 `Electron fuse hardening mismatch`。
[证据: `asar/security/electron-fuses.js:53-57`]

**本次实测：直接从出厂 exe 里读出 fuse 线，与代码期望值完全一致**

```
exe: E:\02_Installers\DailyApps\Modex-MH-Agent\Modex-MH-Agent.exe size: 188753408
sentinel offset: 158719472 (0x975ddf0)
fuse version: 1 length: 8 wire: 01001101
  [0] disabled RunAsNode
  [1] ENABLED  EnableCookieEncryption
  [2] disabled EnableNodeOptionsEnvironmentVariable
  [3] disabled EnableNodeCliInspectArguments
  [4] ENABLED  EnableEmbeddedAsarIntegrityValidation
  [5] ENABLED  OnlyLoadAppFromAsar
  [6] disabled LoadBrowserProcessSpecificV8Snapshot
  [7] ENABLED  GrantFileProtocolExtraPrivileges
```
[证据: 本次执行 `reports/_fx/read-fuses.js`，采用与 `readFuseWire` 相同的哨兵/头部解析逻辑]

【推断】上述「序号 → fuse 名」的映射由**代码自身的声明顺序**与实测线值互相验证：
8 个 fuse 的赋值恰好产生 `0,1,0,0,1,1,0,1`，与实读 `01001101` 逐位一致，
因此这个映射不是外部文档推测，而是自洽结果。

**逐项含义与安全意义**

| fuse | 值 | 意义 |
|---|---|---|
| `RunAsNode` | **false** | 禁止把 Electron 可执行文件当作纯 Node 运行；阻断「用签名宿主跑任意 JS」的手法 |
| `EnableCookieEncryption` | **true** | 用 OS 级密钥加密 Chromium cookie 库 |
| `EnableNodeOptionsEnvironmentVariable` | **false** | 忽略 `NODE_OPTIONS`；阻断通过环境变量注入 `--require` |
| `EnableNodeCliInspectArguments` | **false** | 忽略 `--inspect*` 系列；阻断 Node 调试器接入 |
| `EnableEmbeddedAsarIntegrityValidation` | **true** | 校验 `app.asar` 内嵌完整性（哈希写入主 EXE） |
| `OnlyLoadAppFromAsar` | **true** | 只从 `app.asar` 加载应用代码；**阻断 `resources/app/` 目录劫持加载** |
| `LoadBrowserProcessSpecificV8Snapshot` | **false** | 不带 `browser_v8_context_snapshot.bin`（该文件确实不在安装目录） |
| `GrantFileProtocolExtraPrivileges` | **true** | **授予 `file://` 额外权限**（唯一位「放宽」型设置） |

`OnlyLoadAppFromAsar=true` 与本产品双容器结构的关系【推断】：
产品的 Electron 主进程代码全在 `resources/app.asar`，而 `resources/app/` 目录只承载
**非 Electron 代码的数据与脚本**（后端 `.pyd`、`dist`、`tools`，以及由 `node.exe`
执行的 `update-helper.js`）。因此 `OnlyLoadAppFromAsar` 恰好阻断「往 `resources/app/`
丢一个 `main.js` 让 Electron 优先加载」这一经典劫持路径；
而 `resources/app/` 自身的完整性改由 Ed25519 签名清单负责（第 4 节）。

`GrantFileProtocolExtraPrivileges=true` 的注释理由（"The renderer still loads its static
application through file://"）**与实际代码不符**【直接提取 + 推断】：
- 主窗口加载的是 `http://127.0.0.1:${actualPort}`，不是 `file://`
  [证据: `asar/main.js:870,920`]
- 截图窗的 target 可以是 `file:`，但那只是**被截页面**的 URL，不是 Electron 的应用代码
  [证据: `asar/capture.js:13` 注释；`capture.js:687-697` webPreferences]
- `resources/app/dist` 的 135 个产物里**没有出现 `file://` 字面量**
  [证据: 对 `dist/assets/*.js` 全量 `Select-String -Pattern "file://"` 无命中]
【推断】该 fuse 在当前发行版中很可能**没有实际消费者**（见 6.3-G11）。

### 5.2 `electron-launch-policy.js`

已在 1.2 节展开。要点复述与补充：

- 22 项禁用开关 [证据: `electron-launch-policy.js:7-28`]
- 命名解析 `argvSwitchNames` 用 `/^--([^=\s]+)(?:=|$)/`，并 `toLocaleLowerCase('en-US')`
  归一化 [证据: `electron-launch-policy.js:30-37`]
- **只信 argv**，不信 `commandLine.hasSwitch()`，理由见源码注释 [证据: `:39-45`]
- 命中即先 `removeSwitch` 再抛错；调用方 `app.exit(78)` [证据: `:47-54`；`main.js:25-29`]
- **仅打包态生效**（`if (app.isPackaged)`）[证据: `main.js:23`]

### 5.3 `dev-isolation.js`

【直接提取】这是**开发期**的隔离验收机制，不参与生产安全边界（打包版直接拒绝）：

```js
// dev-isolation.js:168
if (app.isPackaged) throw new Error('正式安装版不接受隔离开发参数');
```
[证据: `asar/security/dev-isolation.js:168`]

设计要点：

| 机制 | 实现 | 行号 |
|---|---|---|
| 目录名格式白名单 | `/^account-real-dev-\d{8}T\d{6}-\d{3}-[a-f0-9]{8}$/`，且必须是 `<repo>/output/<该名>` | :8, 69-71 |
| 拒绝链接/重解析目录 | `lstatSync().isSymbolicLink()`、`realpathSync()` 与绝对路径小写比对 | :11-19 |
| 标记文件校验 | 必须有 `dev-isolation.json`，`schema_version===1` 且 `repository` 匹配 | :72-73 |
| 拒绝混入用户资料 | root 下出现 `db` / `workspaces` / `data_location.json` 任一即拒绝 | :74-76 |
| 递归扫描拒绝链接/硬链接 | 深度 ≤64、条目 ≤100000、`nlink !== 1` 即拒绝 | :49-65 |
| 旧进程必须已退出 | `requireExited(pid)`：`kill(pid,0)` 必须抛 `ESRCH`，否则拒绝（连 PID 复用也保守拒绝） | :38-47 |
| 前端产物新鲜度 | 校验 `index.html` 入口脚本存在、`build-info.json` 版本等于 `desktop/package.json`、构建时间不晚于现在+5 min、`web/frontend/src` 无文件比构建时间新 | :130-160 |
| 一次性锁 | `.resume-start.lock` 用 `openSync(...,'wx')`，`finally` 关闭并删除 | :174-201 |
| 路径重定向 | `app.setPath` 四个路径 + `APPDATA/LOCALAPPDATA/TEMP/TMP` + 三个 `MODEX_DEV_*` 变量 | :182-199 |

**日志与标题**：隔离实例窗口标题被改为「Modex-MH-Agent · 真实账户验收（独立资料）」，
且 `page-title-updated` 被 `preventDefault`，防止前端把标题改回去。
[证据: `asar/main.js:859,901`]

### 5.4 `capture.js`（`--mh-capture`）窗口加固

【直接提取】截图模式给 `BrowserWindow` 的加固参数并不弱：

```js
// capture.js:687-697
webPreferences: {
  offscreen: false,
  // 截的是用户生成的项目页面，禁用 node 集成防脚本越权
  nodeIntegration: false,
  contextIsolation: true,
  sandbox: true,
  webSecurity: true,
  allowRunningInsecureContent: false,
  webviewTag: false,
  navigateOnDragDrop: false,
},
```
外加 [证据: `capture.js:699-702`]：
```js
win.webContents.session.setPermissionCheckHandler(() => false);
win.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
win.webContents.on('will-attach-webview', event => event.preventDefault());
```
以及无头稳定性开关 `disableHardwareAcceleration` / `disable-gpu` / `disable-software-rasterizer`
[证据: `capture.js:36-38`]。

问题不在窗口参数（那些都对），而在**该模式的编排位置**（见 6.3-G3）。

### 5.5 CSP：Electron 侧不设置，由后端响应头提供（本版修正）

#### 5.5.1 Electron 主进程侧：**没有**

【直接提取】对全部解包源码 grep `Content-Security-Policy` / `onHeadersReceived` /
`webSecurity` / `allowRunningInsecureContent` / `setPermissionRequestHandler`，
在 asar 内**只有 4 处命中**，全部与主窗口无关：

| 命中位置 | 内容 |
|---|---|
| `asar/security/startup-status.js:23` | 启动状态窗（`data:` URL）内的 `<meta http-equiv="Content-Security-Policy">` |
| `asar/capture.js:693` | `webSecurity: true`（截图窗） |
| `asar/capture.js:694` | `allowRunningInsecureContent: false`（截图窗） |
| `asar/capture.js:700` | `setPermissionRequestHandler(... => callback(false))`（截图窗） |

- `main.js` 未设置任何 CSP，也未注册 `session.webRequest.onHeadersReceived` 注入响应头。
  [证据: 上述 grep；`main.js:853-934` 的 `createWindow` 全文未见相关调用]
- 前端入口 HTML 亦无 CSP meta（全文 22 行已读）。
  [证据: `E:\02_Installers\DailyApps\Modex-MH-Agent\resources\app\dist\index.html:1-22`]

#### 5.5.2 后端侧：**有 CSP 与安全响应头中间件**（关键修正）

【直接提取】后端 `main.cp311-win_amd64.pyd` 的符号表中存在以下符号：

| 符号 | 推断职责 |
|---|---|
| `main._desktop_content_security_policy` | 构造桌面端 CSP 策略 |
| `main.desktop_security_headers` | 注入安全响应头（Cython 生成 `__pyx_scope_struct_10_desktop_security_headers`） |
| `main.desktop_origin_and_update_middleware` | Origin 校验 + 更新相关中间件（`__pyx_scope_struct_7_...`） |
| `main._is_same_origin_preview_response` | 预览响应同源校验 |
| `main.license_middleware` | 许可证闸（请求级） |
| `main.health` / `main.prepare_desktop_update` | 对应 `GET /api/health` 与 `POST /api/health/update`（后者的调用方即 `main.js:1263-1275` 的 `updateBarrier`） |

[证据: `strings/main.cp311-win_amd64.pyd.strings.txt:136-147,167-172,148-150`；
本报告 §1.14 与 §3.9.1 的调用方对照]

**因此修正 §5.5 的结论**：主窗口并非「无 CSP」，而是
**「CSP 与安全响应头由 Python 后端在 HTTP 响应中下发，Electron 侧不提供任何兜底」**。
【推断】这一点与 §2.7 的信任锚分析形成互补：后端同时扮演
「内容提供方」与「安全头提供方」，因此同源策略的实际强度取决于
`desktop_origin_and_update_middleware` 的正确性，而它在 Electron 侧没有任何第二道防线。

#### 5.5.3 无法评估的部分（不臆造）

【直接提取】对全部 `.pyd` 字符串表 grep `Content-Security-Policy` /
`script-src` / `default-src` / `frame-ancestors` / `X-Frame-Options` /
`Strict-Transport-Security` / `Referrer-Policy`，**零命中**。
[证据: 对 `strings/_merged_strings.txt`（381 KB）与 `reports/_fx/strings.txt`（357 KB）
分别 grep，均无匹配]

【推测】因此**CSP 的具体指令串未能提取**——它很可能是在 `_desktop_content_security_policy`
中由变量/常量拼接构造，或在 Cython 编译后未以明文常量落到字符串表。
按「严禁臆造」原则，**本报告不对其强度作任何评价**，仅确认其存在位置与下发路径。
【推测】如需完整指令串，须动态抓取响应头；而该路径受后端运行时守卫限制
（见附录 B 的 `RuntimeInspectionUnavailable`），静态分析到此为止。

#### 5.5.4 对照：启动状态窗的 CSP 反而是严格的

```
// startup-status.js:23
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';
 script-src 'none'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
```
[证据: `asar/security/startup-status.js:23`]

【推断】该窗口自身注释即声明「never loads backend code, a preload, network resources or
scripts」（:3-4），与 `script-src 'none'` 一致，属于正确的最小权限实践。

### 5.6 其余与加固相关的运行时设置（汇总）

| 设置 | 值 | 证据 |
|---|---|---|
| 主窗口 `contextIsolation` | `true` | `main.js:863` |
| 主窗口 `nodeIntegration` | `false` | `main.js:864` |
| 主窗口 `sandbox` | `true` | `main.js:865` |
| 全局 `app.enableSandbox()` | **未调用**（只在每个窗口单独设 `sandbox:true`） | 全 asar grep `enableSandbox` 无命中 |
| 协议注册（`registerFileProtocol` 等） | **无** | 全 asar grep 无命中 |
| 自定义证书校验（`setCertificateVerifyProc`） | **无**（走系统信任库） | 全 asar grep 无命中 |
| 主窗口权限处理器 | **未设置**（仅截图窗显式全拒） | `main.js` 无 `setPermission*`；`capture.js:699-700` |
| 新窗口一律 deny | 是 | `main.js:886`；`startup-status.js:59`；`capture.js:701` |
| `will-navigate` 限同源 | 是 | `main.js:888-898` |
| 控制令牌注入 | `onBeforeSendHeaders`，限于 `appOrigin/*` 与同端口 `ws://` | `main.js:872-878` |
| Electron 侧 CSP | **无** | §5.5.1 |
| 后端侧 CSP + 安全头 + Origin 中间件 | **有** | §5.5.2 |
| 构建期自检脚本 | `desktop/scripts/audit-electron-fuses.js`、`after-pack-integrity.js`、`smoke-packaged-electron-integrity.js`、`authenticode-tools.js`、`audit-authenticode-release.js`、`generate-update-keys.js`、`publish-signed-update.py`、`publish-full-installer.js`、`verify-packaged-update-gate.py`、`test-installer-acl-elevated.ps1`、`collect-hook-forensics.ps1` | `reports/build-inputs-paths.txt` 中 `desktop/scripts/*` 条目（`:473`、`:481`、`:353`、`:41`、`:404`、`:396`、`:401`、`:449`、`:235`、`:253`、`:138`） |

【直接提取】`build-inputs.js` 明确把 `desktop/security` 与 `desktop/scripts` 纳入
「发布前必须检查源码新鲜度」的范围：

```js
// asar/security/build-inputs.js:22-26
for (const dir of ['web/backend/services','web/backend/routers']) visit(dir, new Set(['.py','.md']));
visit('web/backend/db', new Set(['.sql']));
visit('tools', new Set(['.py','.js','.json']));
visit('desktop/security', new Set(['.js']));
visit('desktop/scripts', new Set(['.js','.py','.ps1','.nsh']));
visit('web/frontend/src', new Set(['.ts','.tsx','.js','.jsx','.css','.json','.svg']));
```
[证据: `asar/security/build-inputs.js:1-31`]

【推断】其意图（原文注释）："Source freshness (not just artifact self-consistency) for
every application module. Kept shared by build and release preflight so new files cannot be
accidentally omitted from a hand-maintained protected-module list."
这解释了 `build-inputs-paths.txt` 中 `desktop/security/*` 与 `desktop/scripts/*` 的出现，
也是第 3.1 节「源码哈希 = 部署哈希」证据链的成因。

---

## 6. 红队评估

### 6.0 评估方法与评级口径

- 仅做**静态分析**与**本机只读测量**。未修改任何目标文件，未实施任何攻击，未运行目标程序。
- 评级口径：
  - **可利用性** = 「攻击者需要什么前提才能用上这条路」。
    【高】= 普通未提权本地进程即可；【中】= 需要特定时机/特定用户交互/需要先拿到旧签名产物；
    【低】= 需要管理员、需要伪造 CA、或需要已被攻破的前提。
  - **影响面** = 「用上之后能得到什么」。
    【高】= 以用户身份执行任意代码 / 绕过全部完整性保证且不留痕；
    【中】= 拒绝服务、信息泄露、降级到更旧的已签名版本；
    【低】= 仅影响体验或需要已有等价权限。
- 每条给出 `依据`，并标注 `【直接提取】/【推断】/【推测】`。

### 6.1 真正的密码学保证 / 真实控制（C 系列）

#### C1. 更新清单与完整性清单的 Ed25519 签名，且信任根编译期固化 ★核心

- **事实**：`crypto.sign(null, canonicalJson, key)` / `crypto.verify(...)`，密钥强制
  `asymmetricKeyType === 'ed25519'`，签名长度强制 64 字节，`key_id` 双向绑定。
  [证据: `update-security.js:174-197,165-172`；`runtime-integrity.js:270-292`]
- **信任根固化**：`PINNED_CHANNEL='intl'`、`PINNED_UPDATE_SERVER='https://up.mingheng.xin'`、
  `PINNED_UPDATE_PUBLIC_KEYS` 单键，`assertPinnedUpdateConfig` 强制
  **通道 / 服务器 / 公钥键集合（数量+逐项名）/ 公钥值（逐字符）/ epoch ≥ 2** 全部相符。
  [证据: `release-trust.js:3-37`]
- **本机独立验签通过**：`signature verifies: true`，canonical JSON 5,001,244 字节。
  [证据: 0.3 节]
- **为什么是真保证（而非混淆）**：验证方只持有公钥；`canonicalJson` 是确定性序列化
  （键排序、整数强制），不存在「同语义不同字节」的签名绕过；schema 白名单使攻击者无法
  添加字段改变语义。Ed25519 在标准模型下不可伪造。
- **可利用性**：【低】（需要私钥）。
- **影响面**：若私钥泄露 → 全线失守（更新 + 完整性双用途、单密钥、无阈值签名）。
  [证据: `updater-config.json:11` 自述私钥保存在本机 gitignored `_local-secrets`]
- **残余缺口**：单密钥、无轮换/吊销设计（见 G13）。

#### C2. 签名内容的严格 schema 与路径规范化

- **事实**：清单字段白名单（未知字段即抛）、路径拒绝 `\`/`\0`/`:`/前导 `/`/`.`/`..`、
  拒绝 Windows 8.3 短名 `~\d+` 与尾随点/空格、NFC 规范化、**大小写不敏感查重**、
  强制升序排列（乱序即报错）。
  [证据: `update-security.js:42-67,88-95,125-151`；`runtime-integrity.js:65-75,233-249`]
- **为什么是真保证**：这些精确对应真实攻击类——路径穿越（`..`）、NTFS 备用数据流与
  短名别名（`~\d+`、`:`）、大小写不敏感文件系统上的同名覆盖、以及「顺序不同→哈希不同」
  的签名歧义。属于工程上少见的高质量实现。
- **可利用性/影响面**：【低】/【低】（这些控制的目标是**防止**上述攻击成立）。

#### C3. 逐文件 sha256 的三层校验 + 内容寻址下载

- **事实**：下载流式哈希（并强制 size 精确相等）→ staging 复制后再验 → 落盘后
  `verifyInstalledTree` 全树复核；schema 2 的下载 URL 为
  `/files/<sha256 前 2 位>/<sha256>.bin`（内容寻址）。
  [证据: `updater.js:220-308,485`；`update-transaction.js:48-74,105-119,219`]
- **可利用性/影响面**：【低】/【低】。

#### C4. 完整安装包的 Windows Authenticode 强校验

- **事实**：必须 `Status == 'Valid'`，且**必须同时存在** `SignerCertificate` 与
  `TimeStamperCertificate`，加 SHA-256 与 `Subject` 精确匹配，最后才
  `Start-Process -Verb RunAs`。[证据: `installer-update.js:39-44`]
- **为什么是真保证**：`Status == 'Valid'` 由 Windows 链式信任计算，时间戳证书强制
  保证签名在证书过期后仍可验证；SHA-256 把「签名有效」锚定到清单里那一个确定文件。
- **可利用性**：【低】（需要能签发可信代码签名证书 + 命中同一 Subject 字符串）。
- **残余弱点（【推断】）**：发布者绑定用的是 `Subject` **字符串**比较，而不是证书
  指纹/公钥哈希。同 Subject 但不同密钥的证书在理论上可被 CA 重新签发，因此
  **弱于指纹锁定**；且 Subject 字符串的编码/顺序变化会造成误拒（可用性问题）。
  影响面【低】，因为攻击者仍需拿到受信任 CA 签发的代码签名证书。

#### C5. 控制令牌只在「操作系统确认端口归属」之后才发送 ★核心

- **事实**：轮询前与建连后各做一次 `netstat -ano -p tcp` 归属核验（端口 + LISTENING
  行 PID + 连接四元组 clientPort 必须唯一且属同一 PID），通过后才允许写入任何 HTTP 字节。
  [证据: `backend-health.js:11-45,84-88`；`backend-port-owner.js:22-34`]
- **为什么是真保证**：它防的是真实且容易被忽视的攻击——**本地端口抢占后窃取控制令牌**。
  归属判定基于内核 TCP 表而非 HTTP 自述，攻击者无法用「伪造一个 /api/health 响应」
  骗过它（响应内容只在归属通过后才被采纳）。
- **可利用性**：【低】/ **影响面**：阻止了「本机不可信进程冒充后端拿到令牌」这一整类攻击。

#### C6. Electron fuse 组合（实测 8 项）

- **事实**：`01001101`，禁用 `RunAsNode` / `NODE_OPTIONS` / Node inspector，
  开启 ASAR 内嵌完整性 + `OnlyLoadAppFromAsar`。[证据: 5.1 节实测输出]
- **为什么是真保证**：这些是 Chromium/Electron 二进制的**编译期**开关，不是 JS 层检查，
  攻击者无法在运行时打开；`OnlyLoadAppFromAsar` 直接封掉「往 `resources/app/` 丢
  `main.js` 让 Electron 优先加载」这一经典劫持。
- 残余问题：`GrantFileProtocolExtraPrivileges=true` 与需求不符（G11）；
  `app.asar` 可被用户写入但被 fuse 拒绝加载（G7/G9）。

#### C7. 更新事务的崩溃一致性（journal + 备份 + 启动恢复）

- **事实**：`backup_complete` journal 先落盘再改文件；失败全量回滚；
  断电后下次启动按 journal 回滚；备份与 journal 都用 `wx` 独占 + `fsync` + 同目录 `rename`。
  [证据: `update-transaction.js:19-30,192-236`；`update-helper.js:59-62,66-75`；`main.js:1008`]
- **为什么是真保证**：这不是「尽力而为」——journal 的写入**先于**任何破坏性操作，
  且状态机只有三个可判定态（`backup_complete` / `committed` / `rolled_back`）。
- 残余缺口：journal 本身无签名（G9）；`copyVerified` 用 `rm + rename` 而非原地原子替换
  （见 G1 附注）。

#### C8. 后端运行时守卫：导入期拒绝带外加载

- **事实**：尝试把编译后的 FastAPI app 当普通模块导入时被直接拒绝：
  `RuntimeInspectionUnavailable: 完整性验证或运行时约束未通过，未执行任何能力；请使用官方安装器修复`。
  [证据: 主控附录 B 实测；`strings/services__runtime_guard.cp311-win_amd64.pyd.strings.txt` 存在]
- **为什么是真保证**：它堵住了静态分析最省力的两条路——(a) `import` 后自省符号，
  (b) 把后端抽出安装目录独立运行。且**在导入期而非请求期**执行，不存在
  「先起来再验」的窗口。
- **可利用性**：【低】/ **影响面**：显著提高动态分析与二次利用成本。

#### C9. 后端环境消毒 + 解释器隔离模式 + 令牌不入命令行

- **事实**：剔除 20 个敏感环境变量（`PYTHONPATH`/`NODE_OPTIONS`/`SSL_CERT_FILE`/
  `NODE_TLS_REJECT_UNAUTHORIZED`/`OPENSSL_MODULES` 等）；打包态用
  `python -I -B -X utf8 -c <bootstrap>`（`-I` = isolated，忽略 user site 与
  `PYTHONPATH`）；控制令牌只经环境变量传递，不出现在 argv 中。
  [证据: `backend-environment.js:5-16`；`main.js:604-613,672`]
- **可利用性/影响面**：【低】/【低】——但它封掉了「用环境变量向子进程注入
  Python/Node/OpenSSL 行为」这一常见且低门槛的持久化手法。
- 残余缺口：开发态**探测**用的 `probeEnv` 是 7 项白名单，但**真正的 spawn 用的是
  消毒后的完整环境**（`sanitizeBackendEnvironment(process.env)` 仍然保留了
  `PATH`/`APPDATA`/`TEMP` 等，这是必要的）。[证据: `main.js:645-660`] 【推断】一致性可接受。

#### C10. 后端侧 CSP / 安全响应头 / Origin 中间件（存在性确认，强度未评估）

- **事实**：`main._desktop_content_security_policy`、`main.desktop_security_headers`、
  `main.desktop_origin_and_update_middleware`、`main._is_same_origin_preview_response`。
  [证据: `strings/main.cp311-win_amd64.pyd.strings.txt:136-147`]
- **评估**：控件**存在**，但具体 CSP 指令串**未能静态提取**（全字符串表 grep 零命中），
  因此**不对其强度作任何评价**。【推测】需要动态抓取响应头才能定论。
  这一点直接决定了 G4 的严重程度上限。

### 6.2 仅属混淆 / 威慑 / 体验性质（D 系列）

#### D1. 错误弹窗中的密钥脱敏 `safeDetail`

- 正则脱敏 PEM 块、`sk-*`、`Bearer *`、`api_key|password|secret|token|authorization`
  赋值，并截断 12000 字符。[证据: `startup-status.js:8-14`]
- **定性**：**混淆/卫生措施**。它降低的是「用户把截图发到群里时泄露密钥」的概率，
  对拥有本机访问权的攻击者无任何作用（他们直接读文件）。
- **可利用性/影响面**：【低】/【低】。

#### D2. 大量安全劝导文案（社会工程防御）

- 典型原文：「不要关闭实时防护，也不要把安装目录或 python.exe/node.exe 加入全局排除项。」
  「不要从第三方网站单独下载 DLL，也不要删除资料。」
  「请管理员查看 CodeIntegrity/Operational 中的 3077、3089 事件。」
  [证据: `main.js:178`；`backend-startup-error.js:10-18,18`]
- **定性**：**威慑/引导**，不是技术控制。相反，这些文案是本产品**质量较高**的一面——
  它明确拒绝「加排除项/关防护」这类典型的错误修复建议。但它不能阻止攻击者，
  也不减少攻击面。**可利用性/影响面**：【低】/【低】。

#### D3. `cleanupLeakedBackendSources()` —— 反编译卫生，且在流水线中位置冗余

- 删除 `backend/services`、`backend/routers` 下所有 `.c` 与「与某个 `.pyd` 同名」的 `.py`，
  并清理 `runtime/python` 的 `__pycache__` / `.pyc` / `.pyo`。
  [证据: `main.js:530-579`]
- **定性**：目的是减少可反编译产物（Cython 静默降级导致源码被打包），属**混淆/卫生**。
- 【推断】**位置冗余**：该函数在 `main.js:1100` 调用，位于 `verifyPackagedAppIntegrity()`
  （:1021）**之后**。而第 4 节证明签名清单是**精确集合比对**——若 `resources/app/backend`
  下真存在多余的 `.c`，`:1021` 会先失败，根本走不到 `:1100`。
  因此对 `.c` / 同名 `.py` 的删除在实际发行版中**永远不会生效**（只在
  「清单已包含它们」这种不该发生的前提下才有意义）。
  真正生效的是其中对 `runtime/python` 易变缓存的清理（该部分不在哈希闭包内）。
- **可利用性/影响面**：【低】/【低】（它不保护任何东西，只是一个死分支）。

#### D4. `verifyRuntime()` 的尺寸窗口检查

- 只检查 `python.exe`(50 KiB–500 KiB)、`python311.dll`(≥1 MiB)、`python311.zip`(≥1 MiB)、
  `node.exe`(≥10 MiB) 的存在与大小区间。[证据: `main.js:132-159`]
- **定性**：**体验性防误报**（针对杀软隔离），不是完整性控制。同尺寸替换可完全绕过。
  注释本身也承认目标：「不要让用户看到神秘的 ENOENT」。[证据: `main.js:127-131`]
- **可利用性**：【高】（改一个字节大小不变即绕过）。
- **影响面**：【低】**但仅在它被当作防线时**——真正的防线是第 4 节的哈希闭包（已覆盖
  `python.exe`、`python311.dll`、`python311.zip`、`node.exe` 中的前三个与第 4 个，
  见 `CRITICAL_RUNTIME_FILES`，唯独 `node\subprocess` 之外的 `runtime/git`、`pandoc` 也已覆盖）。
  【推断】所以这一条是「冗余但无害」。

#### D5. 启动状态窗的严格 CSP

- `default-src 'none'; script-src 'none'; connect-src 'none'`。[证据: `startup-status.js:23`]
- **定性**：**真实控制但价值低**——被保护的窗口本身不加载任何外部/敏感内容
  （原文：`This shell never loads backend code, a preload, network resources or scripts.`）。
- **可利用性/影响面**：【低】/【低】。

#### D6. Cython 编译 `.pyd` + skill capsule 加密

- 后端核心逻辑全部编译为 `*.cp311-win_amd64.pyd`（157 个，28.89 MB）
  [证据: 0.4 节 `files` 扩展名分布]，另有 `services/skill_crypto`、`skill_capsule` 模块
  [证据: `strings/services__skill_crypto.cp311-win_amd64.pyd.strings.txt` 等文件存在]。
- **定性**：**混淆**。Cython 只提高反编译成本（不改变语义可恢复性）；
  客户端加密的密钥必须随客户端分发或可由客户端推导，因此对抗「有本机完整访问权的
  攻击者」时**不构成密码学边界**——本报告不对其强度作评价（超出本次范围）。
- **可利用性/影响面**：【中】（抬高门槛）/【低】（不改变最终可达能力）。

#### D7. 禁用开关列表的「时间窗」局限（详见 G2）

- **定性**：`electron-launch-policy.js` 的检查在 `main.js` 执行时才发生，属**运行时**检查；
  对**已由 Chromium 早期消费**的开关，`removeSwitch` 只能是事后补救。见 G2。

### 6.3 设计缺口（G 系列）

#### G1. 完整性校验只发生在启动瞬间 —— TOCTOU 窗口可达十几分钟到数小时 ★最高优先

- **事实（校验时机）**：
  - `verifyRuntimeTree` 全仓只有 2 处引用：定义与 `main.js:116` 的唯一调用。
  - 该调用发生在 `openApplication()` 内，即**启动一次，之后不再校验**。
  - 校验完成后**不持有任何文件句柄**（`sha256File` 用完即 `close`），
    也不对已校验文件加锁/只读句柄。
  [证据: `main.js:1016-1027`；`runtime-integrity.js:77-85,310-352`；全仓 grep `verifyRuntimeTree`]
- **事实（窗口长度）**：主控运行时日志显示完整性阶段本身耗时 **879.4 秒（14.66 分钟）**
  （4.7 节重算），即校验是**串行推进**的：先哈希 A，再哈希 B……
  一个在 A 被哈希**之后**才写入的 A' 不会被发现。随后应用进入长达数小时的正常使用期，
  期间 `resources/app/backend/**/*.pyd` 由 Python 在**用户点击相应功能时**按需 import。
- **事实（可达性）**：本机实测 ACL 显示 `resources/`、`resources/app/`（含
  `resources/app.asar`）、`Modex-MH-Agent.exe` 对当前普通用户 `FORESAKE\SAKE`
  授予 **FullControl**，而 `whoami /groups` 显示当前令牌为
  **Medium 完整性、Administrators 为 deny-only**（即**非提权**）：
  ```
  === E:\...\Modex-MH-Agent\resources ===
  FORESAKE\SAKE | Allow | FullControl | INHERITED
  BUILTIN\Users | Allow | ReadAndExecute, Synchronize | INHERITED
  === E:\...\Modex-MH-Agent\resources\app ===
  FORESAKE\SAKE | Allow | FullControl | INHERITED
  === E:\...\Modex-MH-Agent\resources\app.asar ===
  FORESAKE\SAKE | Allow | FullControl | INHERITED
  === E:\...\Modex-MH-Agent\runtime ===
  （无 SAKE 项）BUILTIN\Users | Allow | ReadAndExecute, Synchronize
  ```
  [证据: 本次 `Get-Acl` / `icacls` 实测；`whoami /groups` 实测]
- **【推测】关于该 ACL 的可推广性（重要限制）**：安装根目录自身的 ACL **不含** SAKE 项
  （仅 SYSTEM/Administrators FullControl、Users RX），而子目录却带 `(I)` 继承标记的
  SAKE:FullControl —— 这种「子项带继承标记、父项却没有对应 ACE」的状态，通常由
  「先授予继承权、后替换父项 ACL 且未传播」造成。因此**这可能是本分析机上
  「以用户身份落盘/自更新」留下的痕迹，而非官方 NSIS 安装器的默认结果**。
  佐证：`desktop/scripts/test-installer-acl-elevated.ps1`、`desktop/scripts/installer-preflight.ps1`
  存在于源码树中 [证据: `reports/build-inputs-paths.txt:253,465`]，说明厂商**确实在做**
  安装器 ACL 的构建期测试。
  **结论**：把「`resources/app` 用户可写」当作**本机实测事实**（【直接提取】）是可靠的；
  把它当作**所有安装的普遍事实**只是【推测】，须以目标机器实测 ACL 复核。
- **【推断】另一条独立论据（不依赖 ACL）**：**更新机制本身要求用户对 `resources/app`
  有写权限** —— 文件增量更新由 `update-helper.js` 以**用户权限的 node.exe** 执行，
  全程不提权 [证据: `updater.js:603-621`；`update-helper.js:55-88`]，而
  `resources/app.asar` 被 `FULL_INSTALLER_ONLY_PATHS` 明确禁止走增量路径
  [证据: `update-security.js:17-24`]。因此「为了让更新能落盘而放开 `resources/` 的写权限」
  是一个**结构性动机**，与实测 ACL 一致。
- **可利用性与影响面**：
  - **可利用性：【中～高】**。条件 = 能以用户身份写文件（本机实测满足）+ 能选择时机。
    不需要管理员、不需要绕过签名（因为**根本不再校验**）。
    最简单的形态：在应用运行期替换 `resources/app/backend/services/chat_executor...pyd`
    或 `resources/app/dist/assets/*.js`（若前端会被重新加载/新窗口加载），
    或替换尚未被 import 的后端模块。
    **注意**：任何**持久**改动会在下一次启动被 fail-closed 拦住，所以有效利用要求
    「用完即还原」或「在本次会话内完成」，这降低了稳定利用的可行性。
  - **影响面：【高】**。获得的是**以用户身份执行任意代码**，且可完全控制一个已经
    **持有 `MODEX_CONTROL_TOKEN`、持有 license 凭据、并处于用户完全信任语境**的进程。
- **附注（`copyVerified` 的非原子窗口）**：`copyVerified` 的实现是
  `rm(dest)` 然后 `rename(tmp, dest)` [证据: `update-transaction.js:72-73`]，
  两步之间目标文件**短暂不存在**。这本身不构成新漏洞（此时应用已退出），
  但说明「原子替换」在该项目里也是**近似**而非严格保证。属于同一类问题的补充证据。

#### G2. 启动开关检查的时机：`app.exit(78)` 未必来得及拦住 Chromium 早期消费的开关

- **事实**：检查在 `main.js` 顶层（应用 JS 开始执行时）才进行：
  ```js
  // main.js:23-31
  if (app.isPackaged) { enforceProductionLaunchPolicy(app.commandLine, process.argv); ... app.exit(78); }
  ```
  `enforceProductionLaunchPolicy` 内部对命中的开关调用 `commandLine.removeSwitch(name)`
  后抛错。[证据: `electron-launch-policy.js:47-54`]
- **【推断】问题**：`--remote-debugging-port`、`--js-flags`、`--inspect*` 等属于
  Chromium/V8 **进程早期**消费的开关，其中一部分（如 `--js-flags`）在 V8 初始化时生效，
  而 V8 初始化早于应用 JS 执行。`removeSwitch` 是在**已经太晚**之后才移除的；
  真正起作用的是随后的 `app.exit(78)`——但 `exit(78)` 也只是让进程尽快终止，
  在「V8 已被 `--js-flags` 影响」这一情形下不能保证没有副作用。
  源码注释显示作者已意识到相关风险（"Chromium's --remote-debugging-port is
  independent of the Node inspector fuse"）[证据: `main.js:19-22`]，
  但**补偿手段仍只是运行时检查**。
- **可利用性与影响面**：
  - **可利用性：【中】**。需要能以自己的参数启动该 exe。
    但注意：能这样做的人**通常已经是同一用户**，因此实际增益取决于
    「能否借此读到别的进程/其他用户的数据」。
  - **影响面：【中～低】**。`app.exit(78)` 的 fail-closed 大幅限制了实际收益；
    fuse（C6）已经封掉了 Node inspector / NODE_OPTIONS 两条最有力的路。
    主要残余是**「进程内短窗口内的调试能力」**与**「DoD/审计意义上检查发生得太晚」**。
- **建议（仅为评估意见，未实施）**：把这类开关的拒绝下沉到**更早的层**
  （如自我重启的 launcher、或安装器生成的快捷方式固定参数），
  或对 `commandLine` 的检查改为在 `app.on('will-finish-launching')` 之前完成。

#### G3. `--mh-capture` 截图模式的编排位置在安全链之前 ★重要

- **事实**：该分支在 `main.js:40-43`，位于 `dev-isolation`(P2)、单实例锁(P3)、
  用户存储(P4) **之前**，且直接 `return`：
  ```js
  if (process.argv.includes('--mh-capture')) { require('./capture').runCaptureMode(); return; }
  ```
  因此该模式**跳过**：单实例锁、更新事务恢复、Ed25519 完整性校验、`verifyRuntime`、
  `detectPythonInjection`、资料位置校验、更新配置校验（`assertPinnedUpdateConfig`）、托盘。
  [证据: `main.js:33-43` 与 `main.js:999-1121` 对照]
- **事实**：该模式的配置来自**命令行指定的任意 JSON 路径**，`targets[].url` 或
  `targets[].file` 可为任意值，`out` 为任意输出路径，并能 `printToPDF`
  [证据: `capture.js:7-21,654-665,668-676`]。
- **事实**：窗口本身加固良好（sandbox/contextIsolation/webSecurity/permission 全拒）
  [证据: `capture.js:687-702`]，且不在该模式下注入 preload/skill/后端。
- **可利用性与影响面**：
  - **可利用性：【高】**（本机已登录用户可直接带参数运行 exe；且 C1 级的
    `enforceProductionLaunchPolicy` 仍会在它之前运行，故无法借此打开 `--no-sandbox` 等）。
  - **影响面：【中】**：
    1. **本地文件读取的侧信道**：把 `file:` 指向本机 HTML，再 `printToPDF` 到攻击者
       指定路径，可把本机文件的渲染结果带走（对 HTML/文本类有效，
       且受同源/`file://` 权限影响）。
    2. **任意路径文件写入**：`out` 不受约束，可写出 PNG/PDF（内容受限于被截页面）。
    3. **完整性保证被整体旁路**：这是**唯一一条能跳过 Ed25519 校验的启动路径**。
       【推断】因为该模式不加载后端、不加载 preload、不加载 skill，
       所以「旁路」的实际收益有限——但它在**语义上**构成了安全链的一个缺口：
       产品文档/审计若声称「启动即校验」，则该模式是例外。
  - **【推测】**：`--mh-capture` 由后端在设计上调用，属于**有意设计的内部接口**。
    真正的改进方向是给它加一个「由主进程生成的一次性令牌/父进程校验」
    （类似 `fresh-start` 的 token 设计），而不是取消功能。

#### G4. 渲染进程信任锚 = 后端同源；Electron 侧无 CSP 兜底 ★重要

- **事实**：所有 9 个 IPC handler 的准入条件是
  `new URL(event.senderFrame.url).origin === 'http://127.0.0.1:' + actualPort`
  [证据: `main.js:1236-1241`]，而主窗口正是从这个 origin 加载的
  [证据: `main.js:920` `win.loadURL(appOrigin)`]。
- **事实**：Electron 主进程侧**不设置任何 CSP**，也不注册 `onHeadersReceived` 注入
  [证据: 5.5.1 节 grep 结果]；前端 `dist/index.html` 也没有 CSP meta。
- **事实（修正）**：CSP 与安全响应头、Origin 校验**由后端中间件提供**
  [证据: 5.5.2 节符号]，但**指令串不可静态提取**，强度未知。
- **【推断】风险链**：该 origin 同时托管「应用前端 bundle」与「后端 API」，
  并且（按产品功能推断）还托管用户/工作流产出的**可预览内容**。
  一旦存在任意「同源 HTML/JS 注入」（例如某个预览接口把用户内容以 `text/html` 返回），
  注入脚本即获得全部 `electronAPI` 能力：
  | 可达能力 | 直接后果 |
  |---|---|
  | `updater.startDownload` / `applyAndRestart` / `abort` / `skipVersion` | 触发签名更新全流程（受签名保护，收益有限）、干扰更新 |
  | `dialog.pick-folder` | 诱导用户选目录并回传真实路径（信息泄露） |
  | `latex.install` | **触发 `runtime\miktex-setup.exe` 执行**——而该文件**不在**任何哈希清单内（见 G7），见下方复合链 |
  | `updater.skipVersion(payload)` | 任意值写入 `updater-state.json`（G14） |
  若 Electron 侧存在第二道 CSP，注入脚本的外发/内联执行会被进一步限制；
  现在这一层**不存在**。
- **可利用性与影响面**：
  - **可利用性：【中】**：需要先找到一个同源注入点。本报告**未发现**具体注入点
    （未审计 92 条前端 API 与后端渲染逻辑），因此这是**条件性**结论。
  - **影响面：【中～高】**：取决于 `desktop_security_headers` 的实际强度。
    若后端 CSP 严格（`script-src 'self'` 且无 `unsafe-inline`），影响可降至【低】；
    若缺失或宽松，则 IPC 面被完整暴露。
- **复合链（G4 × G7）**：`latex:install` → `main.js:463-502` → `spawn(
  path.join(RUNTIME_DIR,'miktex-setup.exe'), ['--unattended','--auto-install=yes',
  '--package-set=basic','--paper-size=A4','--private'], { windowsHide: true })`。
  该 exe **不在签名清单内**（G7 实测 `miktex: 0` 命中）。
  【推断】若攻击者能写 `runtime\`（本机实测 `runtime` 对标准用户为 RX，
  因此**需要提权或另一原语**），则可把「触发 LaTeX 安装」变成「以用户权限执行任意程序」。
  由于 `spawn` 不带 `shell`，这是直接的 exe 执行。**该链的两个条件目前都不满足**
  （无同源注入点、`runtime` 不可写），故评级为【推测/需动态验证】，列出以供后续验证。

#### G5. 反回滚状态的信任来源在用户可写的本地文件

- **事实**：`_loadState()` 在文件缺失/损坏时返回
  `{ last_check:0, skipped_version:null, highest_sequence:0, security_epoch: this.config.security_epoch }`
  [证据: `updater.js:152-158`]；
  `evaluateUpdatePolicy` 用 `Math.max(config.security_epoch, state.security_epoch)`
  与 `Math.max(state.highest_sequence||0, state.highest_seen_sequence||0)` 作为下界
  [证据: `updater.js:370-375`]。
- **【推断】后果**：`security_epoch` 有**配置层下界（2）**兜底，删状态文件无法把 epoch
  降到 2 以下；但 `highest_sequence` **没有任何下界**，删除
  `<userData>\updater-state.json` 即把序列回滚保护清零。
  此后只要攻击者能让客户端取到一份**更旧但确实由厂商签名**的清单，
  序列回滚检查就不会告警。
- **可利用性**：【中】。需要：(a) 以用户身份删除/改写状态文件（用户可写，满足）；
  (b) 取得一份旧的**已签名** bundle（可从本机历史缓存
  `last-signed-installer-update.json` 备份获得，或在其被清理前留存）；
  (c) 让客户端从该 bundle 取数——需要 TLS 中间人（无证书 pinning，但需在系统信任库
  安装根证书，属提权动作）或直接改 hosts/代理（会被 `_url` 的 origin 校验挡住，
  因为 URL 固定为 `https://up.mingheng.xin` ⇒ **must MITM**）。
- **影响面**：【中～低】。受益限于**降级到更旧的、仍然由厂商签名的版本**；
  攻击者**无法伪造**新清单（C1 成立）。且本版 `full_installer_updates=true`，
  schema 2 的逐文件增量路径被禁用（`updater.js:368`），降级必须落在一个
  通过 Authenticode + 清单 publisher 匹配的旧安装包上。
  【推断】实际危害 = 「回退到某个含已知漏洞的旧正式版」。
- **建议（评估意见）**：把 `highest_sequence` 与 `security_epoch` 也编译期固化一个下界，
  或把状态同时镜像到签名清单能覆盖的位置。

#### G6. 「强制更新」在桌面层的实际阻断语义比表面窄

- **事实（判据）**：`evaluateUpdatePolicy` 的 `mandatory = manifest.mandatory ||
  belowMinimum || (manifest.security_epoch > local.securityEpoch)`
  [证据: `update-security.js:205`]。
- **事实（分支）**：
  - 若 `!newer && !belowMinimum` → 返回 `{hasUpdate:false, reason:'up to date'}`，
    **不携带 `mandatory`** [证据: `updater.js:390-392`]。
    调用方 `main.js:1206-1209` 的判断是
    `if (result.mandatory) throw ...` —— 因为 `result.mandatory` 为 `undefined`，
    **不会阻断启动**，`MODEX_MANDATORY_UPDATE_REQUIRED` 也为 `'0'`
    [证据: `main.js:1091`]。
  - 只有 `belowMinimum && !newer` 才返回 `mandatory:true` 并让 `main.js` 抛错拒启动
    [证据: `updater.js:393-395`；`main.js:1208`]。
- **事实（离线路径）**：网络失败且缓存无效时返回
  `{hasUpdate:false, reason:..., securityError:true}`，`main.js` **不阻断启动**
  [证据: `updater.js:358-365`；`main.js:1210-1213`]。
  源码注释给出理由：「首次离线允许当前已安装版本启动；服务端 License v2 仍会执行
  最低版本门禁。」[证据: `updater.js:359`]
- **【推断】后果**：
  1. 一份 `mandatory:true` 但**版本号与本地相同**的清单，在桌面层是**静默忽略**的
     （只有换版本号才会被当作更新）。这是实现细节而非漏洞，但会让
     「签名清单里写了 mandatory 就该被强制」这一预期落空。
  2. **阻断网络即可绕过桌面层的强制更新**。补偿控制是**服务端** License v2 的最低版本门禁
     （与桌面层解耦）。若攻击者同时阻断 license 服务器，应用会因 license 失败而不可用
     （属自伤），因此这条路的实际收益是「保持旧版本可用」。
- **可利用性**：【中】（本机改 hosts / 断网即可尝试）。
- **影响面**：【低～中】。桌面层不阻断，实际门禁转移到一个本报告**未审计**的
  服务端 + `license_guard`/`license_v2_client` 组合上。**这是一个跨层假设，
  建议独立验证**（本报告不对其有效性下结论）。

#### G7. 签名清单未覆盖的路径（实测）★重要

- **事实**：清单在 `resources/app`（1498 条）+ 运行时闭包（27,752 条）上的覆盖已由脚本
  完全核对（0 缺失、0 多余）[证据: 0.3 节]。但对以下路径**零覆盖**：
  ``` 
  texlive: 0 hits
  draw.io:  0 hits
  miktex:   0 hits
  elevate.exe: 0 hits
  locales/:   0 hits
  app.asar.unpacked: 0 hits
  ```
  [证据: 本次脚本对 `files` + `runtime_files` 全文检索上述关键词的输出]
- **实测未覆盖清单**：

  | 未覆盖对象 | 谁执行它 | 后果 |
  |---|---|---|
  | `runtime\miktex-setup.exe`（存在，`main.js:464,478`） | 主进程 `spawn(..., '--unattended', ...)` | 替换后**用户点「一键安装 LaTeX」即执行**（需能写 `runtime\`） |
  | `runtime\texlive\bin\windows\xelatex.exe` 等（`main.js:404-410`） | 后端 LaTeX 编译链 | 替换后**编译论文即执行** |
  | `runtime\draw.io\**` | 后端图表功能 | 同上 |
  | `resources\elevate.exe`（107,520 字节，存在） | Electron/NSIS 提权辅助 | 替换后可能在提权路径上被调用 |
  | 安装根 `Modex-MH-Agent.exe`、`*.dll`、`*.pak`、`icudtl.dat`、`v8_context_snapshot.bin`、`snapshot_blob.bin`、`locales\**` | Electron/Chromium 本体 | **shell 自身不被应用的任何哈希校验覆盖**（仅依赖 OS 层 ACL / 安装器 / AV） |
  | `Uninstall Modex-MH-Agent.exe`、`Uninstall*.exe` | 卸载流程 | 同上 |

- **【推断】评估**：
  - `app.asar` 的**内容**受签名清单（整文件 sha256）**与** Electron fuse（内嵌 ASAR 完整性）
    双重覆盖 [证据: 4.3 节；5.1 节]，这一点是扎实的。
  - 但**Electron shell 本体（exe/dll/pak/snapshot）不被覆盖**是一个真实的架构缺口：
    `v8_context_snapshot.bin` 与 `snapshot_blob.bin` 会被 V8 在启动时消费，
    `icudtl.dat` 被 Chromium 消费，替换其中任一都可能到位代码执行，
    而应用自身的校验**完全看不到它们**。
  - 缓解因素：本机实测安装根与 `runtime\` 对标准用户为 `BUILTIN\Users:(RX)`
    （`resources\` 除外）[证据: G1 的 ACL 实测]，因此这些路径**需要提权**才能改写。
- **可利用性**：【低】（`runtime\`、安装根、shell 文件均需提权）。
- **影响面**：【高】**若前提（提权）成立**。这属于「纵深防御不完整」，
  而不是「立即可利用的漏洞」。列入缺口是因为：**一旦攻击者拿到管理员，
  应用自研的整套完整性体系对这些路径毫无作用**，且攻击者可把
  `miktex-setup.exe` 当作「借签名主程序执行」的载体。
- **建议（评估意见）**：把 shell 本体（exe/dll/pak/snapshot/icudtl）的哈希也纳入
  `runtime_files`；`runtime/texlive`、`runtime/draw.io`、`miktex-setup.exe`、
  `elevate.exe` 同理。代价是清单规模与校验时间进一步上升（与 G15 冲突）。

#### G8. `detectPythonInjection()` 覆盖面窄，靠哈希闭包兜底

- **事实**：只检查 `runtime/python` 与 `runtime/python/Lib/site-packages` 两个目录下的
  `sitecustomize.py` / `usercustomize.py` [证据: `main.js:204-222`]。
- **【推断】遗漏**：CPython 的 `site` 模块还会在 **`runtime/python/Lib/`** 下尝试
  `import sitecustomize`（该目录在 `sys.path` 上，但**不在这两个 suspectDirs 中**）。
  因此「把 `sitecustomize.py` 放在 `runtime/python/Lib/`」不会被这个函数发现。
- **实际风险（【推断】）**：被第 4 节兜住——`.py` 命中 `PYTHON_EXECUTABLE` 正则，
  属于运行时闭包，多一个 `.py` 会让 `listPythonRuntimeClosure` 的计数与清单不符，
  从而 fail-closed 拒启动 [证据: `runtime-integrity.js:29,184-185,335`]。
  **所以这个窄检查是可接受的，但它的安全性完全寄生于「`.py` 被纳入闭包」这一条件。**
  如果将来有人把 `PYTHON_EXECUTABLE` 里的 `py` 去掉，`detectPythonInjection` 会立刻
  变成一个可绕过的假防线。
- **可利用性**：【低】（当前被闭包拦截）。
- **影响面**：【中】**若闭包正则被改动**（回归风险）。

#### G9. 更新恢复 journal 无签名，且启动期会按它写/删文件

- **事实**：`recoverInterruptedUpdate` 读取 `<installDir>\.app.bak\transaction.json`，
  只要 `status === 'backup_complete'`，就对 `journal.entries` **逐条**
  `rm(target)`（若 `existed` 则再从备份复制回来），然后写 `recovered_on_startup`。
  journal 本身**没有签名**，字段校验仅限 `rel` 是字符串、`existed` 是布尔
  [证据: `update-transaction.js:143-170,121-131`]。
- **【推断】后果**：能写安装目录的攻击者可以伪造一份 journal，让**经过完整性校验的
  `main.js`（来自 fuse 保护的 asar）在每次启动时替他把 `resources/app` 下的文件
  删除或替换**。这在语义上是一个「借签名主程序的写原语」。
- **可利用性**：【中】（需要能写 `.app.bak`，即安装目录可写——本机对
  `resources\` 可写，但 `.app.bak` 在安装根，本机对安装根为 RX ⇒ 需提权）。
- **影响面**：【低】。因为能写安装目录的人**本来就能直接改文件**，
  该机制不提供额外权限；它只是让「改动」带上「由受信进程在启动时执行」的外观，
  可能在日志/取证上增加混淆（`journal` 会被标成 `recovered_on_startup`）。

#### G10. `inspectInstaller` 继承未消毒的环境（含 `PSModulePath`）

- **事实**：PowerShell 子进程的环境是 `{...process.env, MODEX_INSTALLER_*}`，
  **未做**类似 `sanitizeBackendEnvironment` 的剔除
  [证据: `installer-update.js:57-60`]；脚本以 `-EncodedCommand` 执行，
  并 `Import-Module "$PSHOME/Modules/Microsoft.PowerShell.Security/..."` 等三个模块
  [证据: `installer-update.js:33-35`]。
- **【推断】风险**：`PSModulePath` 可被继承的环境变量影响模块解析路径
  （虽然脚本用的是**绝对路径** `$PSHOME/Modules/...`，降低了这一风险）；
  真正未消毒的是 `NODE_OPTIONS` 等对 powershell 无关的变量。
  **路径与 Subject 通过环境变量传递、并以 `-LiteralPath` 使用**，不存在命令注入
  [证据: `installer-update.js:36,38-41,58-59`]。
- **可利用性**：【低】。要求攻击者能控制本进程的环境变量——而能设置本进程环境的人
  已经能在本进程启动前做更糟的事。
- **影响面**：【低】（脚本用的是绝对模块路径，且此时**尚未提权**；
  提权只发生在随后独立的 `Start-Process -Verb RunAs` 上）。

#### G11. `GrantFileProtocolExtraPrivileges = true` 缺乏需求支撑

- **事实**：该 fuse 被**开启**，注释理由是 "The renderer still loads its static
  application through file://." [证据: `electron-fuses.js:49-50`]。
- **事实**：主窗口加载 `http://127.0.0.1:<port>`，不是 `file://`
  [证据: `main.js:870,920`]；`dist/assets/*.js` 中**无 `file://` 字面量**
  [证据: `Select-String -Pattern "file://"` 零命中]；
  Electron 侧也不注册任何 `file://` 协议处理器 [证据: 5.6 节 grep]。
- **【推断】**：该 fuse 的注释理由**与发行版实际行为不符**，很可能是在早期版本
  使用 `file://` 加载前端时开启、后来切换到后端 HTTP 托管却未回收。
  开启它意味着 `file://` 页面获得额外特权，属**无收益的放宽**。
- **可利用性**：【低】（需要先能在渲染进程里加载 `file://` 内容）。
- **影响面**：【低～中】。与 G4（无 Electron 侧 CSP）叠加时，
  它会削弱「即使有 `file://` 内容进入渲染进程也被限制」这层潜在防御。
- **建议（评估意见）**：切到 `false` 并复测（`readFuseWire` 会强制更新
  `EXPECTED_FUSE_WIRE_V1`，改动是显式且可追溯的）。

#### G12. 更新 helper 以用户权限运行 + 锁的 10 分钟陈旧窗口

- **事实**：helper 由 `runtime\node\node.exe` 的副本启动，**不提权**
  [证据: `updater.js:603-621`]；完整安装包路径才通过 UAC 提权
  [证据: `installer-update.js:42-44`]。
- **事实**：`waitForActiveUpdateHelper` 判定锁陈旧的规则是
  「PID 不存在 **或** `started_at` 距今 > 10 分钟」，陈旧则**直接删除锁**
  [证据: `main.js:986-989`]。
- **【推断】**：
  - helper 以用户权限运行是**合理设计**（它只改用户可写的 `resources/app`），
    与 G1 的 ACL 观察一致。
  - 10 分钟阈值 + `process.kill(pid, 0)` 的存活判定意味着：若 helper 卡住超过 10 分钟，
    锁会被下一个启动实例删除，而那个卡住的 helper **仍可能继续提交事务**
    ⇒ 两个进程可能并发改动同一批文件。`applySignedUpdate` 内部**没有**互斥
    （它依赖调用方持锁）。[证据: `update-transaction.js:172-237` 无锁逻辑]
- **可利用性**：【中】（需要一个刻意卡住的 helper —— 攻击者若已能控制 helper
  进程则已具备更高权限）。
- **影响面**：【中】。并发写入 + 回滚交错可能造成**文件集不一致**，
  进而触发下一次启动的 fail-closed 拒绝启动（可用性），
  或在极端时序下留下「部分旧 + 部分新」的树。`verifyInstalledTree` 的存在会
  把不一致暴露为启动失败，而不是静默错误——属于**安全侧偏保守**的失败模式。

#### G13. 单密钥信任根，无轮换/吊销机制

- **事实**：`PINNED_UPDATE_PUBLIC_KEYS` 只有一项
  `intl-update-2026-08-a` [证据: `release-trust.js:8-10`]，
  且 `assertPinnedUpdateConfig` 要求**键集合数量与逐项名完全相等**
  [证据: `release-trust.js:23-27`]。
- **【推断】后果**：`security_epoch` 机制**无法用于吊销密钥**：
  提升 epoch 的清单**必须由当前固定公钥对应的私钥签名**
  [证据: `update-security.js:183`]。因此如果私钥泄露或丢失：
  - 泄露 → 攻击者可用它签名 epoch 更高的清单，并把客户端**迁移到一个新 key_id**。
    而新 key_id 的**公钥必须已经编译进客户端**才能被接受
    （`publicKeys[signatureRecord.key_id]` 缺失即抛
    `untrusted update key` [证据: `update-security.js:179-180`]）。
    ⇒ 攻击者**不能**直接引入新密钥；但他们能用旧密钥签发任意版本/任意文件的清单，
    直到厂商发布一个**编译了新公钥集**的版本为止——而那个版本本身也无法通过
    安全通道下发（旧密钥已失控）。**这是一个真实的密钥轮换死锁。**
  - 丢失 → 无法再签发任何有效更新，客户端只能靠完整安装器离线升级。
- **可利用性**：泄露情形下【中】（需要私钥）。
- **影响面**：【高】。这是**唯一一条能让整套签名体系整体失效**的路径。
  注意配置文件自述私钥存于本机 gitignored 目录
  [证据: `updater-config.json:11`]，属**运维风险**而非代码缺陷。
- **建议（评估意见）**：预置第二个（备用）公钥键位并允许 key 集合是「当前集的超集」，
  或引入「旧密钥签名 + 新密钥签名」双签过渡期。

#### G14. `updater:skip-version` 无参数校验且落盘

- **事实**：preload 无校验 [证据: `preload.js:27`]；主进程无校验
  [证据: `main.js:1318-1326`]；`skipVersion` 只检查 mandatory，然后
  `state.skipped_version = version; this._saveState(state)`
  [证据: `updater.js:641-648`]；`_saveState` 直接 `JSON.stringify` 写入
  [证据: `updater.js:168-175`]。
- **【推断】**：可写入的 `version` **没有长度/类型上限**。虽然 `JSON.stringify` 会转义，
  不构成注入，但可以增大 `updater-state.json`；
  且该状态会影响后续 `state.skipped_version === manifest.version` 的比较
  [证据: `updater.js:385`]——传入畸形值只会让跳过失效（自伤）。
- **可利用性**：【高】（任何同源渲染脚本可调用，见 G4）。
- **影响面**：【低】。无代码执行、无越权，仅状态文件膨胀与跳过逻辑失效。
- **说明**：之所以仍列入，是因为它是 9 个通道中**唯一**「未校验入参 + 落盘」的组合，
  在 IPC 面清单审计中应当被明确指出。

#### G15. 完整性校验耗时本身构成可用性缺陷（并被 G1 放大）

- **事实**：实测完整性阶段 **879,403 ms（14.66 分钟）**，占冷启动 17.08 分钟的 **86%**
  [证据: 4.7 节基于主控运行时日志的重算]。
- **【推断】双重影响**：
  1. **可用性**：每次冷启动约 15 分钟停在启动状态窗，用户会认为程序卡死
     （这也解释了产品为什么要专门做一个「无需重复点击图标；再次点击会回到此窗口」
     的提示 [证据: `startup-status.js:30`]）。
  2. **安全**：这 15 分钟正是 G1 的 TOCTOU 窗口中最长的一段——校验**串行**推进，
     被哈希过的文件在校验仍未结束时就已可被替换。
- **可利用性**：【高】（无需任何特权即可触发/等待）。
- **影响面**：【中】（纯可用性；但对 G1 是**放大器**）。
- **建议（评估意见）**：把运行时闭包从「全部 `.py`/`.dll`」收敛到真正的信任关键集
  （解释器 + 加密库 + 应用代码），或改成「首次全量 + 后续按 mtime/大小快速路径 +
  关键文件每启动全量」；同时把校验与等待并行化（先起界面，后端模块在 import 前逐个校验）。

#### G16. 主窗口未设置权限处理器

- **事实**：`createWindow` 未调用 `setPermissionRequestHandler` /
  `setPermissionCheckHandler`；只有截图窗做了全拒
  [证据: `main.js:853-934` 无相关调用；`capture.js:699-700` 有]。
- **【推断】**：主窗口保持 Electron 默认行为（部分权限会弹系统提示，部分按默认策略处理）。
  对于一个「不需要摄像头/麦克风/地理位置/通知」的桌面 AI 应用，**默认即宽松**。
- **可利用性**：【中】（需要同源脚本，见 G4）。
- **影响面**：【低～中】。可被用于诱导用户授权、或（在默认允许的权限上）
  读取设备信息。
- **建议（评估意见）**：照抄截图窗的两行，显式全拒。

### 6.4 汇总矩阵

| 编号 | 条目 | 类别 | 可利用性 | 影响面 | 依据强度 |
|---|---|---|---|---|---|
| C1 | Ed25519 更新+完整性签名，信任根编译期固化 | 真保证 | 低 | — | 【直接提取】+ 本机独立验签 |
| C2 | 清单 schema 白名单 + 路径规范化 + 排序/查重 | 真保证 | 低 | — | 【直接提取】 |
| C3 | 逐文件 sha256 三层校验 + 内容寻址 | 真保证 | 低 | — | 【直接提取】 |
| C4 | 完整安装包 Authenticode + 时间戳 + SHA-256 | 真保证 | 低 | 低（Subject 非指纹） | 【直接提取】+【推断】 |
| C5 | OS 级端口归属核验后才发令牌 | 真保证 | 低 | — | 【直接提取】 |
| C6 | Electron fuse ×8（实测 `01001101`） | 真保证 | 低 | — | 【直接提取】+ 实测 |
| C7 | 更新事务 journal + 备份 + 启动恢复 | 真保证 | 低 | — | 【直接提取】 |
| C8 | 后端导入期运行时守卫 | 真保证 | 低 | — | 主控附录 B 实测 |
| C9 | 后端环境消毒 + `-I` 隔离 + 令牌走 env | 真保证 | 低 | — | 【直接提取】 |
| C10 | 后端 CSP / 安全头 / Origin 中间件 | 真实但强度未知 | — | — | 【直接提取】（符号） |
| D1 | `safeDetail` 密钥脱敏 | 混淆/卫生 | 低 | 低 | 【直接提取】 |
| D2 | 安全劝导文案 | 威慑 | 低 | 低 | 【直接提取】 |
| D3 | 清理 `.c`/同名 `.py`（位置冗余，实为死分支） | 混淆/卫生 | 低 | 低 | 【直接提取】+【推断】 |
| D4 | `verifyRuntime()` 尺寸窗口 | 体验性 | 高 | 低 | 【直接提取】 |
| D5 | 启动窗严格 CSP | 真保证（低价值） | 低 | 低 | 【直接提取】 |
| D6 | Cython `.pyd` + skill capsule 加密 | 混淆 | 中 | 低 | 【直接提取】 |
| D7 | 禁用开关列表的运行时时机 | 威慑 | 中 | 中～低 | 【推断】 |
| **G1** | **完整性校验为一次性 → TOCTOU 窗口 15 分钟～数小时** | **缺口** | **中～高** | **高** | 【直接提取】+【推断】+ ACL 实测 |
| G2 | 启动开关检查发生得太晚 | 缺口 | 中 | 中～低 | 【推断】 |
| **G3** | **`--mh-capture` 在整条安全链之前 `return`** | **缺口** | **高** | **中** | 【直接提取】 |
| **G4** | **渲染信任锚 = 后端同源；Electron 侧无 CSP 兜底** | **缺口** | **中** | **中～高** | 【直接提取】+【推断】 |
| G5 | 反回滚状态在用户可写的本地文件（`sequence` 无下界） | 缺口 | 中 | 中～低 | 【直接提取】+【推断】 |
| G6 | 强制更新的实际阻断语义比表面窄；断网即绕过桌面层 | 缺口 | 中 | 低～中 | 【直接提取】+【推断】 |
| **G7** | **shell 本体 / texlive / draw.io / miktex-setup.exe 未被哈希覆盖** | **缺口** | **低（需提权）** | **高（前提成立时）** | 脚本实测（零命中） |
| G8 | 注入自检目录覆盖窄（靠 `.py` 闭包兜底） | 缺口 | 低 | 中（回归风险） | 【推断】 |
| G9 | 更新恢复 journal 无签名 → 借签名进程的写原语 | 缺口 | 中 | 低 | 【直接提取】+【推断】 |
| G10 | `inspectInstaller` 继承未消毒环境 | 缺口 | 低 | 低 | 【直接提取】+【推断】 |
| G11 | `GrantFileProtocolExtraPrivileges=true` 无需求支撑 | 缺口 | 低 | 低～中 | 【直接提取】+【推断】 |
| G12 | helper 以用户权限运行 + 锁 10 分钟陈旧窗口 → 可能并发提交 | 缺口 | 中 | 中 | 【直接提取】+【推断】 |
| **G13** | **单密钥信任根，无轮换/吊销 → 密钥轮换死锁** | **缺口** | **中** | **高** | 【直接提取】+【推断】 |
| G14 | `updater:skip-version` 未校验入参且落盘 | 缺口 | 高 | 低 | 【直接提取】 |
| **G15** | **完整性校验 14.66 分钟，占启动 86%（同时放大 G1）** | **缺口** | **高** | **中** | 主控实测日志 + 4.7 节重算 |
| G16 | 主窗口未设权限处理器 | 缺口 | 中 | 低～中 | 【直接提取】 |

**最重要的 4 个发现**（按「可信度 × 影响」排序）：

1. **G1 — 完整性是「启动时一次性」的，且实测校验耗时 879 秒，形成十几分钟级的 TOCTOU 窗口。**
   校验完成后不持有任何文件句柄、不再复核；`resources/` 在本机实测对非提权用户可写。
   后果：以用户身份写文件的一方可以在窗口内替换尚未加载的后端模块，
   获得在该进程语境下的代码执行。**持久改动会被下次启动拦下**，因此稳定利用需要
   「用完即还原」，这限制了自动化利用，但不改变其作为**首要防线缺口**的地位。
2. **G7 + G13 — 两道「架构级」盲区**：签名清单**完全不覆盖** Electron shell 本体
   （含 `v8_context_snapshot.bin`/`snapshot_blob.bin`/`icudtl.dat`）以及
   `runtime\texlive`、`runtime\draw.io`、`runtime\miktex-setup.exe`（被主程序
   `spawn` 直接执行）；同时信任根是**单密钥且无法轮换**，
   私钥一经泄露即成轮换死锁。前者需要提权才可利用，后者需要私钥泄露才触发，
   但两者都是**整套自研完整性体系无法自愈**的场景。
3. **G4 — preload 本身合格，但信任锚与内容提供方是同一个 origin，且 Electron 侧无 CSP。**
   9 条 IPC 通道全部只检查 `origin === http://127.0.0.1:<port>`，而该 origin 同时
   承载前端 bundle、后端 API 与（推断）用户产物预览。CSP 由后端中间件提供
   （符号已确认，指令串未能静态提取），Electron 侧没有第二道防线。
4. **G3 + G15 — `--mh-capture` 是唯一跳过 Ed25519 校验的启动路径；**
   而正常路径每次冷启动要花约 15 分钟做完整性校验（占启动时间 86%）。
   二者相加意味着：产品**要么不校验**（capture 模式），**要么以极高的可用性代价校验**
   （正常模式），缺少中间档位（如「关键集全量 + 其余快速路径 + 并行化」）。

**总体判断**：桌面层的**密码学与工程实现质量明显高于同类 Electron 产品**——
双容器信任切分、编译期固化信任根、确定性序列化、OS 级端口归属核验、
事务化更新与崩溃恢复、fuse 实测与代码期望一致、以及交叉可验证的
「源码哈希 = 部署哈希」证据链（3.1 节），这些都是真实且可验证的**密码学/工程保证**，
不是营销话术。其弱点集中在**「校验的时机与覆盖边界」**（G1/G7/G8）与
**「信任锚的语义」**（G4），以及**单点密钥**（G13）——
即：**设计很认真，但把「完整性」当成了「启动时的一个事件」，而不是「一个持续的状态」。**

---

## 7. 与主控附录的交叉核对与结论修正

> 说明：主控在 §6 之后追加了「附录 A~D」，代表同一时间窗内的独立运行时证据。
> 本节逐条核对它们对本报告正文的影响。**「红队总评」即本报告 §6**（附录 D 中记为 §7）。

| 附录 | 内容 | 对正文的影响 | 处理位置 |
|---|---|---|---|
| 附录 A（第 1、3 条） | 启动状态机 8 阶段真实耗时；「不等待 LaTeX 在线安装」 | **补充**：为 §1.1/§1.15 的静态时序补上真实数据 | §4.7 |
| 附录 A（第 2 条） | 推断「`integrity` 仅 255 ms 完成，可能未真正校验」 | **修正（反向）**：按 `elapsed_ms` 语义与 `main.js:1019` 的「先 set 后 await」，879.4 秒**全部**属于完整性校验本体；`storage` 阶段只有 3.6 秒。详见 §4.7 的相位重算表 | **§4.7** |
| 附录 C | 后端 `_desktop_content_security_policy` / `desktop_security_headers` / `desktop_origin_and_update_middleware` 符号 | **修正**：§5.5 原结论「主窗口无 CSP」须修正为「**CSP 由后端响应头提供，Electron 侧不提供兜底**」；指令串不可静态提取，**不对强度作评价** | **§5.5.2 / §5.5.3** |
| 附录 B | 后端导入期守卫 `RuntimeInspectionUnavailable` | **采纳**为 C8（真实控制） | §6.1-C8 |
| 附录 D 第 2 行 | 「§4.5 校验开销推断 ⚠️ 出现张力，列为待确认项」 | **已消解**：张力源于相位归属错误，非校验未执行。实测 879.4 s ÷ 4273.9 MB ⇒ **有效吞吐 4.86 MB/s**，与 §4.5 预判的「冷缓存 + 27,752 次独立打开」一致 | **§4.7** |
| 附录 D 第 5 行 | 「§7 红队总评：桌面层强、工具授权层弱」 | 本报告 §6.4 的总体判断与之**方向一致**：桌面层密码学/工程实现强，弱点集中在**校验时机与覆盖边界**及**信任锚语义** | §6.4 |

### 7.1 由上述核对产生的最终结论修正（摘要）

1. **§4.4「校验恰好执行一次」→ 成立且被执行**：附录 A 的 879.4 秒实测**证实**了全量校验
   的真实发生，而不是「声明覆盖但未执行」。这**加强**了 §4.3 的覆盖范围结论，
   同时把「每次冷启动 15 分钟」从「推断」升级为「实测」。
2. **§5.5「主窗口无 CSP」→ 修正**：Electron 侧确实不提供 CSP，
   但后端提供了 CSP 与安全响应头中间件。因此 §2.7 与 §6.3-G4 的评级应理解为
   **取决于后端 `desktop_security_headers` 的强度**——该强度本报告未能静态确定，
   故 G4 维持「影响面 中～高（条件性）」并标注**需动态验证**。
3. 未发现其他需要推翻的正文结论。附录 A/B/C 的其余内容均为**补充性**证据，
   不改变 §1~§6 的判断。

### 7.2 本报告的明确边界（不越界断言）

- **未做**：动态抓取响应头、内存转储、调试器附加、补丁注入、权限提升尝试、
  对目标文件的任何写入或删除。全部结论来自源码静态阅读 + 本机只读测量 + 独立复算。
- **未覆盖**（不在本次任务范围）：
  - 后端 Python 逻辑（92 条 API 的授权模型、`license_guard` / `license_v2_client`、
    `instance_guard`、`runtime_guard` 的内部实现）；
  - `skill_crypto` / `skill_capsule` 的加密方案强度；
  - 服务端（`https://up.mingheng.xin` / license 服务）的任何行为。
- **因此**：§6.3-G6（强制更新的实际门禁）与 §6.3-G4（同源注入点）是
  **跨层假设**，本报告只指出桌面层的表现与边界，不对后端/服务端的最终有效性下结论。
  这两处是本报告建议优先做后续验证的方向。

---

*报告结束。全部脚本与原始输出保留在 `reports/_fx/`：
`manifest-stats.js` / `manifest-stats.txt`、`verify-install-tree.js` / `verify-install-tree.txt`、
`read-fuses.js`。*

---

# 附录（主控补充）

> 以下三项由主控（Lead）在同一时间窗内独立取得，**未被子代理覆盖**，故追加于此。
> 证据方法与正文一致：`【直接提取】` / `【推断】` / `【推测】`。

## 附录 A. 启动状态机实测（运行时日志，非静态推断）

正文 §1 的启动时序由 `main.js` 静态读出；本节补充**运行时真实数据**。

**来源**：`%APPDATA%\ModexData\library-aJL7Wi\logs\startup-latest.json`
【直接提取】`[证据: 现场读取, version=2.1.2, pid=8724, 该文件由产品自身写入]`

| 顺序 | `phase` | 用户可见中文文案（UTF-8 原文） | 累计 `elapsed_ms` | **本阶段真实耗时** |
|---|---|---|---|---|
| 1 | `update_recovery` | 检查上次安装或更新是否完成 | 251 | 251 ms |
| 2 | `integrity` | 校验程序与内置运行环境，请稍候 | 255 | **879,403 ms（14.66 min）** |
| 3 | `storage` | 检查资料位置，保留已有工作区 | 879,658 | 3,619 ms |
| 4 | `runtime` | 检查工具可用性（不等待 LaTeX 在线安装） | 883,277 | 3,619 ms |
| 5 | `updates` | 检查更新信息 | 883,965 | 688 ms |
| 6 | `backend` | 正在启动本地服务，冷启动最多等待 3 分钟 | 911,978 | 28,013 ms |
| 7 | `frontend` | 本地服务已就绪，正在打开主界面 | 1,015,491 | 103,513 ms |
| 8 | `ready` | 主界面已打开 | **1,024,525** | 9,034 ms |

### ⚠️ 勘误：本附录初版把耗时归属弄反了

**初版错误**：曾据「`integrity` 的 `elapsed_ms` 只有 255」推断该阶段仅 255 ms 完成、
进而**推测全量校验可能并未真正执行**。**该推断错误，已撤回。**

**根因**：`elapsed_ms` 是**自启动起的累计值**，不是本阶段耗时：

```js
// asar/security/startup-status.js:78
this.state = { ...this.state, phase, message: ..., detail: ..., elapsed_ms: Date.now() - this.started };
```

且 `main.js` 是**先写文案、再 await 校验本体**：

```js
// asar/main.js:1018-1021
if (isQuitting) return;
startupStatus.set('integrity', '核对程序与内置运行环境，请稍候');   // ← 只是写文案
try { const integrity = await verifyPackagedAppIntegrity(); }      // ← 校验在这里，耗时在此之后才被下一次 set() 记录
```

因此 `integrity`→`storage` 两次 `set()` 之间的 **879,403 ms 就是完整性校验本体**，
而 `storage` 阶段实际只有 **3,619 ms**。

**独立交叉验证（本报告自查）**：日志中的实际时间戳给出同一结论——

| 事件 | 时间戳 | 与下一事件的间隔 |
|---|---|---|
| `integrity` | 2026-10-01T12:03:47.440Z | **879.4 s** |
| `storage` | 2026-10-01T12:18:26.843Z | 3.619 s |
| `runtime` | 2026-10-01T12:18:30.462Z | — |

两条独立路径（累计差值 / 绝对时间戳）一致，勘误成立。

### 修正后的三条推论

1. **全量校验确实执行了，不是防线缺口。**
   有效吞吐 = 4273.9 MB ÷ 879.4 s = **4.86 MB/s**，与正文 §4.5 预判的
   「冷缓存 + 27,752 次独立 `open` 的寻道成本」**完全吻合**。
   ⇒ 附录 D 初版的「与 §4.5 存在张力」一行**予以撤销**；正文 §4.5 的推断得到实证支持。
   `【直接提取】`+`【推断】`

2. **真正的可用性缺陷被重新定性**：总冷启动 **17.08 分钟**中，
   **14.66 分钟（86%）全部卡在完整性校验上**，而不是原先误判的 `storage` 阶段。
   这使问题更聚焦：**瓶颈是单一的、可优化的校验实现**（27,752 次独立串行/半并行 `open`），
   而非分散的资料扫描逻辑。
   `【直接提取】`

3. 第 4 阶段文案「**不等待** LaTeX 在线安装」说明蓝方**有意避免被外部依赖阻塞启动**。
   与之形成有趣对照的是：**蓝方愿意为自家的完整性校验付 14.66 分钟**，
   却不愿等一个第三方安装器——优先级取舍非常明确。
   `【直接提取】`+`【推断】`

> **勘误责任说明**：本条错误由主控（Lead）在撰写附录时引入，
> 由桌面安全子代理在回读 `startup-status.js` / `main.js` 时发现并指出，主控已独立复核确认。
> 保留本节勘误记录而非静默改写，以便读者判断其余结论的可信度。

## 附录 B. 后端运行时守卫：带外导入被拒（实测）

在尝试导入编译后的 FastAPI app 以枚举权威路由表时，被守卫直接拒绝：

```
RuntimeInspectionUnavailable: 完整性验证或运行时约束未通过，未执行任何能力；请使用官方安装器修复
```

【直接提取】`[证据: tools/route_probe.py 运行输出；耗时 23.7 s 后抛出；报告见 08-route-probe.md]`

### 意义

- **对蓝方**：这是一道**有效防线**。它同时阻断了两条省力路径——
  (a) 把 `.pyd` 当普通模块 `import` 后自省；(b) 把后端抽出安装目录独立运行。
  与「加密 skill capsule」并列为蓝方**最有效的两项技术保护**。
- **对红方**：**动态分析路径被关闭**，只能走静态提取 + 前端反推。
  本报告的权威路由表即因此改由前端 bundle 确定性提取补齐（92 条，见 `09-frontend-api-surface.md`）。
- **副作用发现**：该守卫在**导入期**（而非请求期）即执行，说明校验紧贴模块初始化，
  不存在"先起来再验"的窗口。这是正确的位置选择。

## 附录 C. 后端侧安全中间件符号

正文 §2.4 提及后端存在 CSP 等中间件；此处给出符号级证据。

【直接提取】`[证据: strings/main.cp311-win_amd64.pyd.strings.txt]`

| 符号 | 推断职责 |
|---|---|
| `main._desktop_content_security_policy` | 构造 CSP 策略 |
| `main.desktop_security_headers` | 注入安全响应头 |
| `main.desktop_origin_and_update_middleware` | 来源（Origin）校验 + 更新相关中间件 |
| `main.license_middleware` | 许可证闸（请求级） |
| `main._is_same_origin_preview_response` | 预览响应同源校验 |

**说明**：CSP 的**具体指令串未能提取到**——它未作为独立字符串常量出现在 Cython 字符串表中
（可能由变量拼接构造）。故**不对其强度作评价**，仅确认其存在。
【推测】如需完整 CSP，须动态抓取响应头，而该路径受附录 B 的守卫限制。

## 附录 D. 与正文结论的一致性核对

| 正文结论 | 本附录是否支持 |
|---|---|
| §1 启动时序 | ✅ 支持，且补充了真实耗时（正文为静态推断） |
| §4.4 校验时机"恰好执行一次" | ✅ 一致（`integrity` 仅出现在阶段 2） |
| §4.5 校验开销推断 | ✅ **实证支持**——实测 879.4 s / 4273.9 MB = 4.86 MB/s，与正文"冷缓存 + 27,752 次独立 open"的预判吻合（初版误判为"张力"，已勘误，见附录 A） |
| §2.4 后端安全中间件 | ✅ 符号级证据补齐 |
| §7 红队总评"桌面层强、工具授权层弱" | ✅ 附录 B 进一步支持"运行时守卫强" |

---

# 附录 E. 独立复核补充（第二次分析 · 2026-10-02）

> 本节是同一分析任务的**第二次独立复核**产物，追加于文末。
> **不覆盖、不修改正文与附录 A–D 的任何结论**；只补充新增发现，并对正文两处判断给出
> 「证据升级」或「范围修正」。证据方法与全文一致：`【直接提取】` / `【推断】` / `【推测】`。
> 本次复核全程**只读**：仅读取文件、用目标自带 `runtime\node\node.exe` 做纯计算校验、
> 以「打开句柄」方式探测权限（**未写入任何字节、未创建/删除/改名任何文件**）。

## E.1 新增发现 E1（★最高优先）：主程序 EXE **无 Authenticode 签名**，且本机当前**非提权用户对其可写** —— 信任链可被整体替换，且**不需要管理员**

> 这是本次复核最重要的发现，也是对正文 §6.3-G1 的**范围升级**：
> 正文 G1 论证的是「运行期 TOCTOU 窗口内替换**尚未 import 的模块**」，
> 本节的证据表明，本机上的替换面不止于运行期，而是**包含信任根自身**。

### E.1.1 主 EXE 确无 Authenticode 签名（实测，硬结论）

【直接提取】对 `Modex-MH-Agent.exe`（188,753,408 字节）做只读 PE 解析与签名检查：

```
e_lfanew: 120
optional header magic: 0x020B (PE32+)
Certificate Table (数据目录索引 4) RVA = 0   Size = 0     ← 无证书表，即未签名
PE checksum 字段: 0x00000000                                ← 未回填 PE 校验和（未签名的旁证）

Get-AuthenticodeSignature:
  Modex-MH-Agent.exe            -> NotSigned
  Uninstall Modex-MH-Agent.exe  -> NotSigned
  resources\elevate.exe         -> NotSigned

Modex-MH-Agent.exe SHA256 = CBD6919454F98742B97A612EEA19B0ACAA967AFEA5E0DB4BE622FFACB0E6E2DA
```

**必须精确表述的边界（避免夸大）**：

- 【直接提取】本机安装副本的**主 EXE、卸载器、`elevate.exe` 三者均未签名**；
- 【直接提取】正文 §5.6 与 C4 讨论的 Authenticode 强校验，作用于
  **「更新流程下载下来的完整安装包」**（`installer-update.js:38-41`），
  **不作用于已经在磁盘上的 `Modex-MH-Agent.exe`**——两者是不同的对象，不能相互替代；
- 【直接提取】发布流水线中确实存在完整签名链
  （`desktop/scripts/certum-sign.js`、`certum-signing-preflight.js`、`native-authenticode.js`、
  `authenticode-tools.js`、`audit-authenticode-release.js`、`verify-public-installer.js`、
  `audit-full-installer.js`，见 `reports/build-inputs-paths.txt`）——
  说明这是**流程已设计、本副本未落地**，不是设计缺失；
- **未决（U-A）**：本工作区**没有**官方发布安装器（`Modex-MH-Agent-Setup-2.1.2.exe`），
  因此**不能**从「本机 EXE 未签名」推出「官方发布产物也未签名」。

### E.1.2 ACL 复核：与正文 G1 一致，但可写范围**更大**（新增 `app.asar` 与 EXE 本体）

【直接提取】以「打开 ReadWrite 句柄」方式逐项探测（不写入、只探测权限）：

| 对象 | 目录 `Get-Acl` 摘要 | **ReadWrite 打开实测** |
|---|---|---|
| 安装根 `Modex-MH-Agent\` | `AreAccessRulesProtected = True`，仅 SYSTEM/Administrators FullControl + Users RX（**无 SAKE 项**） | **不可写**（UnauthorizedAccessException） |
| `Modex-MH-Agent.exe` | 4 条**继承** ACE，含 `FORESAKE\SAKE | FullControl | Allow | inherited=True` | **可写** ✅ |
| `resources\` | 同上（4 条继承 ACE，含 SAKE FullControl） | 目录**不可写** |
| `resources\app.asar` | 同上 | **可写** ✅ |
| `resources\app\update-helper.js` | — | **可写** ✅ |
| `resources\app\security\release-trust.js` | — | **可写** ✅ |
| `resources\app\security\runtime-integrity-manifest.json` | — | **可写** ✅ |
| `resources\app\security\runtime-integrity-manifest.sig.json` | — | **可写** ✅ |
| `resources\app\backend\main.cp311-win_amd64.pyd` | — | **可写** ✅ |
| `resources\app\dist\index.html` | — | **可写** ✅ |
| `runtime\python\python.exe` | `runtime\` 继承 ACE **不含 SAKE 项** | **只读** |
| `runtime\python\libcrypto-3.dll` | 同上 | **只读** |
| `runtime\node\node.exe` | — | **可写** ✅ |

**与正文 G1 的一致性**：完全一致，且**印证了 G1 的自我限制说明**
（正文 §6.3-G1 第 3 条已指出这是「本分析机上以用户身份落盘/自更新留下的痕迹」的【推测】，
并指出安装根自身不含 SAKE 项而子项带继承标记）。本次复核进一步确证了该 ACL 的**形状**：
**根目录 ACL 被保护（`AreAccessRulesProtected=True`）且无 SAKE 项，但子项残留了早期的
继承 ACE**；因此出现「根不可写、根下的**文件**可写、`runtime\` 不可写」这种不规则状态。

**可写性的精确含义（重要区分）**：

- ✅ 已证：可对既有文件**原地全文覆写**（含改长度），无需父目录写权限；
- ❌ 未证：可在这些目录内**新建 / 删除 / 改名**文件（目录写探测全部被拒）；
- 对攻击者而言，**「原地覆写既有文件」已经足够**——因为需要改写的对象
  （EXE、app.asar、`resources/app/security/*`、后端 `.pyd`）**全都已存在**。

**通用性限制（沿用并将正文的【推测】保留为【推测】）**：本状态**可能是本机安装方式
（以用户身份落盘 / 自更新）造成的**，不代表官方 NSIS 安装器的默认结果。
`runtime\` 无 SAKE 项说明厂商**有意**让运行时目录对标准用户只读；
`app\` 与 EXE 的状态则更像安装痕迹。**须以目标机器实测 ACL 复核后才能推广。**

### E.1.3 组合后果：fuse 的 asar 完整性锚点可被**一并**改写（信任链整体替换）

把 E.1.1 与 E.1.2 的事实组合，可推出一个**不存在任何密码学阻力的替换路径**：

| 步骤 | 依据 |
|---|---|
| 1. `resources/app.asar` 对当前用户可写 | **已实测**（E.1.2） |
| 2. fuse `EnableEmbeddedAsarIntegrityValidation` 的比较基准（app.asar 的 SHA-256）**存放在主 EXE 内** | 【直接提取】项目自己的注释即如此陈述：`update-security.js:13-16`「Electron 的 EmbeddedAsarIntegrityValidation 把 app.asar 的 SHA-256 写进主 EXE。**两者不是可独立提交的普通文件**」 |
| 3. `Modex-MH-Agent.exe` 对当前用户**可写**且**无 Authenticode 签名** | **已实测**（E.1.1 + E.1.2） |
| 4. ⇒ 攻击者可**同时**改写 asar 与 EXE 内嵌哈希，使 fuse 校验自洽通过 | 【推断】由 1–3 与 fuse 机制的直接组合；本次未实施 |
| 5. ⇒ asar 内的 `main.js` → `require('./security/release-trust')` → `PINNED_UPDATE_PUBLIC_KEYS` 一并被替换 | 【推断】`main.js` 位于 asar 内（`resources/app/` 下**没有** `main.js`；它只有 `backend/`、`dist/`、`security/`、`templates/`、`tools/`、`update-helper.js` 六项），故 `require('./security/release-trust')` 解析到 **asar 内**的副本 |
| 6. ⇒ 攻击者用**自己的** Ed25519 公钥重新钉扎，并用**自己的**私钥重新签 `resources/app/security/runtime-integrity-manifest.json` + `.sig.json`（两者均可写） | 【推断】`release-trust.js:1-10` 的注释自述「公钥不是秘密；其作用是让本地改 JSON 不足以替换签名者」——**当 asar 本身可写时，这一设计前提失效** |
| 7. ⇒ 下次启动 `verifyPackagedAppIntegrity()` 用攻击者的公钥验签**通过**，应用正常启动 | 【推断】`main.js:1021` 的调用链 |

**结论**：在本机 ACL 状态下，**桌面侧的整条信任链（EXE → app.asar → main.js →
`release-trust.js` → 更新/完整性签名）不存在任何独立于文件系统权限的锚点**；
唯一的锚点是「写权限」，而写权限在本机对非提权用户**成立**。

**为什么这不是"重复 G1"**：G1 的利用形态必须**用完即还原**（否则下次启动 fail-closed），
且受限于「目标模块尚未被 import」；E.1.3 的形态**可持久化**（因为签名与钉扎一起被换掉），
且**不受 import 时机限制**。两者是同一根因（**信任根落在可写介质上**）的不同严重度后果。

### E.1.4 缓解因素与不应夸大的部分

- **需要本机 ACL 如 E.1.2 所示**。在标准机器级安装（安装根与子项都对 Users 只读）下，
  该路径需要**管理员权限**，此时不再构成提权，仅构成"已提权者的持久化"。
- **不构成远程可利用漏洞**：需要以该用户身份在本地执行代码（或用户手动运行）才能落盘。
- **与实际威胁模型的关系**：本产品的定位包含"保护付费内容与 License"，
  因此「本地用户能否绕过客户端保护」**本身就是威胁模型的一部分**。
  在这个模型下，**本地用户 = 潜在对手**，E.1.3 是完全适用的。
- **修复优先级建议（仅为评估意见，未实施）**：
  1. **给 EXE 与安装器做 Authenticode 签名**（成本最低、收益最高的一步，
     且直接决定 C4「发布者主体校验」是否有意义）；
  2. **修正安装器 ACL**：安装完成后把程序目录的写权限从普通用户收回，
     并**对既有子项重新传播继承**（当前"根已保护、子项仍残留继承 ACE"正是问题形态）；
  3. 若更新必须由用户态写入，应把**可写范围**收敛到数据目录，
     而非把程序目录整体交给用户；
  4. 考虑把钉扎公钥**同时**固化在后端 `runtime_guard.pyd` 内（正文附录 C 的符号
     `runtime_guard._verify_runtime_manifest` 表明已有此意图），
     使「换 asar 即换锚点」不再成立——**但前提是 `runtime\` 保持对用户只读**
     （本机实测 `runtime\python` 确实只读，这条基线是**对的**，应保持）。

## E.2 新增发现 E2（证据升级）：CSP 字面量不可提取的**原因已定位**——Cython 字符串压缩

正文 §5.5.3 的结论是：全部 `.pyd` 字符串表对 `Content-Security-Policy` / `script-src` /
`default-src` / `frame-ancestors` **零命中**，并【推测】"很可能是在
`_desktop_content_security_policy` 中由变量/常量拼接构造，或在 Cython 编译后未以明文常量落到字符串表"。

本次复核**找到了确切原因**，可将该【推测】升级为【直接提取】+ 明确结论：

【直接提取】`resources\app\backend\main.cp311-win_amd64.pyd` 内存在字面量：

```
Failed to import '%.20s.decompress' - cannot initialise module strings.
String compression was configured with the C macro 'CYTHON_COMPRESS_STRINGS=%d'.
```

即这些 `.pyd` 在构建时启用了 **Cython 字符串压缩**（`CYTHON_COMPRESS_STRINGS`），
**Python 字符串常量被压缩存放，导入时解压**。旁证（同一文件内的对照）：

| 类别 | 具体项 | 是否可见 |
|---|---|---|
| Cython 符号名 / 方法名表 | `main._desktop_content_security_policy`、`main.desktop_security_headers`、`main.health` | **可见**（约 offset 226192） |
| Python 文档字符串 | license_guard 的 "Native-module integrity is enforced independently by runtime_guard." | **可见** |
| 运行时字面量 | `api/health`、`127.0.0.1`、`GET`、`application/json`、`Content-Type` 以外的常量 | **不可见**（除少量 C 层错误串） |

**由此得到三点可写入结论的判断**：

1. CSP 指令串、`runtime_guard` 内可能存在的**第二处公钥钉扎**、以及其它字符串常量，
   **静态 grep 不可得是预期的**，与"未实现"或"拼接构造"无关；
2. **这是可逆的运行时混淆，不是加密**：字符串在模块导入时即被解压到进程内存，
   内存 dump / 运行时 hook 可完整还原【推断，依据压缩机制的非密钥性】；
3. 因此**不得**把「CSP 抓不到」当作"后端可能没有强 CSP"的证据，
   也**不得**把 Cython 压缩当作与 Ed25519 同级的"密码学保证"——
   它在 §6.2 的 D 系列（混淆/威慑）中定位正确。

> 附带修正一个可能被误读的点：正文 U/待确认项若列有
> "`runtime_guard.pyd` 是否为公钥第二处硬编码"，本次复核的结论是
> **静态无法判定**（157 个 `.pyd` 中均未命中该 base64 字面量，但原因是压缩），
> 属**未决**，不能据此认定"双处锚定"的说法不实。

## E.3 新增发现 E3：签名清单把**开发过程残留**一并固化（发布卫生缺口）

【直接提取】`runtime-integrity-manifest.json` 的 `files[]` **包含并签名保护**了下列文件，
且它们**确实存在于已安装副本中**：

| 路径 | 大小 | 内容性质 |
|---|---|---|
| `backend/.codex_final_backend.log` | 275 B | pytest 点阵进度输出 |
| `backend/.codex_pause_patch.log` | 182 B | `75 passed in 1.72s` |
| `backend/.codex_targeted.log` | 275 B | pytest 点阵进度输出 |
| `backend/.codex_transport.log` | 345 B | pytest 点阵进度输出 |
| `backend/.cache/ai-disclosure-ui.stdout.log` | 469 B | 后端启动日志 |
| `backend/.cache/ai-disclosure-ui.stderr.log` | 919 B | 后端启动日志，含 `services.instance_guard INFO … 后端实例登记: pid=213756 port=8000 parent=None`（**开发模式手动启动**痕迹） |
| `backend/.cache/v/cache/lastfailed` | 3,199 B | pytest 失败缓存，**逐条列出内部测试文件名**（`tests/test_abstract_emphasis_check.py`、`tests/test_ai_tell_check.py`、`tests/test_chat_license_scope.py` …） |

**影响面：低**（信息泄露：暴露内部测试命名与开发流程，间接提示产品边界）；
**但设计含义重要**：它说明**完整性清单的覆盖范围由「打包脚本打了什么」决定，
而不是由「应发布内容白名单」决定**。任何被打进包的杂物都会**被签名固化**，
从而（a）从"临时文件"升级为"受保护、被校验、删了会 fail-closed 的资产"，
（b）与其"源码不随包发布"（`.py`→`.pyd` + 启动清理 `.c`）的意图自相矛盾。

**建议（仅为评估意见）**：在生成清单前加一道发布内容白名单
（`.log` / `.cache` / `lastfailed` / `*.tmp` 一律不入包），并在构建期断言。

## E.4 新增发现 E4：完整性清单**未覆盖**两个会被执行的路径

【直接提取】`runtime_files[]` 的前缀分布为：`runtime/python` 27,747、`runtime/node` 2、
`runtime/pandoc` 1、`runtime/git` 1、`resources/app.asar` 1 —— **没有** `runtime/texlive`、
也没有 `runtime/miktex-setup.exe`。

但 `main.js` 中存在两条会**执行**该目录下可执行文件的路径：

| 路径 | 行为 | 证据 |
|---|---|---|
| `latex:install` → `installMiKTeX()` | `spawn(path.join(RUNTIME_DIR,'miktex-setup.exe'), ['--unattended', ...])` | `main.js:463-488` |
| `getBundledTexDir()` / `checkLaTeXStatus()` | 从 `RUNTIME_DIR/texlive/{bin/windows, miktex/bin/x64}` 找 `xelatex.exe`，并把它**加入后端 PATH** | `main.js:404-410, 414, 686-687` |

- **本机状态**：未安装 TeX（`runtime/texlive` 不存在，清单中也没有），因此**未被触发**；
- **风险**：在**含内置 TeX 的完整安装包**上，若这些文件**不在清单内**，
  则它们既不被完整性校验保护，又可被 `latex:install` 拉起。
  仅当这些路径**用户可写**时才构成实际缺口；本机 `runtime\` 对用户只读（E.1.2），
  所以**本机的实际风险低**，但**清单覆盖范围本身存在空白**。
- **评级**：缺口成立、可利用性【低～中】（依赖目标机 `runtime\` 的可写性与 TeX 是否随包发布），
  影响面【中】（若可写，则是"绕过完整性校验执行代码"的一条独立路径）。
- **建议**：把 `runtime/texlive/**` 与 `runtime/miktex-setup.exe` 纳入
  `CRITICAL_RUNTIME_FILES` 或 `runtime_files[]`；或至少纳入**体积+哈希**校验。

## E.5 与正文各章节的对照（仅列受本次复核影响的部分）

| 正文位置 | 本次复核的结论 |
|---|---|
| §5.5.3「CSP 不可静态提取」 | **证据升级**：原因是 `CYTHON_COMPRESS_STRINGS`（E.2），并明确了它的"混淆而非加密"定位 |
| §6.2 D 系列（混淆/威慑） | **支持并补强**：给出了 Cython 字符串压缩的直接证据（E.2） |
| §6.3-G1（TOCTOU / 用户可写） | **一致 + 范围升级**：可写面包含 **EXE 与 app.asar 本体**（E.1.2），并可组合成**可持久化**的整体替换（E.1.3） |
| §6.1-C4（安装包 Authenticode） | **维持**：该结论仅适用于"下载下来的安装包"；**已安装的 EXE 未签名**（E.1.1），两者不可混同 |
| §5.6「构建期自检脚本」 | **补充**：见附录 F 的全量统计（147 个 `desktop/scripts/*`） |
| §4.3 覆盖范围 | **补充**：`runtime/texlive` 与 `miktex-setup.exe` 未覆盖（E.4） |

---

# 附录 F. 供应链与发布安全（补充面）

> 正文与附录 A–D 未设独立的供应链章节。本附录补齐该面，全部为静态统计。

## F.1 `resources/app/backend/_modex-build-inputs.json` 全字段

【直接提取】

| 字段 | 值 |
|---|---|
| `schema_version` | `2` |
| `generated_at` | `2026-09-25T05:32:30.4226893Z` |
| `material_set_id` | `intl-v2-2026-08-a-09de7029` |
| `cli_proxy_policy` | `loopback_scoped_token` |
| `provider_tls_policy` | `system_pki_hostname_verification` |
| `sha256` | **547** 条 `源码路径 → SHA256` |

**547 条路径的分布**【直接提取：`reports/build-inputs-paths.txt` 解析后分组】：

| 分组 | 条数 |
|---|---|
| `web/backend` | 176 |
| `desktop/scripts` | 147 |
| `web/frontend` | 138 |
| `desktop/security` | **18** |
| `tools/docx_style_profiles` | 13 |
| `tools/docx-cn-engine` | 7 |
| 其余 48 个单文件 | 含 `desktop/main.js`、`desktop/updater.js`、`desktop/update-helper.js`、`desktop/updater-config.json`、`desktop/electron-builder.yml`、`desktop/installer.nsh`、`tools/*.py` 等 |

**`desktop/security` 的 18 条与 asar 内 18 个 `security/*.js` 一一对应**（无遗漏、无多余）
——这与正文 §3.1「源码哈希 = 部署哈希」的证据链一致。

**两个策略字段与实现的一致性**：
- `cli_proxy_policy: "loopback_scoped_token"` ↔ 桌面侧 `backend-health.js` / `backend-port-owner.js`
  的「令牌只发给已确证归属的 loopback 监听者」；后端侧对应 `services/cli_gateway_proxy.py`、
  `services/gateway_security.py`、`services/client_gateway_config.py`（均在 547 条内）。
- `provider_tls_policy: "system_pki_hostname_verification"` ↔ `backend-environment.js:2-4` 的注释
  「TLS must authenticate the destination with the system trust store」（它**刻意不清洗**代理相关
  变量，正是为了让 TLS 走系统 PKI）；后端侧对应 `services/tls_security.py` 的
  `verified_tls_context` / `_tls_policy` 符号【证据：`strings/_merged_strings.txt:9996-10007`】。

**生成逻辑**【直接提取：`asar/security/build-inputs.js:8-29`】：目录白名单 + 扩展名白名单递归枚举；
**符号链接直接抛错**；排除 `__pycache__`/`node_modules`/`tests`/`__tests__` 与 `*.test.*`/`test_*`。
其原始注释点明意图：「Source freshness (not just artifact self-consistency) ...
so new files cannot be accidentally omitted from a hand-maintained protected-module list.」
——**受保护文件清单由目录驱动自动枚举，而不是手工维护**，这是值得直接借鉴的做法。

**时间线旁证**【直接提取】：`_modex-build-inputs.json` 的 `generated_at` = `05:32:30Z`，
`runtime-integrity-manifest.json` 的 `generated_at` = `05:33:35Z`（晚 65 秒），
与「先算构建输入 → 打包 → 最后生成全树签名清单」的流程吻合【推断】。

## F.2 `desktop/scripts/` 147 个脚本：一套成体系的蓝方发布门禁

【直接提取】前缀分布：`verify-*` 17、`check-*` 15、`inspect-*` 13、`smoke-*` 11、
`prepare-*` 10、`audit-*` 7、`probe-*` 6、`publish-*` 6、`test-*` 5、`ssh-*` 5、`deploy-*` 4、
`finalize-*`/`diagnose-*`/`build*`/`delete-*` 各 3、`certum-*` 2，其余为单件。

其中 **52 个（verify 17 + check 15 + inspect 13 + audit 7）是"验证类"脚本**——
把安全与正确性属性写成**可执行断言**，而不是文档承诺。按管线阶段反推（【推断】）：

| 阶段 | 代表脚本 | 反推的门禁 |
|---|---|---|
| 源码快照 | `verify-source-snapshot.py`、`bootstrap-release-lib.js` | 发布必须对应可复现的源码状态 |
| Cython 编译 | `cython_build.py`、`check-packaged-backend.py` | 禁止 `.c`/`.py` 混入（与桌面侧启动清理互证） |
| Fuse 与 Electron 加固 | `audit-electron-fuses.js`、`smoke-packaged-electron.js`、`smoke-packaged-electron-integrity.js` | 与 `electron-fuses.js` 的 `readFuseWire()` 回读断言闭环 |
| 打包后清单 | `after-pack-integrity.js` | 命名即"打包后生成完整性清单"，对应 F.1 的时间线 |
| 代码签名 | `certum-signing-preflight.js`、`certum-sign.js`、`native-authenticode.js`、`authenticode-tools.js`、`audit-authenticode-release.js`、`verify-public-installer.js`、`audit-full-installer.js` | 「签名前预检 → 签名 → 签名后审计」完整链（Certum 为常见代码签名 CA） |
| 更新发布 | `generate-update-keys.js`、`publish-signed-update.py`、`publish-online-update.js`、`publish-full-installer.js`、`prepare-signed-publication.js`、`finalize-signed-publication.js`、`delta-publication-proof.js`、`verify-delta-baseline.js` | 密钥生成 → 签名发布 → 增量基线证明 |
| 老客户端兼容 | `verify-old-client-delta.js`、`verify-old-client-installer.js`、`verify-signed-old-client-update.js`、`verify-delta-nsis.js`、`check-legacy-skill-compat.py`、`legacy-skill-compat-window.py`、`smoke-nsis-legacy-removal.js` | 与 `FULL_INSTALLER_ONLY_PATHS`（`update-security.js:13-24`）的约束配套：**必须证明老版本能安全升级** |
| 安装器 ACL / 提权 | `test-installer-acl-elevated.ps1`、`installer-preflight.ps1`、`prepare-nsis-templates.js`、`desktop/installer.nsh` | 安装权限模型有专门的构建期测试（**与 E.1.2 的 ACL 异常直接相关**） |
| 安装后端到端 | `smoke-packaged-fresh-install.js`、`smoke-packaged-word.py`、`smoke-packaged-vision.py`、`smoke-packaged-paper-gates.py`、`smoke-packaged-repair-classification.py`、`smoke-startup-status.js`、`complete-204-signed-install-qa.ps1`、`prepare-signed-nsis-qa.ps1` | 「已签名安装」有端到端 QA 流程 |
| 事后取证 | `collect-hook-forensics.ps1`、`verify-receipt-incident.py` | 与后端 `quality_receipts.py` 呼应 |

**评价**：**这是本次评估中最有价值的"设计证据"**。一个 147 脚本的发布体系（其中 52 个验证类）
说明厂商**把安全属性当作需要回归测试的工程产物**。同时必须指出其**边界**：
这些脚本是**构建期资产**（`desktop/scripts` 不在运行时清单内、不随包分发），
**它们保障的是"发布那一刻的正确性"，不能替代运行期的密码学锚点**——
E.1 的发现正说明：**再完备的签名流水线，若落地产物的信任锚（EXE 的 Authenticode）缺失，
且程序目录对本地用户可写，则运行期防护的整体强度会回落到文件系统权限这一层。**

## F.3 Authenticode / Certum 链路：现状小结

| 对象 | 是否已签名 | 依据 |
|---|---|---|
| **已安装的 `Modex-MH-Agent.exe`** | **否**（PE 证书表为空，`NotSigned`） | E.1.1 实测 |
| 已安装的卸载器 / `elevate.exe` | **否** | E.1.1 实测 |
| **更新流程下载的完整安装包** | **强制要求**有效且带时间戳的 Authenticode，且 Subject 必须严格等于清单 `publisher` | `installer-update.js:38-41` |
| 官方发布安装器（本工作区不可得） | **未知** | 未决 U-A |

**自洽性问题（值得反馈给发布方）**：`backend-startup-error.js:5-14` 在遇到 Windows 应用控制策略
拦截时，建议用户/管理员「查看 CodeIntegrity/Operational 中的 3077、3089 事件，**按发布者规则审批**」。
但**发布者规则的前提是二进制具备可信 Authenticode 签名**；本机安装副本不满足该前提。
产品给用户的建议与自身产物的签名状态不一致。

---

# 附录 G. 对红方 `modemon` 项目的可借鉴清单

> 判定口径：**抄 = 收益/成本比高且与本项目无关的通用做法**；
> **不抄 = 成本（维护/性能/复杂度）大于其实际防护收益**。

## G.1 建议直接借鉴

| 优先级 | 设计 | 为什么值得抄 | 参考实现位置 |
|---|---|---|---|
| ★★★ | **确定性 JSON 规范化 + Ed25519 签名 + 公钥钉扎在"被同一签名覆盖"的代码里** | 一次投入覆盖「更新」与「完整性」两条链；`canonicalJson`（排序键、无空白、只允许安全整数）消除了签名歧义 | `asar/security/update-security.js:26-40,188-197`；`release-trust.js` |
| ★★★ | **「改本地配置也换不掉签名者」**：逐字段 + 键集合全等比对本机配置与钉扎值 | 绝大多数实现的信任根是"配置里读出来的公钥"，等于没有信任根 | `release-trust.js:12-37`；调用点 `main.js:1165` |
| ★★★ | **全树清单 + 数量比对（新增/删除同样 fail-closed）** | 只查"清单里的文件在不在"会漏掉"多塞一个文件/多一个目录链接" | `runtime-integrity.js:317-325, 99, 146` |
| ★★★ | **关键运行时基线显式列出"加密真正的落点"** | `libcrypto-3.dll`/`_ssl.pyd`/`python311._pth` 的注释解释了"锁 pyd 不够"，是高质量的威胁建模（也是 Cython 加密方案唯一真正有效的自保手段） | `runtime-integrity.js:30-49` |
| ★★★ | **能力隔离：控制令牌只存在于主进程，经 session 级 `onBeforeSendHeaders` 注入** | 渲染层拿不到令牌 → XSS 也偷不走；比"把 token 放 preload"强一个量级 | `main.js:1084, 870-878` |
| ★★☆ | **先核验 socket 归属、再发任何字节**（netstat TCP 四元组 / 监听套接字必须 `0.0.0.0:0` / 同 PID） | 防"抢端口冒充后端骗取令牌"；实现约 50 行 | `backend-health.js:13-45`；`backend-port-owner.js:22-34` |
| ★★☆ | **IPC 来源判定用"发起帧 origin 精确等于运行时 origin"** | 比"检查 sender 存在"强；配合 `will-navigate` 阻断异源导航 | `main.js:1236-1241, 888-898` |
| ★★☆ | **更新/替换事务化：备份 → journal(fsync) → 原子 rename → 全量复验 → 失败逆序回滚，且只在唯一危险状态回滚（幂等）** | 断电/崩溃可恢复；"只认 `backup_complete`"避免了重复回滚 | `update-transaction.js:143-237` |
| ★★☆ | **复制后二次校验哈希再 rename；helper 先等父进程退出** | 消除"复制中途损坏"与"文件被占用"两类真实故障 | `update-transaction.js:59-74`；`update-helper.js:31-37` |
| ★★☆ | **受保护文件清单由目录驱动自动枚举，而非手工维护** | 直接消灭"新文件忘进保护清单"这一高频漏洞 | `build-inputs.js:8-29` |
| ★★☆ | **把安全属性写成可执行脚本（audit/verify/smoke），纳入发布门禁** | 机制本身有回归测试才不会腐化 | 附录 F.2（147 脚本 / 52 验证类） |
| ★★☆ | **环境变量白名单式清洗（`PYTHON*` / `NODE_*` / `SSL_*` / `OPENSSL_*`）** | 约 20 行封掉一整类解释器/运行时注入；且**只清洗子进程副本**，保留用户代理与系统 PKI 语义 | `backend-environment.js:5-15`；`updater.js:53-64` |
| ★★☆ | **开发隔离：打包版拒绝隔离参数 + `realpath`/硬链接/符号链接全拒 + 旧进程必须确证退出 + 锁残留即 fail-closed** | 防"验收环境被伪造"与"误认领真实资料目录" | `dev-isolation.js` 全文 |
| ★★☆ | **`FULL_INSTALLER_ONLY_PATHS`：禁止自更新器替换自身启动链与 asar** | 正确认识"自更新器不能更新自己脚下地板"；否则断电窗口会产生不可启动状态 | `update-security.js:13-24` |
| ★☆☆ | **fuse 回读断言（`EXPECTED_FUSE_WIRE`）** | 约 20 行，杜绝"改了 fuse 配置但忘了重打包" | `electron-fuses.js:6-9, 53-57` |
| ★☆☆ | **诊断文本密钥擦除（`safeDetail`）** | 约 12 行，防崩溃日志/剪贴板泄漏 API key/PEM | `startup-status.js:8-14` |
| ★☆☆ | **启动状态窗用 `data:` URL + `default-src 'none'`** | 在完整性校验完成前提供一个"零能力"的可视诊断面 | `startup-status.js:20-34` |

## G.2 建议**不抄**（成本 > 收益）

| 设计 | 为什么不抄 |
|---|---|
| **每次冷启动全量哈希 ~4.2 GiB / 27,752 条**（本项目实测 **879.4 s**，见正文附录 A） | 收益是"闭包完整"，代价是**每次冷启动 15 分钟**——对桌面产品是难以接受的体验代价（本项目显然也付出了这个代价）。若要保留闭包保证，应改为：对**会被执行的代码**（`.pyd/.dll/.exe` 中被 import 的部分）做全量，对数据型 `.py`/资源做**目录级 Merkle 根 + 尺寸/时间戳**抽样；或分批惰性校验 + 一次性 `fsync` 后缓存。**关键结论：不要每次都把整个 Python 标准库与 site-packages 读一遍。** |
| **147 个发布脚本的规模** | 这是两年以上、多产品线沉淀的产物；新项目照搬会变成"脚本沼泽"。**只抄 4 类**：源码新鲜度（1 个）、打包后清单生成（1 个）、fuse 断言（1 个）、安装后端到端冒烟（1–2 个）。 |
| **业务/服务器专属的 `check-*` / `ssh-*` / `*-skill-release.py` / `license-*` 脚本** | 与具体后端业务强耦合，迁移价值低。 |
| **自建 `update-helper.js` + 复制 `node.exe` 的更新器** | 只在"必须自更新且不能用厂商框架"时才有必要。新项目优先用 `electron-updater` + **自加签名清单校验层**；若确需自建，抄 **journal + 逆序回滚 + 优先级排序** 三点即可。 |
| **Cython 字符串压缩 / 整体 `.pyd` 化** | 对攻击者无效（内存 dump 即还原，见附录 E.2），却显著增加自己的调试/灰度成本，还会掩盖真实问题——**本次连 CSP 与密钥的静态审计都被它挡住**。真正需要保密的算法/密钥应走"服务端下发 + 短期租约"，而不是源码混淆。 |
| **`--mh-capture` 这类"裸 CLI 模式"** | 早返回绕过全部启动校验（正文 G3）。若确需无头截图，应改为**独立可执行 + 与主程序共享的一次性令牌 + 输出路径收敛到调用方工作目录**。 |
| **把开发残留一起打进签名包**（`.codex_*.log`、`.cache/v/cache/lastfailed`） | 无收益、纯风险（附录 E.3）。应在生成清单前加发布内容白名单。 |
| **保持 `GrantFileProtocolExtraPrivileges = true`** | 本项目的理由是"渲染器仍需 `file://` 加载静态应用"，但主窗口实际从 `http://127.0.0.1:<port>` 加载（`main.js:920`），该放宽**在本项目中也没有必要**。新项目默认关闭，除非有确证的 `file://` 需求。 |
| **依赖未签名的可执行文件作为信任根** | 本项目最需修正的一点（附录 E.1）。**哪怕其它全部简化，Authenticode 签名也必须做**——它决定整条链是"密码学"还是"仅自洽"。 |
| **把程序目录交给普通用户可写**（无论出于自愿还是安装痕迹） | 见 E.1.3：信任根落在可写介质上时，Ed25519 签名只能证明"包是自洽的"，**不能证明"包来自厂商"**。更新的用户态可写需求应收敛到数据目录。 |

## G.3 若 `modemon` 只能抄 5 件事（按优先顺序）

1. **Ed25519 签名清单 + `canonicalJson` + 公钥钉扎在签名覆盖范围内**（信任根，基础中的基础）；
2. **全树"数量比对式"完整性校验 + 关键运行时基线显式枚举**（含"加密真正的落点"这一思路）；
3. **控制令牌主进程独占 + session 级 header 注入 + IPC 发起帧 origin 判定**（能力隔离三件套）；
4. **Authenticode 签名 + fuse 加固 + fuse 回读断言 + 安装目录 ACL 收紧**（把信任根真正锚在厂商身份上）；
5. **把"必须为真"的安全属性写成 `verify-*.js` 回归脚本，纳入发布门禁**（工程可持续性）。

---

*附录 E/F/G 由第二次独立复核追加。全文（正文 + 附录 A–G）结束。*
*本次复核未修改、未删除、未创建目标目录下的任何文件（权限探测仅以只读方式打开句柄）。*
