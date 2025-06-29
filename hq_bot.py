#!/usr/bin/python3
import discord
from discord import Message, Thread, TextChannel, Reaction
from discord.abc import GuildChannel
from discord.ext import commands
from discord.ext.commands import Context
from bot_secrets import TOKEN, YOUTUBE_API_KEY, YOUTUBE_CHANNEL_NAME, CHANNELS
from datetime import datetime, timezone, timedelta

from simpleQoC.qoc import performQoC, msgContainsBitrateFix, msgContainsClippingFix, msgContainsSigninErr, ffmpegExists, getFileMetadata
from simpleQoC.metadata import checkMetadata, countDupe, isDupe
import re
import functools
import typing
import math
import json
import os

MESSAGE_SECONDS = 2700  # 45 minutes
PROXY_MESSAGE_SECONDS = 43200  # 12 hours
DISCORD_CHARACTER_LIMIT = 4000 # Lower this to 2000 if we lose boosts (TODO: move to bot_secrets?)
EMBED_COLOR = 0x481761
OVERDUE_DAYS = 30

# Emoji definitions
APPROVED_INDICATOR = '🔥'
AWAITING_SPECIALIST_INDICATOR = '♨️'
OVERDUE_INDICATOR = '🕒'

DEFAULT_CHECK = '✅'
DEFAULT_FIX = '🔧'
DEFAULT_STOP = '🛑'
DEFAULT_GOLDCHECK = '🎉'
DEFAULT_REJECT = '❌'
DEFAULT_ALERT = '❗'
DEFAULT_QOC = '🛃'
DEFAULT_METADATA = '📝'

QOC_DEFAULT_LINKERR = '🔗'
QOC_DEFAULT_BITRATE = '🔢'
QOC_DEFAULT_CLIPPING = '📢'

latest_pin_time = None # Keeps track of the last pinned message's time to distinguish between pins and unpins. To be updated on ready.
latest_scan_time = None

bot = commands.Bot(
    command_prefix='!',
    help_command = commands.DefaultHelpCommand(no_category = 'Commands'), # Change only the no_category default string
    intents = discord.Intents.all() # This was a change necessitated by an update to discord.py :/
    # https://stackoverflow.com/questions/71950432/how-to-resolve-the-following-error-in-discord-py-typeerror-init-missing
    # Also had to enable MESSAGE CONENT INTENT https://stackoverflow.com/questions/71553296/commands-dont-run-in-discord-py-2-0-no-errors-but-run-in-discord-py-1-7-3
    # 10/28/22 They changed it again!!! https://stackoverflow.com/questions/73458847/discord-py-error-message-discord-ext-commands-bot-privileged-message-content-i
)

bot.remove_command('help') # get rid of the dumb default !help command

#===============================================#
#                    EVENTS                     #
#===============================================#

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('#################################')

    # Update latest_pin_time in order to keep track of 
    global latest_pin_time
    latest_pin_time = datetime.now(timezone.utc)


@bot.event
async def on_guild_channel_pins_update(channel: typing.Union[GuildChannel, Thread], last_pin: datetime):
    if not channel_is_type(channel, 'ROUNDUP'):
        return
    
    global latest_pin_time
    if last_pin <= latest_pin_time:
        # print("Seems to be a message being unpinned")
        pass
    else:
        latest_pin_time = last_pin
        pin_list = await channel.pins()
        latest_msg = pin_list[0]
    
        verdict, msg = await check_qoc_and_metadata(latest_msg)

        # Send msg
        if len(verdict) > 0:
            rip_title = get_rip_title(latest_msg)
            link = f"<https://discordapp.com/channels/{str(channel.guild.id)}/{str(channel.id)}/{str(latest_msg.id)}>"
            await channel.send("**Rip**: **[{}]({})**\n**Verdict**: {}\n{}-# React {} if this is resolved.".format(rip_title, link, verdict, msg, DEFAULT_CHECK))


#===============================================#
#                   COMMANDS                    #
#===============================================#

# ============ Aggregate commands ============= #

@bot.command(name='roundup', aliases = ['down_taunt', 'qoc', 'qocparty', 'roudnup'], brief='displays all rips in QoC')
async def roundup(ctx: Context, optional_time = None):
    """
    Roundup command. Retrieve all pinned messages (except the first one) and their reactions.
    Accepts an optional argument to control embed's display time *in hours*.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("roundup", ctx.message.author.name)

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    async with ctx.channel.typing():
        all_pins = await process_pins(channel, True)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        await send_embed(ctx, result, time)


@bot.command(name='links', aliases = ['list', 'ls'], brief='roundup but quicker')
async def links(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) without showing reactions.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("links", ctx.message.author.name)

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    async with ctx.channel.typing():
        all_pins = await process_pins(channel, False)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, False)
        await send_embed(ctx, result, time)


@bot.command(name='mypins', brief='displays rips you\'ve pinned')
async def mypins(ctx: Context, optional_time = None):
    """
    Retrieve all messages pinned by the command author.
    """
    await filter_command(ctx, 'mypins', (lambda ctx, rip_info: rip_info["PinMiser"] == ctx.author.name), True, optional_time)


@bot.command(name='mypins_legacy', brief='displays rips you\'ve pinned (without reacts)')
async def mypins_legacy(ctx: Context, optional_time = None):
    """
    Retrieve all messages pinned by the command author without reacts (legacy behaviour).
    """
    await filter_command(ctx, 'mypins', (lambda ctx, rip_info: rip_info["PinMiser"] == ctx.author.name), False, optional_time)


@bot.command(name='emails', brief='displays emails')
async def emails(ctx: Context, optional_time = None):
    """
    Retrieve all messages that are tagged as email.
    """
    await filter_command(ctx, 'emails', (lambda ctx, rip_info: "email" in rip_info["Author"].lower()), True, optional_time)


@bot.command(name='events', aliases = ['event'], brief='displays event rips')
async def events(ctx: Context, event: str = None, optional_time = None):
    """
    Retrieve all messages that are tagged as for an event.
    The provided string must appear in the rip's author label (case insensitive)
    """
    if channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']) and event is None:
        await ctx.channel.send("Error: Please indicate the event name. Rips should be tagged with this name.")
        return
    
    await filter_command(ctx, 'events', (lambda ctx, rip_info: event.lower() in rip_info["Author"].lower()), True, optional_time)


@bot.command(name="fresh", aliases = ['blank', 'bald', 'clean', 'noreacts'], brief='rips with no reacts yet')
async def fresh(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) with 0 reactions.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("fresh", ctx.message.author.name)

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    result = ""

    async with ctx.channel.typing():
        pin_list = await channel.pins()
        pin_list.pop(-1) # get rid of a certain post about reading the rules

        for pinned_message in pin_list:
            mesg = await channel.fetch_message(pinned_message.id)
            if len(mesg.reactions) < 1:
                title = get_rip_title(mesg)
                link = f"<https://discordapp.com/channels/{str(channel.guild.id)}/{str(channel.id)}/{str(pinned_message.id)}>"
                result = result + f'**[{title}]({link})**\n'

        if result != "":
            await send_embed(ctx, result, time)
        else:
            await ctx.channel.send("No fresh rips.")


@bot.command(name='wrenches', aliases = ['fix'])
async def wrenches(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) with :fix: reactions.
    """
    await react_command(ctx, 'fix', react_is_fix, "No wrenches found.", optional_time)

