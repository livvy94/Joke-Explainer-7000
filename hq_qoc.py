import os
from pathlib import Path
from inspect import getsourcefile
import requests
from email.message import EmailMessage
import re
import json
import time

from mutagen import File, FileType, flac, wave
import subprocess
from enum import Enum, auto
from typing import NamedTuple, Tuple

from hq_strings import slugify
from hq_discord import FloatAndErrors, JSONAndErrors, run_blocking

DOWNLOAD_DIR = Path(os.path.abspath(getsourcefile(lambda:0))).parent / 'audioDownloads'

DEFAULT_CLIPPING_THRESHOLD = 3
DEFAULT_DS_CLIPPING_THRESHOLD = 5

CLIPPING_FILESIZE_LIMIT = 1024 * 1024 * 500 # 500MB

class CheckResultType(Enum):
    NULL = -2 #NOTE: (Ahmayk) Nothing was done (example: No link exists) 
    ERROR = -1 
    PASS = 0 
    FAIL = 1 

class QoCCheck(NamedTuple):
    result: CheckResultType = CheckResultType.NULL 
    msg: str = ""
    value_float: float = 0.0

class QoCCheckType(Enum):
    LINK = auto()
    BITRATE = auto()
    RESOLUTION = auto()
    LENGTH = auto()


#=======================================#
#           FFMPEG / FFPROBE            #
#=======================================#

def ffmpegExists() -> bool:
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def ffprobeFilepath(filepath: str) -> JSONAndErrors: 
    error_strings: list[str] = []
    try:
        probeOutput = subprocess.check_output([
            'ffprobe',
            '-v', 'quiet',
            # '-select_streams', 'a:0',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            # '-of', 'default=noprint_wrappers=1:nokey=1',
            '-i', filepath,
        ])
    except FileNotFoundError:
        error_strings.append("ERROR: ffprobe failed to run (make sure the command 'ffprobe' can run).")
    except Exception as e:
        error_strings.append(f"ERROR: ffprobe failed: {e}")
    
    return JSONAndErrors(json.loads(probeOutput), error_strings)


def ffprobeGetLengthInSeconds(validUrl: str) -> FloatAndErrors:
    probeOutput: bytes = b""
    error_strings: list[str] = []
    try:
        probeOutput = subprocess.check_output([
            'ffprobe',
            '-v', 'quiet',
            '-show_entries',
            'format=duration',
            '-of',
            'default=noprint_wrappers=1:nokey=1',
            validUrl,
        ])
    except Exception as error:
        error_strings.append(f"ERROR on ffprobe: {error}")

    duration = 0.0
    if not len(error_strings):
        try:
            duration = float(probeOutput.decode().strip())
        except ValueError:
            error_strings.append("ERROR: Could not parse duration from ffprobe output")

    return FloatAndErrors(duration, error_strings)


class DownloadedRip(NamedTuple):
    file: FileType | None
    filepath: str
    error_strings: list[str]

class DownloadRipDesc(NamedTuple):
    open_file: bool = False
    convert_to_wav: bool = False

