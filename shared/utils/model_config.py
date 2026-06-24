import os


# Centralized OpenAI model defaults.
# Keep the project on one low-cost reasoning/coding model unless a specific workflow needs a different one.
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini")
OPENAI_PIPELINE_MODEL = os.getenv("OPENAI_PIPELINE_MODEL", OPENAI_CHAT_MODEL)
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
