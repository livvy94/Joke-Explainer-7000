
import typing
from typing import List, NamedTuple
from enum import Enum, auto
import re
import string
import unicodedata
from difflib import SequenceMatcher
import numpy 

def split_long_message(a_message: str, character_limit) -> list[str]:  # avoid Discord's character limit
    """
    Split a long message to fit Discord's character limit.
    Aug 6 2025: apparently embeds have a higher character limit?
    """
    result: List[str] = []
    #TODO: (Ahmayk) While unlikely, this could split things into a group that is bigger than 2000.
    #we're not accounting for that currently.
    all_lines = a_message.splitlines()
    wall_of_text = ""
    is_in_regular_codeblock = False
    is_in_python_codeblock = False
    for i, line in enumerate(all_lines):
        line = line.replace('@', '')  # no more pings lol

        if "```py" in line:
            is_in_python_codeblock = True
        elif "```" in line:
            if is_in_python_codeblock:
                is_in_python_codeblock = False
            else:
                is_in_regular_codeblock = not is_in_regular_codeblock

        need_new_block = False 
        if len(wall_of_text) + len(line) > character_limit:
            need_new_block = True 

        if is_in_python_codeblock or is_in_regular_codeblock:
            if len(wall_of_text) + len(line) + len("\n```") > character_limit:
                need_new_block = True 
            if i != len(all_lines) - 1:
                len_current_and_next = len(wall_of_text) + len(line) + len(all_lines[i + 1])
                if len_current_and_next <= character_limit and \
                   len_current_and_next + len("\n```") > character_limit:
                    need_new_block = True 

        if need_new_block: 
            new_block = wall_of_text[:-1]
            wall_of_text = "" 
            if is_in_python_codeblock:
                new_block += '\n```' 
                wall_of_text = "```py\n" 
            if is_in_regular_codeblock:
                new_block += '\n```' 
                wall_of_text = "```" 
            result.append(new_block)

        wall_of_text += line + '\n'

    result.append(wall_of_text[:-1])  # add anything remaining
    return result


#TODO: (Ahmayk) This is the wrong api. rips can have either a link or an attachment.
# should input a message, and we return a link either from message content or an attachment url
# (this would require an equivalent rip version of this api, which would store attachment urls)
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

def clean_strings_markdown(texts: str) -> list[str]:
    result = []
    for s in texts:
        s = s.replace('*', '').replace('_', '').replace('|', '').replace('#', '').lower()
        result.append(s)
    return result

#TODO: (Ahmayk) don't return None, return empty string
def get_raw_rip_title(text: str) -> str | None:
    """
    Return the rip title line of a Discord message.
    Assumes the message follows the format where the rip title is after the first instance of ```
    """
    # Update: now use regex to find the first instance of "```[\n][text][\n]"
    rip_title = re.search(r'\`\`\`\n*.*\n', text)
    if rip_title is not None:
        rip_title = rip_title.group(0)
        rip_title = rip_title.replace('`', '')
        rip_title = rip_title.replace('\n', '')

    return rip_title


#TODO: (Ahmayk) don't return None, return empty string
def get_rip_title(text: str) -> str | None:
    """
    Wrapper function to format unusual or spoiler rip titles
    """
    rip_title = get_raw_rip_title(text)
    CODEBLOCK_TYPES = ['ansi', 'swift', 'fix', 'ldif']
    if rip_title is None:
        return "`[Unusual Pin Format]`"
    elif '||' in text.split('```')[0]:
        # if || is detected in the message before the first ```, make the rip title into spoiler
        return "`[Rip Contains Spoiler]`"
    elif rip_title in CODEBLOCK_TYPES:
        # 13 Jun 2026: im just gonna hardcode these 3 cases lol
        return get_raw_rip_title(text.replace(f'```{rip_title}', '```', 1))
    else:
        return rip_title


def get_raw_rip_author(text: str) -> str:
    """
    Return the rip author line of a Discord message.
    Assumes the message follows the format where the rip author is after the first instance of ```
    """
    author = text.split("```")[0]
    author = author.replace('\n', '')
    author = author.replace('||', '') # in case of spoilered rips

    return author


