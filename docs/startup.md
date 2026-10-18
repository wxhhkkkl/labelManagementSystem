# 前端与工位打印端启动

在项目根目录双击 `start-ui.cmd`，启动管理前端并打开浏览器，同时启动 Electron 工位打印端。脚本根据自身位置定位项目，可以从其他目录执行。

```powershell
# 同时启动，浏览器暂不打开
.\start-ui.cmd -NoBrowser

# 只启动管理前端
.\start-ui.cmd -Target admin

# 只启动工位打印端
.\start-ui.cmd -Target print
```

后台地址为 `http://127.0.0.1:5173`。工位打印请使用打开的 Electron 窗口，本地打印服务端口为 17650，工位页面开发端口为 5174。

已运行的实例会跳过，不重复启动。端口被其他程序占用时提示错误。日志保存在 `backend/var/startup/`。脚本关闭后服务继续运行；退出工位软件窗口会关闭该实例的本地打印服务。

前提：已安装 Node.js，并在 `admin-web` 和 `print-client` 安装依赖。脚本支持通过 PATH 中的 fnm 初始化 Node。Electron 缺少运行文件时，按错误提示执行安装命令。

管理网页在本地开发时仍需另外运行 8000 端口的后端。

工位打印端默认连接已部署服务 `https://lms.yuwangchenfa.com`，不依赖本机 8000 端口。地址统一维护在 `print-client/src/serviceConfig.ts`。Electron 安装版与开发版的业务请求均通过受限主进程接口访问该 HTTPS 服务；浏览器单独预览开发页面时，Vite 也将 `/api/v1/` 代理到同一服务器。标签出纸仍通过本机 17650 打印服务完成。