@bot.command(name='stops')
async def stops(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) with :stop: reactions.
    """
    await react_command(ctx, 'stop', react_is_stop, "No octogons found.", optional_time)

@bot.command(name='checks')
async def checks(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) with :check: reactions.
    """
    await react_command(ctx, 'check', react_is_check, "No checks found.", optional_time)

@bot.command(name='rejects')
async def rejects(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) with :reject: reactions.
    """
    await react_command(ctx, 'reject', react_is_reject, "No rejected rips found.", optional_time)


@bot.command(name='overdue', brief=f'display rips that have been pinned for over {OVERDUE_DAYS} days')
async def overdue(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) that are overdue.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("overdue", ctx.message.author.name)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    result = ""

    async with ctx.channel.typing():
        all_pins = await process_pins(channel, True)
        result = ""

        for rip_id, rip_info in all_pins.items():
            if rip_info["Indicator"] == OVERDUE_INDICATOR:
                result += make_markdown(rip_info, True)
        await send_embed(ctx, result, time)


# ============ Pin count commands ============== #

@bot.command(name='count', brief="counts all pinned rips")
async def count(ctx: Context):
    """
    Count the number of pinned messages containing rip links.
    """
    heard_command("count", ctx.message.author.name)

    if channel_is_type(ctx.channel, 'PROXY_ROUNDUP'):
        channel = await get_roundup_channel(ctx)
        if channel is None: return
        else: proxy = f"\n-# Showing results from <#{channel.id}>."
    else:
        channel = ctx.channel
        proxy = ""

    async with ctx.channel.typing():
        pincount = await count_rips(channel, 'pin')

        if (pincount < 1):
            result = "`* Determination.`"
        else:
            result = f"`* {pincount} left.`"

        result += proxy
        await ctx.channel.send(result)


@bot.command(name='limitcheck', aliases=['pinlimit'], brief="pin limit checker")
async def limitcheck(ctx: Context):
    """
    Count the number of available pin slots.
    """
    heard_command("limitcheck", ctx.message.author.name)
    max_pins = 50

    if channel_is_type(ctx.channel, 'PROXY_ROUNDUP'):
        channel = await get_roundup_channel(ctx)
        if channel is None: return
        else: proxy = f"\n-# Showing results from <#{channel.id}>."
    else:
        channel = ctx.channel
        proxy = ""

    async with ctx.channel.typing():
        pin_list = await channel.pins()
        pincount = len(pin_list)
        result = f"You can pin {max_pins - pincount} more rips until hitting Discord's pin limit."

        result += proxy
        await ctx.channel.send(result)


# ============ Basic QoC commands ============== #

@bot.command(name='vet', brief='scan pinned messages for bitrate and clipping issues')
async def vet(ctx: Context, optional_arg = None):
    """
    Find rips in pinned messages with bitrate/clipping issues and show their details
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("vet", ctx.message.author.name)

    if optional_arg is not None:
        await ctx.channel.send("WARNING: ``!vet`` takes no argument. Did you mean to use ``!vet_msg`` or ``!vet_url``?")
        return
    
    if ctx.message.reference is not None:
        await ctx.channel.send("WARNING: ``!vet`` takes no argument (nor replies). Did you mean to use ``!vet_msg`` or ``!vet_url``?")
        return

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    if not ffmpegExists():
        await ctx.channel.send("WARNING: ffmpeg command not found on the bot's server. Please contact the developers.")
        return

    async with ctx.channel.typing():
        pin_list = await channel.pins()
        pin_list.pop(-1) # get rid of a certain post about reading the rules

        for pinned_message in pin_list:
            qcCode, qcMsg, _ = await check_qoc(pinned_message, False)
            rip_title = get_rip_title(pinned_message)
            verdict = code_to_verdict(qcCode, qcMsg)

            if qcCode != 0:
                link = f"<https://discordapp.com/channels/{str(channel.guild.id)}/{str(channel.id)}/{str(pinned_message.id)}>"
                await ctx.channel.send("**Rip**: **[{}]({})**\n**Verdict**: {}\n{}\n-# React {} if this is resolved.".format(rip_title, link, verdict, qcMsg, DEFAULT_CHECK))

        if len(pin_list) == 0:
            await ctx.channel.send("No rips found.")
        else:
            await ctx.channel.send("Finished QoC-ing. Please note that these are only automated detections - you should verify the issues in Audacity and react manually.")


@bot.command(name='vet_all', brief='vet all pinned messages and show summary')
async def vet_all(ctx: Context, optional_time = None):
    """
    Retrieve all pinned messages (except the first one) and perform basic QoC, giving emoji labels.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("vet_all", ctx.message.author.name)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    if not ffmpegExists():
        await ctx.channel.send("WARNING: ffmpeg command not found on the bot's server. Please contact the developers.")
        return

    async with ctx.channel.typing():
        all_pins = await vet_pins(channel)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        result += f"```\nLEGEND:\n{QOC_DEFAULT_LINKERR}: Link cannot be parsed\n{DEFAULT_CHECK}: Rip is OK\n{DEFAULT_FIX}: Rip has potential issues, see below\n{QOC_DEFAULT_BITRATE}: Bitrate is not 320kbps\n{QOC_DEFAULT_CLIPPING}: Clipping```"
        await send_embed(ctx, result, time)


@bot.command(name='vet_msg', brief='vet a single message link')
async def vet_msg(ctx: Context, msg_link: str = None):
    """
    Perform basic QoC on a linked message.
    The first non-YouTube link found in the message is treated as the rip URL.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("vet_msg", ctx.message.author.name)

    if msg_link is None:
        await ctx.channel.send("Error: Please provide a link to message.")
        return

    async with ctx.channel.typing():
        try:
            ids = msg_link.split('/')
            server_id = int(ids[4])
            channel_id = int(ids[5])
            msg_id = int(ids[6])
        except IndexError:
            await ctx.channel.send("Error: Cannot parse argument - make sure it is a valid link to message.")
            return
        
        server = bot.get_guild(server_id)
        channel = server.get_channel(channel_id)
        message = await channel.fetch_message(msg_id)

        verdict, msg = await check_qoc_and_metadata(message, True)
        rip_title = get_rip_title(message)

        await ctx.channel.send("**Rip**: **{}**\n**Verdict**: {}\n**Comments**:\n{}".format(rip_title, verdict, msg))


