# illustrator-mcp-server

一个用于 **远程控制 Adobe Illustrator** 的 MCP（Model Context Protocol）服务器。

通过两个简单的工具：

- **`run`**：在 Illustrator 中执行任意 ExtendScript / JavaScript 脚本  
- **`view`**：截取当前 Illustrator 窗口截图并返回为图片内容  

你可以在聊天界面里一边写脚本、一边实时看到效果，非常适合用来做：

- Logo 概念探索
- 图标栅格 / keyline 设计
- 加载动画 / spinner 造型
- 各种自动化排版 /批量出图

---

## 功能概览

### 工具一：`run`

在当前 Illustrator 实例中执行一段 ExtendScript / JavaScript 代码。  
配合 AI 模型，你可以描述你想要的图形，让模型生成脚本，然后用 `run` 执行。

- 平台：
  - **Windows**：通过 COM (`Illustrator.Application.DoJavaScript`) 调用
  - **macOS**：通过 AppleScript 调用 `do javascript`

> ⚠️ 注意  
>
> - 请避免使用 `alert()` / `confirm()` / `prompt()` 等弹框函数，它们会阻塞脚本执行，导致超时。  
> - 脚本中不要写死长时间阻塞的循环，以免卡住 COM / AppleScript。

---

### 工具二：`view`

返回一张 base64 编码的 JPEG 图片（MCP 客户端会解码展示），内容是当前 Illustrator 窗口截图。

- **Windows**：  
  - 使用 `pywin32` 查找标题包含 “Adobe Illustrator” 的窗口  
  - 使用 `Pillow.ImageGrab` 按窗口矩形截屏  

- **macOS**：  
  - 使用 AppleScript 激活 Illustrator（保持你的工作流，也会尝试激活 Claude 客户端）  
  - 使用 `screencapture` 截取屏幕的固定区域 `0,0,960,1080`

截图非常适合做：

- “给我看当前画面，我来继续调整”
- “画错了哪里？给我看截图，我改脚本”

---

## 环境要求

### 通用

