"""Ollama generation adapters."""

from paperforge.services.ollama.client import OllamaClient
from paperforge.services.ollama.prompts import PromptBundle, RAGPromptBuilder

__all__ = ["OllamaClient", "PromptBundle", "RAGPromptBuilder"]
