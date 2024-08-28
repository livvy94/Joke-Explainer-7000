import unittest
import os
from pathlib import Path
from inspect import getsourcefile
from mutagen import File

from simpleQoC import downloadAudioFromUrl, checkBitrate, checkClipping, QoCException

TEST_DIR = Path(os.path.abspath(getsourcefile(lambda:0))).parent / 'tests'

class TestDownload(unittest.TestCase):
    """
    Test suites for the downloadAudioFromUrl function
    """
    DOWNLOAD_DIR = Path(os.path.abspath(getsourcefile(lambda:0))).parent / 'audioDownloads'

    def __init__(self, *args, **kwargs):
        super(TestDownload, self).__init__(*args, **kwargs)
        if not os.path.exists(self.DOWNLOAD_DIR):
            os.mkdir(self.DOWNLOAD_DIR)

    # Successful downloads
    def testSuccessSiivaGunner(self):
        filepath = downloadAudioFromUrl("https://siiva-gunner.com/?id=vnrufKKnxu")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    def testSuccessSiivaGunnerV2(self):
        filepath = downloadAudioFromUrl("https://185.142.239.147/?id=vnrufKKnxu")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    def testSuccessDrive(self):
        filepath = downloadAudioFromUrl("https://drive.google.com/file/d/1ofQMUh1xtItM3a1VXATRovYL9nYVYets/view?usp=sharing")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    def testSuccessDriveV2(self):
        filepath = downloadAudioFromUrl("https://drive.google.com/file/d/1ofQMUh1xtItM3a1VXATRovYL9nYVYets")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    def testSuccessDriveV3(self):
        filepath = downloadAudioFromUrl("https://drive.google.com/open?id=1ofQMUh1xtItM3a1VXATRovYL9nYVYets")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    def testSuccessDriveV4(self):
        filepath = downloadAudioFromUrl("https://drive.google.com/uc?id=1ofQMUh1xtItM3a1VXATRovYL9nYVYets&export=download")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    def testSuccessDropbox(self):
        filepath = downloadAudioFromUrl("https://www.dropbox.com/scl/fi/stkgm8qtw6m9oq5dbeg76/goodQuality.mp3?rlkey=wxhi0wu55a4d4tsppe6buu5by&st=vi8io7zw&dl=0")
        self.assertEqual(filepath, self.DOWNLOAD_DIR / 'goodQuality.mp3')
        if filepath:
            os.remove(filepath)

    # TODO: Ask livvy for neocities sample
    # TODO: b.catgirlsare.sexy does not work for some reason
    # TODO: Try a large Google Drive link (should work)

    # Failed downloads
    def testFailureSiivaGunner(self):
        with self.assertRaises(QoCException):
            filepath = downloadAudioFromUrl("https://siiva-gunner.com/?id=vnrufKKnx")
            if filepath:
                os.remove(filepath)

    def testFailureDrive(self):
        with self.assertRaises(QoCException):
            filepath = downloadAudioFromUrl("https://drive.google.com/file/d/1ofQMUh1xtItM3a1VXATRovYL9nYVYet/view?usp=sharing")
            if filepath:
                os.remove(filepath)