@bot.command(name='vet_url', brief='vet a single url')
async def vet_url(ctx: Context, url: str = None):
    """
    Perform basic QoC on an URL.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("vet_url", ctx.message.author.name)

    urls = extract_rip_link(url)
    if len(urls) == 0:
        await ctx.channel.send("Error: Please provide an URL to rip.")
        return

    async with ctx.channel.typing():
        code, msg = await run_blocking(performQoC, urls[0])
        verdict = code_to_verdict(code, msg)

        await ctx.channel.send("**Verdict**: {}\n**Comments**:\n{}".format(verdict, msg))


@bot.command(name='count_dupe', brief='count the number of dupes')
async def count_dupe(ctx: Context, msg_link: str = None, check_queues: str = None):
    """
    Count the number of dupes for a given link to rip message.
    Accepts an optional argument to also count rips in queues, which can take longer.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("count_dupe", ctx.message.author.name)

    if msg_link is None:
        await ctx.channel.send("Error: Please provide a link to message.")
        return

    async with ctx.channel.typing():
        try:
            ids = msg_link.split('/')
            server_id = int(ids[4])
            channel_id = int(ids[5])
            msg_id = int(ids[6])
        except IndexError:
            await ctx.channel.send("Error: Cannot parse argument - make sure it is a valid link to message.")
            return
        
        server = bot.get_guild(server_id)
        channel = server.get_channel(channel_id)
        message = await channel.fetch_message(msg_id)

        playlistId = extract_playlist_id('\n'.join(message.content.splitlines()[1:])) # ignore author line
        description = get_rip_description(message)
        rip_title = get_rip_title(message)

        p, msg = await run_blocking(countDupe, description, YOUTUBE_CHANNEL_NAME, playlistId, YOUTUBE_API_KEY)
        if len(msg) > 0:
            await ctx.channel.send(msg)
            if check_queues is None: return

        if check_queues is not None:
            q = 0
            queue_channels = [k for k, v in CHANNELS.items() if 'QUEUE' in v]
            for queue_channel_id in queue_channels:
                queue_channel = server.get_channel(queue_channel_id)
                queue_rips = await get_rips(queue_channel, 'msg')
                q += sum([isDupe(description, get_rip_description(r)) for r in queue_rips[queue_channel_id] if r.id != msg_id])

                queue_thread_rips = await get_rips(queue_channel, 'thread')
                for thread, rips in queue_thread_rips.items():
                    q += sum([isDupe(description, get_rip_description(r)) for r in rips if r.id != msg_id])

        # https://codegolf.stackexchange.com/questions/4707/outputting-ordinal-numbers-1st-2nd-3rd#answer-4712 how
        ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])

        if check_queues is not None:
            await ctx.channel.send(f"**Rip**: **{rip_title}**\nFound {p + q} rips of the same track ({p} on the channel, {q} in queues). This is the {ordinal(p + q + 1)} rip of this track.")
        else:
            await ctx.channel.send(f"**Rip**: **{rip_title}**\nFound {p} rips of the same track on the channel. This is the {ordinal(p + 1)} rip of this track.")


@bot.command(name='scan', brief='scan queue/sub channel for metadata issues')
async def scan(ctx: Context, channel_link: str = None, start_index: int = None, end_index: int = None):
    """
    Scan through a submission or queue channel for metadata issues.
    Channel link must be provided as argument.
    Accepts two optional arguments to specify the range of rips to scan through, if the channel has too many rips.

    - `start_index`: First rip to look at (inclusive). Index 1 means start from the oldest rip.
    - `end_index`: Last rip to look at (inclusive). Index 100 means scan until and including the 100th oldest rip. If this is not provided, scan to the latest rip.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("scan", ctx.message.author.name)

    global latest_scan_time
    if latest_scan_time is not None and datetime.now(timezone.utc) - latest_scan_time > timedelta(minutes=30):
        await ctx.channel.send("Please wait at least 30 minutes and contact bot developers before running this command again.")
        return

    if channel_link is None:
        await ctx.channel.send("Please provide a link to the channel you want to scan.")
        return

    channel_id, msg = parse_channel_link(channel_link, ['SUBS', 'SUBS_PIN', 'SUBS_THREAD', 'QUEUE'])
    if len(msg) > 0:
        await ctx.channel.send(msg)
        return
    
    channel = bot.get_channel(channel_id)
    if channel_is_type(channel, 'SUBS'): types = ['msg']
    elif channel_is_type(channel, 'SUBS_PIN'): types = ['pin']
    elif channel_is_type(channel, 'SUBS_THREAD'): types = ['thread']
    elif channel_is_type(channel, 'QUEUE'): types = ['msg', 'thread']

    rips = []
    for t in types:
        t_rips = await get_rips(channel, t)
        for k, v in t_rips.items():
            rips.extend(v)

    rips = rips.reverse()
    num_rips = len(rips)

    if start_index is not None:
        try:
            sInd = int(start_index)
            if sInd < 1: raise ValueError()
        except ValueError:
            await ctx.channel.send("Invalid start index argument.")
            return
        sInd = max(sInd, 1)
        
        if end_index is not None:
            try:
                eInd = int(start_index)
                if eInd < sInd: raise ValueError()
            except ValueError:
                await ctx.channel.send("Invalid end index argument.")
                return
            eInd = min(eInd, num_rips)
        else:
            eInd = num_rips
    else:
        sInd = 1
        eInd = num_rips

    if eInd - sInd > 100:
        await ctx.channel.send("Warning: More than 100 rips found. Limit the scanning range by specifying the indexes, e.g. `!scan [link] 1 50` to scan the oldest 50 rips.")
        return

    async with ctx.channel.typing():
        index = 0
        for message in rips:
            index += 1
            if (index < sInd):
                continue
            if (index > eInd):
                break
            
            rip_title = get_rip_title(message)

            mtCode, mtMsg = await check_metadata(message)
            if mtCode == -1:
                write_log("Warning: cannot check metadata of message\nRip: {}\n{}".format(rip_title, mtMsg))

            if mtCode == 1:
                link = f"<https://discordapp.com/channels/{str(ctx.guild.id)}/{str(channel_id)}/{str(message.id)}>"
                await ctx.channel.send("**Rip**: **[{}]({})**\n**Verdict**: {}\n{}".format(rip_title, link, DEFAULT_METADATA, mtMsg))
        
        latest_scan_time = datetime.now(timezone.utc)
        await ctx.channel.send("Finished checking metadata of {} rips. Wait for ~30 minutes and contact bot developers if you wish to use this command again today.".format(eInd - sInd))


@bot.command(name='peek_msg', brief='print file metadata from message link')
async def peek_msg(ctx: Context, msg_link: str = None):
    """
    Prints the file metadata of the rip at linked message.
    The first non-YouTube link found in the message is treated as the rip URL.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("peek_msg", ctx.message.author.name)

    if msg_link is None:
        await ctx.channel.send("Error: Please provide a link to message.")
        return

    async with ctx.channel.typing():
        try:
            ids = msg_link.split('/')
            server_id = int(ids[4])
            channel_id = int(ids[5])
            msg_id = int(ids[6])
        except IndexError:
            await ctx.channel.send("Error: Cannot parse argument - make sure it is a valid link to message.")
            return
        
        server = bot.get_guild(server_id)
        channel = server.get_channel(channel_id)
        message = await channel.fetch_message(msg_id)
        rip_title = get_rip_title(message)
        
        urls = extract_rip_link(message.content)
        errs = []
        for url in urls:
            code, msg = await run_blocking(getFileMetadata, url)
            if code != -1:
                break
            errs.append(msg)
        if code == -1:
            await ctx.channel.send("Error reading message:\n{}".format('\n'.join(errs)))
        else:
            await ctx.channel.send("**Rip**: **{}**\n**File metadata**:\n{}".format(rip_title, msg))


