import os
from pathlib import Path
from inspect import getsourcefile
from typing import Tuple
import requests
from email.message import EmailMessage
import re
import json
import time

from mutagen import File, FileType, flac, wave
from scipy.io import wavfile
import subprocess
import numpy as np
from enum import Enum, auto
from typing import NamedTuple, List, Tuple

from hq_strings import slugify
from hq_react import *
from hq_discord import FloatAndErrors, run_blocking

#=======================================#
#           TYPES AND CONSTANTS         #
#=======================================#

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
    CLIPPING = auto()
    RESOLUTION = auto()
    LENGTH = auto()

#=======================================#
#               DEBUGGING               #
#=======================================#
DEBUG_MODE = False

def DEBUG(msg):
    if DEBUG_MODE:
        print(msg)

"""
Usage: Run the following command in main directory: python -m simpleQoC.simpleQoCtests.test [TestClass[.testfunc]]
"""

#=======================================#
#          EXCEPTION HANDLING           #
#=======================================#

# https://stackoverflow.com/a/26938914
class QoCException(Exception):
    def __init__(self, message, *args):
        self.message = message # without this you may get DeprecationWarning
  
        # allow users initialize misc. arguments as any other builtin Error
        super(QoCException, self).__init__(message, *args) 


#=======================================#
#           FFMPEG / FFPROBE            #
#=======================================#

def ffmpegExists():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def ffprobeUrl(validUrl: str):
    """
    Retrives file metadata from URL using ffprobe.
    """
    try:
        probeOutput = subprocess.check_output([
            'ffprobe',
            '-v', 'quiet',
            # '-select_streams', 'a:0',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            # '-of', 'default=noprint_wrappers=1:nokey=1',
            '-i', validUrl,
        ])
    except FileNotFoundError:
        raise QoCException("ERROR: ffprobe failed to run (make sure the command 'ffprobe' can run).")
    
    return json.loads(probeOutput)

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


def ffmpegToWAV(filepath: str, wav_filepath: str):
    """
    Runs ffmpeg to create a WAV file from the provided audio filepath or URL.
    - **filepath**: Path to local file, or URL to file
    - **wav_filepath**: Path to WAV file to be generated
    """
    try:
        subprocess.call([
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', filepath,
            '-c:a', 'pcm_f32le',
            wav_filepath,
        ])
    except FileNotFoundError:
        raise QoCException("ERROR: ffmpeg failed to run (make sure the command 'ffmpeg' can run).")
    
    if not os.path.exists(wav_filepath):
        raise QoCException("ERROR: ffmpeg failed to generate .wav file.")

#=======================================#
#           URL DOWNLOADING             #
#=======================================#

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

#=======================================#
#           BITRATE CHECKING            #
#=======================================#

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


#=======================================#
#           CLIPPING CHECKING           #
#=======================================#

# https://stackoverflow.com/a/24892274
def sameValueRuns(arr: np.ndarray, value) -> np.ndarray:
    # Create an array that is 1 where a is value, and pad each end with an extra 0.
    iszero = np.concatenate(([0], np.equal(arr, value), [0]))
    absdiff = np.abs(np.diff(iszero))
    # Runs start and end where absdiff is 1.
    ranges = np.where(absdiff == 1)[0].reshape(-1, 2)
    return ranges

def getClipping(channel: np.ndarray, ceiling, threshold: int) -> list:
    clipSamples = []
    runs = sameValueRuns(channel, ceiling)
    for run in runs:
        if run[1] - run[0] >= threshold:
            clipSamples.append(run)
    return clipSamples

def channelHasClipping(channel: np.ndarray, max, min, threshold: int) -> list:
    return getClipping(channel, max, threshold) + getClipping(channel, min, threshold)
    

