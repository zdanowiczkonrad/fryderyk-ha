"""Constants for the Fryderyk integration."""

DOMAIN = "fryderyk"

CONF_WEEKS = "weeks"
CONF_SCAN_MINUTES = "scan_minutes"
DEFAULT_WEEKS = 2
DEFAULT_SCAN_MINUTES = 30

# Upper bound for on-demand calendar fetches (weeks per request) to stay polite to the school server.
MAX_CALENDAR_WEEKS = 8

EVENT_LESSON_CANCELLED = "fryderyk_lesson_cancelled"
EVENT_NEW_MESSAGE = "fryderyk_new_message"