@bot.command(name='peek_url', brief='print file metadata from url')
async def peek_url(ctx: Context, url: str = None):
    """
    Prints the file metadata of the rip at linked URL.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("peek_url", ctx.message.author.name)

    urls = extract_rip_link(url)
    if len(urls) == 0:
        await ctx.channel.send("Error: Please provide an URL to rip.")
        return

    async with ctx.channel.typing():
        code, msg = await run_blocking(getFileMetadata, urls[0])
        if code == -1:
            await ctx.channel.send("Error reading URL: {}".format(msg))
        else:
            await ctx.channel.send("**File metadata**:\n{}".format(msg))


@bot.command(name='scout', brief='find approved rips with specific title prefix')
async def scout(ctx: Context, prefix: str = None, channel_link: str = None):
    """
    Search queue channel for rips starting with the specific prefix (e.g. letter E).
    The prefix is case insensitive.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("scout", ctx.message.author.name)

    if prefix is None:
        await ctx.channel.send("Error: Please provide a prefix string.")
        return

    channel_id, msg = parse_channel_link(channel_link, ['QUEUE'])
    if len(msg) > 0:
        await ctx.channel.send(msg)
        return
    
    channel = bot.get_channel(channel_id)
    async with ctx.channel.typing():
        rips: typing.List[Message] = []
        for t in ['msg', 'thread']:
            t_rips = await get_rips(channel, t)
            for k, v in t_rips.items():
                rips.extend(v)
        
        result = ""
        for rip in rips:
            rip_title = get_rip_title(rip)
            rip_link = f"<https://discordapp.com/channels/{str(ctx.guild.id)}/{str(channel_id)}/{str(rip.id)}>"
            if rip_title.lower().startswith(prefix.lower()):
                result += f'**[{rip_title}]({rip_link})**\n'

        if len(result) == 0:
            await ctx.channel.send("No rips found.")
        else:
            await send_embed(ctx, result)

# ============ Config commands ============== #

@bot.command(name='enable_metadata')
async def enable_metadata(ctx: Context): 
    set_config('metadata', True)
    await ctx.channel.send("Advanced metadata checking enabled.")

@bot.command(name='disable_metadata')
async def disable_metadata(ctx: Context): 
    set_config('metadata', False)
    await ctx.channel.send("Advanced metadata checking disabled.")

def set_config(config: str, value: bool):
    if os.path.exists('config.json'):
        with open('config.json', 'r', encoding='utf-8') as file:
            configs = json.load(file)
    else:
        configs = {}
    configs[config] = value
    with open('config.json', 'w', encoding='utf-8') as file:
        json.dump(configs, file, indent=4)

def get_config(config: str):
    if os.path.exists('config.json'):
        with open('config.json', 'r', encoding='utf-8') as file:
            configs = json.load(file)
            try:
                value = configs[config]
            except KeyError:
                value = None
            return value
    else:
        return None

# ============ Helper/test commands ============== #

@bot.command(name='help', aliases = ['commands', 'halp', 'test'])
async def help(ctx: Context):    
    async with ctx.channel.typing():
        result = "_**YOU ARE NOW QoCING:**_\n`!roundup [embed_minutes: float]`" + roundup.brief \
            + "\n`!links` " + links.brief \
            + "\n_**Special lists:**_\n`!mypins`" + mypins.brief \
            + "\n`!emails` " + emails.brief + "\n`!events <name: str>` " + events.brief \
            + "\n`!checks`\n`!rejects`\n`!wrenches`\n`!stops`" \
            + "\n`!overdue` " + overdue.brief \
            + "\n_**Misc. tools:**_\n`!count` " + count.brief \
            + "\n`!limitcheck` " + limitcheck.brief \
            + "\n`!count_subs [channel: link]` " + count_subs.brief \
            + "\n`!stats [show_queues: any]`" + stats.brief \
            + "\n`!channel_list`" + channel_list.brief \
            + "\n`!cleanup [search_limit: int]`" + cleanup.brief \
            + "\n_**Auto QoC tools:**_\n`!vet` " + vet.brief + "\n`!vet_all` " + vet_all.brief \
            + "\n`!vet_msg <message: link>` " + vet_msg.brief + "\n`!vet_url <URL: link>` " + vet_url.brief \
            + "\n`!peek_msg <message: link>` " + peek_msg.brief + "\n`!peek_url <URL: link>` " + peek_url.brief \
            + "\n`!count_dupe <message: link> [count_queues: any]`" + count_dupe.brief \
            + "\n`!scout <prefix: str> [channel: link]`" + scout.brief \
            + "\n_**Experimental tools:**_\n`!scan <channel: link> [start_index: int] [end_index: int]`" + scan.brief \
            + "\n_**Config:**_\n`![enable/disable]_metadata` enables/disables advanced metadata checking (currently {})".format("enabled" if get_config('metadata') else "disabled")
        await send_embed(ctx, result, delete_after=None)


@bot.command(name='channel_list', brief='show channels and their supported commands')
async def channel_list(ctx: Context):
    async with ctx.channel.typing():
        channels = [f"<#{channel_id}>: " + ", ".join(types) for channel_id, types in CHANNELS.items()]
        message = [
            "_**Command channel types**_",
            "`ROUNDUP`: QoC-type channels with rips pinned. All QoC tools are available here.",
            "`PROXY_ROUNDUP`: Allows running ROUNDUP commands in a different channel (and embed last longer by default).",
            "`DEBUG`: For developer testing purposes.",
            "_**Stats channel types**_",
            "`QOC`: QoC channel. Rips are pinned.",
            "`SUBS`: Submission channel. Rips are posted as messages in main channel.",
            "`SUBS_PIN`: Submission channel. Rips are pinned.",
            "`SUBS_THREAD`: Submission channel. Rips are posted in threads.",
            "`QUEUE`: Queue channel. Rips are posted as messages in main channel or threads.",
            "_**Channels**_",
        ]
        message.extend(channels)
        result = "\n".join(message)
        
        await send_embed(ctx, result, delete_after=None)


@bot.command(name='cleanup', brief='remove bot\'s old embed messages')
async def cleanup(ctx: Context, search_limit: int = None):
    if search_limit is None:
        search_limit = 200
    
    count = 0
    async for message in ctx.channel.history(limit = search_limit):
        if message.author == bot.user and message.embeds:
            await message.delete()
            count += 1
    
    await ctx.channel.send(f"Removed {count} embed messages.")


@bot.command(name='op')
async def test(ctx: Context):
    print(f"op ({ctx.message.author.name})")
    await ctx.channel.send("op")

@bot.command(name='cat', aliases = ['meow'], brief='cat')
async def cat(ctx: Context):
    print(f"cat ({ctx.message.author.name})")
    await ctx.channel.send("meow!")


