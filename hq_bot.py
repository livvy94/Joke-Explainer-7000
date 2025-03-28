#!/usr/bin/python3
import discord
from discord import Message, Thread, TextChannel, Reaction
from discord.abc import GuildChannel
from discord.ext import commands
from discord.ext.commands import Context
from bot_secrets import token, roundup_channels, discussion_channels, submission_channel, op_channelid, youtube_api_key, channel_name
from datetime import datetime, timezone

from simpleQoC.qoc import performQoC, msgContainsBitrateFix, msgContainsClippingFix, ffmpegExists
from simpleQoC.metadataChecker import verifyTitle
import re
import functools
import typing
import math

MESSAGE_SECONDS = 2700  # 45 minutes
DISCORD_CHARACTER_LIMIT = 4000 # Lower this to 2000 if we lose boosts
EMBED_COLOR = 0x481761

# Emoji definitions
APPROVED_INDICATOR = '🔥'
AWAITING_SPECIALIST_INDICATOR = '♨️'

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
    if channel_is_not_qoc(channel):
        return
    
    global latest_pin_time
    if last_pin <= latest_pin_time:
        # print("Seems to be a message being unpinned")
        pass
    else:
        pin_list = await channel.pins()
        latest_msg = pin_list[0]
    
        verdict, msg = await check_qoc_and_metadata(latest_msg)

        # Send msg
        if len(verdict) > 0:
            rip_title = get_rip_title(latest_msg)
            link = f"<https://discordapp.com/channels/{str(channel.guild.id)}/{str(channel.id)}/{str(latest_msg.id)}>"
            await channel.send("**Rip**: **[{}]({})**\n**Verdict**: {}\n{}-# React {} if this is resolved.".format(rip_title, link, verdict, msg, DEFAULT_CHECK))

        latest_pin_time = last_pin

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
    if channel_is_not_qoc(ctx.channel): return
    heard_command("roundup", ctx.message.author.name)

    if optional_time is not None:
        try:
            time = float(optional_time) * 60 * 60
            if math.isnan(time) or math.isinf(time) or time < 1:
                raise ValueError
        except ValueError:
            await ctx.channel.send("Error: Cannot parse argument - make sure it is a valid value.")
            return
    else:
        time = MESSAGE_SECONDS

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, True)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        await send_embed(ctx, result, time)


@bot.command(name='links', aliases = ['list', 'ls'], brief='roundup but quicker')
async def links(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) without showing reactions.
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("links", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, False)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, False)
        await send_embed(ctx, result)


@bot.command(name='mypins', brief='displays rips you\'ve pinned')
async def mypins(ctx: Context, optional_arg = None):
    """
    Retrieve all messages pinned by the command author.
    Accepts an optional argument to "hide" the reactions (legacy behavior).
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("mypins", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, optional_arg is None)
        result = ""
        for rip_id, rip_info in all_pins.items():
            if rip_info["PinMiser"] == ctx.author.name:
                result += make_markdown(rip_info, optional_arg is None) # a match!
        if result == "":
            await ctx.channel.send("No rips found.")
        else:
            await send_embed(ctx, result)


@bot.command(name="fresh", aliases = ['blank', 'bald', 'clean', 'noreacts'], brief='rips with no reacts yet')
async def fresh(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with 0 reactions.
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("fresh", ctx.message.author.name)
    result = ""

    async with ctx.channel.typing():
        pin_list = await ctx.channel.pins()
        pin_list.pop(-1) # get rid of a certain post about reading the rules

        for pinned_message in pin_list:
            mesg = await ctx.channel.fetch_message(pinned_message.id)
            if len(mesg.reactions) < 1:
                title = pinned_message.content.split('\n')[1].replace('`', '')
                link = f"<https://discordapp.com/channels/{str(ctx.guild.id)}/{str(ctx.channel.id)}/{str(pinned_message.id)}>"
                result = result + f'**[{title}]({link})**\n'

        if result != "":
            await send_embed(ctx, result)
        else:
            await ctx.channel.send("No fresh rips.")


@bot.command(name='wrenches', aliases = ['fix'])
async def wrenches(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :fix: reactions.
    """
    await react_command(ctx, 'fix', react_is_fix, "No wrenches found.")