def checkClipping(wav_filepath: Path, threshold: int, doGradientAnalysis: bool) -> QoCCheck: 
    """
    Checks whether a WAV file is clipping (waveform contains "flat" peaks).
    - **wav_filepath**: Path to a local WAV file.
    - **threshold**: How many consecutive samples to look for. Recommended value: 3.
    - **doGradientAnalysis**: Set to True if the waveform may contain overflows.
    """
    if os.path.getsize(wav_filepath) > CLIPPING_FILESIZE_LIMIT:
        # if WAV file is over 500 MB, skip clipping checking to not nuke the RAM by loading the entire waveform into memory
        # TODO: change to analyze by chunk?
        return QoCCheck(CheckResultType.ERROR, "Unable to check for clipping due to large file size or audio length. Workaround TBA.")
    
    wavFile = None
    try:
        wavFile = File(wav_filepath)
        if wavFile is None:
            return QoCCheck(CheckResultType.FAIL, 'Something went wrong parsing downloaded rip.')
    except wave.error as e:
        return QoCCheck(CheckResultType.FAIL, f'File type {os.path.splitext(wav_filepath)[1]} is not supported ({e}). You can manually inspect file metadata with ffprobe.')

    clips = []
    framerate, data = wavfile.read(wav_filepath)

    # Special case: 24-bit FLACs can go over sample limit and cause overflow/underflow,
    # apply specialized algorithm to check for clicking instead.
    if doGradientAnalysis:
        data_deriv = np.gradient(data, axis=0)
        maxG = np.max(data_deriv)
        minG = np.min(data_deriv)
        DEBUG('G: Max: {}, Min: {}'.format(maxG, minG))

        # TODO: fine tune arbitrarily chosen threshold
        # it may be possible to use 'and' since overflow/underflow will create large gradient both ways
        if maxG > 0.8 or minG < -0.8:
            return QoCCheck(CheckResultType.ERROR, "Detected large gradient. Please verify clipping in Audacity.")
        else:
            return QoCCheck(CheckResultType.PASS, "The rip is not clipping.")

    # +1 to min in order to mimic Audacity's Find Clipping algorithm,
    # even though WAV samples can technically go lower
    limits = {
        16: (-2**15     +1,     2**15-1     ),
        24: (-2**31     +1,     2147483392  ),
        32: (-2**31     +1,     2**31-1     ),
    }

    # Apparently WAV 32-bit float can go over +-1.0
    if data.dtype == np.float32:
        data.clip(-1.0, 1.0, out=data)
    else:
        data.clip(limits[wavFile.info.bits_per_sample][0], limits[wavFile.info.bits_per_sample][1], out=data)

    # If audio is mono, reshape data for consistency
    if data.ndim == 1:
        data = data[:,None]

    # Find max and min values in case someone tries to fix clipping in Audacity
    maxVals = data.max(axis=0)
    minVals = data.min(axis=0)

    DEBUG('Data type: {}'.format(data.dtype))
    DEBUG('Max: {}'.format(maxVals))
    DEBUG('Min: {}'.format(minVals))

    debugClipSamples = []
    upperClip = np.full(maxVals.shape, False)
    lowerClip = np.full(minVals.shape, False)

    clipSamples = []
    for c in range(maxVals.size):
        samples = channelHasClipping(data[:, c], maxVals[c], minVals[c], threshold)
        for s in samples:
            upperClip[c] = upperClip[c] or (data[s[0], c] == maxVals[c])
            lowerClip[c] = lowerClip[c] or (data[s[0], c] == minVals[c])
            debugClipSamples.append((s[0] / framerate, data[s[0]:s[1], 0]))
        clipSamples.extend(samples)

    for d in debugClipSamples:
        DEBUG(d)

    clipSamples.sort(key = lambda x: (x[0], x[1])) # Sort by time for viewing purpose
    for clipSample in clipSamples:
        clips.append('{:.2f} sec ({} samples)'.format(clipSample[0] / framerate, clipSample[1] - clipSample[0]))
    
    if len(clips) > 0:
        msg = ""

        # Detect if volume was reduced post-render
        formatMin, formatMax = (-1.0, 1.0) if data.dtype == np.float32 else limits[wavFile.info.bits_per_sample]

        if np.any(np.logical_and(upperClip, maxVals < formatMax)) or np.any(np.logical_and(lowerClip, minVals > formatMin)):
            msg = " Post-render volume reduction detected, please lower the volume before rendering."
        
        if len(clips) > 10:
            msg = "The rip is heavily clipping." + msg
        else:
            msg = "The rip is clipping at: " + ", ".join(clips) + "." + msg
        
        return QoCCheck(CheckResultType.FAIL, msg)
    else:
        return QoCCheck(CheckResultType.PASS, "The rip is not clipping.")


