#!/usr/bin/env python3
"""
main.py
========
Program entry point for the LangGraph-Agent project.

This script currently provides a simple CLI stub that can be expanded as the
project grows. Run `python main.py --help` to see available options.
"""

import argparse
import sys
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from dotenv import load_dotenv

load_dotenv()  # ensure .env variables available before other imports

from graphs.chat_graph import get_chat_graph
import uvicorn

app = FastAPI()

chat_graph = get_chat_graph()

@app.get("/ping")
async def ping():
    """Health-check endpoint returning a simple response."""
    return {"message": "pong"}

@app.get("/chat")
async def chat_endpoint(message: str):
    """Chat endpoint.

    Query parameter:
    - message: user input text
    """
    user_msg = {"role": "user", "content": message}
    result = chat_graph.invoke({"messages": [user_msg]})
    ai_msg = result["messages"][-1]
    return {"answer": ai_msg.content}

@app.get("/chat/stream")
async def chat_stream_endpoint(message: str):
    """Streaming chat endpoint.

    Query parameter:
    - message: user input text
    
    Returns:
    - Server-Sent Events (SSE) stream of chat response tokens
    """
    async def generate_stream():
        user_msg = {"role": "user", "content": message}
        
        async for message_chunk, metadata in chat_graph.astream(
            {"messages": [user_msg]}, 
            stream_mode="messages"
        ):
            if message_chunk.content:
                # Format as Server-Sent Events
                data = {
                    "content": message_chunk.content,
                    "metadata": {
                        "node": metadata.get("langgraph_node", ""),
                        "step": metadata.get("langgraph_step", 0)
                    }
                }
                yield f"data: {json.dumps(data)}\n\n"
        
        # Send end-of-stream marker
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(), 
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

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
