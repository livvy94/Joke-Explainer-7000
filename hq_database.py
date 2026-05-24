
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
##python 3.10 doesn't have StrEnum, python documentation reccomends making it yourself
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
        else:
            error_strings.extend(floatAndErrors.error_strings)

        #NOTE: (Ahmayk) store 0 when we error. 
        # This results in not retrying on paths where don't want to download anything
        await store_in_database_float(duration, url, DatabaseKey.RIP_LENGTH)
    else:
        duration = JE_DATABASE[DatabaseKey.RIP_LENGTH][url]

    return FloatAndErrors(duration, error_strings)

