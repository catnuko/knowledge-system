"""Web 服务入口：python -m knowledge_engine.web [--port 8000]。

开发/自托管用；桌面端打包入口为 desktop/scripts/backend_main.py。
"""
import argparse

import uvicorn

from knowledge_engine.web.app import create_app


def main() -> None:
    p = argparse.ArgumentParser(prog="knowledge-engine", description="启动知识引擎 Web 面板")
    p.add_argument("--port", type=int, default=int(__import__("os").environ.get("KE_PORT", "8000")))
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
