import os
from pathlib import Path
from inspect import getsourcefile
from typing import Tuple
import requests
import cgi

from mutagen import File, FileType, flac, wave
from scipy.io import wavfile
import subprocess
import numpy as np

DOWNLOAD_DIR = Path(os.path.abspath(getsourcefile(lambda:0))).parent / 'audioDownloads'

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
    
    if url.find('185.142.239.147/?id=') != -1:
        # probably don't wanna deal with SSL certificate stuff
        return url.replace('185.142.239.147/?id=', 'siiva-gunner.com/api/v2/file/')
    
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

    return url

# https://stackoverflow.com/questions/38511444/python-download-files-from-google-drive-using-url
def save_response_content(response, destination):
    CHUNK_SIZE = 32768

    with open(destination, "wb") as f:
        for chunk in response.iter_content(CHUNK_SIZE):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)


def downloadAudioFromUrl(url: str) -> str:
    url = parseUrl(url)
    filepath = None

    try:
        session = requests.Session()
        response = session.get(url, stream=True)

        try:
            # apparently cgi is deprecated? may need to change to email.message
            # https://stackoverflow.com/questions/32330152/how-can-i-parse-the-value-of-content-type-from-an-http-header-response
            _, params = cgi.parse_header(response.headers['Content-Disposition'])
            filename = params['filename']
        except KeyError:
            if not ('audio' in response.headers['Content-Type'] or 'video' in response.headers['Content-Type']):
                raise QoCException('Filename cannot be parsed from the URL (it may be an invalid link).')
            filename = url.split('/')[-1]
        
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

def checkBitrate(file: FileType) -> Tuple[bool, str]:
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


#=======================================#
#           CLIPPING CHECKING           #
#=======================================#

def convertToWAV(filepath: str, wav_filepath: str):
    """
    Runs ffmpeg to create a WAV file from the provided audio filepath
    """
    try:
        subprocess.call([
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', Path(filepath),
            '-c:a', 'pcm_f32le',
            wav_filepath,
        ], shell=True)
    except FileNotFoundError:
        raise QoCException("ERROR: ffmpeg failed to run (make sure the command 'ffmpeg' can run).")
    
    if not os.path.exists(wav_filepath):
        raise QoCException("ERROR: ffmpeg failed to generate .wav file.")


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
    

def checkClipping(file: FileType, filepath: str, threshold: int = 3) -> Tuple[bool, str]:
    wav_filepath = Path(filepath)
    newfile = False
    if not isinstance(file, wave.WAVE):
        newfile = True
        wav_filepath = "{}_temp.wav".format(Path.joinpath(wav_filepath.parent, wav_filepath.stem))
    else:
        DEBUG('Bits per sample: {}'.format(file.info.bits_per_sample))
        
    if not os.path.exists(wav_filepath):
        convertToWAV(filepath, wav_filepath)
    
    DEBUG('Wav file: {}'.format(wav_filepath))
    wavFile: wave.WAVE = parseAudio(wav_filepath)
    DEBUG('Metadata: {}'.format(wavFile.pprint()))

    clips = []
    framerate, data = wavfile.read(wav_filepath)

    # Special case: 24-bit FLACs can go over sample limit and cause overflow/underflow,
    # apply specialized algorithm to check for clicking instead.
    # TODO: what about other bit depths?
    if isinstance(file, flac.FLAC) and file.info.bits_per_sample == 24:
        DEBUG("Input file is detected as 24-bit FLAC. Recommend verifing clipping in Audacity.")
        data_deriv = np.gradient(data, axis=0)
        maxG = np.max(data_deriv)
        minG = np.min(data_deriv)
        DEBUG('G: Max: {}, Min: {}'.format(maxG, minG))

        # TODO: fine tune arbitrarily chosen threshold
        # it may be possible to use 'and' since overflow/underflow will create large gradient both ways
        if maxG > 0.8 or minG < -0.8:
            return (False, "Detected large gradient in 24-bit FLAC file. Please verify clipping in Audacity.")
        else:
            return (True, "The rip is not clipping.")

    # +1 to min in order to mimic Audacity's Find Clipping algorithm,
    # even though WAV samples can technically go lower
    # TODO: 8bit not tested yet
    limits = {
        8:  ( 0         +1,     255         ),
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

    if newfile and not isinstance(file, wave.WAVE):
        os.remove(wav_filepath)
    
    if len(clips) > 0:
        msg = ""

        # Detect if volume was reduced post-render
        if newfile or data.dtype == np.float32:
            formatMax = 1.0
            formatMin = -1.0
        else:
            formatMax = limits[file.info.bits_per_sample][1]
            formatMin = limits[file.info.bits_per_sample][0]

        if np.any(np.logical_and(upperClip, maxVals < formatMax)) or np.any(np.logical_and(lowerClip, minVals > formatMin)):
            msg = " Post-render volume reduction detected, please lower the volume before rendering."
        
        if len(clips) > 10:
            msg = "The rip is heavily clipping." + msg
        else:
            msg = "The rip is clipping at: " + ", ".join(clips) + "." + msg
        
        return (False, msg)
    else:
        return (True, "The rip is not clipping.")


#=======================================#
#            Main Function              #
#=======================================#

def simpleQoC(url: str) -> Tuple[bool, str]:
    if not os.path.exists(DOWNLOAD_DIR):
        os.mkdir(DOWNLOAD_DIR)
    
    filepath = None
    errors = []

    try:
        filepath = downloadAudioFromUrl(url)
        DEBUG("Downloaded audio: " + Path(filepath).name)
    
    except QoCException as e:
        errors.append(e.message)
    
    else:
        file = parseAudio(filepath)
        DEBUG("File metadata: " + file.pprint())

        try:
            bitrateCheck, bitrateMsg = checkBitrate(file)
        except QoCException as e:
            errors.append(e.message)

        try:
            clippingCheck, clippingMsg = checkClipping(file, filepath)
        except QoCException as e:
            errors.append(e.message)
    
    finally:
        if filepath:
            os.remove(filepath)

    if len(errors) > 0:
        raise QoCException('\n'.join(errors))
    
    return (bitrateCheck and clippingCheck, '- {}\n- {}'.format(bitrateMsg, clippingMsg))


#=======================================#
#           Script Testing              #
#=======================================#
import sys

if __name__ == '__main__':
    if '-d' in sys.argv:
        print('DEBUG MODE ENABLED')
        DEBUG_MODE = True
    
    url = input('Paste the path of the audio you want to check: ')
    check, msg = simpleQoC(url)
    
    print(":check:" if check else ":fix:")
    print(msg)