@bot.command(name='count_subs', brief='count number of remaining submissions')
async def count_subs(ctx: Context, sub_channel_link: str = None):
    """
    Count number of messages in a channel (e.g. submissions).
    Retrieve the entire history of a channel and count the number of messages not in threads.
    Accepts an optional link argument to the subs-type channel to view - if not, first valid channel in config is used.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("count_subs", ctx.message.author.name)

    sub_channel, msg = parse_channel_link(sub_channel_link, ['SUBS', 'SUBS_PIN', 'SUBS_THREAD'])
    if len(msg) > 0:
        await ctx.channel.send(msg)
        if sub_channel == -1: return

    async with ctx.channel.typing():
        server = ctx.guild
        channel = server.get_channel(sub_channel)

        if channel_is_type(channel, 'SUBS'): t = 'msg'
        elif channel_is_type(channel, 'SUBS_PIN'): t = 'pin'
        elif channel_is_type(channel, 'SUBS_THREAD'): t = 'thread'

        count = await count_rips(channel, t)
        if t == 'thread':
            count = sum(count.values())

        if (count < 1):
            result = "```ansi\n\u001b[0;31m* Determination.\u001b[0;0m```"
        else:
            result = f"```ansi\n\u001b[0;31m* {count} left.\u001b[0;0m```"

        await ctx.channel.send(result)

@bot.command(name='stats', brief='display remaining number of rips across channels')
async def stats(ctx: Context, optional_arg = None):
    """
    Display the number of rips in the QoC and submission channels.
    Accepts an optional argument to show queue channels too.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command("stats", ctx.message.author.name)

    server = ctx.guild

    async with ctx.channel.typing():
        ret = "**QoC channels**\n"
        qoc_channels = [k for k, v in CHANNELS.items() if 'QOC' in v]
        for channel_id in qoc_channels:
            team_count = 0
            email_count = 0

            channel = server.get_channel(channel_id)
            pin_list = await channel.pins()
            pin_list.pop(-1) # get rid of a certain post about reading the rules

            for pinned_message in pin_list:
                author = get_rip_author(pinned_message)
                if 'email' in author.lower():
                    email_count += 1
                else:
                    team_count += 1
            
            ret += f"- <#{channel_id}>: **{team_count + email_count}** rips\n  - {team_count} team subs\n  - {email_count} email subs\n"

        ret += "**Submission channels**\n"
        sub_channels = [k for k, v in CHANNELS.items() if any(t in v for t in ['SUBS', 'SUBS_PIN', 'SUBS_THREAD'])]
        for channel_id in sub_channels:
            channel = server.get_channel(channel_id)

            if channel_is_type(channel, 'SUBS'): t = 'msg'
            elif channel_is_type(channel, 'SUBS_PIN'): t = 'pin'
            elif channel_is_type(channel, 'SUBS_THREAD'): t = 'thread'

            sub_count = await count_rips(channel, t)
            if t =='thread':
                ret += f"- <#{channel_id}>:\n"
                for thread, count in sub_count.items():
                    if count > 0:
                        ret += f"  - <#{thread}>: **{count}** rips\n"
            else:
                ret += f"- <#{channel_id}>: **{sub_count}** rips\n"

        if optional_arg is not None:
            ret += "**Queues**\n"
            queue_channels = [k for k, v in CHANNELS.items() if 'QUEUE' in v]
            for channel_id in queue_channels:
                channel = server.get_channel(channel_id)
                rip_count = await count_rips(channel, 'msg')
                ret += f"- <#{channel_id}>: **{rip_count}** rips\n"

                rip_thread_counts = await count_rips(channel, 'thread')
                for thread, count in rip_thread_counts.items():
                    if count > 0:
                        ret += f"  - <#{thread}>: **{count}** rips\n"

        long_message = split_long_message(ret)
        for line in long_message:
            await ctx.channel.send(line)


# While it might occur to folks in the future that a good command to write would be a rip feedback-sending command, something like that
# would be way too impersonal imo.

# This thing here is for when I start attempting slash commands again. Until then, this should be unused.
# Thank you to cibere on the Digiwind server for having the patience of a saint.
#@bot.command(name='sync_commands')
#@commands.is_owner()
#async def sync(ctx):
#  cmds = await bot.tree.sync()
#  await ctx.send(f"Synced {len(cmds)} commands globally!")

#===============================================#
#               HELPER FUNCTIONS                #
#===============================================#

def make_markdown(rip_info: dict, display_reacts: bool) -> str:
    """
    Convert a dictionary of rip information to a markdown message
    """
    base_message = f'**[{rip_info["Title"]}]({rip_info["Link"]})**\n{rip_info["Author"]}'
    result = ""

    if len(rip_info["Indicator"]) > 0:
        base_message = f'{rip_info["Indicator"]} **[{rip_info["Title"]}]({rip_info["Link"]})** {rip_info["Indicator"]}\n{rip_info["Author"]}'

    if display_reacts:
        result = base_message + f' | {rip_info["Reacts"]}\n'
    else:
        result = base_message + "\n"

    result += "━━━━━━━━━━━━━━━━━━\n" # a line for readability!
    return result


