
import shelve 
import asyncio 
from typing import NamedTuple, List
from enum import Enum
from discord import TextChannel, Thread, Guild

from hq_react import ReactType, react_type_to_react_name
from hq_discord import FloatAndErrors, run_blocking
from simpleQoC.qoc import getAudioLengthInSecondsFFprobe 

JE_DATABASE = shelve.open("je_database", writeback=True)

##NOTE: (Ahmayk) database keys must be strings
##python 3.10 doesn't have it, documentation reccomends making it yourself
## https://docs.python.org/3.10/library/enum.html#otherIs

class StrEnum(str, Enum):
    pass

class DatabaseKey(StrEnum):
    RIP_LENGTH = "RIP_LENGTH" 

DATABASE_LOCK = asyncio.Lock()

async def store_in_database_float(value: float, key: str, database_key: str):
    if (
        database_key != DatabaseKey.RIP_LENGTH
    ):
        assert f"{database_key} does not support float as input"

    await DATABASE_LOCK.acquire()
    try:
        JE_DATABASE[database_key][key] = value 
        JE_DATABASE.sync()
    finally:
        DATABASE_LOCK.release()


class GetRipUrlLengthDesc(NamedTuple):
    force_download: bool = False

async def get_rip_url_length(url: str, desc: GetRipUrlLengthDesc) -> FloatAndErrors: 
    duration = 0.0
    error_strings = []

    if DatabaseKey.RIP_LENGTH not in JE_DATABASE:
        JE_DATABASE[DatabaseKey.RIP_LENGTH] = {}

    if desc.force_download or (url not in JE_DATABASE[DatabaseKey.RIP_LENGTH]):
        floatAndErrors = await run_blocking(getAudioLengthInSecondsFFprobe, url)
        if not len(floatAndErrors.error_strings):
            duration = floatAndErrors.result
            await store_in_database_float(floatAndErrors.result, url, DatabaseKey.RIP_LENGTH)
        else:
            error_strings.extend(floatAndErrors.error_strings)
    else:
        duration = JE_DATABASE[DatabaseKey.RIP_LENGTH][url]

    return FloatAndErrors(duration, error_strings)


def format_rip_timecode(seconds: float, guild: Guild, jingle_length_in_seconds: float) -> str:
    jingle_emoji = ""
    if seconds <= jingle_length_in_seconds:
        jingle_emoji = f'{react_type_to_react_name(ReactType.JINGLE, guild)} '
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    time_string = f"{minutes:02d}:{secs:02d}"
    if hours > 0:
        time_string = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f'{jingle_emoji}**{time_string}**'