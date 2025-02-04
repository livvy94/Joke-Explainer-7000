#!/usr/bin/python3
import discord
from discord import Message, Thread
from discord.abc import Messageable, GuildChannel
from discord.ext import commands
from discord.ext.commands import Context
from bot_secrets import token, roundup_channels, discussion_channels, submission_channel, op_channelid
from datetime import datetime

from simpleQoC.qoc import performQoC, msgContainsBitrateFix, msgContainsClippingFix
import re
import functools
import typing

MESSAGE_SECONDS = 2700  # 45 minutes
DISCORD_CHARACTER_LIMIT = 4000 # Lower this to 2000 if we lose boosts
EMBED_COLOR = 0x481761
APPROVED_INDICATOR = "🔥"

bot = commands.Bot(
    command_prefix='!',
    help_command = commands.DefaultHelpCommand(no_category = 'Commands'), # Change only the no_category default string
    intents = discord.Intents.all() # This was a change necessitated by an update to discord.py :/
    # https://stackoverflow.com/questions/71950432/how-to-resolve-the-following-error-in-discord-py-typeerror-init-missing
    # Also had to enable MESSAGE CONENT INTENT https://stackoverflow.com/questions/71553296/commands-dont-run-in-discord-py-2-0-no-errors-but-run-in-discord-py-1-7-3
    # 10/28/22 They changed it again!!! https://stackoverflow.com/questions/73458847/discord-py-error-message-discord-ext-commands-bot-privileged-message-content-i
)

bot.remove_command('help') # get rid of the dumb default !help command

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('#################################')

# This thing here is for when I start attempting slash commands again. Until then, this should be unused.
# Thank you to cibere on the Digiwind server for having the patience of a saint.
#@bot.command(name='sync_commands')
#@commands.is_owner()
#async def sync(ctx):
#  cmds = await bot.tree.sync()
#  await ctx.send(f"Synced {len(cmds)} commands globally!")

@bot.event
async def on_guild_channel_pins_update(channel: typing.Union[GuildChannel, Thread], last_pin: datetime):
    if channel_is_not_qoc(channel.id):
        return
    
    print(last_pin)

#===============================================#
#                   COMMANDS                    #
#===============================================#

# ============ Aggregate commands ============= #

@bot.command(name='roundup', aliases = ['down_taunt', 'qoc', 'qocparty', 'roudnup'], brief='displays all rips in QoC')
async def roundup(ctx: Context):
    """
    Roundup command. Retrieve all pinned messages (except the first one) and their reactions.
    """
    if channel_is_not_qoc(ctx): return
    heard_command("roundup", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, True)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        await send_embed(ctx, result)


@bot.command(name='links', aliases = ['list', 'ls'], brief='roundup but quicker')
async def links(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) without showing reactions.
    """
    if channel_is_not_qoc(ctx): return
    heard_command("links", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, False)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, False)
        await send_embed(ctx, result)


@bot.command(name='mypins', brief='displays rips you\'ve pinned')
async def mypins(ctx: Context):
    """
    Retrieve all messages pinned by the command author.
    """
    if channel_is_not_qoc(ctx): return
    heard_command("mypins", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, False)
        result = ""
        for rip_id, rip_info in all_pins.items():
            if rip_info["PinMiser"] == ctx.author.name:
                result += make_markdown(rip_info, False) # a match!
        if result == "":
            await ctx.channel.send("No rips found.")
        else:
            await send_embed(ctx, result)


@bot.command(name="fresh", aliases = ['blank', 'bald', 'clean', 'noreacts'], brief='rips with no reacts yet')
async def fresh(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with 0 reactions.
    """
    if channel_is_not_qoc(ctx): return
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
    await react_command(ctx, 'fix', ['fix', 'wrench', '🔧'], "No wrenches found.")

