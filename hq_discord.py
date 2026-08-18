import discord
from discord.abc import GuildChannel
from discord import Message, Thread, TextChannel, CategoryChannel
from datetime import datetime, timezone, timedelta

from typing import NamedTuple, List

import traceback

from contextlib import asynccontextmanager

from hq_types import Rip, React 
from hq_config import * 
from hq_strings import *

import discord
bot = discord.Client(
    intents = discord.Intents.all() # This was a change necessitated by an update to discord.py :/
    # https://stackoverflow.com/questions/71950432/how-to-resolve-the-following-error-in-discord-py-typeerror-init-missing
    # Also had to enable MESSAGE CONENT INTENT https://stackoverflow.com/questions/71553296/commands-dont-run-in-discord-py-2-0-no-errors-but-run-in-discord-py-1-7-3
    # 10/28/22 They changed it again!!! https://stackoverflow.com/questions/73458847/discord-py-error-message-discord-ext-commands-bot-privileged-message-content-i
)

#===============================================#
#                AndErrors Types                #
#===============================================#

class ChannelAndErrors(NamedTuple):
    channel: TextChannel | Thread | None
    error_strings: List[str]

class ChannelsAndErrors(NamedTuple):
    channels: List[TextChannel | Thread]
    error_strings: List[str]

class MessageAndErrors(NamedTuple):
    message: Message | None 
    error_strings: List[str]

class MessagesAndErrors(NamedTuple):
    messages: List[Message]
    error_strings: List[str]

class UserReactDictAndErrors(NamedTuple):
    user_react_dict: dict[React, List[int]]
    error_strings: List[str]

class StringAndErrors(NamedTuple):
    string: str
    error_strings: List[str]

class RipsAndErrors(NamedTuple):
    rips: List[Rip]
    error_strings: List[str]

class BoolAndErrors(NamedTuple):
    result: bool
    error_strings: List[str]

class IntAndErrors(NamedTuple):
    result: int 
    error_strings: List[str]

class FloatAndErrors(NamedTuple):
    result: float 
    error_strings: List[str]

class AuditLogEntriesAndErrors(NamedTuple):
    audit_log_entires: List[discord.AuditLogEntry] 
    error_strings: List[str]

#NOTE: (Ahmayk) JSON is untyped boooo
class JSONAndErrors(NamedTuple):
    json: dict[typing.Any, dict]
    error_strings: list[str]

#===============================================#
#                Discord API Calls              #
#===============================================#

async def send(text: str, channel: TextChannel | Thread, delete_after: float = 0):
    limit = get_config("character_limit")
    split_message = split_long_message(text, limit)
    for line in split_message:
        if len(line):
            try:
                if delete_after:
                    await channel.send(line, delete_after=delete_after)
                else:
                    await channel.send(line)
            except Exception as error:
                #NOTE: (Ahmayk) write_log here could cause infinite error loops so just stay quiet about this one 
                txt = f'Failed to send message to {channel.jump_url}: {type(error).__name__}: {error}'
                print(f"\033[91m {txt}\033[0m")


def parse_errors(if_errors_txt: str, error_strings: List[str]) -> str:
    max_errors_to_send = 3
    return_text = "" 
    if len(error_strings):
        return_text += f':bangbang:{if_errors_txt}\n```' 
        return_text += "\n".join(error_strings[:max_errors_to_send])
        if len(error_strings) > max_errors_to_send:
            return_text += '\n ...(errors truncated)...'
        return_text += "```" 
    return return_text

async def send_if_errors(if_errors_txt: str, error_strings: List[str], channel: TextChannel | Thread):
    return_text = parse_errors(if_errors_txt, error_strings) 
    await send(return_text, channel)

async def send_and_if_errors(txt: str, if_errors_txt: str, error_strings: List[str], channel: TextChannel | Thread, delete_after: float = 0):
    error_text = parse_errors(if_errors_txt, error_strings) 
    if len(txt) or len(error_text):
        await send(f'{txt}\n{error_text}', channel, delete_after)


