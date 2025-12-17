"""Constants for QingLong integration."""

DOMAIN = "qinglong"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_SSL = "ssl"
CONF_TOKEN = "token"
CONF_TOKEN_EXPIRES = "token_expires"

# Defaults
DEFAULT_PORT = 5700
DEFAULT_SSL = False

# API endpoints
API_AUTH = "/open/auth/token"
API_CRONS = "/open/crons"
API_CRONS_RUN = "/open/crons/run"

# Token refresh settings - 提前1天刷新token
TOKEN_REFRESH_THRESHOLD = 86400  # 提前1天刷新token (24小时)
TOKEN_EXPIRY_BUFFER = 3600  # 1小时缓冲时间

# Platforms
PLATFORMS = ["sensor", "select", "button"]