async def react_command(ctx: Context, cmd_name: str, check_func: typing.Callable, not_found_message: str, optional_time = None): # I've been meaning to simplify this for AGES (7/7/24)
    """
    Unified command to only return messages with specific reactions.
    Uses the react_is_ABC helper functions to filter reacts.
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command(cmd_name, ctx.message.author.name)

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    async with ctx.channel.typing():
        async def filter_reacts(c: TextChannel, m: Message):
            if any([check_func(r) for r in m.reactions]):
                return await get_reactions(c, m)
            # if not, return an indication string to skip from markdown
            return "FILTERED", ""

        filtered_pins = await get_pinned_msgs_and_react(channel, filter_reacts)
        
        result = ""
        for rip_id, rip_info in filtered_pins.items():
            if rip_info["Reacts"] != "FILTERED":
                result += make_markdown(rip_info, True)

        if result == "":
            await ctx.channel.send(not_found_message)
        else:
            await send_embed(ctx, result, time)


async def filter_command(ctx: Context, cmd_name: str, filter_func: typing.Callable, display_reacts: bool, optional_time = None):
    """
    Unified command to only return messages according to a predicate.
    `filter_func` is a function accepting 2 parameters: `ctx`, `rip_info`
    """
    if not channel_is_types(ctx.channel, ['ROUNDUP', 'PROXY_ROUNDUP']): return
    heard_command(cmd_name, ctx.message.author.name)

    time, msg = parse_optional_time(ctx.channel, optional_time)
    if msg is not None: await ctx.channel.send(msg)

    channel = await get_roundup_channel(ctx)
    if channel is None: return

    async with ctx.channel.typing():
        all_pins = await process_pins(channel, display_reacts)
        result = ""
        for rip_id, rip_info in all_pins.items():
            if filter_func(ctx, rip_info):
                result += make_markdown(rip_info, display_reacts) # a match!
        if result == "":
            await ctx.channel.send("No rips found.")
        else:
            await send_embed(ctx, result, time)


def split_long_message(a_message: str) -> list[str]:  # avoid Discord's character limit
    """
    Split a long message to fit Discord's character limit.
    """
    result = []
    all_lines = a_message.splitlines()
    wall_of_text = ""
    for line in all_lines:
        line = line.replace('@', '')  # no more pings lol
        next_length = len(wall_of_text) + len(line)
        if next_length > DISCORD_CHARACTER_LIMIT:
            result.append(wall_of_text[:-1])  # append and get rid of the last newline
            wall_of_text = line + '\n'
        else:
            wall_of_text += line + '\n'

    result.append(wall_of_text[:-1])  # add anything remaining
    return result


async def send_embed(ctx: Context, message: str, delete_after: float = MESSAGE_SECONDS):
    """
    Send a long message as embed.

    - message: Text to send as embed
    - delete_after: Number of seconds to automatically remove the message. Defaults to constant at the beginning of file. If set to None, message will not delete.
    """
    long_message = split_long_message(message)
    for line in long_message:
        fancy_message = discord.Embed(description=line, color=EMBED_COLOR)
        await ctx.channel.send(embed=fancy_message, delete_after=delete_after)

def channel_is_type(channel: TextChannel, type: str):
    return channel.id in CHANNELS.keys() and type in CHANNELS[channel.id]

def channel_is_types(channel: TextChannel, types: typing.List[str]):
    return channel.id in CHANNELS.keys() and any([t in CHANNELS[channel.id] for t in types])

async def get_roundup_channel(ctx: Context):
    if channel_is_type(ctx.channel, 'PROXY_ROUNDUP'):
        qoc_channel, msg = parse_channel_link(None, ["ROUNDUP"])
        if len(msg) > 0:
            await ctx.channel.send(msg)
            if qoc_channel == -1: return None
        channel = bot.get_channel(qoc_channel)
    else:
        channel = ctx.channel
    return channel

def heard_command(command_name: str, user: str):
    today = datetime.now() # Technically not useful, but it looks gorgeous on my CRT monitor
    print(f"{today.strftime('%m/%d/%y %I:%M %p')}  ~~~  Heard {command_name} command from {user}!")


def parse_optional_time(channel: TextChannel, optional_time):
    """
    Get the number of houminutesrs from user input for roundup embed commands.
    """
    time = PROXY_MESSAGE_SECONDS if channel_is_type(channel, 'PROXY_ROUNDUP') else MESSAGE_SECONDS
    msg = None
    if optional_time is not None:
        try:
            new_time = float(optional_time) * 60
            if math.isnan(new_time) or math.isinf(new_time) or new_time < 1:
                raise ValueError
        except ValueError:
            msg = "Warning: Cannot parse time argument - make sure it is a valid value. Using default time of {:.2f} minutes.".format(time / 60)
        else:
            time = new_time
    
    return time, msg    


# https://stackoverflow.com/a/65882269
async def run_blocking(blocking_func: typing.Callable, *args, **kwargs) -> typing.Any:
    """
    Runs a blocking function in a non-blocking way.
    Needed because QoC functions take a while to run.
    """
    func = functools.partial(blocking_func, *args, **kwargs) # `run_in_executor` doesn't support kwargs, `functools.partial` does
    return await bot.loop.run_in_executor(None, func)


def extract_rip_link(text: str) -> typing.List[str]:
    """
    Extract potential rip links from text.
    Ignores Youtube links.
    """
    # Regular expression to match links that start with "http"
    pattern = r'\b(http[^\s]+)\b'
    # Find all matches in the text
    matches = re.findall(pattern, text)
    # Filter out any matches that contain "youtu"
    ret = []
    for match in matches:
        if "youtu" not in match:
            ret.append(match)
    return ret


def extract_playlist_id(text: str) -> str:
    """
    Extract the YouTube playlist ID from text.
    Assumes it is the first YouTube link.
    """
    playlist_regex = r'(?:https?://)?(?:www\.)?(?:youtube\.com/|youtu\.be/)playlist\?list=([a-zA-Z0-9_-]+)'
    match = re.search(playlist_regex, text)
    if match:
        # Return the extracted playlist ID
        return match.group(1)
    else:
        return ""  # Return empty string if no valid links are found


def get_raw_rip_title(message: Message) -> str:
    """
    Return the rip title line of a Discord message.
    Assumes the message follows the format where the rip title is after the first instance of ```
    """
    # Update: now use regex to find the first instance of "```[\n][text][\n]"
    pattern = r'\`\`\`\n*.*\n'
    rip_title = re.search(pattern, message.content)
    if rip_title is not None:
        rip_title = rip_title.group(0)
        rip_title = rip_title.replace('`', '')
        rip_title = rip_title.replace('\n', '')

    return rip_title


def get_rip_title(message: Message) -> str:
    """
    Wrapper function to format unusual or spoiler rip titles
    """
    rip_title = get_raw_rip_title(message)
    if rip_title is None:
        return "`[Unusual Pin Format]`"
    elif '||' in message.content.split('```')[0]:
        # if || is detected in the message before the first ```, make the rip title into spoiler
        return "`[Rip Contains Spoiler]`"
    else:
        return rip_title


def get_rip_author(message: Message) -> str:
    """
    Return the rip author line of a Discord message.
    If the line contains "by me", append the message sender's name to the author line.
    Assumes the message follows the format where the rip author is before the first instance of ```
    """
    author = message.content.split("```")[0]
    author = author.replace('\n', '')
    author = author.replace('||', '') # in case of spoilered rips
    
    if len(re.findall(r'\bby\b', author.lower())) == 0:
        # If "by" is not found, notify that the "author line" might be unusual
        author = author + " [Unusual Pin Format]"

    elif len(re.findall(r'\bby me\b', author.lower())) > 0: 
        # Overwrite it and do something else if the rip's author and the pinner are the same
        cleaned_author = str(message.author).split('#')[0]
        author += (f' (**{cleaned_author}**)')

    return author


def get_rip_description(message: Message) -> str:
    """
    Return the description of a rip, i.e. the part inside ```
    """
    # Use a regular expression to find text between two ``` markers
    match = re.search(r'```(.*?)```', message.content, re.DOTALL)

    if match:
        # Return the extracted text, stripping any leading/trailing whitespace
        return match.group(1).strip()
    else:
        return ""  # Return empty string if no match was found


async def get_pinned_msgs_and_react(channel: TextChannel, react_func: typing.Callable | None = None) -> dict:
    """
    Unified function to retrieve all pinned messages (except the first one) from a channel and give corresponding emojis.
    - react_func: A function in the form of fn(TextChannel, Message) that returns some emojis for a message. If None, show no emojis.
    
    Returns a dictionary of pinned messages.
    """
    pin_list = await channel.pins()

    pin_list.pop(-1) # get rid of a certain post about reading the rules

    dict_index = 1
    pins_in_message = {}  # make a dict for everything

    for pinned_message in pin_list:
        # Get the rip title
        rip_title = get_rip_title(pinned_message)

        # Find the rip's author
        author = get_rip_author(pinned_message)        

        # Get reactions
        if react_func is not None:
            message = await channel.fetch_message(pinned_message.id)
            reacts, indicator = await react_func(channel, message)
        else:
            reacts, indicator = "", ""

        #get rid of all asterisks and underscores in the author so an odd number of them doesn't mess up the rest of the message
        author = author.replace('*', '').replace('_', '')

        # Put all this information in the dict
        pins_in_message[dict_index] = {
            'Title': rip_title,
            'Author': author,
            'Reacts': reacts,
            'PinMiser': pinned_message.author.name,  # im mister rip christmas, im mister qoc
            'Indicator': indicator,
            'Link': f"<https://discordapp.com/channels/{str(channel.guild.id)}/{str(channel.id)}/{str(pinned_message.id)}>"
        }
        dict_index += 1

    return pins_in_message


