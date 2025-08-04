"""Shared LLM configuration for all graphs.

This module provides a single, shared Azure OpenAI LLM instance that can be
imported and used across all graph modules to avoid duplication.

Environment variables (define in a `.env` file):
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_KEY
- AZURE_OPENAI_DEPLOYMENT (optional, default "gpt-4o-mini")
- AZURE_OPENAI_API_VERSION (optional, default "2024-08-01-preview")
"""

import os
from langchain_openai import AzureChatOpenAI

# Global shared LLM instance
llm = AzureChatOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    openai_api_key=os.environ["AZURE_OPENAI_KEY"],
    openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
    deployment_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
)
