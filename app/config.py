import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.157:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen2.5:14b")

# Athenaeum is reached via its LAN Ingress hostname. Targeted directly by
# IP + explicit Host header for now (avoids needing local DNS / /etc/hosts
# entries on every client) — revisit once Hermes itself runs inside K3s,
# where in-cluster service DNS (http://athenaeum-api:8000) is simpler.
ATHENAEUM_URL = os.environ.get("ATHENAEUM_URL", "http://192.168.1.157")
ATHENAEUM_HOST_HEADER = os.environ.get("ATHENAEUM_HOST_HEADER", "athenaeum.home.local")

# Iris runs bare-metal on the host (not K3s — see its own README for why),
# so it's reached the same way whether Hermes runs locally or in-cluster —
# no Ingress/Host-header trick needed, just the host's LAN IP:port.
IRIS_URL = os.environ.get("IRIS_URL", "http://192.168.1.157:8100")

# Hindsight runs bare-metal on the host via Docker Compose (not K3s — no
# derived resources here, just the published image), reached the same way
# whether Hermes runs locally or in-cluster. HINDSIGHT_BANK_ID scopes
# memory to a single project rather than mixing in everything Hermes ever
# discusses — see the tool descriptions in tools.py.
HINDSIGHT_URL = os.environ.get("HINDSIGHT_URL", "http://192.168.1.157:8888")
HINDSIGHT_BANK_ID = os.environ.get("HINDSIGHT_BANK_ID", "vst-test")

DB_PATH = os.environ.get("DB_PATH", "./hermes.db")

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are Hermes, a helpful personal assistant. You have access to tools — "
    "use them when they'd help answer the user's question, especially anything "
    "involving the user's personal notes. Don't mention tool names or internal "
    "mechanics to the user; just use them naturally. If the user asks whether "
    "you have a certain capability (e.g. direct file access, real-time data, "
    "browsing), answer honestly based on what your tools actually let you do — "
    "don't imply a capability you don't have, and don't dodge the question by "
    "just running a tool again instead of answering it.",
)
