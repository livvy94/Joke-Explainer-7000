
from typing import NamedTuple, List
from datetime import datetime

#NOTE: (Ahmayk) These the most important types that the entire program relies on
#types that are only relevant to a specific file and that file's dependants do not need to go here

class React(NamedTuple):
    id: int
    name: str
    string: str

class Rip(NamedTuple):
    text: str
    message_id: int
    channel_id: int
    guild_id: int
    message_author_id: int
    message_author_name: str
    reacts: List[React]
    created_at: datetime