def get_rip_author(text: str, message_author_name: str) -> str:
    """
    Wrapper function to format author line.
    If the line contains "by me", append the message sender's name to the author line.
    """
    author = get_raw_rip_author(text)
    
    if len(re.findall(r'\bby\b', author.lower())) == 0:
        # If "by" is not found, notify that the "author line" might be unusual
        author = author + " [Unusual Pin Format]"

    elif len(re.findall(r'\bby me\b', author.lower())) > 0: 
        # Overwrite it and do something else if the rip's author and the pinner are the same
        cleaned_author = message_author_name.split('#')[0]
        author += (f' (**{cleaned_author}**)')

    return author


def get_rip_description(text: str) -> str:
    """
    Return the description of a rip, i.e. the part inside ```
    """
    # Use a regular expression to find text between two ``` markers
    match = re.search(r'```(.*?)```', text, re.DOTALL)

    if match:
        # Return the extracted text, stripping any leading/trailing whitespace
        return match.group(1).strip()
    else:
        return ""  # Return empty string if no match was found

def get_rip_joke(text: str) -> str:
    result = ""
    after_desc = text
    chunks = text.split('```')
    if len(chunks) >= 3:
        after_desc = chunks[2]
    for line in after_desc.splitlines():
        if ':' in line and ('oke:' in line or 'okes:' in line or 'joke' in line):
            result = (line[line.index(':')+1:]).lstrip()
            break
    return result

def format_message_link(guild_id: int, channel_id: int, message_id: int):
    return  f"<https://discord.com/channels/{str(guild_id)}/{str(channel_id)}/{str(message_id)}>"


def extract_discord_link(text: str) -> str:
    regex = r'(https://discord\.com/channels/\d+/\d+/\d+)'
    match = re.search(regex, text)
    if match:
        return match.group(1)
    else:
        return ""


def line_contains_substring(line: str, substring: str) -> bool:
    """
    Helper function to search substrings in Discord markdown-formatted line, ignoring case and formatting
    """
    return substring.lower() in line.replace('*', '').replace('_', '').replace('|', '').replace('#', '').lower()


#NOTE: (Ahmayk) does not check if input is actually an emoji
def emoji_to_react_name_if_emoji(s: str) -> str:
    react_input = s 
    match = re.fullmatch(r'<a?:(\w+):\d+>', react_input)
    if match:
        react_input = match.group(1)
    return react_input



class ParsedSearchInput(NamedTuple):
    search_keys: List[str]
    regex_search_keys: List[str]
    is_not: bool
    containing_error_string: str
    invalid_input_error_string: str

def format_list(list: List) -> str:
    result = ""
    if len(list) == 1:
        result = f'`{list[0]}`'
    elif len(list) == 2:
        result = f'`{list[0]}` or `{list[1]}`'
    elif len(list) > 2:
        result = f'`{list}`'
    return result

def parse_search_input(args: List[str]) -> ParsedSearchInput:

    is_not = False
    if "NOT" in args:
        is_not = True
        args.remove("NOT")

    search_keys = " ".join([str(s) for s in args]).split('|')
    for i in range(len(search_keys)):
        search_keys[i] = search_keys[i].strip()

    regex_search_keys: List[str] = [] 
    invalid_input_error_string = ""

    to_remove = []
    for key in search_keys:

        if ((key.startswith("r\'") and key.endswith("\'")) 
            or (key.startswith("r\"") and key.endswith("\""))
        ):
            try:
                re.compile(key)
                regex_search_keys.append(key[2:-1])
            except re.error:
                invalid_input_error_string += f'\nError: Invalid regex input: {key}'
            to_remove.append(key)

    for key in to_remove:
        search_keys.remove(key)

    containing_error_string = 'containing '
    if is_not:
        containing_error_string = 'NOT containing '

    if len(search_keys):
        containing_error_string += format_list(search_keys) 
    if len(regex_search_keys):
        containing_error_string += f'regex input `{format_list(regex_search_keys)}`'

    return ParsedSearchInput(search_keys, regex_search_keys, is_not, containing_error_string, invalid_input_error_string)

