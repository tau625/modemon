# 路由探测

## 阶段 1：字符串表中的路由形态（静态）

### `routers__chat_internal`

- `/api/settings`
- `/v1/messages`

### `routers__project_preview`

- `/api/editor`

### `services__chat_ticket`

- `/api/settings`
- `/state`

## 阶段 2：导入编译后的 FastAPI app 并枚举真实路由（权威）

导入失败：`RuntimeInspectionUnavailable: 网关验证组件完整性检查未通过；未执行该组件，请使用官方安装包修复`

（这本身是一条有价值的发现：编译后的后端在导入期就会执行守卫逻辑，
说明存在启动时的许可证/环境校验。）

