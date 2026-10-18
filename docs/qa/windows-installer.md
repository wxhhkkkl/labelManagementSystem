# Windows 工位端合一安装包

2026-10-18 实际构建产物：`print-client/release/LMS-Print-Setup-0.1.0.exe`，171,770,168 字节，约 163.81 MiB。同目录附有安装说明和 SHA-256 校验文件。`release/` 为本地产物目录，不提交 Git。

## 构建

在 `print-client` 中执行 `npm run dist:win`，会先构建代码，再将 Electron 33.4.11 的 x64 与 ia32 程序合并到同一个 NSIS 安装器。安装器自动选择对应程序版本，整机安装需要管理员权限。

若 GitHub 运行文件下载超时，可在构建进程设置 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`、`ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 后重试。

本机首次提取 winCodeSign 工具时遇到 macOS dylib 软链接权限错误，已在构建缓存中只提取当前 Windows 打包所需工具，未要求关闭系统安全限制，也未修改目标程序的签名校验设置。

## 已验证

- 构建日志确认安装器 `archs=x64, ia32`；实际检查到两个完整嵌入应用压缩流，头部校验通过。
- 可执行文件 PE 类型分别为 x64 `0x8664` 和 x86 `0x014c`，版本资源为 0.1.0。
- 两个 `app.asar` 均包含主进程、preload、界面、Logo 和部署服务地址；没有本地 `.env`、后端或测试目录。
- 在本机 Windows 11 x64 上分别运行打包后的两个程序，确认 `app.isPackaged=true`，运行架构分别为 x64 / ia32。
- 两个程序均能显示登录页及 Logo，通过实际 preload / IPC 登录部署服务，当前用户、产品选项、工位列表接口均返回 200。
- 未创建业务打印任务，未实际出纸；不更改机器绑定。

## 验证范围

目标是 Windows 10 x86 / x64。以上不等于已经完成 Windows 10 电脑上的安装、卸载或驱动实物打印验收，仍需在目标工位进行。当前安装器没有数字签名，Windows 可能显示未知发布者。

运行依赖由安装包携带；目标电脑不需要 Node.js、Python 或 MySQL，但需要可用的网络和对应系统位数的打印机驱动。