def search_with_parsed_input(text: str, parsed_search_input: ParsedSearchInput) -> bool:
    is_valid = False

    for regex_search_key in parsed_search_input.regex_search_keys:
        is_valid |= re.search(regex_search_key, text) is not None

    for key in parsed_search_input.search_keys:
        if line_contains_substring(text, key):
            is_valid = True
            break

    if parsed_search_input.is_not:
        is_valid = not is_valid 

    return is_valid


class ParsedRandomInput(NamedTuple):
    random_count: int
    parsed_search_input: ParsedSearchInput 
    invalid_input_error_string: str
    invalid_input_error_string_is_embed: bool
    not_found_error_string: str

async def parse_random_input(args: List[str], search_type_string: str) -> ParsedRandomInput:

    invalid_input_error_string = ""
    invalid_input_error_string_is_embed = False
    parsed_search_input = ParsedSearchInput([], [], False, "", "") 
    not_found_error_string = 'No gambling today!' 

    random_count = 1
    if len(args):
        if args[0].isdigit():
            random_count = int(args[0])
            if random_count == 0:
                invalid_input_error_string = f'**[Zero. - Zero 64 (Zero Mix)](<https://www.youtube.com/watch?v=UtGL5yKdSCk>)**\nby Zero Z | 🔥 🔥 🍌 😭\n------------------------------'
                invalid_input_error_string_is_embed = True
            elif random_count < 0:
                invalid_input_error_string = f'ERROR: Negative rips not implemented `(library not found: antirip)`'
            else:
                args = args[1:]

    if not len(invalid_input_error_string) and len(args):
        parsed_search_input = parse_search_input(args)
        invalid_input_error_string = parsed_search_input.invalid_input_error_string

    if len(parsed_search_input.containing_error_string):
        not_found_error_string = f'No rips {parsed_search_input.containing_error_string} in {search_type_string} found.'

    return ParsedRandomInput(random_count, parsed_search_input, invalid_input_error_string, invalid_input_error_string_is_embed, not_found_error_string) 


class GameAndTrackPair(NamedTuple):
    track_name: str
    game_name: str

def _parse_title_internal(title: str, divider: str, track_name: str) -> list[GameAndTrackPair]:
    pairs: list[GameAndTrackPair] = []
    for i in range(len(title)):
        j = i+len(divider)
        if (title[i:j] == divider):
            before = title[0:i]
            after = title[j-1:]
            before = before.strip()
            after = after.strip()

            before_no_mixname = "" 
            after_no_mixname = "" 
            if (before.endswith(")") and "(" in before):
                before_no_mixname = before[0:before.rindex("(")].strip()
            if (after.endswith(")") and "(" in after):
                after_no_mixname = after[0:after.rindex("(")].strip()

            add_before_after = False
            add_after_before = False

            if len(track_name):
                if before == track_name:
                    add_before_after = True
                if after == track_name:
                    add_after_before = True
            else:
                add_before_after = True

            if add_before_after:
                pairs.append(GameAndTrackPair(before, after))
                if len(before_no_mixname):
                    pairs.append(GameAndTrackPair(before_no_mixname, after))
                if len(after_no_mixname):
                    pairs.append(GameAndTrackPair(before, after_no_mixname))
            if add_after_before:
                pairs.append(GameAndTrackPair(after, before))
                if len(before_no_mixname):
                    pairs.append(GameAndTrackPair(after, before_no_mixname))
                if len(after_no_mixname):
                    pairs.append(GameAndTrackPair(after_no_mixname, before))

    return pairs

def parseTitle(title: str, divider: str, track_name: str) -> list[GameAndTrackPair]:
    pairs = [] 
    if divider in title:
        pairs = _parse_title_internal(title, divider, track_name)
        #NOTE: (Ahmayk) if trying to match to a track_name doesn't turn up anything, repeat without matching to track_name
        if not len(pairs) and len(track_name):
            pairs = _parse_title_internal(title, divider, "")
    else:
        pairs.append(GameAndTrackPair(title, title))
    return pairs


