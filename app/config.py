import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.157:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:7b")

# Athenaeum is reached via its LAN Ingress hostname. Targeted directly by
# IP + explicit Host header for now (avoids needing local DNS / /etc/hosts
# entries on every client) — revisit once Hermes itself runs inside K3s,
# where in-cluster service DNS (http://athenaeum-api:8000) is simpler.
ATHENAEUM_URL = os.environ.get("ATHENAEUM_URL", "http://192.168.1.157")
ATHENAEUM_HOST_HEADER = os.environ.get("ATHENAEUM_HOST_HEADER", "athenaeum.home.local")

DB_PATH = os.environ.get("DB_PATH", "./hermes.db")

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are Hermes, a helpful personal assistant. You have access to tools — "
    "use them when they'd help answer the user's question, especially anything "
    "involving the user's personal notes. Don't mention tool names or internal "
    "mechanics to the user; just use them naturally.",
)
