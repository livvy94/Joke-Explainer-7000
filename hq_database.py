
import shelve 
import asyncio 
from typing import NamedTuple
from enum import StrEnum
from datetime import datetime, timedelta, timezone

from hq_config import get_config, get_channel_ids_of_types 
from hq_discord import FloatAndErrors, run_blocking, discord_find_channel, discord_delete_messages
from simpleQoC.qoc import getAudioLengthInSecondsFFprobe 

JE_DATABASE = shelve.open("je_database", writeback=True)

class DatabaseKey(StrEnum):
    RIP_LENGTH = "RIP_LENGTH" 
    SENT_EMBED_TO_EXPIRE = "SENT_EMBED_TO_EXPIRE" 

DATABASE_LOCK = asyncio.Lock()

class GetRipUrlLengthDesc(NamedTuple):
    force_download: bool = False

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


class SentEmbed(NamedTuple):
    channel_id: int
    message_id: int
    sent_time: datetime

async def store_sent_embeds_in_expire_database(message_ids: list[int], channel_id: int):

    if DatabaseKey.SENT_EMBED_TO_EXPIRE not in JE_DATABASE:
        JE_DATABASE[DatabaseKey.SENT_EMBED_TO_EXPIRE] = [] 

    await DATABASE_LOCK.acquire()
    try:
        for message_id in message_ids:
            JE_DATABASE[DatabaseKey.SENT_EMBED_TO_EXPIRE].append(SentEmbed(channel_id, message_id, datetime.now(timezone.utc)))
        JE_DATABASE.sync()
    finally:
        DATABASE_LOCK.release()


async def cleanup_sent_embeds_in_expire_database():

    if DatabaseKey.SENT_EMBED_TO_EXPIRE not in JE_DATABASE:
        JE_DATABASE[DatabaseKey.SENT_EMBED_TO_EXPIRE] = [] 

    expire_time_proxy_qoc = get_config('proxy_embed_seconds')
    expire_time_qoc = get_config('embed_seconds')
    proxy_channel_ids = get_channel_ids_of_types(['PROXY_QOC'])

    sent_embeds_to_delete = []
    for sent_embed in JE_DATABASE[DatabaseKey.SENT_EMBED_TO_EXPIRE]:
        expire_time = expire_time_qoc
        if sent_embed.channel_id in proxy_channel_ids:
            expire_time = expire_time_proxy_qoc
        if (datetime.now(timezone.utc) - sent_embed.sent_time) > timedelta(seconds=expire_time):
            sent_embeds_to_delete.append(sent_embed)

    error_strings = []

    if len(sent_embeds_to_delete):

        channel_dict_channels = {}
        channel_dict_message_ids = {}

        for sent_embed in sent_embeds_to_delete:
            if sent_embed.channel_id not in channel_dict_channels:
                channel_and_errors = await discord_find_channel(sent_embed.channel_id)
                if channel_and_errors.channel:
                    channel_dict_channels[sent_embed.channel_id] = channel_and_errors.channel
            
            if sent_embed.channel_id not in channel_dict_message_ids:
                channel_dict_message_ids[sent_embed.channel_id] = []

            channel_dict_message_ids[sent_embed.channel_id].append(sent_embed.message_id)

        for channel in channel_dict_channels.values():
            await discord_delete_messages(channel_dict_message_ids[sent_embed.channel_id], channel)

        await DATABASE_LOCK.acquire()
        try:
            for sent_embed in sent_embeds_to_delete:
                JE_DATABASE[DatabaseKey.SENT_EMBED_TO_EXPIRE].remove(sent_embed)
            JE_DATABASE.sync()
        finally:
            DATABASE_LOCK.release()