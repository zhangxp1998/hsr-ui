# hsr-ui

《崩坏：星穹铁道》本地视觉语义 UI：Sprite 匹配、局部 OCR、结构化状态，
以及绑定实时观察的点击/滚动。提供 JSON CLI、OpenClaw 插件和本地 Web 控制台。
这不是游戏原生无障碍树；目前针对中文界面、2200×1440 参考布局和 TCL 平板校准。

## 包含什么

- `vision.py` 与各 `*_state.py`：主界面、菜单、指南、实训、委托、勋礼、编队、
  地图、隧洞/历战余响准备、材料库存弹窗、结算和奖励等有限页面。
- `service.py`：当前帧引用、owner/过期/取消检查、点击前重新识别、一次输入、
  页面稳定检测。允许轻微 OCR 框抖动，但不降低外观差异阈值。
- `output.py`：默认精简 `hsr-agent-v1`；`format:"full"` 保留坐标、证据和诊断信息。
- `video_capture.py`、`scripts/`：只读 scrcpy 视频与 JPEG 回退、显示几何验证、亮度保存恢复。
- `plugin/`：原生 `hsr_ui` 工具。启动路径不依赖插件捕获目录，修复重定位后的 ENOENT。
- `web/`：按设备比例绘制语义树，语义点击/滚动，60 秒服务端空闲锁屏。

**这是脱敏源码版，不包含运行所需的游戏图像资源。**截图、UID/库存记录、设备序列号、
私有路径、凭据、模型、运行日志和历史仓库均未导入。资源清单只有名称、相对路径及来源类别；
安装前阅读 [资源准备](docs/assets.md)。不自动下载游戏资源或读取解锁凭据。

## 安装

Linux、Python 3.12+、ADB、FFmpeg/ffprobe；视频加速使用 **scrcpy server 3.3.4**。

```sh
git clone https://github.com/zhangxp1998/hsr-ui.git
cd hsr-ui
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 中的设备和本地资源配置，再导入：
set -a; . ./.env; set +a
./hsr-ui <<'JSON'
{"action":"status"}
JSON
```

`status` 不接触设备、不加载图像资源。`analyze` 需要自备资源和 JPEG，但不需要连接平板。
`observe` 要求配置精确序列号、唯一匹配的设备、已解锁且游戏在前台。
不会自动选择另一台设备，不负责启动游戏。默认使用 CPU OCR；CUDA 是可选配置。
RapidOCR 可能在首次加载时下载模型，离线使用时请先准备其模型缓存。

```json
{"action":"analyze","image":"/absolute/path/to/frame.jpg"}
{"action":"observe","_owner":"example-run"}
{"action":"click","observationId":"LATEST_ID","ref":"NODE_REF","dryRun":true,"_owner":"example-run"}
{"action":"scroll","observationId":"LATEST_ID","ref":"SCROLL_REF","_owner":"example-run"}
{"action":"release","_owner":"example-run"}
```

每次向 CLI 的 stdin 传一个 JSON 对象。先检查 `ok`，再读取 `result`。
CLI owner 必须一致；截图回放不能用于实机点击。`ref` 不是消费/领奖授权。
未知状态保持 null，不视为 0/OFF；未覆盖页面不产生推测动作。

更多：[OpenClaw 插件](plugin/README.md) · [Web 控制台](web/README.md) ·
[语义优先工作流](docs/workflow.md) · [验证范围](docs/validation.md)。

## 验证

以下默认测试不连接平板、不需要私人截图或游戏图像：

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python web/test_server.py
cd plugin
npm ci
npm run build
npm test
```

OpenClaw SDK 作为插件 peer dependency；插件构建要求 Node.js 24+。
真实截图回归与本机验收不等同于所有页面/设备的识别准确率，详见验证说明。
