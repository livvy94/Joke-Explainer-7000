
import shelve 
import asyncio 
from typing import NamedTuple, List
from enum import Enum, auto
from discord import TextChannel, Thread, Guild

from hq_react import ReactType, react_type_to_react_name
from hq_vet import run_blocking 
from hq_discord import FloatAndErrors 
from simpleQoC.qoc import ffmpegExists, getAudioLengthInSecondsFFprobe 

JE_DATABASE = shelve.open("je_database", writeback=True)

DATABASE_LOCK = asyncio.Lock()

class GetRipUrlLengthDesc(NamedTuple):
    force_download: bool = False

async def get_rip_url_length(url: str, desc: GetRipUrlLengthDesc) -> FloatAndErrors: 
    duration = 0.0
    error_strings = []

    rip_length_key = "RIP_LENGTH"

    if rip_length_key not in JE_DATABASE:
        JE_DATABASE[rip_length_key] = {}

    if desc.force_download or (url not in JE_DATABASE[rip_length_key]):
        floatAndErrors = await run_blocking(getAudioLengthInSecondsFFprobe, url)
        if not len(floatAndErrors.error_strings):
            await DATABASE_LOCK.acquire()
            try:
                duration = floatAndErrors.value
                JE_DATABASE[rip_length_key][url] = floatAndErrors.value
                JE_DATABASE.sync()
            finally:
                DATABASE_LOCK.release()
        else:
            error_strings.extend(floatAndErrors.error_strings)

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