async def discord_find_channel(channel_id: int) -> ChannelAndErrors:
    channel = bot.get_channel(channel_id)
    error_strings: List[str] = []
    if not channel:
        try:
            channel = await bot.fetch_channel(channel_id)
            ##TODO: (Ahmayk) does a less intrusive way of unarchiving a thread exist?
            if isinstance(channel, Thread) and channel.archived:
                await send("Unarchiving!", channel, 1) 
        except Exception as error:
            await log_exception(f'Discord API call failed to fetch channel id {channel_id}', error, error_strings, True)
    return ChannelAndErrors(channel, error_strings) 


async def discord_get_text_channels_in_category(category_id) -> ChannelsAndErrors:
    channels: List[TextChannel] = []
    error_strings: List[str] = []
    try:
        category = bot.get_channel(category_id) 
        if isinstance(category, CategoryChannel):
            for channel in category.channels:
                ##NOTE: (Ahmayk) Only consider text channels, ignore voice and forum channels
                if isinstance(channel, TextChannel):
                    channels.append(channel)
        else:
            msg = f'Category ID: {category_id} isn\'t a category!'
            await write_log(msg)
            error_strings.append(msg)
    except Exception as error:
        await log_exception(f'Discord API call failed to fetch category id {category_id}', error, error_strings, True)
    return ChannelsAndErrors(channels, error_strings) 


async def get_log_channel() -> TextChannel | Thread | None:
    channel_and_errors = await discord_find_channel(get_log_channel_id())
    if len(channel_and_errors.error_strings):
        print("ERROR: Cound not post to log channel, channel not found." + "\n".join(channel_and_errors.error_strings))
    return channel_and_errors.channel

async def write_log(msg: str = "Placeholder message"):
    """
    Logging function.
    If LOG_CHANNEL is valid, send a message there.
    Also write to a log file as backup.
    """
    log_channel = await get_log_channel()
    if log_channel:
        await send(msg, log_channel)

    with open('bot_logs.txt', 'a', encoding='utf-8') as file:
        file.write(datetime.now(timezone.utc).strftime('%m/%d/%y %I:%M %p'))
        file.write('\n')
        file.write(msg)
        file.write('\n=========================================\n')

async def send_crash(txt: str, error: Exception, channel: TextChannel | Thread | None):
    error_string = f"{type(error).__name__}: {error}"
    description = f":boom: Intriguing! I have encountered an unexpected error! ```{error_string}```"
    if channel:
        await send(description, channel)

    await log_exception(txt, error, [], False)


async def log_exception(txt: str, error: Exception, error_strings: List[str], full_stack: bool):
    error_text = f'{txt}\n{type(error).__name__}: {error}'
    trace = traceback.format_exc()
    if full_stack:
        trace = "".join(traceback.extract_stack().format())
    print(f"\033[91m {error_text}\n{trace}\033[0m")
    log_channel = await get_log_channel()
    if log_channel:
        await send(f'**{error_text}**\n```py\n{trace}\n```', log_channel)
    error_strings.append(error_text)


async def get_channels_of_types(include_types: list[str], exclude_types: list[str]) -> ChannelsAndErrors: 

    channel_ids = [] 
    channels_json = get_config(CHANNEL_KEY)
    for channel_json in channels_json:
        is_match = False
        for type in include_types:
            if type in channel_json["types"]: 
                is_match = True
                break
        for type in exclude_types:
            if type in channel_json["types"]: 
                is_match = False 
                break
        if is_match:
            channel_ids.append(int(channel_json["id"]))

    category_ids = []
    json = get_config(CATEGORY_KEY)
    for category_json in json:
        for type in include_types:
            if type == category_json["type"]: 
                category_ids.append(int(category_json["id"]))
                break

    channels = []
    error_strings = []
    for channel_json in channel_ids:
        channel_and_errors = await discord_find_channel(channel_json)
        error_strings.extend(channel_and_errors.error_strings)
        if channel_and_errors.channel:
            channels.append(channel_and_errors.channel)

    for category_id in category_ids:
        channels_and_errors = await discord_get_text_channels_in_category(category_id)
        error_strings.extend(channel_and_errors.error_strings)
        for channel in channels_and_errors.channels:
            if channel not in channels:
                channels.append(channel)

    return ChannelsAndErrors(channels, error_strings) 



async def discord_fetch_message(message_id: int, channel: TextChannel | Thread) -> MessageAndErrors: 
    message = None
    error_strings: List[str] = [] 
    try:
        message = await channel.fetch_message(message_id)
    except Exception as error:
        await log_exception(f'Discord API call failed to fetch message id {message_id}', error, error_strings, True)
    return MessageAndErrors(message, error_strings)


