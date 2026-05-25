
import discord
from discord.abc import GuildChannel
from discord import Message, Thread, TextChannel
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

class FloatAndErrors(NamedTuple):
    result: float 
    error_strings: List[str]

class AuditLogEntriesAndErrors(NamedTuple):
    audit_log_entires: List[discord.AuditLogEntry] 
    error_strings: List[str]

#===============================================#
#                Discord API Calls              #
#===============================================#

async def send(text: str, channel: TextChannel | Thread, delete_after: int = 0):
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


def split_text_in_halves(text: str, limit: int, seperator: str) -> list[str]:
    split_halves: List[str] = [] 
    if len(text) <= limit:
        split_halves.append(text)
    else:
        groups = text.split(seperator)
        groups_processed: list[str] = []
        total_char_len = 0
        for group_i, group in enumerate(groups):
            to_add = group
            if group_i != (len(groups) - 1):
                to_add += seperator
            groups_processed.append(to_add)
            total_char_len += len(to_add)

        embed_desc_1 = "" 
        embed_desc_2 = "" 
        len_iterator = 0
        for group in groups_processed:
            len_iterator += len(group)
            if len_iterator < (total_char_len / 2.0):
                embed_desc_1 += group
            else:
                embed_desc_2 += group

        if len(embed_desc_1):
            split_halves.append(embed_desc_1)
        if len(embed_desc_2): 
            split_halves.append(embed_desc_2)

    return split_halves

def split_text_groups_over_limit_by_seperator(groups: list[str], limit: int, seperator: str) -> list[str]:
    result = []
    for group in groups:
        if len(group) < limit:
            result.append(group)
        else:
            result.extend(split_text_in_halves(group, limit, seperator))
    return result

class EmbedDesc(NamedTuple):
    expires: bool = False
    title: str = ""
    footer: str = ""
    seperator: str = "\n"

async def send_embed(text: str, channel: TextChannel | Thread, desc: EmbedDesc):
    text = text.strip()
    color = get_config('embed_color')
    delete_after_seconds = None
    if desc.expires:
        if channel_is_types(channel, ['PROXY_QOC']):
            delete_after_seconds = get_config('proxy_embed_seconds')
        else: 
            delete_after_seconds = get_config('embed_seconds')

    embed_character_limit_title = get_config("embed_character_limit_title")
    title = desc.title
    if len(title) > embed_character_limit_title:
        title = title[:embed_character_limit_title]

    embed_character_limit_footer = get_config("embed_character_limit_footer")
    footer = desc.footer
    if len(footer) > embed_character_limit_footer:
        footer = footer[:embed_character_limit_footer]

    ##NOTE: (Ahmayk) we want to send the least amount of messages for speed
    ##since sending each message in sequence takes time
    ##As of writing, embed descs can hold 4096 characters
    ##however messages in total can only hold 6000 characters
    ##so in order to send the least amount of messages possible,
    ##we send the most characters we can in each message
    ##while also staying under the embed desc limit per embed 

    embed_character_limit_total = get_config("embed_character_limit_total")

    split_messages: List[str] = []
    all_lines = text.split(desc.seperator)
    wall_of_text = ""
    for line in all_lines:
        # line = line.replace('@', '')  # pings are fine specifically in embed
        next_length = len(wall_of_text) + len(line)

        desc_limit = embed_character_limit_total 
        if not len(split_messages):
            desc_limit -= len(title) 

        #TODO: (Ahmayk) don't subtract footer if we know we don't need it
        desc_limit -= len(footer) 

        if next_length > desc_limit:
            new_desc = wall_of_text[:-len(desc.seperator)]
            split_messages.append(new_desc)
            wall_of_text = line + desc.seperator 
        else:
            wall_of_text += line + desc.seperator

    split_messages.append(wall_of_text[:-len(desc.seperator)])

    embed_character_limit_desc = get_config("embed_character_limit_desc")

    embed_groups: List[List[discord.Embed]] = []
    for i, text_part in enumerate(split_messages):

        if len(text_part):

            #NOTE: (Ahmayk) split in half, assuming that half of the  
            #max message character length (6000)
            #will fit inside the max embed desc length (4096)
            split_subgroups = split_text_in_halves(text_part, embed_character_limit_desc, desc.seperator)  

            #NOTE: (Ahmayk) however this does not guarentee our seperator will
            #split our text under the desc limit. Keep splitting text chunks by reasonable seperators until they fit
            if desc.seperator != "\n":
                split_subgroups = split_text_groups_over_limit_by_seperator(split_subgroups, embed_character_limit_desc, "\n")

            if desc.seperator != " ":
                split_subgroups = split_text_groups_over_limit_by_seperator(split_subgroups, embed_character_limit_desc, " ")

            embed_list: List[discord.Embed] = []
            for k, subgroup in enumerate(split_subgroups):
                embed = None
                if i == 0 and k == 0: 
                    embed = discord.Embed(description=subgroup, color=color, title=title)
                else:
                    embed = discord.Embed(description=subgroup, color=color)
                
                if i == len(split_messages) - 1 and k == len(split_subgroups) - 1: 
                    embed.set_footer(text=desc.footer)
                embed_list.append(embed)
            
            embed_groups.append(embed_list)

    for embed_group in embed_groups:
        try:
            await channel.send(embeds=embed_group, delete_after=delete_after_seconds)
        except Exception as error:
            error_strings: list[str] = []
            await log_exception(f'Failed to send embed to {channel.jump_url}', error, error_strings, False)
            await send_if_errors("Failed to send embed", error_strings, channel)

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

