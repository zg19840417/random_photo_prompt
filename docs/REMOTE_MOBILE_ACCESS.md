# 手机远程访问 ComfyUI

## 文档职责

本文只负责手机跨网络或局域网访问笔记本 ComfyUI 的方案、启动要求和安全边界。

本文不负责提示词规则、规则2选项扩充或图生视频动作写法。相关文档：

- `docs/AI_CONTEXT.md`：项目总索引和当前开发上下文。
- `docs/PROMPT_GENERATION_RULES.md`：规则1文生图提示词生成规则。
- `docs/KEYWORD_EXPANSION_OPTION_GUIDE.md`：规则2关键词扩写模式选项扩充规则。
- `docs/VIDEO_PROMPT_OPTION_GUIDE.md`：图生视频动作提示词选项扩充规则。

目标：手机和笔记本不在同一个局域网时，手机仍然可以打开生成页面、提交任务，并查看远端 ComfyUI 返回到本机的图片。

## Mac 远程代理方案

当前 Mac 推荐收口为“18199 统一入口”：

```text
手机
  -> Mac 18199 远程代理
  -> 本机 8188 手机页面接口
  -> 远端 4090 ComfyUI
  -> 通过 ComfyUI WebSocket 把成品图直接回传到 Mac
  -> 手机从 Mac /view 查看本地图片
```

手机入口使用：

```text
http://Mac地址:18199/random_photo_prompt/mobile
```

也可以直接打开：

```text
http://Mac地址:18199/
```

代理根路径打开网页端，手机页使用 `/random_photo_prompt/mobile`。这两个用户入口都走 18199。

不要直接用远端 4090 的地址打开手机页。手机页需要本机节点逻辑、模型列表、图库和删除接口；18199 代理会把手机页相关接口转给本机 8188，同时把 ComfyUI 队列、history、view 等请求接到远端。

### 启动要求

本机 8188 仍然要启动，但只作为 18199 背后的内部接口，负责手机页和本地文件管理。推荐启动环境：

```text
RPP_REMOTE_COMFYUI_URL=http://192.168.123.111:8188
RPP_REMOTE_OUTPUT_DIR=/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/output/4090 生成
RPP_REMOTE_DELETE_OUTPUT=1
RPP_REMOTE_WEBSOCKET_OUTPUT=1
```

远程代理 18199 的推荐启动环境：

```text
RPP_PROXY_REMOTE_URL=http://192.168.123.111:8188
RPP_PROXY_LOCAL_MOBILE_URL=http://127.0.0.1:8188
RPP_PROXY_OUTPUT_DIR=/Users/zouge/Documents/Codex/2026-06-02/macbook-air-80/work/ComfyUI/output/4090 生成
RPP_PROXY_PORT=18199
RPP_PROXY_DELETE_REMOTE_OUTPUT=1
RPP_PROXY_WEBSOCKET_OUTPUT=1
```

`tools/run_mac_remote_proxy_daemon.py` 和 `tools/start_mac_remote_proxy.sh` 都使用这些变量；如果外部已经设置变量，脚本会沿用外部值。

### 图片回传和本地映射

默认回传链路不再依赖远端 output 文件夹。生成任务提交到远端前，本机/代理会把工作流里的 `SaveImage` 替换为：

1. `PreviewImage`：保留远端执行过程中的可见输出。
2. `SaveImageWebsocket`：让远端 ComfyUI 通过 WebSocket 把成品 PNG 直接发回 Mac。

Mac 收到二进制图片帧后，会先写入临时文件，确认非空后替换成正式文件，文件名沿用本次任务的 `mobile_xxx_00001.png` 规则。本机图库扫描 `RPP_REMOTE_OUTPUT_DIR` / `RPP_PROXY_OUTPUT_DIR`，所以刷新页面后仍能看到已回传图片。

旧的远端 history `/view` 下载逻辑仍保留，用于读取历史里已经存在的远端图片；但新生成的主链路不再要求远端先落 output、Mac 再复制、最后删除远端文件。

### 远端删除