##TODO: (Ahmayk) lol stupid library
# #We're calling unexposed functions because discord.py wants a message object for this
# despite only using the id. which is stupid 
# (it also doesn't handle bulk deletion for above 100)
async def discord_delete_messages(message_ids: list[int], channel: TextChannel | Thread) -> list[str]: 
    error_strings: List[str] = [] 
    if len(message_ids) == 1:
        try:
            await channel._state.http.delete_message(channel.id, message_ids[0])
        except discord.errors.NotFound:
            pass
        except Exception as error:
            await log_exception(f'Discord API call failed to delete message id {message_ids[0]} in {channel.jump_url}', error, error_strings, True)
    else:
        while len(message_ids):
            try:
                await channel._state.http.delete_messages(channel.id, message_ids[:100])
            except discord.errors.NotFound:
                pass
            except Exception as error:
                await log_exception(f'Discord API call failed to bulk delete messages in {channel.jump_url}', error, error_strings, True)
            message_ids = message_ids[100:]
    return error_strings


async def discord_get_channel_messages(limit: int | None, channel: TextChannel | Thread) -> MessagesAndErrors: 
    messages = [] 
    error_strings: List[str] = [] 
    try:
        messages = [message async for message in channel.history(limit=limit)]
    except Exception as error:
        await log_exception(f'Discord API call failed to fetch channel messages from {channel.jump_url}', error, error_strings, True)
    return MessagesAndErrors(messages, error_strings) 


async def discord_get_channel_messages_after(message: Message, limit: int | None) -> MessagesAndErrors: 
    messages = [] 
    error_strings: List[str] = [] 
    try:
        messages = [message async for message in message.channel.history(limit=limit, after=message)]
    except Exception as error:
        await log_exception(f'Discord API call failed to fetch channel messages from {message.channel.jump_url} after message {message.jump_url}', error, error_strings, True)
    return MessagesAndErrors(messages, error_strings) 


async def discord_get_channel_pins(limit: int | None, channel: TextChannel | Thread) -> MessagesAndErrors: 
    messages: List[Message] = [] 
    error_strings: List[str] = [] 
    try:
        messages = [message async for message in channel.pins(limit=limit)]
    except Exception as error:
        await log_exception(f'Discord API call failed to fetch channel pins from {channel.name}', error, error_strings, True)
    return MessagesAndErrors(messages, error_strings)

# NOTE: (Ahmayk) Dummy async context that we can call instead in the case where
# we do not input a channel for channel.typing()
@asynccontextmanager
async def empty_async_context():
    yield

async def discord_cleanup_embeds(limit: int | None, expire_time: float, channel: TextChannel | Thread, \
                                 typing_channel: TextChannel | Thread | None) -> MessagesAndErrors: 
    deleted_messages = [] 
    error_strings: List[str] = [] 

    def should_delete(message: Message):
        result = message.author == bot.user and len(message.embeds) and (message.embeds[0].type == "rich") and (message.embeds[0].title is None)
        if result and expire_time: 
            result = (datetime.now(timezone.utc) - message.created_at) > timedelta(seconds=expire_time)
        return result 

    try:
        async with typing_channel.typing() if typing_channel is not None else empty_async_context():
            deleted_messages = await channel.purge(limit=limit, check=should_delete)
    except Exception as error:
        await log_exception(f'Discord API call failed to delete messages from {channel.jump_url}', error, error_strings, True)

    return MessagesAndErrors(deleted_messages, error_strings)


async def discord_get_audit_log_entries(action_type: discord.AuditLogAction, limit: int | None, guild: discord.Guild) -> AuditLogEntriesAndErrors: 
    audit_log_entries = [] 
    error_strings: List[str] = [] 
    try:
        audit_log_entries = [entry async for entry in guild.audit_logs(limit=limit, action=action_type)]
    except Exception as error:
        await log_exception(f'Discord API call failed to read audit log', error, error_strings, True)
    return AuditLogEntriesAndErrors(audit_log_entries, error_strings) 


