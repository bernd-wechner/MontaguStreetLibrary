# Translate Tuya source IDs to a useful string describing the source
# Based on https://developer.tuya.com/en/docs/cloud/0a30fc557f?id=Ka7kjybdo0jse
EVENT_SOURCES = {-1: "unknown",
                  1: "device itself",
                  2: "client instructions",
                  3: "third-party platforms",
                  4: "cloud instructions"}

# Translate Tuya event IDs to a useful string describing the type of event
# Based on https://developer.tuya.com/en/docs/cloud/0a30fc557f?id=Ka7kjybdo0jse
EVENT_IDS = {-1: "unknown",
              1: "online",
              2: "offline",
              3: "device activation",
              4: "device reset",
              5: "command issuance",
              6: "firmware upgrade",
              7: "data report",
              8: "device semaphore",
              9: "device restart",
             10: "timing information"}

# JUst list the codes we support (for reference)
CODES = ["doorcontact_state", "updown_state", "battery_state"]

# translate door states True=Open, False=Closed
# Deduced by comparing a log here with one on the web at:
#     https://eu.iot.tuya.com/cloud/device/detail/
# where Tuya make that translation for us.
# Note: This is an EVENT not a STATE
DOOR_STATES = { "true": "Open",  # Moves the state from closed to open
                "false": "Closed" }  # Moves teh state fro open to closed

# The sensor only reports three battery states (alas).
BATTERY_STATES = ["low", "middle", "high"]

# And Event Type to code map
# Tuya only provide codes for "data report" events. But we give other event
# types a code as well, as we store it in a database column anyhow, to group
# related events.
UPTIME_CODE = "updown_state"

EVENT_CODES = {"online": UPTIME_CODE,
               "offline": UPTIME_CODE }

# Defines the gap between openings that separates visits.
# A gap this long or greater is classified a new visit.
VISIT_SEPARATION = 10  # Minutes
