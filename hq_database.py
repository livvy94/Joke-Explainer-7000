
import shelve 
import asyncio 
from typing import NamedTuple
from enum import StrEnum
from datetime import datetime, timedelta, timezone

from hq_config import get_config, get_channel_ids_of_types 
from hq_discord import FloatAndErrors, StringAndErrors, MessagesAndErrors, run_blocking, discord_find_channel, discord_delete_messages, discord_get_channel_messages
from simpleQoC.qoc import getAudioLengthInSecondsFFprobe 

JE_DATABASE = shelve.open("je_database", writeback=True)
THUMBNAIL_DATABASE = shelve.open("thumbnail_database", writeback=True)

class JEDatabaseKey(StrEnum):
    RIP_LENGTH = "RIP_LENGTH" 
    SENT_EMBED_TO_EXPIRE = "SENT_EMBED_TO_EXPIRE" 

JE_DATABASE_LOCK = asyncio.Lock()
THUMBNAIL_DATABASE_LOCK = asyncio.Lock()

class GetRipUrlLengthDesc(NamedTuple):
    force_download: bool = False

async def store_in_database_float(value: float, key: str, database_key: str):
    if (
        database_key != JEDatabaseKey.RIP_LENGTH
    ):
        assert f"{database_key} does not support float as input"

    await JE_DATABASE_LOCK.acquire()
    try:
        JE_DATABASE[database_key][key] = value 
        JE_DATABASE.sync()
    finally:
        JE_DATABASE_LOCK.release()

async def get_rip_url_length(url: str, desc: GetRipUrlLengthDesc) -> FloatAndErrors: 
    duration = 0.0
    error_strings = []

    if JEDatabaseKey.RIP_LENGTH not in JE_DATABASE:
        JE_DATABASE[JEDatabaseKey.RIP_LENGTH] = {}

    if desc.force_download or (url not in JE_DATABASE[JEDatabaseKey.RIP_LENGTH]):
        floatAndErrors = await run_blocking(getAudioLengthInSecondsFFprobe, url)
        if not len(floatAndErrors.error_strings):
            duration = floatAndErrors.result
        else:
            error_strings.extend(floatAndErrors.error_strings)

        await JE_DATABASE_LOCK.acquire()
        try:
            #NOTE: (Ahmayk) store 0 when we error. 
            # This results in not retrying on paths where don't want to download anything
            JE_DATABASE[JEDatabaseKey.RIP_LENGTH][url] = duration
            JE_DATABASE.sync()
        finally:
            JE_DATABASE_LOCK.release()
    else:
        duration = JE_DATABASE[JEDatabaseKey.RIP_LENGTH][url]

    return FloatAndErrors(duration, error_strings)


async def remove_urls_from_database(urls_to_remove: list[str]):
    if len(urls_to_remove):
        await JE_DATABASE_LOCK.acquire()
        try:
            for url in urls_to_remove:
                JE_DATABASE[JEDatabaseKey.RIP_LENGTH].pop(url)
            JE_DATABASE.sync()
        finally:
            JE_DATABASE_LOCK.release()


class SentEmbed(NamedTuple):
    channel_id: int
    message_id: int
    sent_time: datetime

async def store_sent_embeds_in_expire_database(message_ids: list[int], channel_id: int):

    if JEDatabaseKey.SENT_EMBED_TO_EXPIRE not in JE_DATABASE:
        JE_DATABASE[JEDatabaseKey.SENT_EMBED_TO_EXPIRE] = [] 

    await JE_DATABASE_LOCK.acquire()
    try:
        for message_id in message_ids:
            JE_DATABASE[JEDatabaseKey.SENT_EMBED_TO_EXPIRE].append(SentEmbed(channel_id, message_id, datetime.now(timezone.utc)))
        JE_DATABASE.sync()
    finally:
        JE_DATABASE_LOCK.release()


async def cleanup_sent_embeds_in_expire_database():

    if JEDatabaseKey.SENT_EMBED_TO_EXPIRE not in JE_DATABASE:
        JE_DATABASE[JEDatabaseKey.SENT_EMBED_TO_EXPIRE] = [] 

    expire_time_proxy_qoc = get_config('proxy_embed_seconds')
    expire_time_qoc = get_config('embed_seconds')
    proxy_channel_ids = get_channel_ids_of_types(['PROXY_QOC'])

    sent_embeds_to_delete = []
    for sent_embed in JE_DATABASE[JEDatabaseKey.SENT_EMBED_TO_EXPIRE]:
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

        await JE_DATABASE_LOCK.acquire()
        try:
            for sent_embed in sent_embeds_to_delete:
                JE_DATABASE[JEDatabaseKey.SENT_EMBED_TO_EXPIRE].remove(sent_embed)
            JE_DATABASE.sync()
        finally:
            JE_DATABASE_LOCK.release()


THUMBNAIL_DICT_KEY = "THUMBNAIL_DICT_KEY"

async def refresh_thumbnail_cache() -> StringAndErrors: 

    string = ""
    error_strings = []

    channel_ids = get_channel_ids_of_types(['THUMBNAILS'])
    if not len(channel_ids):
        error_strings.append(f"Thumbnail channel not defined in bot config (contact bot maintainer).")

    if not len(error_strings):
        channel_and_errors = await discord_find_channel(channel_ids[0])
        error_strings.extend(channel_and_errors.error_strings)

    messages_and_errors = MessagesAndErrors([], []) 
    if not len(error_strings):
        messages_and_errors = await discord_get_channel_messages(None, channel_and_errors.channel)
        error_strings.extend(messages_and_errors.error_strings)

    if not len(error_strings):

        thumbnail_dict = {} 
        for message in messages_and_errors.messages:
            if (
                len(message.content)
                and len(message.attachments)
                and message.attachments[0].width
                and message.attachments[0].height
            ):
                thumbnail_dict[message.id] = message.content
        
        await THUMBNAIL_DATABASE_LOCK.acquire()
        try:
            THUMBNAIL_DATABASE[THUMBNAIL_DICT_KEY] = thumbnail_dict 
            THUMBNAIL_DATABASE.sync()
        finally:
            THUMBNAIL_DATABASE_LOCK.release()

        ##NOTE: (Ahmayk) output list in text of everything in database, cause it's maybe useful 
        #And doesn't take that much space
        output_file_text = ""
        for v in thumbnail_dict.values():
            output_file_text += f'\n{v}'
        with open("thumbnail_message_titles.txt", "a", encoding="utf-8") as f:
            f.write(output_file_text)

        string = f"All done!"
        string += f"\n- {len(messages_and_errors.messages)} searched messages."
        string += f"\n- {len(thumbnail_dict)} image messages."

    return StringAndErrors(string, error_strings)