def checkClippingFromFile(downloaded_rip: DownloadedRip, threshold: int = DEFAULT_CLIPPING_THRESHOLD) -> QoCCheck:
    """
    Checks whether a mutagen File is clipping.
    Requires the file having been downloaded locally.
    """
    wav_filepath = Path(downloaded_rip.filepath)
    newfile = False
    if not isinstance(downloaded_rip.file, wave.WAVE):
        newfile = True
        wav_filepath = "{}_temp.wav".format(Path.joinpath(wav_filepath.parent, wav_filepath.stem))
    else:
        DEBUG('Bits per sample: {}'.format(downloaded_rip.file.info.bits_per_sample))
    
    if not os.path.exists(wav_filepath):
        ffmpegToWAV(downloaded_rip.filepath, wav_filepath)

    qoc_check = QoCCheck() 
    # do gradient analysis if file is 24-bit FLAC
    if isinstance(downloaded_rip.file, flac.FLAC) and downloaded_rip.file.info.bits_per_sample == 24:
        DEBUG("Input file is detected as 24-bit FLAC. Recommend verifing clipping in Audacity.")
        qoc_check = checkClipping(wav_filepath, threshold, True)
    else:
        qoc_check = checkClipping(wav_filepath, threshold, False)

    if newfile:
        try:
            os.remove(wav_filepath)
        except:
            pass

    return qoc_check 


#=======================================#
#         DLS CLIPPING CHECKING         #
#=======================================#
"""
Same idea behind checking clipping, but not limited to min/max values.
We assume that DLS clipping will create non-peaking flat lines in the waveform that causes distortion.
"""

def getConsecutiveRuns(channel: np.ndarray, threshold: int) -> list:
    # ensure array
    if channel.ndim != 1:
        raise ValueError('Only 1D array supported')
    
    consRun = np.append(np.equal(channel[:-1], channel[1:]).astype(np.int16), 0)
    consSamples = []

    runs = sameValueRuns(consRun, 1)
    for run in runs:
        # Each streak of 1 in consRun correspond to a streak in the channel array with 1 fewer sample
        # since each individual sample is a consecutive run of length 1
        if run[1] - run[0] >= threshold-1:
            consSamples.append((channel[run[0]], run))
    
    return consSamples


def checkDLSClipping(wav_filepath: Path, threshold: int) -> Tuple[bool, str]:
    """
    Checks whether a WAV file might have DLS clipping (waveform contains non-zero "flat" samples).
    - **threshold**: How many consecutive samples to look for. Recommended value: 5.
    """
    wavFile = None
    try:
        wavFile = File(wav_filepath)
        if wavFile is None:
            return (False, 'Something went wrong parsing downloaded rip.')
    except wave.error as e:
        return (False, f'File type {os.path.splitext(wav_filepath)[1]} is not supported ({e}). You can manually inspect file metadata with ffprobe.')

    cons = []
    framerate, data = wavfile.read(wav_filepath)

    # +1 to min in order to mimic Audacity's Find Clipping algorithm,
    # even though WAV samples can technically go lower
    limits = {
        16: (-2**15     +1,     2**15-1     ),
        24: (-2**31     +1,     2147483392  ),
        32: (-2**31     +1,     2**31-1     ),
    }

    # Apparently WAV 32-bit float can go over +-1.0
    if data.dtype == np.float32:
        data.clip(-1.0, 1.0, out=data)
    else:
        data.clip(limits[wavFile.info.bits_per_sample][0], limits[wavFile.info.bits_per_sample][1], out=data)

    # If audio is mono, reshape data for consistency
    if data.ndim == 1:
        data = data[:,None]

    # Find max and min values
    maxVals = data.max(axis=0)
    minVals = data.min(axis=0)

    DEBUG('Data type: {}'.format(data.dtype))
    DEBUG('Max: {}'.format(maxVals))
    DEBUG('Min: {}'.format(minVals))

    formatMin, formatMax = (-1.0, 1.0) if data.dtype == np.float32 else limits[wavFile.info.bits_per_sample]
    maxClip = False
    minClip = False
    dlsClip = False

    consSamples = []
    for c in range(maxVals.size):
        samples = getConsecutiveRuns(data[:, c], threshold)
        for s in samples:
            if s[0] == maxVals[c]:
                if maxVals[c] < formatMax:
                    maxClip = True
            elif s[0] == minVals[c]:
                if minVals[c] < formatMin:
                    minClip = True
            elif abs(s[0]) / formatMax > 1e-3: # this needs to be changed if unsigned WAVs will be used
                dlsClip = True
        
        consSamples.extend(samples)

    consSamples.sort(key = lambda x: (x[1][0], x[1][1])) # Sort by time for viewing purpose
    for s in consSamples:
        if s[0] == formatMax or s[0] == formatMin or s[0] in maxVals or s[0] in minVals or abs(s[0]) / formatMax < 1e-3:
            continue
        cons.append('{:.2f} sec ({} samples, value: {})'.format(s[1][0] / framerate, s[1][1] - s[1][0] + 1, s[0]))
        
    if len(cons) > 0:
        msg = ""

        if dlsClip:
            msg = "DLS clipping detected"
            if len(cons) > 10:
                msg = msg + " at many samples."
            else:
                msg = msg + " at: " + ", ".join(cons) + "."
        elif maxClip or minClip:
            msg = "No DLS clipping detected, but post-render volume reduction clipping detected"
        else:
            msg = "No DLS clipping detected, but clipping detected"
        
        return (False, msg)
    else:
        return (True, "The rip has no DLS clipping.")


