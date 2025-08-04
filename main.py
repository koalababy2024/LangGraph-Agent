#!/usr/bin/env python3
"""
main.py
========
Program entry point for the LangGraph-Agent project.

This script currently provides a simple CLI stub that can be expanded as the
project grows. Run `python main.py --help` to see available options.
"""

import argparse
import logging
import sys
from fastapi import FastAPI

from dotenv import load_dotenv

load_dotenv()  # ensure .env variables available before other imports

from api.chat_routes import router as chat_router
from api.tool_routes import router as tool_router
import uvicorn

from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files (index.html, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(chat_router)
app.include_router(tool_router)

# 设置日志级别
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

@app.get("/ping")
async def ping():
    """Health-check endpoint returning a simple response."""
    return {"message": "pong"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list[str] | None
        Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="LangGraph-Agent",
        description="LangGraph-Agent CLI entry point.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
        help="Show program version and exit.",
    )

    return parser.parse_args(argv)


def main() -> None:
    """Main execution function.

    Parses CLI arguments and starts the FastAPI server using uvicorn.
    """
    # Parse CLI arguments (currently unused)
    _ = parse_args()

    uvicorn.run(app, host="0.0.0.0", port=8008, reload=False)


if __name__ == "__main__":
    main()
