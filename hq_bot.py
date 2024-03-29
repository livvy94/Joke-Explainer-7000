#!/usr/bin/python3
import discord
from discord.ext import commands
from secrets import token, server_id, qoc_channelid, op_channelid
from datetime import datetime

message_seconds = 2700  # 45 minutes
discord_character_limit = 4000 # Lower this to 2000 if we lose boosts
embedColor = 0x481761
approved_indicator = "🔥"

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

@bot.command(name='roundup', aliases = ['down_taunt', 'qoc', 'qocparty'], brief='displays all rips in QoC')
async def roundup(ctx):
    if channel_is_not_qoc(ctx): return
    heard_command("roundup", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx, True)
        result = ""
        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, True)
        await send_embed(ctx, result)


@bot.command(name='links',aliases = ['list', 'ls'], brief='roundup but quicker')
async def links(ctx):
    if channel_is_not_qoc(ctx): return
    heard_command("links", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx, False)
        result = ""

        for rip_id, rip_info in all_pins.items():
            result += make_markdown(rip_info, False)

        await send_embed(ctx, result)


@bot.command(name='mypins', brief='displays rips you\'ve pinned')
async def mypins(ctx):
    if channel_is_not_qoc(ctx): return
    heard_command("mypins", ctx.message.author.name)

    async with ctx.channel.typing():
        all_pins = await process_pins(ctx, False)
        result = ""

        for rip_id, rip_info in all_pins.items():
            # print(rip_info["PinMiser"] + " =? " + ctx.author.name)
            if rip_info["PinMiser"] == ctx.author.name:
                result += make_markdown(rip_info, False) # a match!

        if result == "":
            await ctx.channel.send("No rips found.")
        else:
            await send_embed(ctx, result)


@bot.command(name='wrenches', aliases = ['fix'])
async def wrenches(ctx):
    if channel_is_not_qoc(ctx): return
    heard_command("wrenches", ctx.message.author.name)

    async with ctx.channel.typing():
        result = await only_return_messages_with_a_react(ctx, "fix")

        if result == "":
            await ctx.channel.send("No wrenches found.")
        else:
            await send_embed(ctx, result)


@bot.command(name='stops')
async def stops(ctx):
    if channel_is_not_qoc(ctx): return
    heard_command("stops", ctx.message.author.name)

    async with ctx.channel.typing():
        result = await only_return_messages_with_a_react(ctx, "stop")

        if result == "":
            await ctx.channel.send("No octagons found.")
        else:
            await send_embed(ctx, result)

@bot.command(name='checks')
async def checks(ctx):
    if channel_is_not_qoc(ctx): return
    heard_command("checks", ctx.message.author.name)

    async with ctx.channel.typing():
        result = await only_return_messages_with_a_react(ctx, "check")

        if result == "":
            await ctx.channel.send("No checks found.")
        else:
            await send_embed(ctx, result)

@bot.command(name='count', brief="counts all pinned rips")
async def count(ctx):
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
async def limitcheck(ctx):
    heard_command("limitcheck", ctx.message.author.name)
    max_pins = 50

    async with ctx.channel.typing():
        pin_list = await ctx.channel.pins()
        pincount = len(pin_list)
        result = f"You can pin {max_pins - pincount} more rips until hitting Discord's pin limit."

        await ctx.channel.send(result)

@bot.command(name='help', aliases = ['commands', 'halp', 'test'])
async def help(ctx):
    async with ctx.channel.typing():
        result = "_**YOU ARE NOW QoCING:**_\n`!roundup` " + roundup.brief + "\n`!links` " + links.brief + "\n_**Special lists:**_\n`!mypins` " + mypins.brief + "\n`!checks`\n`!wrenches`\n`!stops`" + "\n_**Misc. tools**_\n`!count` " + count.brief + "\n`!limitcheck` " + limitcheck.brief
        await send_embed(ctx, result)

@bot.command(name='op')
async def test(ctx):
    if channel_is_not_op(ctx):
        await ctx.message.delete()
        print(f"{ctx.message.author.name} opped out of bounds!")
        await ctx.channel.send("#op", delete_after=5)
    else:
        print(f"op ({ctx.message.author.name})")
        await ctx.channel.send("op")

# While it might occur to folks in the future that a good command to write would be a rip feedback-sending command, something like that
# would be way too impersonal imo.