async def discord_unpin_message(message: Message) -> List[str]: 
    error_strings: List[str] = [] 
    try:
        await message.unpin()
    except Exception as error:
        await log_exception(f'Discord API call failed to unpin message: {message.id}', error, error_strings, True)
    return error_strings


async def discord_add_reaction(reaction_string: str, message: Message) -> List[str]: 
    error_strings: List[str] = [] 
    try:
        await message.add_reaction(reaction_string)
    except Exception as error:
        await log_exception(f'Discord API call failed to add reaction {reaction_string} to {message.jump_url}', error, error_strings, True)
    return error_strings


async def discord_clear_reaction(reaction_string: str, message: Message) -> List[str]: 
    error_strings: List[str] = [] 
    try:
        await message.clear_reaction(reaction_string)
    except Exception as error:
        await log_exception(f'Discord API call failed to clear reaction {reaction_string} from {message.jump_url}', error, error_strings, True)
    return error_strings


async def discord_remove_reaction(reaction_string: str, user_id: int, message: Message) -> List[str]: 
    error_strings: List[str] = [] 
    try:
        member = message.guild.get_member(user_id)
        await message.remove_reaction(reaction_string, member)
    except Exception as error:
        await log_exception(f'Discord API call failed to remove reaction {reaction_string} from {message.jump_url} from user id {user_id}', error, error_strings, True)
    return error_strings


async def discord_edit_message(message: Message, text: str) -> List[str]: 
    error_strings: List[str] = [] 
    try:
        #NOTE: (Ahmayk) if message has attachments, components, or embeds they will disappear
        await message.edit(content=text)
    except Exception as error:
        await log_exception(f'Discord API call failed to edit message: {message.jump_url}', error, error_strings, True)
    return error_strings


def channel_is_types(channel: TextChannel | Thread, types: list[str]) -> bool:
    result = False
    channel_config = get_channel_config(channel.id)
    if len(channel_config.types):
        for type in types: 
            if type in channel_config.types:
                result = True
                break
    else:
        if hasattr(channel, "parent") and isinstance(channel.parent, TextChannel):
            result = channel_is_types(channel.parent, types)
        elif isinstance(channel.category, CategoryChannel):
            category_config = get_category_config(channel.category.id)
            if category_config.type in types: 
                result = True
    return result 


def channel_is_type(channel: TextChannel | Thread, type: str) -> bool:
    return channel_is_types(channel, [type])


async def get_qoc_channel(channel: TextChannel | Thread) -> ChannelAndErrors:
    if channel_is_types(channel, ['PROXY_QOC']):
        return await get_default_config_channel_of_type("QOC")
    else:
        return ChannelAndErrors(channel, []) 


#TODO: (Ahmayk) simplify 
async def parse_message_link(link: str):
    """
    Parse the message link and return the server, channel and message objects.
    """
    try:
        ids = link.replace('>', '').split('/')
        server_id = int(ids[4])
        channel_id = int(ids[5])
        msg_id = int(ids[6])
    except (IndexError, ValueError):
        return None, None, None, "Error: Cannot parse argument - make sure it is a valid link to message (right click > Copy Link)."

    server = bot.get_guild(server_id)

    #TODO: (Ahmayk) handle server being null
    channel = server.get_channel_or_thread(channel_id)

    #TODO: (Ahmayk) handle message being null
    message_and_errors = await discord_fetch_message(msg_id, channel)
    status = "" 
    if len(message_and_errors.error_strings):
        status = "\n".join(message_and_errors.error_strings)

    return server, channel, message_and_errors.message, status 

async def get_default_config_channel_of_type(channel_type: str) -> ChannelAndErrors:
    channel = None
    error_strings = []
    channels_json = get_config(CHANNEL_KEY)
    if len(channels_json):
        channel_id = 0
        for channel_json in channels_json:
            if channel_type in channel_json["types"]: 
                channel_id = int(channel_json["id"])
                break
        channel_and_errors = await discord_find_channel(channel_id)
        channel = channel_and_errors.channel
        error_strings.extend(channel_and_errors.error_strings)
    else:
        error_strings.append("No channels configured. Contact a bot maintainer.")
    return ChannelAndErrors(channel, error_strings)


class ParseChannelLinkResult(NamedTuple):
    channel: TextChannel | Thread | None
    input_error: str
    error_strings: list[str]