class TestBitrate(unittest.TestCase):
    """
    Test suites for the checkBitrate function
    """
    # Helper strings and functions
    BITRATE_OK_MSG = "Bitrate is OK."
    BITRATE_LOSSLESS_MSG = "Lossless file is OK."

    def BITRATE_LOW_MSG(self, filetype, kbps): 
        return "The {} file's bitrate is {}kbps. Please re-render at 320kbps.".format(filetype, kbps)

    # Lossless
    def testBitrateFLAC(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.flac'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_LOSSLESS_MSG)

    def testBitrateWAV(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.wav'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_LOSSLESS_MSG)

    # Bitrate OK
    def testBitrateAIFF(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.aiff'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_OK_MSG)

    def testBitrateMP2(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.mp2'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_OK_MSG)

    def testBitrateMP3(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.mp3'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_OK_MSG)

    def testLowBitrateMP4(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.mp4'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_OK_MSG)

    def testBitrateOGG(self):
        check, msg = checkBitrate(File(TEST_DIR / 'goodQuality.ogg'))
        self.assertTrue(check)
        self.assertEqual(msg, self.BITRATE_OK_MSG)

    # Low bitrate
    def testLowBitrateMP3(self):
        check, msg = checkBitrate(File(TEST_DIR / 'lowBitrate.mp3'))
        self.assertFalse(check)
        self.assertEqual(msg, self.BITRATE_LOW_MSG('MP3', 128))
    
    def testLowBitrateMP4(self):
        check, msg = checkBitrate(File(TEST_DIR / 'clipping6lowBitrate.mp4'))
        self.assertFalse(check)
        self.assertEqual(msg, self.BITRATE_LOW_MSG('MP4', 192))
    
    def testLowBitrateM4A(self):
        check, msg = checkBitrate(File(TEST_DIR / 'lowBitrate.m4a'))
        self.assertFalse(check)
        self.assertEqual(msg, self.BITRATE_LOW_MSG('MP4', 127))

    def testLowBitrateOGG(self):
        check, msg = checkBitrate(File(TEST_DIR / 'lowBitrate.ogg'))
        self.assertFalse(check)
        self.assertEqual(msg, self.BITRATE_LOW_MSG('OggVorbis', 192))
    

class TestClipping(unittest.TestCase):
    """
    Test suites for the checkClipping function
    """
    # Helper strings and functions
    CLIPPING_OK_MSG = "The rip is not clipping."
    CLIPPING_HEAVY_MSG = "The rip is heavily clipping."
    CLIPPING_REDUCED_MSG = " Post-render volume reduction detected, please lower the volume before rendering."

    def CLIPPING_MSG(self, clips): 
        return "The rip is clipping at: " + ", ".join(clips) + "."
    
    def checkFilepathClipping(self, filepath):
        return checkClipping(File(filepath), filepath)
    
    def clip(self, t, n):
        return '{:.2f} sec ({} samples)'.format(t, n)

    # No clipping
    def testNoClippingMP3(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'goodQuality.mp3')
        self.assertTrue(check)
        self.assertEqual(msg, self.CLIPPING_OK_MSG)
    
    def testNoClippingFLAC(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'goodQuality.flac')
        self.assertTrue(check)
        self.assertEqual(msg, self.CLIPPING_OK_MSG)
    
    def testNoClippingWAV(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'goodQuality.wav')
        self.assertTrue(check)
        self.assertEqual(msg, self.CLIPPING_OK_MSG)

    def testNoClippingWAVMono(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'goodQualityMono.wav')
        self.assertTrue(check)
        self.assertEqual(msg, self.CLIPPING_OK_MSG)

    def testAlmostClippingMP3(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'almostClipping.mp3')
        self.assertTrue(check)
        self.assertEqual(msg, self.CLIPPING_OK_MSG)

    # Clipping
    def testClipping1(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping1.mp3')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_HEAVY_MSG)
    
    def testClipping2(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping2.mp3')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_MSG([
            self.clip(12.13, 4), 
            self.clip(13.01, 3),
        ]))
    
    def testClipping2inverted(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping2inverted.wav')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_MSG([
            self.clip(12.13, 3),
        ]))
    
    def testClipping3(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping3.wav')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_HEAVY_MSG + self.CLIPPING_REDUCED_MSG)

    def testClipping4(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping4.wav')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_HEAVY_MSG)

    def testClipping5(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping5.ogg')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_MSG([
            self.clip(6.23, 4),
            self.clip(7.18, 5),
            self.clip(7.97, 4), 
            self.clip(9.82, 3),
            self.clip(12.04, 5), 
            self.clip(13.01, 3),
        ]))

    def testClipping6(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping6lowBitrate.mp4')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_HEAVY_MSG)

    def testClipping24bitFLAC(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping24bit.flac')
        self.assertFalse(check)
        self.assertEqual(msg, "Detected large gradient in 24-bit FLAC file. Please verify clipping in Audacity.")

    def testClipping24bitWAV(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping24bit.wav')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_HEAVY_MSG)

    def testClipping32bitWAV(self):
        check, msg = self.checkFilepathClipping(TEST_DIR / 'clipping32bitfloat.wav')
        self.assertFalse(check)
        self.assertEqual(msg, self.CLIPPING_MSG([
            self.clip(12.99, 6),
            self.clip(12.99, 7),
            self.clip(13.00, 6), 
            self.clip(13.01, 8),
            self.clip(13.01, 4),
            self.clip(13.01, 4), 
            self.clip(13.02, 10),
        ]))

import simpleQoC
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1:
        print('DEBUG MODE ENABLED')
        simpleQoC.DEBUG_MODE = True
    
    unittest.main()