# A bunch of functions to check if react is of specific types
def react_name(react: Reaction) -> str:
    if hasattr(react.emoji, "name"): return react.emoji.name
    else: return react.emoji

def react_is_goldcheck(react: Reaction) -> bool:
    return any([r in react_name(react).lower() for r in ["goldcheck", DEFAULT_GOLDCHECK]])

def react_is_checkreq(react: Reaction) -> bool:
    return react_name(react).lower().endswith("check") and react_name(react).lower()[0].isdigit()

def react_is_check(react: Reaction) -> bool:
    return not react_is_goldcheck(react) and not react_is_checkreq(react) \
            and any([r in react_name(react).lower() for r in ["check", DEFAULT_CHECK]])

def react_is_fix(react: Reaction) -> bool:
    return any([r in react_name(react).lower() for r in ["fix", "wrench", DEFAULT_FIX]])

def react_is_reject(react: Reaction) -> bool:
    return any([r in react_name(react).lower() for r in ["reject", DEFAULT_REJECT]])

def react_is_stop(react: Reaction) -> bool:
    return any([r in react_name(react).lower() for r in ["stop", "octagonal", DEFAULT_STOP]])

def react_is_alert(react: Reaction) -> bool:
    return any([r in react_name(react).lower() for r in ["alert", DEFAULT_ALERT]])

def react_is_qoc(react: Reaction) -> bool:
    return any([r in react_name(react).lower() for r in ["qoc", DEFAULT_QOC]])


