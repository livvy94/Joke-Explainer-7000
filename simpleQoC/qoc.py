import os
from pathlib import Path
from inspect import getsourcefile
from typing import Tuple
import requests
import cgi
import re
import json

from mutagen import File, FileType, flac, wave
from scipy.io import wavfile
import subprocess
import numpy as np

DOWNLOAD_DIR = Path(os.path.abspath(getsourcefile(lambda:0))).parent / 'audioDownloads'

DEFAULT_CLIPPING_THRESHOLD = 3
DEFAULT_DS_CLIPPING_THRESHOLD = 5

#=======================================#
#               DEBUGGING               #
#=======================================#
DEBUG_MODE = False

def DEBUG(msg):
    if DEBUG_MODE:
        print(msg)

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

def ffprobeUrl(validUrl: str):
    """
    Retrives file metadata from URL using ffprobe.
    """
    try:
        probeOutput = subprocess.check_output([
            'ffprobe',
            '-v', 'quiet',
            '-select_streams', 'a:0',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            # '-of', 'default=noprint_wrappers=1:nokey=1',
            '-i', validUrl,
        ])
    except FileNotFoundError:
        raise QoCException("ERROR: ffprobe failed to run (make sure the command 'ffprobe' can run).")
    
    return json.loads(probeOutput)


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

def parseUrl(url: str) -> str:
    """
    Certain domains have to be treated in a unique way in order to download files
    For now this function just "converts" the given URL to the "downloadable" version,
    depending on the detected domain
    """
    if url.find('siiva-gunner.com/?id=') != -1:
        return url.replace('?id=', 'api/v2/file/')
    
    if re.search(r'(?:\d{1,3}\.){3}\d{1,3}/\?id=', url):
        # probably don't wanna deal with SSL certificate stuff
        return 'https://siiva-gunner.com/api/v2/file/' + url.split('?id=')[1]
    
    if url.find('drive.google.com') != -1:
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
            raise QoCException("Drive ID cannot be detected from URL: {}".format(url))
        else:
            # let's hope google doesn't randomly decide to change how downloading works in the future...
            return "https://drive.usercontent.google.com/download?id={}&export=download&confirm=t".format(id)
    
    if url.find('dropbox.com') != -1:
        return url.replace('&dl=0', '&dl=1')

    if url.find('catgirlsare.sexy') != -1:
        return url.replace('catgirlsare.sexy', 'cgas.io')

    return url

# https://stackoverflow.com/questions/38511444/python-download-files-from-google-drive-using-url
def save_response_content(response, destination):
    CHUNK_SIZE = 32768

    with open(destination, "wb") as f:
        for chunk in response.iter_content(CHUNK_SIZE):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)


def getHeadFromUrl(validUrl: str):
    try:
        session = requests.Session()
        response = session.head(validUrl, stream=True)

        return response.headers
    
    # https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
    except requests.exceptions.Timeout:
        raise QoCException('Request timed out.')
    except requests.exceptions.TooManyRedirects:
        raise QoCException('Bad URL.')
    except requests.exceptions.RequestException as e: # Other errors
        raise QoCException('Unknown URL error. {}'.format(e.strerror))


def downloadAudioFromUrl(validUrl: str) -> str:
    filepath = None

    try:
        session = requests.Session()
        response = session.get(validUrl, stream=True)

        try:
            # apparently cgi is deprecated? may need to change to email.message
            # https://stackoverflow.com/questions/32330152/how-can-i-parse-the-value-of-content-type-from-an-http-header-response
            _, params = cgi.parse_header(response.headers['Content-Disposition'])
            filename = params['filename']
        except KeyError:
            if not ('audio' in response.headers['Content-Type'] or 'video' in response.headers['Content-Type']):
                if 'html' in response.headers['Content-Type']:
                    text = response.text
                    title = re.search('<\W*title\W*(.*)</title', text, re.IGNORECASE).group(1)
                    raise QoCException('Filename cannot be parsed from the URL (server response: {}).'.format(title))
                else:
                    raise QoCException('Unknown error trying to parse filename.')
            filename = validUrl.split('/')[-1]
        
        filepath = DOWNLOAD_DIR / filename

        save_response_content(response, filepath)
    
    # https://stackoverflow.com/questions/16511337/correct-way-to-try-except-using-python-requests-module
    except requests.exceptions.Timeout:
        raise QoCException('Request timed out.')
    except requests.exceptions.TooManyRedirects:
        raise QoCException('Bad URL.')
    except requests.exceptions.RequestException as e: # Other errors
        raise QoCException('Unknown URL error. {}'.format(e.strerror))

    DEBUG('Downloaded filepath: {}'.format(filepath))
    return filepath