async def downloadRip(url: str, desc: DownloadRipDesc) -> DownloadedRip:
    error_strings = []

    """
    Certain domains have to be treated in a unique way in order to download files
    For now this function just "converts" the given URL to the "downloadable" version,
    depending on the detected domain
    """
    parsed_url = url 
    if url.find('siiva-gunner.com/?id=') != -1:
        parsed_url = url.replace('?id=', 'api/v2/file/')
    
    elif re.search(r'(?:\d{1,3}\.){3}\d{1,3}/\?id=', url):
        # probably don't wanna deal with SSL certificate stuff
        parsed_url = 'https://siiva-gunner.com/api/v2/file/' + url.split('?id=')[1]
    
    elif url.find('drive.google.com') != -1:
        if 'drive/folders' in url:
            error_strings.append("Drive link is a folder. Please replace it with the link to the rip in the folder.")
        else:
            """
            Assumes the following, taken from moder's scheduler program:
                // Handles 3 kinds of links (they can be preceeded by https://):
                // - drive.google.com/open?id=FILEID
                // - drive.google.com/file/d/FILEID/view?usp=sharing
                // - drive.google.com/uc?id=FILEID&export=download
            """
            id = ""
            if url.find("open?id=") != -1:
                id = url.split("open?id=")[1].split("&")[0]
            if url.find("file/d/") != -1:
                id = url.split("file/d/")[1].split("/")[0]
            if url.find("uc?id=") != -1:
                id = url.split("uc?id=")[1].split("&")[0]

            if id == "":
                error_strings.append("Drive ID cannot be detected from URL: {}".format(url))
            else:
                # let's hope google doesn't randomly decide to change how downloading works in the future...
                parsed_url = "https://drive.usercontent.google.com/download?id={}&export=download&confirm=t".format(id)

    elif url.find('docs.google.com/spreadsheets') != -1:
        error_strings.append("Sir this is a google sheets link.")
    
    elif url.find('dropbox.com') != -1:
        parsed_url = url.replace('&dl=0', '&dl=1')

    elif url.find('catgirlsare.sexy') != -1:
        parsed_url = url.replace('catgirlsare.sexy', 'cgas.io')

    response = None 
    if not len(error_strings):

        session = requests.Session()
        # https://stackoverflow.com/questions/33174804/python-requests-getting-connection-aborted-badstatusline-error
        headers = { 'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36' }
        try:
            response = await run_blocking(session.get, parsed_url, stream=True, headers=headers)
        # https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
        except requests.exceptions.Timeout as e:
            error_strings.append('Request timed out. {}'.format(e))
        except requests.exceptions.TooManyRedirects as e:
            error_strings.append('Bad URL. {}'.format(e))
        except requests.exceptions.ConnectionError as e:
            error_strings.append('Connection error. {}'.format(e))
        except Exception as e:
            error_strings.append('Unknown URL error. {}'.format(e))

    if not len(error_strings) and not response:
        error_strings.append('Internal URL error (No response).')

    filename = parsed_url.split('/')[-1]
    if not len(error_strings) and response:

        response_text = ""
        if 'html' in response.headers['Content-Type']:
            text = response.text
            title = re.search(r'<\W*title\W*(.*)</title', text, re.IGNORECASE)
            if title:
                response_text = title.group(1)

        if 'drive' in url and 'Sign-in' in response_text:
            error_strings.append("Drive link is not accessible. Ask Mailroom to reupload if this is an email sub.")

    filepath = ""
    if not len(error_strings) and response:
        content_disposition = response.headers.get("Content-Disposition")
        if content_disposition:
            msg = EmailMessage()
            msg["Content-Disposition"] = ''.join([char for char in content_disposition if char.isprintable()])
            content_filename = msg.get_filename()
            if content_filename:
                filename = f'{str(time.time_ns())}{content_filename}'

        if filename.endswith(".zip"):
            error_strings.append(f"Rip is compressed in a `.zip` file. I'm not touching that.")

    if not len(error_strings) and response:
        if not os.path.exists(DOWNLOAD_DIR):
            os.mkdir(DOWNLOAD_DIR)

        filename = filename.split('/')[-1]
        filename = slugify(filename)
        filepath = str(DOWNLOAD_DIR / filename)

        # https://stackoverflow.com/questions/38511444/python-download-files-from-google-drive-using-url
        CHUNK_SIZE = 1024 * 32
        try:
            with open(filepath, "wb") as f:
                for chunk in await run_blocking(response.iter_content, CHUNK_SIZE):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
        except Exception as e:
            error_strings.append(f"Failed to download file: {str(e)}")

    file = None
    if desc.open_file and len(filepath) and not len(error_strings):
        try:
            file = File(filepath)
            if file is None:
                error_strings.append('Something went wrong parsing downloaded rip.')
        except wave.error as e:
            error_strings.append(f'File type {os.path.splitext(filepath)[1]} is not supported ({e}). You can manually inspect file metadata with ffprobe.')
        except Exception as e:
            error_strings.append(f'Error while downloading rip: {(str(e))}')

    return DownloadedRip(file, filepath, error_strings) 


def removeDownloadedRip(downloaded_rip: DownloadedRip):
    if downloaded_rip.filepath:
        try:
            os.remove(downloaded_rip.filepath)
        except:
            pass


