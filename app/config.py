import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.157:11434")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen3:14b")

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

# CodebaseSearcher runs inside K3s too, same as Athenaeum now does —
# in-cluster service DNS, no Host-header trick needed. On-demand repo
# research/indexing, not a background sync — see its own README for why
# that's a deliberately different shape from Athenaeum's hourly vault sync.
CODEBASE_SEARCHER_URL = os.environ.get("CODEBASE_SEARCHER_URL", "http://codebase-searcher-api:8000")

# What "today" means for habit logging/streaks. Deliberately explicit rather
# than trusting the pod's system clock — K3s containers default to UTC
# regardless of the host machine's own local timezone, so date.today() in
# the pod silently rolls over to tomorrow hours before it actually is
# tomorrow for the user (confirmed live: still showing "today" as done at
# 7:39pm Eastern, because UTC had already ticked into the next day).
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "America/New_York")

# Tasks (urgency x importance quadrants) and habit tracking — a separate Postgres
# instance from Hindsight's, deliberately: this is mutable structured
# state (status flags, streak counts), not semantic memory to recall by
# similarity, so it doesn't belong in Hindsight's bank.
PLANNER_DB_URL = os.environ.get(
    "PLANNER_DB_URL", "postgresql://hermes:hermes@localhost:5432/planner"
)

# Single shared password gating the whole app — appropriate for a personal,
# single-user tool, not a multi-account system. Required because Hermes is
# now reachable via a NodePort (see k8s/hermes-api.yaml) as well as the
# hostname-based Ingress, and a NodePort bypasses Traefik entirely, so any
# auth enforced at the ingress/reverse-proxy layer wouldn't cover it. Auth
# lives in the app itself so both paths are covered by the same check.
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "hermes")
# Signs the session cookie issued after a successful login. Must be set to a
# real random value in production (K8s secret) — the dev default is fine
# locally but would let anyone forge a valid session if used in deployment.
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-insecure-secret")

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "You are Hermes, a helpful personal assistant. You have access to tools — "
    "use them when they'd help answer the user's question, especially anything "
    "involving the user's personal notes. Don't mention tool names or internal "
    "mechanics to the user; just use them naturally. If the user asks whether "
    "you have a certain capability (e.g. direct file access, real-time data, "
    "browsing), answer honestly based on what your tools actually let you do — "
    "don't imply a capability you don't have, and don't dodge the question by "
    "just running a tool again instead of answering it. If the user asks for "
    "an image — even one identical or very similar to something asked for "
    "earlier in this conversation — always actually call generate_image "
    "again. Never just say you've made one without calling the tool for "
    "that message; a repeated request is a request for a new image, not a "
    "reference to the old one.",
)
