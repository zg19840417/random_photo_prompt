# 手机与远端生成访问

## 当前架构

手机和 Mac 浏览器直接访问 Mac 本机 ComfyUI 的手机页面；Mac 仅向 Windows 4090 提交计算任务。不得建立任何网络中间层。

```text
手机或 Mac 浏览器
  -> Mac 本机 8188 /random_photo_prompt/mobile
  -> 远端 4090 ComfyUI（仅计算）
  -> WebSocket 二进制结果帧
  -> Mac 本地图库与收藏目录
```

手机入口格式：

```text
http://Mac当前局域网IP:8188/random_photo_prompt/mobile
```

远端 `192.168.123.111:8188` 不是手机入口；它只供 Mac 提交工作流、读取模型列表与接收执行状态。Mac IP 变化后，应使用当前局域网 IP，不要添加网络中间层来固定地址。

Mac 存在多张局域网网卡时，所有到远端计算主机的 HTTP 与 WebSocket 连接必须绑定到系统对该远端路由选出的本机源 IP；每次连接重新计算，不能固定写入某一个 Mac IP，也不得修改系统路由。

远端 WebSocket 在任务提交前的首次建连遇到瞬时网络错误时，可在同一直连路径上短暂重试三次；三次均失败才拒绝任务，不能把一次短暂失败直接显示为远端停机。

远端页面不能作为手机入口；误打开远端的 `/random_photo_prompt/mobile` 不具备访问 Mac 本地图库的能力。应关闭该页面并改用 Mac 当前局域网 IP 的 `8188` 地址。

远端重启时会清除该节点的 Python 代码缓存，确保同步后的节点代码立即生效。

Mac ComfyUI 的 `custom_nodes/random_photo_prompt` 必须链接到本项目目录，不能维护第二份可编辑副本。项目目录是唯一源码；远端由同步脚本更新。

## 瀑布流 NEW 标记

普通图片瀑布流默认只读取 A（本机 ComfyUI `output`）中的图片；开启“本次”筛选时，按页面刷新时间和唯一任务前缀识别本次生成内容，忽略通用 `mobile` 前缀，再追加本次生成且已收藏、但 A 中已不存在的 B 备份（`output/random_photo_prompt_favorites`），同一源图只保留一份。收藏页只读取 B。A 图片收藏时复制到 B，删除 A 不会删除 B；取消收藏只删除 B。未查看图片显示绿色小圆点，已收藏图片显示金色星标；打开详情后绿色小圆点立即消失。已查看状态由 Mac 本机服务端保存于 ComfyUI `output/.random_photo_prompt_mobile_viewed.json`，图片和收藏备份都按源图 key 关联；不写入远端，也不依赖浏览器 IP、浏览器缓存或服务重启。旧版本浏览器中的 `localStorage` 查看记录仅在首次加载时迁移到该索引，迁移成功后删除旧记录。

## 资产驻留与回传

生成图片必须使用 WebSocket 直回 Mac：Mac 在提交前把工作流中的保存节点改为流式输出节点，远端将 PNG 二进制帧直接推送到 Mac。Mac 只在收到完整字节后，将文件原子写入本机 ComfyUI 输出目录；临时 `.tmp` 文件也只允许在 Mac 本机出现。

远端不得创建 output、temp、input 或其他生成资产文件。生成结果只有 WebSocket 直回 Mac 这一条路径，不提供远端保存、下载、删除或其他回退方式。

视频遵循同一资产驻留原则：远端内存编码后通过已授权的回传接口直接写入 Mac 本地视频目录；不得在远端落盘视频。

## 启动与验证

Mac 本机 8188 负责手机页面、提示词、工作流改写、本地图库、收藏与远端 WebSocket 监听。远端 Windows 8188 负责模型推理。

图片通过 WebSocket 在 Mac 本地原子落盘后，必须立即以文件名、提示词和 Seed 写入本地提示词索引；不得依赖手机浏览器后续轮询任务状态。这样即使用户直接打开瀑布流或服务重启，图库详情仍能显示对应提示词。

收藏图片是 Mac 本地的独立备份，仅由收藏页读取。瀑布流扫描生成目录时必须排除 `random_photo_prompt_favorites`，不得把同一资产的原图和收藏备份同时展示；但原图仍应保留在普通瀑布流中，收藏状态不得隐藏原图。