def checkBitrateFromFile(file: FileType) -> QoCCheck: 
    """
    Check the bitrate of a mutagen File.
    Requires either lossless format or the metadata contains bitrate information.
    """
    result = CheckResultType.ERROR
    msg = "ERROR: Unknown bitrate. File metadata: {}".format(file.pprint())

    if isinstance(file, wave.WAVE) or isinstance(file, flac.FLAC):
        result = CheckResultType.PASS
        msg = "Lossless file is OK." 
    # seems video files show lower bitrate on properties view for some reason, shouldn't be an issue generally
    elif hasattr(file.info, 'bitrate'):
        bitrate = file.info.bitrate
        if bitrate == 0:      # Some MP4 files have 0 kbps bitrate?
            result = CheckResultType.PASS
            msg = "Bitrate is OK (0 kbps detected)."
        elif bitrate < 300000:    # Apparently some weird files can have bitrate at 317kbps or even 319.999kbps. Let's say 300k is good enough
            result = CheckResultType.FAIL
            msg = "The {} file's bitrate is {}kbps. Please re-render at 320kbps.".format(type(file).__name__, bitrate // 1000)
        else:
            result = CheckResultType.PASS
            msg = "Bitrate is OK."
    
    return QoCCheck(result, msg)



def checkResolution(filepath: str) -> QoCCheck: 
    result = QoCCheck()

    jsonAndErrors = ffprobeFilepath(filepath)
    if not len(jsonAndErrors.error_strings):
        height = None
        for stream in jsonAndErrors.json['streams']:
            if 'height' in stream:
                height = stream['height']
        
        if height is None:
            result = QoCCheck(CheckResultType.PASS, "No video streams detected.")  
        else:
            if height < 1080:
                result = QoCCheck(CheckResultType.FAIL, f"The video file height is {height}. Please re-render at 1080p, unless intentional.")  
            else:
                result = QoCCheck(CheckResultType.PASS, f"The video file height is {height}.")  
    else:
        result = QoCCheck(CheckResultType.ERROR, "\n".join(jsonAndErrors.error_strings))

    return result 


async def getFileMetadataMutagen(url: str) -> Tuple[int, str]:
    """
    Returns the metadata of file at given URL via mutagen's `pprint()` function.
    """
    status = 0
    msg = ""

    downloaded_rip = await downloadRip(url, DownloadRipDesc(open_file=True))
    if downloaded_rip.file != None:
        msg = downloaded_rip.file.pprint()
    else:
        status = -1
        msg = "\n".join(downloaded_rip.error_strings)

    if len(downloaded_rip.filepath):
        try:
            os.remove(downloaded_rip.filepath)
        except:
            pass

    return (status, msg)
    

async def getFileMetadataFfprobe(url: str) -> Tuple[int, str]:
    """
    Returns the metadata of file at given URL via ffprobe.
    """
    status = 0
    msg = ""

    downloaded_rip = await downloadRip(url, DownloadRipDesc())
    if len(downloaded_rip.filepath):
        probeOutput = ffprobeFilepath(downloaded_rip.filepath)
        try:
            probeOutput['format']['filename'] = "[REDACTED]"
        except KeyError:
            pass

        # some entries in the json may be too long to be sent on Discord
        def redactLongStrings(obj, max_length = 300):
            if max_length < 11:
                raise ValueError("Cannot shorten more than the [LONG TEXT] message")
            if isinstance(obj, dict):
                keys_to_delete = []
                for key, value in obj.items():
                    if isinstance(value, str) and len(value) > max_length:
                        keys_to_delete.append(key)
                    else:
                        redactLongStrings(value, max_length) # Recurse for nested objects/lists
                for key in keys_to_delete:
                    obj[key] = "[LONG TEXT]"
            elif isinstance(obj, list):
                i = 0
                while i < len(obj):
                    if isinstance(obj[i], str) and len(obj[i]) > max_length:
                        obj[i] = "[LONG TEXT]"
                    else:
                        redactLongStrings(obj[i], max_length) # Recurse for nested objects/lists
                        i += 1

        redactLongStrings(probeOutput)
        msg = json.dumps(probeOutput, indent=2)

    else:
        status = -1
        msg = "\n".join(downloaded_rip.error_strings)

    if len(downloaded_rip.filepath):
        try:
            os.remove(downloaded_rip.filepath)
        except:
            pass

    return (status, msg)


async def getAudioLengthInSecondsFFprobe(url: str) -> FloatAndErrors: 
    duration = 0.0

    downloaded_rip = await downloadRip(url, DownloadRipDesc())
    error_strings = downloaded_rip.error_strings

    if len(downloaded_rip.filepath):
        floatAndErrors = ffprobeGetLengthInSeconds(downloaded_rip.filepath)
        duration = floatAndErrors.result
        error_strings.extend(floatAndErrors.error_strings)

    if len(downloaded_rip.filepath):
        try:
            os.remove(downloaded_rip.filepath)
        except:
            pass

    return FloatAndErrors(duration, error_strings) 


async def performQoC(url: str) -> dict[QoCCheckType, QoCCheck]: 
    """
    Performs QoC on the given URL.
    """
    
    downloaded_rip = await downloadRip(url, DownloadRipDesc(open_file = True))

    result: dict[QoCCheckType, QoCCheck] = {}
    if downloaded_rip.file != None:
        result[QoCCheckType.LINK] = QoCCheck(CheckResultType.PASS, "")
        result[QoCCheckType.BITRATE] = checkBitrateFromFile(downloaded_rip.file)
        result[QoCCheckType.RESOLUTION] = checkResolution(downloaded_rip.filepath)

        float_and_errors = ffprobeGetLengthInSeconds(downloaded_rip.filepath)
        if not len(float_and_errors.error_strings):
            result[QoCCheckType.LENGTH] = QoCCheck(CheckResultType.PASS, "", float_and_errors.result)
        else:
            result[QoCCheckType.LENGTH] = QoCCheck(CheckResultType.FAIL, " ".join(float_and_errors.error_strings))

    else: 
        result[QoCCheckType.LINK] = QoCCheck(CheckResultType.ERROR, "\n".join(downloaded_rip.error_strings))

    if len(downloaded_rip.filepath):
        try:
            os.remove(downloaded_rip.filepath)
        except:
            pass

    return result
