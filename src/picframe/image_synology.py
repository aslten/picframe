import sqlite3
import os
import time
import logging
import threading

import sys
from pathlib import Path
## Add the root directory to sys.path
#sys.path.append(str(Path(__file__).resolve().parent.parent))

from picframe import get_image_meta, synology_photo_access


class ImageSynology:

    EXTENSIONS = ['.png', '.jpg', '.jpeg', '.heif', '.heic']
    EXIF_TO_FIELD = {'EXIF FNumber': 'f_number',
                     'Image Make': 'make',
                     'Image Model': 'model',
                     'EXIF ExposureTime': 'exposure_time',
                     'EXIF ISOSpeedRatings': 'iso',
                     'EXIF FocalLength': 'focal_length',
                     'EXIF Rating': 'rating',
                     'EXIF LensModel': 'lens',
                     'EXIF DateTimeOriginal': 'exif_datetime',
                     'IPTC Keywords': 'tags',
                     'IPTC Caption/Abstract': 'caption',
                     'IPTC Object Name': 'title'}

    def __init__(self, update_interval):
        # TODO these class methods will crash if Model attempts to instantiate this using a
        # different version from the latest one - should this argument be taken out?
        self.__modified_folders = []
        self.__modified_files = []
        self.__cached_file_stats = []  # collection shared between threads
        self.__logger = logging.getLogger("image_synology.ImageSynology")
        self.__logger.debug('Creating an instance of ImageSynology')
        self.__albumName = 't'
        self.__update_interval = update_interval

        self.__keep_looping = True
        self.__pause_looping = False
        self.__shutdown_completed = False

        self.__synology_photo = synology_photo_access.SynologyAccess()

        t = threading.Thread(target=self.__loop)
        t.start()

    def __loop(self):
        while self.__keep_looping:
            if not self.__pause_looping and self.__albumName != '':
                self.create_album_list()
                for _ in range(self.__update_interval):
                    if self.__keep_looping == False:
                        break
                    time.sleep(1)
            time.sleep(0.01)
        self.__shutdown_completed = True

    def pause_looping(self, value):
        self.__pause_looping = value

    def stop(self):
        self.__synology_photo.stop()
        self.__keep_looping = False
        while not self.__shutdown_completed:
            time.sleep(0.05)  # make function blocking to ensure staged shutdown

    def set_albumName(self, albumName):
        self.__albumName = albumName
        
    def create_album_list(self):
        """Update the album list
        """
        self.__logger.debug('Updating album list')
        self.__synology_photo.create_album_list()
        
    def get_album_list(self, team=False):
        return self.__synology_photo.get_album_list(team)

    def get_file_list(self):
        return self.__synology_photo.get_file_list(self.__albumName)
        #try:
         #   return self.__synology_photo.get_file_list(self.__albumName)
        #except Exception:
         #   print('Exception when getting file list')
         #   return []

    def get_file_info(self, fileIndex):
        try:
            fileInfo = self.__synology_photo.get_file_info(fileIndex)
        except Exception:
            self.__logger.error('Could not get file info')
            fileInfo = {}

        return fileInfo


# If being executed (instead of imported), kick it off...
if __name__ == "__main__":
    synoPhoto = ImageSynology('/', 30)
    #synoPhoto.create_album_list()
    time.sleep(10)
    #print(synoPhoto.file_list)

    synoPhoto.set_albumName('test')
    print(synoPhoto.get_file_list())
    #get_file_info
    synoPhoto.stop()
    #cache = ImageCache(picture_dir='/home/pi/Pictures', follow_links=False, db_file='/home/pi/db.db3', geo_reverse=None, update_interval=2)
