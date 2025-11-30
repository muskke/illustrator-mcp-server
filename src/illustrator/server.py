import subprocess
import tempfile
import os
import sys
import asyncio
import base64
import io

import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# 尝试导入 Pillow 的 Image / ImageGrab
try:
    from PIL import Image, ImageGrab
    HAS_IMAGEGRAB = True
except ImportError:
    from PIL import Image  # 至少 Image 一般是有的
    ImageGrab = None
    HAS_IMAGEGRAB = False

# Windows 平台：尝试导入 pywin32 相关模块
if sys.platform == "win32":
    try:
        import win32gui
        import win32com.client
        import pythoncom
        import win32con

        HAS_WIN32 = True
    except ImportError:
        HAS_WIN32 = False
else:
    HAS_WIN32 = False


server = Server("illustrator")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="view",
            description="View a screenshot of the Adobe Illustrator window",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="run",
            description=(
                "Run ExtendScript/JavaScript code in Illustrator. "
                "It will run on the current document. You only need to create/open the document once."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "ExtendScript/JavaScript code to execute in Illustrator. "
                            "Avoid blocking UI calls like alert()/confirm()/prompt()."
                        ),
                    }
                },
                "required": ["code"],
            },
        ),
    ]


# ======================
# 截图工具：view
# ======================