@bot.command(name='stops')
async def stops(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :stop: reactions.
    """
    await react_command(ctx, 'stop', ['stop', 'octagonal', '🛑'], "No octogons found.")

@bot.command(name='checks')
async def checks(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :check: reactions.
    """
    await react_command(ctx, 'check', ['check', '✅'], "No checks found.")

@bot.command(name='rejects')
async def rejects(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) with :reject: reactions.
    """
    await react_command(ctx, 'reject', ['reject', '❌'], "No rejected rips found.")


@bot.command(name='qoc_roundup', brief='view rips in QoC in the discussion channel')
async def qoc_roundup(ctx: Context):
    """
    Same as roundup, but to be run in a different channel for viewing convenience
    """
    if channel_is_not_discussion(ctx): return
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
    if channel_is_not_qoc(ctx): return
    heard_command("vet", ctx.message.author.name)

    async with ctx.channel.typing():
        pin_list = await ctx.channel.pins()
        pin_list.pop(-1) # get rid of a certain post about reading the rules

        for pinned_message in pin_list:
            message = await ctx.channel.fetch_message(pinned_message.id)
            url = extract_first_link(message.content)
            code, msg = await run_blocking(performQoC, url)
            rip_title = get_rip_title(message)
            verdict = {
                -1: '🔗',
                0: '✅',
                1: '🔧',
            }[code]

            if code != 0:
                if msgContainsBitrateFix(msg):
                    verdict += ' 🔢'
                if msgContainsClippingFix(msg):
                    verdict += ' 📢'
                link = f"<https://discordapp.com/channels/{str(ctx.guild.id)}/{str(ctx.channel.id)}/{str(pinned_message.id)}>"
                await ctx.channel.send("**Rip**: **[{}]({})**\n**Verdict**: {}\n{}".format(rip_title, link, verdict, msg))

        if len(pin_list) == 0:
            await ctx.channel.send("No rips found.")
        else:
            await ctx.channel.send("Finished QoC-ing. Please note that these are only automated detections - you should verify the issues in Audacity and react manually.")


@bot.command(name='vet_all', brief='vet all pinned messages and show summary')
async def vet_all(ctx: Context):
    """
    Retrieve all pinned messages (except the first one) and perform basic QoC, giving emoji labels.
    """
    if channel_is_not_qoc(ctx): return
    heard_command("vet_all", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await vet_pins(ctx.channel)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        result += "```\nLEGEND:\n🔗: Link cannot be parsed\n✅: Rip is OK\n🔧: Rip has potential issues, see below\n🔢: Bitrate is not 320kbps\n📢: Clipping```"
        await send_embed(ctx, result)


@bot.command(name='vet_msg', brief='vet a single message link')
async def vet_msg(ctx: Context, msg_link: str):
    """
    Perform basic QoC on a linked message.
    The first non-YouTube link found in the message is treated as the rip URL.
    """
    if channel_is_not_qoc(ctx): return
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

        url = extract_first_link(message.content)
        code, msg = await run_blocking(performQoC, url)
        rip_title = get_rip_title(message)
        verdict = {
            -1: '🔗',
            0: '✅',
            1: '🔧',
        }[code]

        await ctx.channel.send("**Rip**: {}\n**Verdict**: {}\n**Comments**:\n{}".format(rip_title, verdict, msg))


@bot.command(name='vet_url', brief='vet a single url')
async def vet_url(ctx: Context, url: str):
    """
    Perform basic QoC on an URL.
    """
    if channel_is_not_qoc(ctx): return
    heard_command("vet_url", ctx.message.author.name)

    async with ctx.channel.typing():
        code, msg = await run_blocking(performQoC, url)
        verdict = {
            -1: '🔗',
            0: '✅',
            1: '🔧',
        }[code]

        await ctx.channel.send("**Verdict**: {}\n**Comments**: {}".format(verdict, msg))


# ============ Helper/test commands ============== #

@bot.command(name='help', aliases = ['commands', 'halp', 'test'])
async def help(ctx: Context):
    async with ctx.channel.typing():
        result = "_**YOU ARE NOW QoCING:**_\n`!roundup` " + roundup.brief \
            + "\n`!links` " + links.brief \
            + "\n`!qoc_roundup` " + qoc_roundup.brief \
            + "\n_**Special lists:**_\n`!mypins` " + mypins.brief \
            + "\n`!checks`\n`!rejects`\n`!wrenches`\n`!stops`" \
            + "\n_**Misc. tools**_\n`!count` " + count.brief \
            + "\n`!limitcheck` " + limitcheck.brief \
            + "\n`!count_subs` " + count_subs.brief \
            + "\n_**Auto QoC tools**_\n`!vet` " + vet.brief + "\n`!vet_all` " + vet_all.brief \
            + "\n`!vet_msg` " + vet_msg.brief + "\n`!vet_url` " + vet_url.brief
        await send_embed(ctx, result)

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
    Turns out to be pretty fast for channels with not a lot of messages or conversations.
    """
    if channel_is_not_qoc(ctx): return
    heard_command("count_subs", ctx.message.author.name)

    async with ctx.channel.typing():
        server = ctx.guild
        channel = server.get_channel(submission_channel)

        count = 0
        async for message in channel.history(limit = None):
            if not (message.channel is Thread):
                count = count + 1

        if (count < 1):
            result = "```ansi\n\u001b[0;31m* Determination.\u001b[0;0m```"
        else:
            result = f"```ansi\n\u001b[0;31m* {count} left.\u001b[0;0m```"

        await ctx.channel.send(result)

# While it might occur to folks in the future that a good command to write would be a rip feedback-sending command, something like that
# would be way too impersonal imo.

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


async def react_command(ctx: Context, react: str, valid_react_names: list[str], not_found_message: str): # I've been meaning to simplify this for AGES (7/7/24)
    """
    Unified command to only return messages with specific reactions.
    """
    if channel_is_not_qoc(ctx):
        return
    heard_command(react, ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx.channel, True)
        result = ""
        for rip_id, rip_info in all_pins.items():
            if any([r in rip_info["Reacts"] for r in valid_react_names]):
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

def channel_is_not_qoc(ctx: Context):
    return ctx.channel.id not in roundup_channels

def channel_is_not_discussion(ctx: Context):
    return ctx.channel.id not in discussion_channels

def channel_is_not_op(ctx: Context):
    return ctx.channel.id != op_channelid

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


def extract_first_link(text: str) -> str | None:
    """
    Extract the first non-YouTube link from a text.
    """
    # Regular expression to match links that start with "http"
    pattern = r'\b(http[^\s]+)\b'
    # Find all matches in the text
    matches = re.findall(pattern, text)
    # Filter out any matches that contain "youtu"
    for match in matches:
        if "youtu" not in match:
            return match  # Return the first valid link
    return None  # Return None if no valid links are found


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


async def get_pinned_msgs_and_react(channel: Messageable, react_func: typing.Callable | None = None) -> dict:
    """
    Unified function to retrieve all pinned messages (except the first one) from a channel and give corresponding emojis.
    - react_func: A function in the form of fn(Messageable, Message) that returns some emojis for a message. If None, show no emojis.
    
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
            reacts, approved = await react_func(channel, pinned_message)
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


async def get_reactions(channel: Messageable, message: Message):
    """
    Return the reactions of a message.
    """
    reacts = ""
    approved = False
    
    mesg = await channel.fetch_message(message.id)
    for react in mesg.reactions:
        if ":check:" in str(react.emoji): # keep track of how many checks there are so we can add an indicator if there's more than three
            approved = react.count >= 3 # react.count is how many times this react was made on this message
        for x in range(react.count):  # add ALL of them. If you don't use count it just spits out one even if there's multiple checks
            reacts += f"{react.emoji} "  # make a nice string of all of them with a space
    
    return reacts, approved

async def process_pins(channel: Messageable, get_reacts: bool):
    """
    Retrieve all pinned messages (except the first one) from a channel.
    - get_reacts: Whether to show messages' reactions as emojis
    """
    return await get_pinned_msgs_and_react(channel, get_reactions if get_reacts else None)


async def vet_message(channel: Messageable, message: Message):
    """
    Return the QoC verdict of a message as emoji reactions.
    """
    url = extract_first_link(message.content)
    reacts = ""
    if url is not None:
        code, msg = await run_blocking(performQoC, url)
        # TODO: use server reaction?
        reacts = {
            -1: '🔗',
            0: '✅',
            1: '🔧',
        }[code]
        if code == 1:
            if msgContainsBitrateFix(msg):
                reacts += ' 🔢'
            if msgContainsClippingFix(msg):
                reacts += ' 📢'
        
        # debug
        if code == -1:
            print("Message: {}\n\nURL: {}\n\nError: {}".format(message.content, url, msg))

    return reacts, False

async def vet_pins(channel: Messageable):
    """
    Retrieve all pinned messages (except the first one) from a channel and perform basic QoC, showing verdicts as emojis.
    """
    return await get_pinned_msgs_and_react(channel, vet_message)


# Now that everything's defined, run the dang thing
bot.run(token)