- Python 3.10+
- 已安装 Adobe Illustrator（2022+ 建议）
- 已安装依赖：
  - [`mcp`](https://github.com/modelcontextprotocol/python-sdk)（Python 版 MCP SDK）
  - `Pillow`（用于图像编码 / 截图）

### Windows 11

必需：

- `pywin32`
  - 用于：
    - 通过 COM 调用 `Illustrator.Application.DoJavaScript`
    - 查找窗口、置前窗口等（`win32gui` / `win32con`）
- `Pillow` 带 `ImageGrab` 模块

安装示例（在你的虚拟环境中）：

```bash
pip install mcp pillow pywin32

```

### macOS

- 系统自带 `osascript`（AppleScript 命令行）
- 系统命令 `screencapture` 可用
- 需要给运行 MCP 的终端 / 客户端 **开启屏幕录制权限**，否则 `view` 截屏会失败。

------

## 安装和开发

建议项目结构如下：

```
text复制编辑illustrator-mcp-server/
├─ pyproject.toml
└─ src/
   └─ illustrator/
      ├─ __init__.py
      └─ server.py
```

你的 `pyproject.toml` 大致可以是（示例）：

```
toml复制编辑[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "illustrator"
version = "0.1.0"
dependencies = [
    "mcp>=1.1.1",
    "pillow>=11.0.0",
    "pywin32>=306; sys_platform == 'win32'",
]

[project.scripts]
illustrator = "illustrator:main"
```

`src/illustrator/__init__.py` 示例：

```
python复制编辑from . import server
import asyncio


def main():
    asyncio.run(server.main())


__all__ = ["main", "server"]
```

> 这样你就可以通过 `illustrator` 这个命令启动 MCP server（由 `pyproject.toml` 的 `project.scripts` 提供）。

------

## 启动 MCP Server

在项目根目录下（含 `pyproject.toml` 的目录）：

```
bash复制编辑# 安装当前项目为可执行包（可选）
pip install -e .

# 启动 MCP server
illustrator
```

或者直接（如果你不想安装为脚本）：

```
bash


复制编辑
python -m illustrator
```

具体命令取决于你在 `__init__.py` / `pyproject.toml` 里怎么配置 `main` 入口。

------

## 在 MCP 客户端中配置

不同客户端配置方式略有不同，大致思路是：

1. 指定一个 MCP “服务器” 名称（例如 `illustrator`）
2. 指定启动命令（例如 `illustrator` 或 `python -m illustrator`）
3. 指定工作目录（项目根目录）

举例（伪 JSON 配置，仅示意）：

```
json复制编辑{
  "mcpServers": {
    "illustrator": {
      "command": "illustrator",
      "args": [],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

配置完成后，在客户端里你应该能看到一个名为 `illustrator` 的 MCP 服务器，里面有两个工具：`view` 和 `run`。

------

## 使用示例

### 1. 创建一个 Logo 画板并画一个简单标志

在 MCP 客户端中调用 `run` 工具，传入如下 `code`：

```
js复制编辑// 新建一个文档
var doc = app.documents.add(DocumentColorSpace.RGB, 1024, 768);

// 激活图层
var layer = doc.activeLayer;

// 画一个圆形标志
var centerX = 512;
var centerY = 384;
var radius = 120;
var top = centerY + radius;
var left = centerX - radius;

var circle = layer.pathItems.ellipse(top, left, radius * 2, radius * 2);
circle.stroked = false;
circle.filled = true;

var c = new RGBColor();
c.red = 20;
c.green = 120;
c.blue = 255;
circle.fillColor = c;

// 添加品牌名文字
var textFrame = layer.textFrames.add();
textFrame.contents = "Nova Bank";
textFrame.textRange.size = 48;
textFrame.position = [centerX - 150, centerY - radius - 40];
```

执行完成后，再调用 `view` 工具，即可看到当前窗口截图，验证效果。

------

### 2. 创建图标栅格（24×24）

```
js复制编辑var base = 24;
var rows = 2;
var cols = 4;
var gutter = 40;

var docW = cols * base + (cols + 1) * gutter;
var docH = rows * base + (rows + 1) * gutter;

var doc = app.documents.add(DocumentColorSpace.RGB, docW, docH);
var layer = doc.activeLayer;

var left = 0;
var top = doc.height;

var startX = left + gutter;
var startY = top - gutter;

for (var i = 0; i < rows; i++) {
    for (var j = 0; j < cols; j++) {
        var x = startX + j * (base + gutter);
        var y = startY - i * (base + gutter);

        var box = layer.pathItems.rectangle(y, x, base, base);
        box.stroked = true;
        box.filled = false;

        // 中心辅助圆
        var r = base * 0.4;
        var cx = x + base / 2;
        var cy = y - base / 2;
        var topCircle = cy + r;
        var leftCircle = cx - r;

        var circle = layer.pathItems.ellipse(topCircle, leftCircle, r * 2, r * 2);
        circle.stroked = true;
        circle.filled = false;
    }
}
```

------

### 3. 画一个加载动画 Spinner 造型（圆环）

```
js复制编辑var doc = app.documents.add(DocumentColorSpace.RGB, 512, 512);
var layer = doc.activeLayer;

var ab = doc.artboards[doc.artboards.getActiveArtboardIndex()];
var rect = ab.artboardRect; // [left, top, right, bottom]
var left = rect[0];
var top = rect[1];
var right = rect[2];
var bottom = rect[3];

var cx = (left + right) / 2;
var cy = (top + bottom) / 2;

var radiusOuter = 120;
var radiusInner = 80;

// 外圈
var topOuter = cy + radiusOuter;
var leftOuter = cx - radiusOuter;
var outer = layer.pathItems.ellipse(topOuter, leftOuter, radiusOuter * 2, radiusOuter * 2);
outer.stroked = true;
outer.strokeWidth = 16;
outer.filled = false;

// 通过剪切或透明渐变等，你可以在后续进一步细化 Loader 造型
```

------

## 许可证

MIT License
