"""PyInstaller 打包入口：按 KE_PORT（默认 8000）启动知识引擎面板服务。

仅用于发布桌面端时把 Python 后端打成单文件二进制，随 Tauri 应用分发。
开发模式不经过这里，直接使用 `python -m knowledge_engine.web`。
"""
import os

import uvicorn
from knowledge_engine.web.app import create_app


def main() -> None:
    port = int(os.environ.get("KE_PORT", "8000"))
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