def parseAudio(filepath: str) -> FileType:
    return File(filepath)


#=======================================#
#           BITRATE CHECKING            #
#=======================================#

def checkBitrateFromFile(file: FileType) -> Tuple[bool, str]:
    """
    Check the bitrate of a mutagen File.
    Requires either lossless format or the metadata contains bitrate information.
    If not, raises QoCException with the file metadata.
    """
    if isinstance(file, wave.WAVE) or isinstance(file, flac.FLAC):
        return (True, "Lossless file is OK.")
    
    # seems video files show lower bitrate on properties view for some reason, shouldn't be an issue generally
    if hasattr(file.info, 'bitrate'):
        bitrate = file.info.bitrate
        if bitrate < 300000:    # Apparently some weird files can have bitrate at 317kbps or even 319.999kbps. Let's say 300k is good enough
            return (False, "The {} file's bitrate is {}kbps. Please re-render at 320kbps.".format(type(file).__name__, bitrate // 1000))
        else:
            return (True, "Bitrate is OK.")
    
    raise QoCException("ERROR: Unknown bitrate. File metadata: {}".format(file.pprint()))


def checkBitrateFromUrl(validUrl: str) -> Tuple[bool, str]:
    """
    Check the bitrate of an URL by first finding the type of media
    If media is wav or flac, no need to do anything further.
    Otherwise, use ffprobe to download and check bitrate.
    """
    contentType = getHeadFromUrl(validUrl)['Content-Type'].lower()
    if 'wav' in contentType or 'flac' in contentType:
        return (True, "Lossless file is OK.")
    
    try:
        probeOutput = ffprobeUrl(validUrl)
        bitrate = int(probeOutput['streams'][0]['bit_rate'])
    except KeyError:
        # seems FLAC does not contain this info but it should have been skipped anyway
        raise QoCException("ERROR: Bitrate cannot be detected from ffprobe output:\n{}".format(probeOutput))
    except ValueError:
        raise QoCException("ERROR: Bitrate cannot be parsed from ffprobe output:\n{}".format(probeOutput))

    try:
        filetype = probeOutput['format']['format_name'].upper()
    except KeyError:
        filetype = "[TYPE UNKNOWN]"

    if bitrate < 300000:    # Apparently some weird files can have bitrate at 317kbps or even 319.999kbps. Let's say 300k is good enough
        return (False, "The {} file's bitrate is {}kbps. Please re-render at 320kbps.".format(filetype, bitrate // 1000))
    else:
        return (True, "Bitrate is OK.")


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
    

def checkClipping(wav_filepath: Path, threshold: int, doGradientAnalysis: bool) -> Tuple[bool, str]:
    """
    Checks whether a WAV file is clipping (waveform contains "flat" peaks).
    - **wav_filepath**: Path to a local WAV file.
    - **threshold**: How many consecutive samples to look for. Recommended value: 3.
    - **doGradientAnalysis**: Set to True if the waveform may contain overflows.
    """
    wavFile = parseAudio(wav_filepath)

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
            return (False, "Detected large gradient. Please verify clipping in Audacity.")
        else:
            return (True, "The rip is not clipping.")

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
        
        return (False, msg)
    else:
        return (True, "The rip is not clipping.")


def checkClippingFromFile(file: FileType, filepath: str, threshold: int = DEFAULT_CLIPPING_THRESHOLD) -> Tuple[bool, str]:
    """
    Checks whether a mutagen File is clipping.
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

    # do gradient analysis if file is 24-bit FLAC
    if isinstance(file, flac.FLAC) and file.info.bits_per_sample == 24:
        DEBUG("Input file is detected as 24-bit FLAC. Recommend verifing clipping in Audacity.")
        check, msg = checkClipping(wav_filepath, threshold, True)
    else:
        check, msg = checkClipping(wav_filepath, threshold, False)

    if newfile:
        os.remove(wav_filepath)

    return (check, msg)


def checkClippingFromUrl(validUrl: str, threshold: int = DEFAULT_CLIPPING_THRESHOLD) -> Tuple[bool, str]:
    """
    Checks whether a URL media is clipping.
    Will only download locally if the URL contains WAV; otherwise convert to local WAV file directly.
    """
    contentType = getHeadFromUrl(validUrl)['Content-Type'].lower()
    wav_filepath = DOWNLOAD_DIR / 'temp.wav'
    if 'wav' in contentType:
        wav_filepath = downloadAudioFromUrl(validUrl)
    else:
        ffmpegToWAV(validUrl, wav_filepath)
        
    # do gradient analysis if file is 24-bit FLAC
    is24bitFLAC = False
    try:
        probeOutput = ffprobeUrl(validUrl)
        is24bitFLAC = ('flac' in probeOutput['format']['format_name']) and (int(probeOutput['streams'][0]['bits_per_raw_sample']) == 24)
    except (KeyError, ValueError):
        pass

    if is24bitFLAC:
        DEBUG("Input file is detected as 24-bit FLAC. Recommend verifing clipping in Audacity.")
        check, msg = checkClipping(wav_filepath, threshold, True)
    else:
        check, msg = checkClipping(wav_filepath, threshold, False)

    os.remove(wav_filepath)

    return (check, msg)


#=======================================#
#         DLS CLIPPING CHECKING          #
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
    - **wav_filepath**: Path to a local WAV file.
    - **threshold**: How many consecutive samples to look for. Recommended value: 5.
    """
    wavFile = parseAudio(wav_filepath)

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

def checkDLSClippingFromUrl(validUrl: str, threshold: int = DEFAULT_DS_CLIPPING_THRESHOLD) -> Tuple[bool, str]:
    """
    Checks whether a URL media has DLS clipping.
    Will only download locally if the URL contains WAV; otherwise convert to local WAV file directly.
    """
    contentType = getHeadFromUrl(validUrl)['Content-Type'].lower()
    wav_filepath = DOWNLOAD_DIR / 'temp.wav'
    if 'wav' in contentType:
        wav_filepath = downloadAudioFromUrl(validUrl)
    else:
        ffmpegToWAV(validUrl, wav_filepath)

    check, msg = checkDLSClipping(wav_filepath, threshold)

    os.remove(wav_filepath)

    return (check, msg)


#=======================================#
#                Utility                #
#=======================================#
"""
Utility functions to parse the message returned by QoC functions
"""
def msgContainsBitrateFix(msg: str) -> bool:
    return msg.find("Please re-render at 320kbps") != -1

def msgContainsClippingFix(msg: str) -> bool:
    return (msg.find("The rip is clipping") != -1) or (msg.find("The rip is heavily clipping") != -1)

def msgContainsPRVRClippingFix(msg: str) -> bool:
    return msg.find("Post-render volume reduction detected") != -1

#=======================================#
#            Main Function              #
#=======================================#

def performQoC(url: str) -> Tuple[int, str]:
    """
    Version 1: Download file from URL then process metadata and waveform
    """
    try:
        downloadableUrl = parseUrl(url)
    except QoCException as e:
        return (-1, e.message)
    
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)
    
    filepath = None
    errors = []

    try:
        filepath = downloadAudioFromUrl(downloadableUrl)
        DEBUG("Downloaded audio: " + Path(filepath).name)
    
    except QoCException as e:
        errors.append(e.message)
    
    else:
        file = parseAudio(filepath)
        DEBUG("File metadata: " + file.pprint())

        try:
            bitrateCheck, bitrateMsg = checkBitrateFromFile(file)
        except QoCException as e:
            errors.append(e.message)

        try:
            clippingCheck, clippingMsg = checkClippingFromFile(file, filepath)
        except QoCException as e:
            errors.append(e.message)
    
    finally:
        if filepath:
            os.remove(filepath)

    if len(errors) > 0:
        return (-1, '\n'.join(errors))
    
    return (0 if (bitrateCheck and clippingCheck) else 1, '- {}\n- {}'.format(bitrateMsg, clippingMsg))

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


#=======================================#
#           Script Testing              #
#=======================================#
import sys

if __name__ == '__main__':
    if '-d' in sys.argv:
        print('DEBUG MODE ENABLED')
        DEBUG_MODE = True
    
    url = input('Paste the path of the audio you want to check: ')
    code, msg = performQoC(url)

    code2emoji = {
        -1: ":link:",
        0: ":check:",
        1: ":fix:",
    }
    
    print(code2emoji[code] 
          + (" :1234:" if msgContainsBitrateFix(msg) else "") 
          + (" :loud_sound:" if msgContainsClippingFix(msg) else "")
    )
    print(msg)