async def parse_channel_link(link: str, valid_channel_types: list[str]) -> ParseChannelLinkResult: 
    channel = None
    input_error = ""
    error_strings: list[str] = []

    if len(link):
        args = link.split('/')
        if len(args) < 6:
            input_error = f"Invalid discord channel link: `{link}`"

        if not len(input_error):
            channel_and_errors = await discord_find_channel(int(args[5]))
            error_strings.extend(channel_and_errors.error_strings)
            if not len(channel_and_errors.error_strings):
                if channel_and_errors.channel and channel_is_types(channel_and_errors.channel, valid_channel_types):
                    channel = channel_and_errors.channel
                elif channel_and_errors.channel:
                    input_error = f"{channel_and_errors.channel.jump_url} is not a valid channel type (Expected: {valid_channel_types})."

    if not len(input_error) and not channel and len(valid_channel_types):
        channel_and_errors = await get_default_config_channel_of_type(valid_channel_types[0])
        channel = channel_and_errors.channel
        error_strings.extend(channel_and_errors.error_strings)

    return ParseChannelLinkResult(channel, input_error, error_strings)

async def parse_channel_link_or_text(args: list[str]) -> StringAndErrors:
    text = " ".join(args)
    error_strings = []
    if len(args):
        message_link = extract_discord_link(args[0])
        if len(message_link):
            server, channel, message, status = await parse_message_link(message_link)
            if message is None:
                error_strings.append(status)
            text = message.content
    return StringAndErrors(text, error_strings) 


async def get_message_from_referece_or_args(message_reference: discord.MessageReference | None, command_args: list[str]) -> MessageAndErrors:
    message = None
    error_strings = []

    if len(command_args):
        link = command_args[0].strip()
        if len(link):
            server, channel, message, status = await parse_message_link(link)
            if message is None:
                error_strings.append(status)

    if not message and message_reference and message_reference.message_id:
        if message_reference.cached_message:
            message = message_reference.cached_message
        else:
            channel_and_errors = await discord_find_channel(message_reference.channel_id)
            error_strings.extend(channel_and_errors.error_strings)
            if channel_and_errors.channel:
                message_and_errors = await discord_fetch_message(message_reference.message_id, channel_and_errors.channel)
                message = message_and_errors.message
                error_strings.extend(message_and_errors.error_strings)

    return MessageAndErrors(message, error_strings)


##NOTE: (Ahmayk) idk where to put this, not a discord thing
##NOTE: (Ahmayk later) actually this does belong here because it's using discord.py
import functools
# https://stackoverflow.com/a/65882269
async def run_blocking(blocking_func: typing.Callable, *args, **kwargs) -> typing.Any:
    """
    Runs a blocking function in a non-blocking way.
    For API calls and long operations
    """
    func = functools.partial(blocking_func, *args, **kwargs) # `run_in_executor` doesn't support kwargs, `functools.partial` does
    return await bot.loop.run_in_executor(None, func)


##NOTE: (Ahmayk) custom button for simpler button usage 
class JEButton(discord.ui.Button):
    def __init__(
            self,
            label: str,
            custom_id: str,
            style: discord.ButtonStyle,
            ##NOTE: (Ahmayk) 2nd parameter is button_state
            # has anything you want in it to keep state across buttons
            # method must be async
            callback: Callable[[discord.Interaction, typing.Any, discord.ui.Button], typing.Awaitable[typing.Any]],
            button_state: typing.Any,
        ):
        self.custom_callback = callback
        self.button_state = button_state
        super().__init__(
            label=label,
            custom_id=custom_id,
            style=style
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.custom_callback(interaction, self.button_state, self)
        except Exception as error:
            await send_crash(f'ERROR on button', error, interaction.channel)


#NOTE: (Ahmayk) Custom View (discord.py abstraction that holds components)
# does some shennanigans to disable buttons on timeout
# Wild that this isn't built into the library
class JEView(discord.ui.View):
    def __init__(self, timeout_in_seconds: float):
        self.message: Message | None = None
        super().__init__(timeout=timeout_in_seconds)

    async def on_timeout(self):
        try:
            if self.message:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)
        except Exception as error:
            await log_exception(f'ERROR on button timeout', error, False)
        

    async def wait_then_disable(self, message: Message):
        self.message = message
        await super().wait()