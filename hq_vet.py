
from hq_types import *
from hq_react import *
from hq_discord import *
from hq_rip import *
from hq_database import * 

from bot_secrets import YOUTUBE_API_KEY, YOUTUBE_CHANNEL_NAME
from simpleQoC.qoc import CheckResultType, QoCCheckType, QoCCheck, performQoC
from simpleQoC.metadata import checkMetadata, isDupe

#===============================================#
#                  RIP VETTING                  #
#===============================================#

UNPIN_START_STRING = "-# :pushpin::x:"

class VetRipDesc(NamedTuple):
    rip: Rip | None = None
    message: Message | None = None
    use_youtube_api: bool = False
    past_rip_message_content: str = ""
    full_feedback: bool = False
    is_new_pinned_message: bool = False

async def vet_rip_or_url(rip_text_or_url: str, desc: VetRipDesc, guild: discord.Guild) -> StringAndErrors:
    """
    Single function for vetting rip audio. Checks for metadata correctness and auto-QoCs rip audio for common issues.
    Accepts either the message text or a single URL to the rip audio and auto detects what to analyze.
    If sourced from a message (!vet_msg or on pin), the message should be included too in VetRipDesc
    Same as if it is sourced from a rip (!vet_from)

    Any vet command, regardless of source, keeps a message that is found underneath the rip in QoC updated
    that reports info on the vet. If the message is not found nearby after the rip message, it is posted in the qoc channel.
    The message is edited with the latest vet info on every command automatically regardless of how it is done.
    Pass in past_rip_message_content when editing the message to handle this correctly

    Link and Pin emojis are also handled on the rip message, adding or removing them to reflect the state of the rip or pin state. 
    Any check emojis (used to say that something should be ignored) is removed from the vet message if it is updated
    to avoid a stale check giving wrong info on what should be ignored.
    """

    rip_message_text = ""
    urls = [] 

    if '```' in rip_text_or_url:
        rip_message_text = rip_text_or_url
        urls = extract_rip_link(rip_text_or_url)
    
    if not len(urls) and desc.rip:
        rip_message_text = desc.rip.text
        urls = extract_rip_link(desc.rip.text)
        #TODO: (Ahmayk) if the rip audio is an attachment, it won't be found!
        #this codepath and situation is too rare to refactor how links are handled
        #to fix this though lol

    if not len(urls) and desc.message:
        rip_message_text = desc.message.content
        urls = extract_rip_link(desc.message.content)
        if not len(urls) and len(desc.message.attachments):
            urls = [desc.message.attachments[0].url]

    if not len(urls):
        urls = [rip_text_or_url]

    qoc_checks_dict: dict[QoCCheckType, QoCCheck] = {} 
    qoced_url = "" 
    for url in urls:
        qoc_checks_dict = await run_blocking(performQoC, url)
        if QoCCheckType.LINK in qoc_checks_dict and qoc_checks_dict[QoCCheckType.LINK].result != CheckResultType.ERROR:
            qoced_url = url
            break

    link_error = QoCCheckType.LINK in qoc_checks_dict and \
        qoc_checks_dict[QoCCheckType.LINK].result == CheckResultType.ERROR

    react_types_add: list[ReactType] = []
    react_types_remove: list[ReactType] = []

    duration_string = "`[Unknown length]`"
    if (
        QoCCheckType.LENGTH in qoc_checks_dict
        and qoc_checks_dict[QoCCheckType.LENGTH].result == CheckResultType.PASS
        and len(qoced_url)
    ):
        jingle_length_in_seconds = get_config("jingle_length_in_seconds")
        duration = qoc_checks_dict[QoCCheckType.LENGTH].value_float
        duration_string = format_rip_timecode(duration)
        await store_in_database_float(duration, qoced_url, JEDatabaseKey.RIP_LENGTH)
        if duration <= jingle_length_in_seconds:
            react_types_add.append(ReactType.JINGLE)

    is_qoc_pass_all = len(qoc_checks_dict) > 0
    for qoc_check in qoc_checks_dict.values():
        if qoc_check.result != CheckResultType.PASS:
            is_qoc_pass_all = False
            break

    error_strings = []
    metadata_checks: List[QoCCheck] = []
    advancedCheck = get_config('metadata')
    rip_message_link = "" 
    if len(rip_message_text):
        description = get_rip_description(rip_message_text)
        is_unusual_metadata = "unusual metadata" in rip_message_text.lower()
        if not is_unusual_metadata and len(description) > 0:
            playlistId = extract_playlist_id('\n'.join(rip_message_text.splitlines()[1:])) # ignore author line
            metadata_checks = await run_blocking(checkMetadata, description, YOUTUBE_CHANNEL_NAME, playlistId, \
                                                 YOUTUBE_API_KEY, desc.use_youtube_api, advancedCheck)

        message_id = 0
        vetted_message_link = ""
        message_author_name = ""
        if desc.rip:
            vetted_message_link = format_message_link(desc.rip.guild_id, desc.rip.channel_id, desc.rip.message_id)
            message_author_name = desc.rip.message_author_name
            message_id = desc.rip.message_id
        if desc.message:
            vetted_message_link = desc.message.jump_url
            message_author_name = str(desc.message.author)
            message_id = desc.message.id

        if len(vetted_message_link):
            rip_message_link = f'[{get_rip_title(rip_message_text)}]({vetted_message_link})' 

        if not len(metadata_checks) and "[Unusual Pin Format]" in get_rip_author(rip_message_text, message_author_name):
            metadata_checks.append(QoCCheck(CheckResultType.FAIL, "Rip author is missing."))

        # TODO: (Ahmayk) All of this belongs in QoC code 
        if not is_unusual_metadata:
            rips = []
            channel_ids = get_channel_ids_of_types(['QUEUE', 'QOC'])
            for channel_id in channel_ids:
                channel_and_errors = await discord_find_channel(channel_id)
                error_strings.extend(channel_and_errors.error_strings)
                if channel_and_errors.channel:
                    rips_and_errors = await get_rips_fast(channel_and_errors.channel, GetRipsDesc())
                    rips = rips_and_errors.rips
                    error_strings.extend(rips_and_errors.error_strings)

            title = get_raw_rip_title(rip_message_text)
            for rip in rips:
                if rip.message_id != message_id:
                    rip_title = get_raw_rip_title(rip.text)
                    if title == rip_title:
                        link = format_message_link(rip.guild_id, rip.channel_id, rip.message_id)
                        metadata_checks.append(QoCCheck(CheckResultType.FAIL, f"Video title already exists in <#{rip.channel_id}>: [{rip_title}]({link})."))
                    if isDupe(description, get_rip_description(rip.text), True):
                        link = format_message_link(rip.guild_id, rip.channel_id, rip.message_id)
                        metadata_checks.append(QoCCheck(CheckResultType.FAIL, f"Main mix detected in <#{rip.channel_id}>: [{rip_title}]({link}). Add something on the author line to avoid uploading this early."))

            # Check for lines between the rip description and link - if it does not start with "Joke", add a warning
            # in order to minimize accidental joke lines when uploading
            if len(qoced_url) and advancedCheck:
                try:
                    for line in rip_message_text.split('```', 2)[2].splitlines():
                        line = "".join(c for c in line if c.isprintable())
                        if qoced_url in line:
                            break
                        elif len(line) > 0 and not line.startswith('Joke') and not line == '||':
                            metadata_checks.append(QoCCheck(CheckResultType.FAIL, "Line not starting with ``Joke`` detected between description and rip URL. Recommend putting the URL directly under description to avoid accidentally uploading joke lines."))
                            break
                except IndexError:
                    pass

    everything_passed = is_qoc_pass_all and not len(metadata_checks)

    past_vet_message = None 
    if desc.message and channel_is_types(desc.message.channel, ['QOC']):

        #TODO: (Ahmayk) don't do this anymore, utilize database!
        after_messages_and_errors = await discord_get_channel_messages_after(desc.message, 100)
        error_strings.extend(after_messages_and_errors.error_strings)
        assert bot.user
        for message in after_messages_and_errors.messages:
            if (
                message.author.id == bot.user.id 
                and desc.message.jump_url in message.content
                and not message.content.startswith(UNPIN_START_STRING)
            ):
                past_vet_message = message
                break

        if desc.message.pinned:
            react_types_remove.append(ReactType.PIN)

        if link_error:
            react_types_add.append(ReactType.LINKERR)
        else:
            react_types_remove.append(ReactType.LINKERR)

        if (
            QoCCheckType.BITRATE in qoc_checks_dict
            and qoc_checks_dict[QoCCheckType.BITRATE].result == CheckResultType.FAIL
        ):
            react_types_add.append(ReactType.BITRATE)
        else:
            react_types_remove.append(ReactType.BITRATE)

        errors = await update_rip_status_reacts(desc.message, react_types_add, react_types_remove, guild)
        error_strings.extend(errors)

    return_message = ""

    intro_warnings = [] 
    if not len(qoced_url) and not link_error:
        intro_warnings.append(":warning: No rip links detected.")

    verdict_react_strings: List[str] = [] 

    if link_error: 
        verdict_react_strings.append(QOC_DEFAULT_LINKERR)
        intro_warnings.append(":warning: **Rip link not Auto-QoCed**")

    bitrate_react = react_type_to_react(ReactType.BITRATE, guild)
    clipping_react = react_type_to_react(ReactType.CLIPPING, guild)
    metadata_react = react_type_to_react(ReactType.METADATA, guild)
    fix_react = react_type_to_react(ReactType.FIX, guild)
    regular_check_react = react_type_to_react(ReactType.REGULAR_CHECK, guild)

    issue_list = []
    for qoc_check_type, qoc_check in qoc_checks_dict.items():
        if len(qoc_check.msg) and (desc.full_feedback or qoc_check.result != CheckResultType.PASS):
            issue_list.append(qoc_check.msg)

        if qoc_check.result == CheckResultType.FAIL and fix_react.string not in verdict_react_strings:
            verdict_react_strings.append(fix_react.string)
            if qoc_check_type == QoCCheckType.BITRATE:
                verdict_react_strings.append(bitrate_react.string)
            if qoc_check_type == QoCCheckType.CLIPPING:
                verdict_react_strings.append(clipping_react.string)

        if qoc_check.result == CheckResultType.ERROR and DEFAULT_ERROR not in verdict_react_strings:
            verdict_react_strings.append(DEFAULT_ERROR)

    if len(metadata_checks):
        verdict_react_strings.append(metadata_react.string)
        for qoc_check in metadata_checks:
            if len(qoc_check.msg):
                issue_list.append(qoc_check.msg)
    elif desc.full_feedback:
        issue_list.append('Metadata is OK.')

    if everything_passed:
        verdict_react_strings.append(regular_check_react.string)

    return_header = "" 
    if len(rip_message_link):
        return_header_title = "Rip"
        if desc.past_rip_message_content:

            old_rip_links = extract_rip_link(desc.past_rip_message_content)
            old_rip_link = ""
            if len(old_rip_links):
                old_rip_link = old_rip_links[0]
            is_link_updated = qoced_url and old_rip_link != qoced_url

            #NOTE: (Ahmayk) assumes that "metadata" is everything before the audio rip link
            linkless_metadata_old = desc.past_rip_message_content 
            if len(old_rip_link):
                linkless_metadata_old = desc.past_rip_message_content.split(old_rip_link)[0]
            linkless_metadata_new = rip_message_text
            if len(qoced_url):
                linkless_metadata_new = rip_message_text.split(qoced_url)[0]
            is_metadata_updated = linkless_metadata_old != linkless_metadata_new 

            if is_link_updated and is_metadata_updated:
                return_header_title = f'{QOC_DEFAULT_LINKERR}{metadata_react.string} Link and Metadata Updated'
            elif is_link_updated:
                return_header_title = f'{QOC_DEFAULT_LINKERR} Link Updated'
            elif is_metadata_updated:
                return_header_title = f'{metadata_react.string} Metadata Updated'
            else:
                return_header_title = f'Message Updated'

        return_header = f'**{return_header_title}: {rip_message_link}** - {duration_string}'

    intro_warnings_string = "\n".join(intro_warnings)
    return_message = f'{intro_warnings_string}\n{return_header}\n**Verdict**: {" ".join(verdict_react_strings)}'
    if len(issue_list):
        return_message += "\n- " + "\n- ".join(issue_list)

    react_check_if_resolved_string = f'-# React {DEFAULT_CHECK} if this should be ignored (will be removed if this message updates).'

    vet_report_text = return_message
    if not everything_passed and len(issue_list):
        vet_report_text += f'\n{react_check_if_resolved_string}'
    vet_report_text = vet_report_text.strip()

    if past_vet_message:
        errors = await discord_edit_message(past_vet_message, vet_report_text)
        error_strings.extend(errors)
    elif desc.is_new_pinned_message and desc.message and channel_is_types(desc.message.channel, ['QOC']):
        await send(vet_report_text, desc.message.channel)

    if not everything_passed and desc.is_new_pinned_message and len(issue_list):
        return_message += f'\n{react_check_if_resolved_string}'

    return_message = return_message.strip()

    if (
        past_vet_message 
        and past_vet_message.content != vet_report_text 
        and message_has_react(regular_check_react, past_vet_message)
    ):
        errors = await discord_clear_reaction(DEFAULT_CHECK, past_vet_message)
        error_strings.extend(errors)

    return StringAndErrors(return_message, error_strings) 