KEYCAP_EMOJIS = {'2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10}
def react_is_number(react: Reaction) -> bool:
    return react_name(react) in KEYCAP_EMOJIS


def rip_is_overdue(message: Message) -> bool:
    """
    Returns true if the message is older than OVERDUE_DAYS
    """
    return datetime.now(timezone.utc) - message.created_at > timedelta(days=OVERDUE_DAYS)


async def get_reactions(channel: TextChannel, message: Message) -> typing.Tuple[str, str]:
    """
    Return the reactions of a message.
    The message should contain the full reactions information.
    Returns an additional emoji as special indicator for the message.
    Requirements for approval:
    - At least 3 more checks than rejects
    - No fixes or alerts
    - If stop is present, number of goldchecks must be at least the numerical react (if any), or 1 (default)
    - If checkreq is present, change 3 to the corresponding value
    """
    reacts = ""
    indicator = ""

    num_checks = 0
    num_rejects = 0
    num_goldchecks = 0
    specs_required = 1
    checks_required = 3
    specs_needed = False
    fix_or_alert = False
    
    emote_names = [e.name for e in channel.guild.emojis]

    for react in message.reactions:
        if react_is_goldcheck(react): num_goldchecks += react.count
        elif react_is_checkreq(react): 
            try:
                checks_required = int(react_name(react).split("check")[0])
            except ValueError:
                print("Error parsing checkreq react: {}".format(react_name(react)))
        elif react_is_check(react): num_checks += react.count
        elif react_is_reject(react): num_rejects += react.count
        elif react_is_fix(react) or react_is_alert(react): fix_or_alert = True
        elif react_is_stop(react): specs_needed = True
        elif react_is_number(react):
            specs_required = KEYCAP_EMOJIS[react_name(react)]
        
        if react_name(react) in emote_names:
            for e in channel.guild.emojis:
                if e.name == react_name(react):
                    reacts += f"{e} " * react.count
                    break
        else:
            reacts += f"{react.emoji} " * react.count
    
    check_passed = (num_checks - num_rejects >= checks_required) and not fix_or_alert
    specs_passed = (not specs_needed or num_goldchecks >= specs_required)

    if check_passed:
        indicator = APPROVED_INDICATOR if specs_passed else AWAITING_SPECIALIST_INDICATOR
    elif rip_is_overdue(message):
        indicator = OVERDUE_INDICATOR

    return reacts, indicator

async def process_pins(channel: TextChannel, get_reacts: bool):
    """
    Retrieve all pinned messages (except the first one) from a channel.
    - get_reacts: Whether to show messages' reactions as emojis
    """
    return await get_pinned_msgs_and_react(channel, get_reactions if get_reacts else None)


async def vet_message(channel: TextChannel, message: Message) -> typing.Tuple[str, str]:
    """
    Return the QoC verdict of a message as emoji reactions.
    """
    urls = extract_rip_link(message.content)
    reacts = ""
    for url in urls:
        code, msg = await run_blocking(performQoC, url)
        reacts = code_to_verdict(code, msg)
        
        # debug
        if code == -1:
            write_log("Message: {}\n\nURL: {}\n\nError: {}".format(message.content, url, msg))
        else:
            break

    return reacts, ""

async def vet_pins(channel: TextChannel):
    """
    Retrieve all pinned messages (except the first one) from a channel and perform basic QoC, showing verdicts as emojis.
    """
    return await get_pinned_msgs_and_react(channel, vet_message)


def code_to_verdict(code: int, msg: str) -> str:
    """
    Helper function to convert performQoC code output to emoji
    """
    # TODO: use server reaction?
    verdict = {
        -1: QOC_DEFAULT_LINKERR,
        0: DEFAULT_CHECK,
        1: DEFAULT_FIX,
    }[code]
    if code == 1:
        if msgContainsSigninErr(msg):
            verdict = QOC_DEFAULT_LINKERR
        if msgContainsBitrateFix(msg):
            verdict += ' ' + QOC_DEFAULT_BITRATE
        if msgContainsClippingFix(msg):
            verdict += ' ' + QOC_DEFAULT_CLIPPING
    return verdict


async def check_qoc(message: Message, fullFeedback: bool = False) -> typing.Tuple[str, str, str]:
    """
    Perform simpleQoC on a message.
    """
    urls = extract_rip_link(message.content)
    qcCode, qcMsg = -1, "No links detected."
    detectedUrl = None
    for url in urls:
        qcCode, qcMsg = await run_blocking(performQoC, url, fullFeedback)
        if qcCode != -1:
            detectedUrl = url
            break
    return qcCode, qcMsg, detectedUrl


async def check_metadata(message: Message, fullFeedback: bool = False) -> typing.Tuple[str, str]:
    """
    Perform metadata checking on a message.
    If message contains the phrase "unusual metadata", skip most checks
    """
    playlistId = extract_playlist_id('\n'.join(message.content.splitlines()[1:])) # ignore author line
    description = get_rip_description(message)
    advancedCheck = get_config('metadata')
    skipCheck = "unusual metadata" in message.content.lower()
    if not skipCheck and len(description) > 0:
        mtCode, mtMsgs = await run_blocking(checkMetadata, description, YOUTUBE_CHANNEL_NAME, playlistId, YOUTUBE_API_KEY, advancedCheck)
    else:
        mtCode, mtMsgs = 0, []

    if mtCode != -1 and "[Unusual Pin Format]" in get_rip_author(message):
        mtCode = 1
        mtMsgs.append("Rip author is missing.")

    if mtCode != -1 and not skipCheck:
        server = message.guild

        queue_channels = [k for k, v in CHANNELS.items() if 'QUEUE' in v]
        for queue_channel_id in queue_channels:
            queue_channel = server.get_channel(queue_channel_id)
            queue_rips = await get_rips(queue_channel, 'msg')
            if any([get_raw_rip_title(message) == get_raw_rip_title(r) for r in queue_rips[queue_channel_id] if r.id != message.id]):
                mtCode = 1
                mtMsgs.append(f"Video title already exists in <#{queue_channel_id}>.")

            queue_thread_rips = await get_rips(queue_channel, 'thread')
            for thread, rips in queue_thread_rips.items():
                if any([get_raw_rip_title(message) == get_raw_rip_title(r) for r in rips if r.id != message.id]):
                    mtCode = 1
                    mtMsgs.append(f"Video title already exists in <#{thread}>.")
        
        qoc_channels = [k for k, v in CHANNELS.items() if 'QOC' in v]
        for qoc_channel_id in qoc_channels:
            qoc_channel = server.get_channel(qoc_channel_id)
            qoc_rips = await get_rips(qoc_channel, 'pin')
            if any([get_raw_rip_title(message) == get_raw_rip_title(r) for r in qoc_rips[qoc_channel_id] if r.id != message.id]):
                mtCode = 1
                mtMsgs.append(f"Video title already exists in <#{qoc_channel_id}>.")      

    mtMsg = '\n'.join(["- " + m for m in mtMsgs]) if len(mtMsgs) > 0 else ("- Metadata is OK." if fullFeedback else "")
    
    return mtCode, mtMsg


async def check_qoc_and_metadata(message: Message, fullFeedback: bool = False) -> typing.Tuple[str, str]:
    """
    Perform simpleQoC and metadata checking on a message.

    - **message**: Message to check
    - **fullFeedback**: If True, display "OK" messages. Otherwise, display only issues.
    """
    verdict = ""
    msg = ""
    rip_title = get_rip_title(message)
    
    # QoC
    qcCode, qcMsg, detectedUrl = await check_qoc(message, fullFeedback)
    if qcCode == -1:
        write_log("Warning: cannot QoC message\nRip: {}\n{}".format(rip_title, qcMsg))
    elif (qcCode == 1) or fullFeedback:
        verdict += code_to_verdict(qcCode, qcMsg)
        msg += qcMsg + "\n"

    # Metadata
    mtCode, mtMsg = await check_metadata(message, fullFeedback)
    if mtCode == -1:
        write_log("Warning: cannot check metadata of message\nRip: {}\n{}".format(rip_title, mtMsg))
    elif mtCode == 1:
        verdict += ("" if len(verdict) == 0 else " ") + DEFAULT_METADATA
    if (mtCode == 1) or fullFeedback:
        msg += mtMsg + "\n"

    # Check for lines between the rip description and link - if it does not start with "Joke", add a warning
    # in order to minimize accidental joke lines when uploading
    if detectedUrl is not None:
        try:
            for line in message.content.split('```', 2)[2].splitlines():
                if detectedUrl in line:
                    break
                elif len(line) > 0 and not line.startswith('Joke') and not line == '||':
                    msg += "- Line not starting with ``Joke`` detected between description and rip URL. Recommend putting the URL directly under description to avoid accidentally uploading joke lines.\n"
                    break
        except IndexError:
            pass

    return verdict, msg


async def count_rips(channel: TextChannel, type: typing.Literal['pin', 'msg', 'thread']) -> int | dict:
    """
    Returns the number of rips in a channel.
    `type` argument specifies what type of messages to retrieve (see get_rips).
    """
    rips = await get_rips(channel, type)
    if len(rips) == 1:
        return len(rips[channel.id])
    else:
        count = {}
        for k, v in rips.items():
            count[k] = len(v)
        return count


async def get_rips(channel: TextChannel, type: typing.Literal['pin', 'msg', 'thread']) -> dict[int, typing.List[Message]]:
    """
    Retrieve all rips in a channel, depending on the type: rips are in pins, messages or threads.
    `type` argument specifies what type of messages to retrieve:
    - 'pin': Pinned messages. Assumes first pinned message is not a rip for simplicity.
    - 'msg': Messages in channel, ignoring threads. Only count messages with ```.
    - 'thread': Messages in threads.

    Return value is a dictionary of channel IDs as key and list of messages as values.

    Notes:
    - `msg` might take a long time for big channels. Limit this to submissions or queue channels.
    """
    rips = {
        channel.id: []
    }
    if type == 'pin':
        pins = await channel.pins()
        rips[channel.id] = pins[:-1]
    elif type == 'msg':
        async for message in channel.history(limit = None):
            if channel is Thread or not (message.channel is Thread):
                if '```' in message.content and len(extract_rip_link(message.content)) > 0:
                    rips[channel.id].append(message)
    elif type == 'thread':
        rips = {}
        async for message in channel.history(limit = None):
            if message.thread is not None:
                thread_rips = await get_rips(message.thread, 'msg')
                rips[message.thread.id] = thread_rips[message.thread.id]
    
    return rips


def parse_channel_link(link: str | None, types: typing.List[str]) -> typing.Tuple[int, str]:
    """
    Parse the channel link and return the channel ID if it matches the specified types.
    If channel is invalid or does not match the types, returns the first channel in config matching the types.
    Returns null channel if no such channel types exists - the caller function should return early.

    Return values:
    - `channel_id`: Parsed channel ID if it is valid, default channel if it isn't, and -1 if no default channel
    - `msg`: Message to print if `channel_id` is not parsed from `link`, empty string otherwise
    """
    try:
        default_id = [k for k, v in CHANNELS.items() if any(t in v for t in types)][0]
    except IndexError:
        return -1, f"Error: No default channels found."
    
    if link is None:
        return default_id, ""

    try:
        arg = int(link.split('/')[5])
    except IndexError:
        return -1, "Error: Cannot parse argument - make sure it is a valid link to channel."

    # this is same as channel_is_type, but we only have the ID number
    if arg in CHANNELS.keys() and any(t in CHANNELS[arg] for t in types):
        return arg, ""
    else:
        return default_id, f"Warning: Link is not a valid roundup channel, defaulting to <#{default_id}>."


def write_log(msg: str):
    """
    Helper function to write debug text to a file so it doesn't get drowned in terminal.
    The files should be cleaned up regularly.
    """
    with open('logs.txt', 'a', encoding='utf-8') as file:
        file.write(datetime.now(timezone.utc).strftime('%m/%d/%y %I:%M %p'))
        file.write('\n')
        file.write(msg)
        file.write('\n=========================================\n')


# Now that everything's defined, run the dang thing
bot.run(TOKEN)
