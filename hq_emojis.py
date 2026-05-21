from typing import NamedTuple
from enum import Enum, auto

APPROVED_INDICATOR = '🔥'
AWAITING_SPECIALIST_INDICATOR = '♨️'
SPECS_OVERDUE_INDICATOR = '🫑'
OVERDUE_INDICATOR = '🕒'

DEFAULT_CHECK = '✅'
DEFAULT_FIX = '🔧'
DEFAULT_ERROR = '💢'
DEFAULT_STOP = '🛑'
DEFAULT_GOLDCHECK = '🎉'
DEFAULT_REJECT = '❌'
DEFAULT_ALERT = '❗'
DEFAULT_QOC = '🛃'
DEFAULT_METADATA = '📝'
DEFAULT_THUMBNAIL = '🖼️'
DEFAULT_SENDBACK = '➡️'
DEFAULT_CALENDAR_1 = '📆'
DEFAULT_CALENDAR_2 = '📅'
DEFAULT_CALENDAR_3 = '🗓️' 
DEFAULT_PIN = '📌'

QOC_DEFAULT_LINKERR = '🔗'
QOC_DEFAULT_BITRATE = '🔢'
QOC_DEFAULT_CLIPPING = '📢'

#NOTE: (Ahmayk) reacts that match to a single emoji,
# either a custom emoji or a default fallback
class ReactType(Enum):
    NULL = auto()
    GOLDCHECK = auto()
    CHECK = auto()
    FIX = auto()
    REJECT = auto()
    STOP = auto()
    ALERT = auto()
    QOC = auto()
    METADATA = auto()
    THUMBNAIL = auto()
    EMAILSENT = auto()
    ANTIMAIL = auto()
    SENDBACK = auto()
    CALENDAR = auto()
    BITRATE = auto()
    CLIPPING = auto()

class ReactInfo(NamedTuple):
    default_names: list[str]
    custom_names: list[str]

REACT_DATABASE: dict[ReactType, ReactInfo] = {
    ReactType.GOLDCHECK: ReactInfo([DEFAULT_GOLDCHECK], ["goldcheck"]),
    ReactType.CHECK: ReactInfo([DEFAULT_CHECK], ["check"]),
    ReactType.FIX: ReactInfo([DEFAULT_FIX], ["fix", "wrench"]),
    ReactType.REJECT: ReactInfo([DEFAULT_REJECT], ["reject"]),
    ReactType.STOP: ReactInfo([DEFAULT_STOP], ["stop", "octagonal"]),
    ReactType.ALERT: ReactInfo([DEFAULT_ALERT], ["alert"]),
    ReactType.QOC: ReactInfo([DEFAULT_QOC], ["qoc"]),
    ReactType.METADATA: ReactInfo([DEFAULT_METADATA], ["metadata"]),
    ReactType.THUMBNAIL: ReactInfo([DEFAULT_THUMBNAIL], ["thumbnail"]),
    ReactType.EMAILSENT: ReactInfo([""], ["emailsent"]),
    ReactType.ANTIMAIL: ReactInfo([""], ["antimail"]),
    ReactType.SENDBACK: ReactInfo([DEFAULT_SENDBACK], ["sendback"]),
    ReactType.CALENDAR: ReactInfo([DEFAULT_CALENDAR_1, DEFAULT_CALENDAR_2, DEFAULT_CALENDAR_3], ["calendar"]),
    ReactType.BITRATE: ReactInfo([QOC_DEFAULT_BITRATE], ["bitrate"]),
    ReactType.CLIPPING: ReactInfo([QOC_DEFAULT_CLIPPING], ["clipping"]),
}

#NOTE: (Ahmayk) react categories where multiple emojis are valid
class ReactCategory(Enum):
    CHECKREQ = auto()
    NUMBER = auto()

REVIEW_REACT_LIST = [ReactType.CHECK, ReactType.GOLDCHECK, ReactType.FIX, ReactType.ALERT, ReactType.REJECT]
FIX_REACT_LIST = [ReactType.FIX, ReactType.ALERT]

KEYCAP_EMOJIS = {'2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10}