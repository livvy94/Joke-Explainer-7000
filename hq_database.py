
import shelve 
import asyncio 
from typing import NamedTuple, List
from enum import Enum, StrEnum
from discord import TextChannel, Thread, Guild

from hq_discord import FloatAndErrors, run_blocking
from simpleQoC.qoc import getAudioLengthInSecondsFFprobe 

JE_DATABASE = shelve.open("je_database", writeback=True)

class DatabaseKey(StrEnum):
    RIP_LENGTH = "RIP_LENGTH" 

DATABASE_LOCK = asyncio.Lock()

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

        await DATABASE_LOCK.acquire()
        try:
            #NOTE: (Ahmayk) store 0 when we error. 
            # This results in not retrying on paths where don't want to download anything
            JE_DATABASE[DatabaseKey.RIP_LENGTH][url] = duration
            JE_DATABASE.sync()
        finally:
            DATABASE_LOCK.release()
    else:
        duration = JE_DATABASE[DatabaseKey.RIP_LENGTH][url]

    return FloatAndErrors(duration, error_strings)


async def remove_urls_from_database(urls_to_remove: list[str]):
    if len(urls_to_remove):
        await DATABASE_LOCK.acquire()
        try:
            for url in urls_to_remove:
                JE_DATABASE[DatabaseKey.RIP_LENGTH].pop(url)
            JE_DATABASE.sync()
        finally:
            DATABASE_LOCK.release()