def captureIllustrator() -> list[types.TextContent | types.ImageContent]:
    """
    根据平台截取 Illustrator 窗口/屏幕：
    - Windows: 使用 pywin32 + ImageGrab 按窗口矩形截图。
    - macOS: 使用 AppleScript + screencapture（保留你原始逻辑）。
    - 其他平台: 提示不支持。
    """

    # ---------- Windows 分支 ----------
    if sys.platform == "win32":
        if not HAS_WIN32:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Screenshot on Windows requires pywin32 (win32gui/win32con). "
                        "请确认已经安装 pywin32。"
                    ),
                )
            ]
        if not HAS_IMAGEGRAB:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Screenshot on Windows requires Pillow's ImageGrab. "
                        "请确认已安装 Pillow 并包含 ImageGrab 模块。"
                    ),
                )
            ]

        try:
            # 优先精确匹配窗口标题
            hwnd = win32gui.FindWindow(None, "Adobe Illustrator")
            if not hwnd:
                # 枚举窗口，模糊匹配包含 "Adobe Illustrator"
                def callback(h, ctx):
                    title = win32gui.GetWindowText(h)
                    if "Adobe Illustrator" in title:
                        ctx.append(h)

                hwnds: list[int] = []
                win32gui.EnumWindows(callback, hwnds)
                if hwnds:
                    hwnd = hwnds[0]

            if not hwnd:
                return [
                    types.TextContent(
                        type="text",
                        text=(
                            "Adobe Illustrator window not found.\n"
                            "请确认 Illustrator 已经打开，并且有至少一个文档窗口。"
                        ),
                    )
                ]

            # 尽量恢复并置前窗口（失败也无所谓）
            try:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass

            # 按窗口矩形截图
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            img = ImageGrab.grab(bbox=(left, top, right, bottom))

            if img.mode in ("RGBA", "LA"):
                img = img.convert("RGB")

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=50, optimize=True)
            compressed_data = buffer.getvalue()
            screenshot_data = base64.b64encode(compressed_data).decode("utf-8")

            return [
                types.ImageContent(
                    type="image",
                    mimeType="image/jpeg",
                    data=screenshot_data,
                )
            ]
        except Exception as e:
            # 所有异常都转成 TextContent，避免进程崩溃
            return [
                types.TextContent(
                    type="text",
                    text=f"Failed to capture Illustrator window on Windows:\n{e}",
                )
            ]

    # ---------- macOS 分支（保持你原始逻辑） ----------
    if sys.platform == "darwin":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            screenshot_path = f.name

        try:
            activate_script = """
                tell application "Adobe Illustrator" to activate
                delay 1
                tell application "Claude" to activate
            """
            # 不对这个做硬性检查，Claude 不存在也继续往下走
            subprocess.run(["osascript", "-e", activate_script])

            result = subprocess.run(
                [
                    "screencapture",
                    "-R",
                    "0,0,960,1080",
                    "-C",
                    "-T",
                    "2",
                    "-x",
                    screenshot_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                detail = result.stderr.strip() or "screencapture failed"
                return [
                    types.TextContent(
                        type="text",
                        text=f"Failed to capture screenshot.\nDetail: {detail}",
                    )
                ]

            with Image.open(screenshot_path) as img:
                if img.mode in ("RGBA", "LA"):
                    img = img.convert("RGB")
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=50, optimize=True)
                compressed_data = buffer.getvalue()
                screenshot_data = base64.b64encode(compressed_data).decode("utf-8")

            return [
                types.ImageContent(
                    type="image",
                    mimeType="image/jpeg",
                    data=screenshot_data,
                )
            ]

        finally:
            if os.path.exists(screenshot_path):
                os.unlink(screenshot_path)

    # ---------- 其他平台 ----------
    return [
        types.TextContent(
            type="text",
            text="Screenshot capture is only implemented for Windows and macOS.",
        )
    ]


# ======================
# 运行脚本工具：run
# ======================

def runIllustratorScript(code: str) -> list[types.TextContent]:
    """
    在 Illustrator 中运行 ExtendScript/JS：

    - Windows:
        如果安装了 pywin32，则通过 COM 调用 Illustrator.Application.DoJavaScript(code)
        否则返回清晰的提示，不让进程崩溃。

    - macOS:
        保留你原始 AppleScript 的调用方式（仍然存在一些字符串转义风险，但行为不变）。

    - 其他平台:
        返回不支持的提示。
    """

    # ---------- Windows 分支 ----------
    if sys.platform == "win32":
        if not HAS_WIN32:
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Running scripts on Windows requires pywin32 (win32com.client/pythoncom).\n"
                        "请确认已经安装 pywin32。"
                    ),
                )
            ]

        try:
            pythoncom.CoInitialize()
            try:
                try:
                    app = win32com.client.Dispatch("Illustrator.Application")
                except Exception as e:
                    return [
                        types.TextContent(
                            type="text",
                            text=(
                                "Failed to connect to Illustrator via COM on Windows.\n"
                                f"Detail: {e}\n"
                                "请确认已正确安装 Adobe Illustrator，并至少启动过一次。"
                            ),
                        )
                    ]

                try:
                    result = app.DoJavaScript(code)
                except Exception as e:
                    # 把一点脚本片段带上，方便你 debug
                    snippet = code[:200].replace("\n", " ")
                    return [
                        types.TextContent(
                            type="text",
                            text=(
                                "Illustrator reported an error when running the script on Windows:\n"
                                f"{e}\n\n"
                                f"Script snippet (first 200 chars):\n{snippet}"
                            ),
                        )
                    ]

                success_message = "Script executed successfully in Illustrator (Windows)."
                if result is not None:
                    success_message += f"\nReturn value: {result}"

                return [types.TextContent(type="text", text=success_message)]

            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"COM initialization error on Windows:\n{e}",
                )
            ]

    # ---------- macOS 分支（原始逻辑） ----------
    if sys.platform == "darwin":
        # 原始版本的简单转义：有风险，但保持你原来行为
        script = code.replace('"', '\\"').replace("\n", "\\n")

        applescript = f"""
            tell application "Adobe Illustrator"
                do javascript "{script}"
            end tell
        """

        result = subprocess.run(
            ["osascript", "-e", applescript], capture_output=True, text=True
        )

        if result.returncode != 0:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error executing script: {result.stderr}",
                )
            ]

        success_message = "Script executed successfully in Illustrator (macOS)."
        if result.stdout:
            success_message += f"\nOutput: {result.stdout}"

        return [types.TextContent(type="text", text=success_message)]

    # ---------- 其他平台 ----------
    return [
        types.TextContent(
            type="text",
            text="Illustrator script execution is only implemented for Windows and macOS.",
        )
    ]


# ======================
# MCP 工具分发
# ======================

@server.call_tool()
async def handleCallTool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    try:
        if name == "view":
            return captureIllustrator()

        elif name == "run":
            if not arguments or "code" not in arguments:
                return [types.TextContent(type="text", text="No code provided")]
            return runIllustratorScript(arguments["code"])

        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        # 最后一层兜底：任何没被我们捕获的异常都转成文本，不让进程直接挂掉
        return [
            types.TextContent(
                type="text",
                text=f"Unexpected error in MCP tool '{name}':\n{e}",
            )
        ]


# ======================
# main
# ======================

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="illustrator",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