远端删除只服务于旧的 history `/view` 下载兼容路径，并且只在本地图片已经成功落盘、文件大小大于 0 后触发。默认 WebSocket 直回 Mac 的链路不会在远端 output 生成成品图，因此也不需要远端删除成品图。

远端 ComfyUI 必须安装本插件，并提供：

```text
POST /random_photo_prompt/remote/delete_output
```

删除接口只允许删除 ComfyUI 已知目录类型下的安全文件名和安全子目录。关闭删除：

```text
RPP_PROXY_DELETE_REMOTE_OUTPUT=0
RPP_REMOTE_DELETE_OUTPUT=0
```

### 状态检查

代理提供可读状态页：

```text
http://Mac地址:18199/random_photo_prompt/proxy/status
```

它会显示：

- 手机端内部服务是否可访问。
- 远端 4090 ComfyUI 是否可访问。
- 本地输出目录是否存在且可写。
- 远端删除接口是否可用或是否关闭。
- 当前代理的远端地址、本地输出目录和映射数量。

如果需要 JSON：

```text
http://Mac地址:18199/random_photo_prompt/proxy/status?format=json
```

手机版顶部只展示统一入口状态：

- `统一入口`：手机从 18199 进入，远端 4090 负责生成，资产回传到 Mac。

当手机端内部服务、远端 4090 或输出目录不可用时，手机版状态栏会尽量指出断在哪一段。

## 跨网络访问：Tailscale 私有网络

这是当前最安全、最省事的跨网络方案。它不是把 ComfyUI 直接公开到互联网，而是让手机和笔记本进入同一个私有虚拟网络。

使用方式：

1. 笔记本和手机都安装 Tailscale，并登录同一个账号。
2. 启动 Mac 内部服务和 18199 统一入口。
3. 控制台会显示类似下面的地址：

```text
http://100.x.x.x:18199/random_photo_prompt/mobile
```

4. 在手机上保持 Tailscale 开启，用这个地址打开生成页面。

只要 Tailscale 连接正常，手机使用蜂窝网络、公司 Wi-Fi、家里 Wi-Fi 都可以访问同一台笔记本。

## 局域网地址

同一个 Wi-Fi 下仍然可以使用局域网地址：

```text
http://电脑局域网IP:18199/random_photo_prompt/mobile
```

`一键远程启动ComfyUI.bat` 会自动列出当前检测到的局域网地址。

## 公网链接方案

如果需要一个不依赖手机 VPN 的公网链接，可以使用 FRP、cpolar、natapp、Cloudflare Tunnel 等工具把 18199 统一入口转发出去。

注意：统一入口可以控制工作流和读取输出文件，不能无保护地公开到公网。公网链接必须至少满足一个条件：

- 使用账号登录保护。
- 使用访问密码或隧道访问控制。
- 只暴露专门的受限代理，不直接暴露完整 ComfyUI。

在没有访问控制前，不要把 18199 统一入口直接映射成公开地址。

## 内部服务说明

本机 8188 只作为 18199 背后的内部接口使用，不再作为日常用户入口。

如果需要检查内部服务，可访问：

```text
http://127.0.0.1:8188/random_photo_prompt/local/status
```

普通使用时不要把 8188 暴露给手机、其他电脑或公网隧道。

## 当前项目侧逻辑

手机生成页面、图库、视频页、收藏页都使用相对路径访问当前服务。当前用户入口统一为 18199，当前服务就是 Mac 远程代理。

远端模式的跨网络访问主要依赖启动参数和隧道/VPN：

- 本机 8188 只监听 `127.0.0.1`，作为 Mac 内部接口，避免被当成用户入口。
- 代理 18199 监听 `0.0.0.0`，手机和电脑网页端都从这个统一入口进入。
- 远端 4090 必须能被 Mac 访问到 `RPP_PROXY_REMOTE_URL` / `RPP_REMOTE_COMFYUI_URL`。
- 手机访问远端代理方案时必须指向同一台 Mac 的 18199 端口。
- 如果走公网隧道，隧道转发到本机 `127.0.0.1:18199` 或 `localhost:18199`。
