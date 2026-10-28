# F14 政务 Agent Web Demo

本目录是政务服务智能办理的阶段成果展示页，以及与现有后端会话接口对接的实时交互入口。

## 环境

- Node.js v22.23.2
- npm 10.9.8

只使用 npm。

## 安装与启动

在 `frontend/` 目录执行：

```bash
npm ci
npm run dev
```

前端地址：http://localhost:5173

后端预期地址：http://127.0.0.1:18000

浏览器只请求同源路径：

- `GET /health`
- `POST /api/v1/session/turn`

Vite 开发服务器把这两个路径代理到上述后端（默认 `http://127.0.0.1:18000`；可用环境变量 `GOVAGENT_DEV_BACKEND_URL` 覆盖）。业务代码不直接写后端绝对地址。

真实对话依赖已经启动的现有后端运行时。本前端不连接模型服务。

## 检查命令

```bash
npm run test:run
npm run build
```

`npm run build` 会先做 TypeScript 检查，再执行 Vite 构建。构建产物位于 `dist/`，已被 `frontend/.gitignore` 忽略。