视频不经过代理或远端磁盘。远端完成编码后，`RandomPhotoPromptRemoteUploadVideo` 直接 POST 到 Mac 的 `/random_photo_prompt/remote/video/upload`；Mac 只接受携带本机 `.rpp_remote_transfer_token` 对应令牌、且来源为已授权远端计算主机或其当前路由出口的请求。启动 Mac 8188 时会固定允许 `192.168.123.111` 与当前路由网关的精确 IP，两者都必须通过同一令牌校验。每次手机视频提交都会按 Mac 到远端的当前网络路由，将本次回传地址写入工作流；不得依赖远端启动脚本中的旧 Mac IP。

图生视频的首帧也不复制到远端磁盘：Mac 先在本机视频输入目录保存源图，远端 `RandomPhotoPromptRemoteLoadImageFromMac` 以令牌直接读取 `/random_photo_prompt/remote/video/source_image?filename=...` 的字节并只在远端内存中解码。该接口拒绝非远端 IP、无效令牌和不在本机视频输入目录的文件名。

图生视频参考图只允许写入 Mac 本机 ComfyUI 的 `input/random_photo_prompt_mobile_video`；不得复制到 `output` 或任何图片瀑布流扫描目录。图片瀑布流必须排除 `output/random_photo_prompt_mobile_video` 中遗留的参考图，避免将输入误展示为新生成资产。

图生视频的输出宽高必须按首帧长宽比计算并对齐到 32 像素网格，最长边不得超过 960 像素、总像素不得超过 620,000；实现直接写入 `MiniMaxH3ImageToVideo` 的宽高，不得使用模板固定的 `9:16` 分辨率选择器。文生视频没有首帧，使用 540x960 画布，亦满足两项限制。

手机版任务状态栏显示的视频像素必须取实际写入 `MiniMaxH3ImageToVideo` 的宽高，不能复用文生图提示词的分辨率字段。

远端视频回传到 Mac 本地视频目录后，接收接口必须立即把视频文件名与任务前缀绑定并持久化；任务状态优先按该收据和任务文件名前缀检出该视频并标记完成，不能依赖 Mac 本地 ComfyUI history。视频回传等待窗口独立于图片，并至少保留 300 秒，避免编码或传输较慢时误报“未收到内存回传图片”。视频任务不依赖图片 WebSocket：视频由远端内存编码后直接 HTTP 回传 Mac；状态栏按远端队列显示“生成中”，不显示无法保证准确性的伪步骤数。视频详情打开后延迟 1 秒静音内联播放，关闭或切换视频时取消待执行播放。

文生视频和图生视频的动作输入框一旦提交非空自定义提示词，Mac 必须原样将该文本写入视频工作流正向提示词节点；不得二次清洗、分段、补全、裁剪或改写。仅空输入允许自动生成动作提示词。

推荐运行环境：

```text
RPP_REMOTE_COMFYUI_URL=http://192.168.123.111:8188
RPP_BLOCK_REMOTE_ASSET_SAVE=1
RPP_REMOTE_WEBSOCKET_OUTPUT=1
```

不要配置任何会启用网络中间层、远端输出目录、远端删除或远端图片上传的环境变量。

验证时必须同时确认：

1. Mac `8188` 手机页面可访问。
2. 远端队列能接受任务，且工作流不含远端保存节点。
3. 结果图片只出现在 Mac 本地输出目录，远端输出目录没有对应资产。
4. 任务结束后远端队列为空，模型缓存与显存已释放。

`ZIT+ZIB` 双采在第一阶段 ZIB 采样结束后，必须先经过 `LayerUtility: PurgeVRAM V2`（`purge_models=true`、`purge_cache=true`）再进入第二阶段 ZIT 采样，不能只在整个工作流结束时清理。这样避免两套大模型在切换瞬间争用 Windows 锁页内存，引发 `HostBuffer.read_file_slice failed`。

只改文档不需要重启服务。改动手机端、远程提交、工作流输出或回传代码时，必须重启 Mac 8188；远端会读取的节点或工作流文件还必须同步至 `D:\ComfyUI\ComfyUI\custom_nodes\random_photo_prompt` 并重启远端 8188。
