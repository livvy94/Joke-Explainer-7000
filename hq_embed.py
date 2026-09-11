
from hq_discord import * 
from hq_database import store_sent_embeds_in_expire_database

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
    external_pre_text: str = ""

async def send_embed(text: str, channel: TextChannel | Thread, desc: EmbedDesc):

    if not len(desc.seperator):
        desc = desc._replace(seperator = "\n")

    text = text.strip()
    color = get_config('embed_color')

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

    sent_message_ids = []
    for embed_group in embed_groups:
        try:
            message = await channel.send(content=desc.external_pre_text, embeds=embed_group)
            sent_message_ids.append(message.id)
        except Exception as error:
            error_strings: list[str] = []
            await log_exception(f'Failed to send embed to {channel.jump_url}', error, error_strings, False)
            await send_if_errors("Failed to send embed", error_strings, channel)

    if desc.expires:
        await store_sent_embeds_in_expire_database(sent_message_ids, channel.id)