async def write_log(msg: str = "Placeholder message", embed: bool = False):
    """
    Logging function.
    If LOG_CHANNEL is valid, send a message there.
    Also write to a log file as backup.
    """
    try:
        log_channel = bot.get_channel(get_log_channel())
        if embed:
            await send_embed(msg, log_channel, EmbedDesc())
        else:
            await send(msg, log_channel)
    except (discord.InvalidData, discord.HTTPException, discord.Forbidden) as e:
        msg += "\nError fetching log channel: {}".format(e.text)
    except discord.NotFound:
        pass

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
    log_channel = bot.get_channel(get_log_channel())
    if log_channel:
        await send(f'**{error_text}**\n```py\n{trace}\n```', log_channel)
    else:
        print("No log channel found.")
    error_strings.append(error_text)

async def discord_fetch_message(message_id: int, channel: TextChannel | Thread) -> MessageAndErrors: 
    message = None
    error_strings: List[str] = [] 
    try:
        message = await channel.fetch_message(message_id)
    except Exception as error:
        await log_exception(f'Discord API call failed to fetch message id {message_id}', error, error_strings, True)
    return MessageAndErrors(message, error_strings)


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



def channel_is_type(channel: typing.Union[GuildChannel, Thread], type: str) -> bool:
    return type in get_channel_config(channel.id).types or hasattr(channel, "parent") and channel_is_type(channel.parent, type)


def channel_is_types(channel: typing.Union[GuildChannel, Thread], types: typing.List[str]) -> bool:
    return any([t in get_channel_config(channel.id).types for t in types]) or hasattr(channel, "parent") and channel_is_types(channel.parent, types)


async def get_qoc_channel(channel: TextChannel | Thread):
    """
    Gets the first channel labeled QOC in bot_secrets.py 
    """
    if channel_is_type(channel, 'PROXY_QOC'):
        qoc_channel, msg = parse_channel_link(None, ["QOC"])
        if len(msg) > 0:
            await channel.send(msg)
            if qoc_channel == -1: return None
        channel = bot.get_channel(qoc_channel)
    return channel


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


##TODO: (Ahmayk) refactor input system, don't give default on error by default
def parse_channel_link(link: str | None, types: typing.List[str], give_default: bool = True) -> typing.Tuple[int, str]:
    """
    Parse the channel link and return the channel ID if it matches the specified types.
    If channel is invalid or does not match the types, returns the first channel in config matching the types.
    Returns null channel if no such channel types exists - the caller function should return early.

    Return values:
    - `channel_id`: Parsed channel ID if it is valid, default channel if it isn't, and -1 if no default channel
    - `msg`: Message to print if `channel_id` is not parsed from `link`, empty string otherwise
    """
    try:
        default_id = get_channel_ids_all()[0]
    except IndexError:
        return -1, "Error: No default channels found."
    
    if link is None or not len(link):
        return default_id, ""

    try:
        arg = int(link.split('/')[5])
    except IndexError:
        return -1, "Error: Cannot parse argument - make sure it is a valid link to channel."

    channel = bot.get_channel(arg)
    if channel_is_types(channel, types):
        return arg, ""
    elif give_default:
        return default_id, f"Warning: Link is not a valid roundup channel, defaulting to <#{default_id}>."
    else:
        return -1, "Error: Link is not a valid roundup channel."

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
            channel = bot.get_channel(message_reference.channel_id)
            if channel:
                message_and_errors = await discord_fetch_message(message_reference.message_id, channel)
                message = message_and_errors.message
                error_strings.extend(message_and_errors.error_strings)
            else:
                error_strings.extend("Error: Channel not found when parsing message reference")

    if not len(error_strings):
        assert message

    return MessageAndErrors(message, error_strings)


##NOTE: (Ahmayk) idk where to put this, not a discord thing
import functools
# https://stackoverflow.com/a/65882269
async def run_blocking(blocking_func: typing.Callable, *args, **kwargs) -> typing.Any:
    """
    Runs a blocking function in a non-blocking way.
    Needed because QoC functions take a while to run.
    """
    func = functools.partial(blocking_func, *args, **kwargs) # `run_in_executor` doesn't support kwargs, `functools.partial` does
    return await bot.loop.run_in_executor(None, func)