def checkDLSClippingFromFile(file: FileType, filepath: str, threshold: int = DEFAULT_DS_CLIPPING_THRESHOLD) -> Tuple[bool, str]:
    """
    Checks whether a mutagen File has DLS clipping.
    Requires the file having been downloaded locally.
    """
    wav_filepath = Path(filepath)
    newfile = False
    if not isinstance(file, wave.WAVE):
        newfile = True
        wav_filepath = "{}_temp.wav".format(Path.joinpath(wav_filepath.parent, wav_filepath.stem))
    else:
        DEBUG('Bits per sample: {}'.format(file.info.bits_per_sample))
        
    if not os.path.exists(wav_filepath):
        ffmpegToWAV(filepath, wav_filepath)

    check, msg = checkDLSClipping(wav_filepath, threshold)

    if newfile:
        os.remove(wav_filepath)

    return (check, msg)


#=======================================#
#            VIDEO RESOLUTION           #
#=======================================#
"""
Verify that video files are at least 1080p
"""

def checkResolution(filepath: str) -> QoCCheck: 
    probeOutput = ffprobeUrl(filepath)
    height = None
    for stream in probeOutput['streams']:
        try:
            height = stream['height']
        except KeyError:
            continue
    
    if height is None:
        return QoCCheck(CheckResultType.PASS, "No video streams detected.")  
    else:
        if height < 1080:
            return QoCCheck(CheckResultType.FAIL, f"The video file height is {height}. Please re-render at 1080p, unless intentional.")  
        else:
            return QoCCheck(CheckResultType.PASS, f"The video file height is {height}.")  


#=======================================#
#                Utility                #
#=======================================#

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
        probeOutput = ffprobeUrl(downloaded_rip.filepath)
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
        DEBUG("File metadata: " + downloaded_rip.file.pprint())
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


"""
Commented this out to work on it later
"""
# def performQoCWithoutDL(url: str) -> Tuple[bool, str]:
#     """
#     Version 2: Use HTTP head, ffprobe and ffmpeg to reduce temporary files

#     TODO: slow afffff
#     """
#     downloadableUrl = parseUrl(url)
#     if not os.path.exists(DOWNLOAD_DIR):
#         os.mkdir(DOWNLOAD_DIR)
    
#     errors = []

#     try:
#         bitrateCheck, bitrateMsg = checkBitrateFromUrl(downloadableUrl)
#     except QoCException as e:
#         errors.append(e.message)

#     try:
#         clippingCheck, clippingMsg = checkClippingFromUrl(downloadableUrl)
#     except QoCException as e:
#         errors.append(e.message)

#     if len(errors) > 0:
#         raise QoCException('\n'.join(errors))
    
#     return (bitrateCheck and clippingCheck, '- {}\n- {}'.format(bitrateMsg, clippingMsg))