@bot.command(name='stops')
async def stops(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :stop: reactions.
    """
    await react_command(ctx, 'stop', react_is_stop, "No octogons found.")

@bot.command(name='checks')
async def checks(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :check: reactions.
    """
    await react_command(ctx, 'check', react_is_check, "No checks found.")

@bot.command(name='rejects')
async def rejects(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :reject: reactions.
    """
    await react_command(ctx, 'reject', react_is_reject, "No rejected rips found.")


@bot.command(name='qoc_roundup', brief='view rips in QoC in the discussion channel')
async def qoc_roundup(ctx: Context):
    """
    Same as roundup, but to be run in a different channel for viewing convenience
    """
    if channel_is_not_discussion(ctx.channel): return
    heard_command("qoc_roundup", ctx.message.author.name)

    # Hardcode the channel to fetch pins from to be the first in the roundup_channels list
    channel = bot.get_channel(roundup_channels[0])

    async with ctx.channel.typing():
        all_pins = await process_pins(channel, True)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        
        # Assuming this command is meant to be run in a not-very-active channel
        # Set to expire after 12 hours
        await send_embed(ctx, result, 60*60*12)


# ============ Pin count commands ============== #

@bot.command(name='count', brief="counts all pinned rips")
async def count(ctx: Context):
    """
    Count the number of pinned messages (minus 1).
    """
    heard_command("count", ctx.message.author.name)

    async with ctx.channel.typing():
        pin_list = await ctx.channel.pins()
        pincount = len(pin_list) - 1

        if (pincount < 1):
            result = "`* Determination.`"
        else:
            result = f"`* {pincount} left.`"

        await ctx.channel.send(result)


@bot.command(name='limitcheck', brief="pin limit checker")
async def limitcheck(ctx: Context):
    """
    Count the number of available pin slots.
    """
    heard_command("limitcheck", ctx.message.author.name)
    max_pins = 50

    async with ctx.channel.typing():
        pin_list = await ctx.channel.pins()
        pincount = len(pin_list)
        result = f"You can pin {max_pins - pincount} more rips until hitting Discord's pin limit."

        await ctx.channel.send(result)


# ============ Basic QoC commands ============== #

@bot.command(name='vet', brief='scan pinned messages for bitrate and clipping issues')
async def vet(ctx: Context):
    """
    Find rips in pinned messages with bitrate/clipping issues and show their details
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("vet", ctx.message.author.name)

    if not ffmpegExists():
        await ctx.channel.send("WARNING: ffmpeg command not found on the bot's server. Please contact the developers.")
        return

    async with ctx.channel.typing():
        pin_list = await ctx.channel.pins()
        pin_list.pop(-1) # get rid of a certain post about reading the rules

        for pinned_message in pin_list:
            url = extract_rip_link(pinned_message.content)
            code, msg = await run_blocking(performQoC, url, False)
            rip_title = get_rip_title(pinned_message)
            verdict = code_to_verdict(code, msg)

            if code != 0:
                link = f"<https://discordapp.com/channels/{str(ctx.guild.id)}/{str(ctx.channel.id)}/{str(pinned_message.id)}>"
                await ctx.channel.send("**Rip**: **[{}]({})**\n**Verdict**: {}\n{}\n-# React {} if this is resolved.".format(rip_title, link, verdict, msg, DEFAULT_CHECK))

        if len(pin_list) == 0:
            await ctx.channel.send("No rips found.")
        else:
            await ctx.channel.send("Finished QoC-ing. Please note that these are only automated detections - you should verify the issues in Audacity and react manually.")


@bot.command(name='vet_all', brief='vet all pinned messages and show summary')
async def vet_all(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) and perform basic QoC, giving emoji labels.
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("vet_all", ctx.message.author.name)

    if not ffmpegExists():
        await ctx.channel.send("WARNING: ffmpeg command not found on the bot's server. Please contact the developers.")
        return

    async with ctx.channel.typing():
        all_pins = await vet_pins(ctx.channel)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        result += f"```\nLEGEND:\n{QOC_DEFAULT_LINKERR}: Link cannot be parsed\n{DEFAULT_CHECK}: Rip is OK\n{DEFAULT_FIX}: Rip has potential issues, see below\n{QOC_DEFAULT_BITRATE}: Bitrate is not 320kbps\n{QOC_DEFAULT_CLIPPING}: Clipping```"
        await send_embed(ctx, result)


@bot.command(name='vet_msg', brief='vet a single message link')
async def vet_msg(ctx: Context, msg_link: str):
    """
    Perform basic QoC on a linked message.
    The first non-YouTube link found in the message is treated as the rip URL.
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("vet_msg", ctx.message.author.name)

    async with ctx.channel.typing():
        # https://stackoverflow.com/a/63212069
        ids = msg_link.split('/')
        server_id = int(ids[4])
        channel_id = int(ids[5])
        msg_id = int(ids[6])
        server = bot.get_guild(server_id)
        channel = server.get_channel(channel_id)
        message = await channel.fetch_message(msg_id)

        verdict, msg = await check_qoc_and_metadata(message, True)
        rip_title = get_rip_title(message)

        await ctx.channel.send("**Rip**: {}\n**Verdict**: {}\n**Comments**:\n{}".format(rip_title, verdict, msg))


@bot.command(name='vet_url', brief='vet a single url')
async def vet_url(ctx: Context, url: str):
    """
    Perform basic QoC on an URL.
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("vet_url", ctx.message.author.name)

    async with ctx.channel.typing():
        code, msg = await run_blocking(performQoC, url)
        verdict = code_to_verdict(code, msg)

        await ctx.channel.send("**Verdict**: {}\n**Comments**:\n{}".format(verdict, msg))


# ============ Helper/test commands ============== #

@bot.command(name='help', aliases = ['commands', 'halp', 'test'])
async def help(ctx: Context):
    async with ctx.channel.typing():
        result = "_**YOU ARE NOW QoCING:**_\n`!roundup` [embed_hours]" + roundup.brief \
            + "\n`!links` " + links.brief \
            + "\n`!qoc_roundup` " + qoc_roundup.brief + f' <#{discussion_channels[0]}>' \
            + "\n_**Special lists:**_\n`!mypins` [no_react]" + mypins.brief \
            + "\n`!checks`\n`!rejects`\n`!wrenches`\n`!stops`" \
            + "\n_**Misc. tools**_\n`!count` " + count.brief \
            + "\n`!limitcheck` " + limitcheck.brief \
            + "\n`!count_subs` " + count_subs.brief \
            + "\n`!stats` " + stats.brief \
            + "\n_**Auto QoC tools**_\n`!vet` " + vet.brief + "\n`!vet_all` " + vet_all.brief \
            + "\n`!vet_msg <link to message>` " + vet_msg.brief + "\n`!vet_url <link to URL>` " + vet_url.brief
        await send_embed(ctx, result, delete_after=None)

@bot.command(name='op')
async def test(ctx: Context):
    print(f"op ({ctx.message.author.name})")
    await ctx.channel.send("op")

@bot.command(name='cat', aliases = ['meow'], brief='cat')
async def cat(ctx: Context):
    print(f"cat ({ctx.message.author.name})")
    await ctx.channel.send("meow!")


@bot.command(name='count_subs', brief='count number of remaining submissions')
async def count_subs(ctx: Context):
    """
    Count number of messages in a channel (e.g. submissions).
    Retrieve the entire history of a channel and count the number of messages not in threads.
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("count_subs", ctx.message.author.name)

    async with ctx.channel.typing():
        server = ctx.guild
        channel = server.get_channel(submission_channel)

        count = await count_messages(channel)

        if (count < 1):
            result = "```ansi\n\u001b[0;31m* Determination.\u001b[0;0m```"
        else:
            result = f"```ansi\n\u001b[0;31m* {count} left.\u001b[0;0m```"

        await ctx.channel.send(result)

@bot.command(name='stats', brief='display remaining number of rips across channels')
async def stats(ctx: Context):
    """
    Display the number of rips in the QoC and submission channels
    """
    if channel_is_not_qoc(ctx.channel): return
    heard_command("stats", ctx.message.author.name)

    server = ctx.guild

    async with ctx.channel.typing():
        ret = "**QoC channels**\n"

        for channel_id in roundup_channels:
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

        sub_count = await count_messages(server.get_channel(submission_channel))
        ret += f"- <#{submission_channel}>: **{sub_count}** rips"

        await ctx.channel.send(ret)


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

    if rip_info["Approved"] == True:
        base_message = f'{APPROVED_INDICATOR} **[{rip_info["Title"]}]({rip_info["Link"]})** {APPROVED_INDICATOR}\n{rip_info["Author"]}'

    if display_reacts:
        result = base_message + f' | {rip_info["Reacts"]}\n'
    else:
        result = base_message + "\n"

    result += "━━━━━━━━━━━━━━━━━━\n" # a line for readability!
    return result


async def react_command(ctx: Context, react: str, check_func: typing.Callable, not_found_message: str): # I've been meaning to simplify this for AGES (7/7/24)
    """
    Unified command to only return messages with specific reactions.
    Uses the react_is_ABC helper functions to filter reacts.
    """
    if channel_is_not_qoc(ctx.channel):
        return
    heard_command(react, ctx.message.author.name)

    async with ctx.channel.typing():
        async def filter_reacts(channel: TextChannel, message: Message):
            if any([check_func(r) for r in message.reactions]):
                return await get_reactions(channel, message)
            # if not, return an indication string to skip from markdown
            return "FILTERED", False

        filtered_pins = await get_pinned_msgs_and_react(ctx.channel, filter_reacts)
        
        result = ""
        for rip_id, rip_info in filtered_pins.items():
            if rip_info["Reacts"] != "FILTERED":
                result += make_markdown(rip_info, True)

        if result == "":
            await ctx.channel.send(not_found_message)
        else:
            await send_embed(ctx, result)


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

def channel_is_not_qoc(channel: TextChannel):
    return channel.id not in roundup_channels

def channel_is_not_discussion(channel: TextChannel):
    return channel.id not in discussion_channels

def channel_is_not_op(channel: TextChannel):
    return channel.id != op_channelid

def heard_command(command_name: str, user: str):
    today = datetime.now() # Technically not useful, but it looks gorgeous on my CRT monitor
    print(f"{today.strftime('%m/%d/%y %I:%M %p')}  ~~~  Heard {command_name} command from {user}!")


# https://stackoverflow.com/a/65882269
async def run_blocking(blocking_func: typing.Callable, *args, **kwargs) -> typing.Any:
    """
    Runs a blocking function in a non-blocking way.
    Needed because QoC functions take a while to run.
    """
    func = functools.partial(blocking_func, *args, **kwargs) # `run_in_executor` doesn't support kwargs, `functools.partial` does
    return await bot.loop.run_in_executor(None, func)


def extract_rip_link(text: str) -> str:
    """
    Extract the rip link from text.
    Assumes it is the first non-YouTube link.
    """
    # Regular expression to match links that start with "http"
    pattern = r'\b(http[^\s]+)\b'
    # Find all matches in the text
    matches = re.findall(pattern, text)
    # Filter out any matches that contain "youtu"
    for match in matches:
        if "youtu" not in match:
            return match  # Return the first valid link
    return ""  # Return empty string if no valid links are found


def extract_playlist_id(text: str) -> str:
    """
    Extract the YouTube playlist ID from text.
    Assumes it is the first YouTube link.
    """
    playlist_regex = r'(?:https?://)?(?:www\.)?(?:youtube\.com/playlist\?list=|youtu\.be/)([a-zA-Z0-9_-]+)'
    match = re.search(playlist_regex, text)
    if match:
        # Return the extracted playlist ID
        return match.group(1)
    else:
        return ""  # Return empty string if no valid links are found


def get_rip_title(message: Message) -> str:
    """
    Return the rip title line of a Discord message.
    Assumes the message follows the format where the rip title is after the first instance of ```
    """
    # Update: now use regex to find the first instance of "```[\n][text][\n]"
    pattern = r'\`\`\`\n*.*\n'
    rip_title = re.search(pattern, message.content)
    if rip_title is None:
        return "`[Unusual Pin Format]"

    rip_title = rip_title.group(0)
    rip_title = rip_title.replace('`', '')
    rip_title = rip_title.replace('\n', '')

    # if || is detected in the message before the first ```, make the rip title into spoiler
    splits = message.content.split('```')
    if '||' in splits[0]:
        rip_title = "`[Rip Contains Spoiler]`"

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
            reacts, approved = await react_func(channel, message)
        else:
            reacts, approved = "", False

        #get rid of all asterisks and underscores in the author so an odd number of them doesn't mess up the rest of the message
        author = author.replace('*', '').replace('_', '')

        # Put all this information in the dict
        pins_in_message[dict_index] = {
            'Title': rip_title,
            'Author': author,
            'Reacts': reacts,
            'PinMiser': pinned_message.author.name,  # im mister rip christmas, im mister qoc
            'Approved': approved,
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

def react_is_check(react: Reaction) -> bool:
    return not react_is_goldcheck(react) and any([r in react_name(react).lower() for r in ["check", DEFAULT_CHECK]])

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

def react_is_checkreq(react: Reaction) -> bool:
    # TBA
    return False

KEYCAP_EMOJIS = {'2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5, '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10}
def react_is_number(react: Reaction) -> bool:
    return react_name(react) in KEYCAP_EMOJIS


async def get_reactions(channel: TextChannel, message: Message) -> typing.Tuple[str, bool]:
    """
    Return the reactions of a message.
    The message should contain the full reactions information.
    Set 'approved' to True if the reactions indicate that the rip is approved.
    Requirements for approval:
    - At least 3 more checks than rejects
    - No fixes or alerts
    - If stop is present, number of goldchecks must be at least the numerical react (if any), or 1 (default)
    - If checkreq is present, change 3 to the corresponding value
    """
    reacts = ""
    approved = False

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
        elif react_is_check(react): num_checks += react.count
        elif react_is_reject(react): num_rejects += react.count
        elif react_is_fix(react) or react_is_alert(react): fix_or_alert = True
        elif react_is_stop(react): specs_needed = True
        elif react_is_checkreq(react):
            # TODO
            pass
        elif react_is_number(react):
            specs_required = KEYCAP_EMOJIS[react_name(react)]
        
        if react_name(react) in emote_names:
            for e in channel.guild.emojis:
                if e.name == react_name(react):
                    reacts += f"{e} " * react.count
                    break
        else:
            reacts += f"{react.emoji} " * react.count
    
    approved = (num_checks - num_rejects >= checks_required) and not fix_or_alert and (not specs_needed or num_goldchecks >= specs_required)

    return reacts, approved

async def process_pins(channel: TextChannel, get_reacts: bool):
    """
    Retrieve all pinned messages (except the first one) from a channel.
    - get_reacts: Whether to show messages' reactions as emojis
    """
    return await get_pinned_msgs_and_react(channel, get_reactions if get_reacts else None)


async def vet_message(channel: TextChannel, message: Message) -> typing.Tuple[str, bool]:
    """
    Return the QoC verdict of a message as emoji reactions.
    """
    url = extract_rip_link(message.content)
    reacts = ""
    if url is not None:
        code, msg = await run_blocking(performQoC, url)
        reacts = code_to_verdict(code, msg)
        
        # debug
        if code == -1:
            print("Message: {}\n\nURL: {}\n\nError: {}".format(message.content, url, msg))

    return reacts, False

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
        if msgContainsBitrateFix(msg):
            verdict += ' ' + QOC_DEFAULT_BITRATE
        if msgContainsClippingFix(msg):
            verdict += ' ' + QOC_DEFAULT_CLIPPING
    return verdict


async def check_qoc_and_metadata(message: Message, fullFeedback: bool = False) -> typing.Tuple[str, str]:
    """
    Perform simpleQoC and metadata checking on a message.

    - **message**: Message to check
    - **show_ok**: If True, display "OK" messages. Otherwise, display only issues.
    """
    verdict = ""
    msg = ""
    rip_title = get_rip_title(message)
    
    # QoC
    url = extract_rip_link(message.content)
    qcCode, qcMsg = await run_blocking(performQoC, url, fullFeedback)
    if qcCode == -1:
        print("Warning: cannot QoC message\nRip: {}\n{}".format(rip_title, qcMsg))
    elif (qcCode == 1) or fullFeedback:
        verdict += code_to_verdict(qcCode, qcMsg)
        msg += qcMsg + "\n"

    # Metadata
    playlistId = extract_playlist_id(message.content)
    description = get_rip_description(message)
    if len(playlistId) > 0 and len(description) > 0:
        title = description.splitlines()[0]
        # game = title.split(' - ')[-1]     # this doesn't work in certain cases, think of another way to get game name

        mtCode, mtMsg = await run_blocking(verifyTitle, title, channel_name, playlistId, youtube_api_key)
    else:
        mtCode, mtMsg = 0, "Metadata is OK."

    if mtCode == -1:
        print("Warning: cannot check metadata of message\nRip: {}\n{}".format(rip_title, mtMsg))
    elif mtCode == 1:
        verdict += ("" if len(verdict) == 0 else " ") + DEFAULT_METADATA
    
    if (mtCode == 1) or fullFeedback:
        msg += "- {}\n".format(mtMsg)

    return verdict, msg


async def count_messages(channel: TextChannel) -> int:
    """
    Returns the number of non-thread messages in a channel.
    This includes "started a thread" messages.
    
    Warning: Might take a long time for big channels. Limit this to submissions or queue channels.
    """
    count = 0
    async for message in channel.history(limit = None):
        if not (message.channel is Thread):
            count = count + 1
    
    return count

# Now that everything's defined, run the dang thing
bot.run(token)