##  HELPER METHODS  ##############################################################################
def make_markdown(rip_info, display_reacts):
    base_message = f'**[{rip_info["Title"]}]({rip_info["Link"]})**\n{rip_info["Author"]}'
    result = ""

    if rip_info["Approved"] == True:
        base_message = f'{approved_indicator} **[{rip_info["Title"]}]({rip_info["Link"]})** {approved_indicator}\n{rip_info["Author"]}'

    if display_reacts:
        result = base_message + f' | {rip_info["Reacts"]}\n'
    else:
        result = base_message + "\n"

    result += "━━━━━━━━━━━━━━━━━━\n" # a line for readability!
    return result


async def process_pins(ctx, get_reacts):
    pin_list = await ctx.channel.pins()

    pin_list.pop(-1) # get rid of a certain post about reading the rules

    dict_index = 1
    pins_in_message = {}  # make a dict for everything

    for pinned_message in pin_list:
        list_of_lines = pinned_message.content.split('\n')

        # Get the rip title
        # To get around non-standard messages (like fusion collab drafts), do something else if the first line doesn't include "by [ripper]"
        if "by " not in list_of_lines[0].lower() or len(list_of_lines) < 1:
            rip_title = "`[Unusual Pin Format]`"
        else:
            # Go through each line in the message and search for the rip title
            for line in list_of_lines:
                if "```" in line:
                    stripped_title = line.strip("```").strip("**")
                    if stripped_title != "":  # if line has title on it, make stripped version title
                        rip_title = stripped_title
                    elif stripped_title == "":
                        index_to_use = list_of_lines.index(line)
                        rip_title = list_of_lines[(index_to_use + 1)]  # use the next line instead
                    break

        # Find the rip's author
        author = list_of_lines[0]
        if 'by me' in author.lower(): # Overwrite it and do something else if the rip's author and the pinner are the same
            cleaned_author = str(pinned_message.author).split('#')[0]
            author += (f' (**{cleaned_author}**)')

        # Get reactions
        reacts = ""
        approved = False
        if get_reacts:
            mesg = await ctx.channel.fetch_message(pinned_message.id)
            for react in mesg.reactions:
                if ":check:" in str(react.emoji): # keep track of how many checks there are so we can add an indicator if there's more than three
                    approved = react.count >= 3 # react.count is how many times this react was made on this message
                for x in range(react.count):  # add ALL of them. If you don't use count it just spits out one even if there's multiple checks
                    reacts += f"{react.emoji} "  # make a nice string of all of them with a space

        #get rid of all asterisks and underscores in the author so an odd number of them doesn't mess up the rest of the message
        author = author.replace('*', '').replace('_', '')

        # Put all this information in the dict
        pins_in_message[dict_index] = {
            'Title': rip_title,
            'Author': author,
            'Reacts': reacts,
            'PinMiser': pinned_message.author.name,  # im mister rip christmas, im mister qoc
            'Approved': approved,
            'Link': f"<https://discordapp.com/channels/{str(server_id)}/{str(qoc_channelid)}/{str(pinned_message.id)}>"
        }
        dict_index += 1

    return pins_in_message


async def only_return_messages_with_a_react(ctx, react_to_look_for):
    all_pins = await process_pins(ctx, True)

    result = ""
    for rip_id, rip_info in all_pins.items():
        if react_to_look_for in rip_info["Reacts"]:
            result += make_markdown(rip_info, True)

    return result

def split_long_message(a_message):  # avoid Discord's character limit
    result = []
    all_lines = a_message.splitlines()
    wall_of_text = ""
    for line in all_lines:
        line = line.replace('@', '')  # no more pings lol
        next_length = len(wall_of_text) + len(line)
        if next_length > discord_character_limit:
            result.append(wall_of_text[:-1])  # append and get rid of the last newline
            wall_of_text = line + '\n'
        else:
            wall_of_text += line + '\n'

    result.append(wall_of_text[:-1])  # add anything remaining
    return result


async def send_embed(ctx, message):
    long_message = split_long_message(message)
    for line in long_message:
        fancy_message = discord.Embed(description=line, color=embedColor)
        await ctx.channel.send(embed=fancy_message, delete_after=message_seconds)

def channel_is_not_qoc(ctx):
    return ctx.channel.id != qoc_channelid

def channel_is_not_op(ctx):
    return ctx.channel.id != op_channelid

def heard_command(command_name, user):
    today = datetime.now() # Technically not useful, but it looks gorgeous on my CRT monitor
    print(f"{today.strftime('%m/%d/%y %I:%M %p')}  ~~~  Heard {command_name} command from {user}!")

# Now that everything's defined, run the dang thing
bot.run(token)
