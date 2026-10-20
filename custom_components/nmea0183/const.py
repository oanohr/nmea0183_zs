DOMAIN = "nmea0183"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_SENTENCE_INCLUDE = "sentence_include"
CONF_SENTENCE_EXCLUDE = "sentence_exclude"
CONF_SECONDS_BETWEEN_UPDATES = "seconds_between_updates"
CONF_READ_TIMEOUT = "read_timeout"
CONF_STALE_TIMEOUT = "stale_timeout"

DEFAULT_SECONDS_BETWEEN_UPDATES = 5
# Receivers send GGA every 30 s: allow a few missed/late sentences before reacting
DEFAULT_READ_TIMEOUT = 120
DEFAULT_STALE_TIMEOUT = 120