# NOTE: (Ahmayk) https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
def slugify(s: str) -> str:
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^\w\s-]', '', s.lower())
    return re.sub(r'[-\s]+', '-', s).strip('-_')


class TitleType(Enum):
    TRACK = auto()
    ALBUM = auto()
    THUMBNAIL = auto()

def get_cleaned_words(title: str, track_type: TitleType) -> str:
    title = title.lower()
    title = title.translate(str.maketrans('', '', string.punctuation))
    #NOTE: (Ahmayk) remove common keywords, matching to them dilutes search
    if track_type == TitleType.ALBUM:
        title = title.replace(" ost", " ")
        title = title.replace(" original soundtrack", " ")
        title = title.replace(" official soundtrack", " ")
        title = title.replace(" the complete soundtrack", " ")
        title = title.replace(" complete soundtrack", " ")
        title = title.replace(" digital soundtrack", " ")
        title = title.replace(" official ost", " ")
        title = title.replace(" unofficial soundtrack", " ")
        title = title.replace(" unofficial ost", " ")
        title = title.replace(" soundtrack", " ")
    if track_type == TitleType.TRACK:
        title = title.replace(" version", " ")
        title = title.replace(" mix", " ")
    if track_type == TitleType.TRACK:
        title = title.replace(" (retcon)", " ")
    title = title.strip()
    return title


#NOTE: (Ahamyk) fine tuned similarity algorythm
def score_title_similarity(title_to_score: str, match_title: str, scan_result_type: TitleType) -> float:

    score = 0.0

    title_to_score = get_cleaned_words(title_to_score, scan_result_type)
    match_title = get_cleaned_words(match_title, scan_result_type)

    # print(f'SUB: {submitted_title} SCAN: {scanned_title}')

    longest_common_substring_ratio = 0.0
    if len(title_to_score):

        match = SequenceMatcher(None, title_to_score, match_title).find_longest_match()
        longest_common_substring_ratio = match.size / len(title_to_score) 
        # print(match)
        # print(f"LCS: {longest_common_substring_ratio}")

    match scan_result_type:

        case TitleType.ALBUM:
            # print(f'SUB: {submitted_title} SCAN: {scanned_title}')
            # print(f'SUB: {len(submitted_title)} SCAN: {len(scanned_title)}')

            if longest_common_substring_ratio > 0.1:
                title_included = title_to_score == match_title
                ratio_rattcliff = SequenceMatcher(None, title_to_score, match_title).ratio()

                score = (
                    (0.5 * longest_common_substring_ratio)
                    + (0.25 * title_included)
                    + (0.25 * ratio_rattcliff)
                )

        case TitleType.TRACK:

            if longest_common_substring_ratio > 0.5:

                if title_to_score == match_title:
                    # print("Exact match!")
                    score = 1.0
                else:
                    is_partial_match = 0.0 
                    if title_to_score in match_title:
                        # print(f"Included! {submitted_title} -> {scanned_title}")
                        is_partial_match = 1.0 

                    ratio_rattcliff = SequenceMatcher(None, title_to_score, match_title).ratio()
                    # print(f"ratio: {ratio_rattcliff}")

                    score = (
                        (0.5 * longest_common_substring_ratio)
                        + (0.25 * ratio_rattcliff)
                        + (0.25 * is_partial_match)
                    )

                    #NOTE: (Ahmayk) introduces harsher cutoff, makes lower scores lower than higher scores
                    score = score * score * score

        case TitleType.THUMBNAIL:
            # print(f'SUB: {submitted_title} SCAN: {scanned_title}')
            # print(f'SUB: {len(submitted_title)} SCAN: {len(scanned_title)}')

            if longest_common_substring_ratio > 0.1:
                score = 0
                if match_title in title_to_score:
                    score = SequenceMatcher(None, title_to_score, match_title).ratio()

    return score

