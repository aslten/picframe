import os
import requests
import configparser
import logging
import datetime
import pickle
import threading
import time

from requests.packages.urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress only the InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

config_folder = 'config'
config_file = 'config.ini'

# Constants
API_INFO = "SYNO.API.Info"
AUTH_API = "SYNO.API.Auth"
PHOTO_API = "SYNO.Foto.Browse.Album"
PHOTO_BROWSE_ALBUM_API = 'SYNO.Foto.Browse.Item'
PHOTOTEAM_BROWSE_ALBUM_API = 'SYNO.FotoTeam.Browse.Item'
PHOTO_BROWSE_FOLDER_API = "SYNO.Foto.Browse.Folder"
PHOTO_BROWSE_TEAM_FOLDER_API = "SYNO.FotoTeam.Browse.Folder"

TEAM = True
USER = False

DEFAULT_FOLDER_FILE = "~/picframe_data/config/folder.pkl"
DEFAULT_FILEINFO_FILE= "~/picframe_data/config/fileinfo.pkl"
FOLDER_INFO = True
FILE_INFO = False
DEFAULT_CONFIGFILE = "~/picframe_data/config/config.ini"

class SynologyAccess():
    def __init__(self):
        self.__logger = logging.getLogger("synology_photo_access.SynologyAccess")
        self.__logger.debug('Creating an instance of SynologyAccess')
        self.config_file_path = os.path.expanduser(DEFAULT_CONFIGFILE)
        # Get login details from 'config.ini'
        parser = configparser.ConfigParser()
        if os.path.exists(self.config_file_path):
            candidates = self.config_file_path
            found = parser.read(candidates)
            self.url = parser.get('nas', 'url')
            self.username = parser.get('nas', 'username')
            self.password = parser.get('nas', 'password')
        else:
            quit()

        self.sid = None

        self.albumsInformation = {}
        self.folderDict = self.load_dict_from_file(FOLDER_INFO)
        self.fileInfoDict = self.load_dict_from_file(FILE_INFO)

        self.mineId = 0

        self.login()

        """ Start the periodic task of folder scanning
        
        :param interval: Time interval in seconds for the periodic task.
        """
        self.interval = 3600
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_periodic_task, daemon=True)
        self._thread.start()


    def load_dict_from_file(self, fileType):
        """
        Load a dictionary from a Pickle file, handling the case where the file does not exist.
        
        :param file_path: Path to the file
        :param default: Default value to return if the file does not exist. Defaults to an empty dictionary.
        :return: Dictionary loaded from the file, or the default value if the file does not exist.
        """
        if fileType == FOLDER_INFO:
            filePath = DEFAULT_FOLDER_FILE
        else:
            filePath = DEFAULT_FILEINFO_FILE
            
        folderfile = os.path.expanduser(filePath)
        
        if not os.path.exists(folderfile):
            self.__logger.warning(f"Folder file {folderfile} not found. Returning empty dictionary.")
            return {}

        with open(folderfile, 'rb') as file:
            return pickle.load(file)

    def save_folderdict_to_file(self, fileType):
        """
        Save a dictionary to a file in Pickle format. Overwrites existing content.
        
        :param dictionary: Dictionary to save
        :param file_path: Path to the file
        """

        if fileType == FOLDER_INFO:
            filePath = DEFAULT_FOLDER_FILE
        else:
            filePath = DEFAULT_FILEINFO_FILE

        folderfile = os.path.expanduser(filePath)
        
        with open(folderfile, 'wb') as file:
            if fileType == FOLDER_INFO:
                pickle.dump(self.folderDict, file)
            else:
                pickle.dump(self.fileInfoDict, file)

    def _run_periodic_task(self):
        """
        Internal method to run the periodic task.
        This method executes the task at the specified interval until stopped.
        """

    
        while not self._stop_event.is_set():
            self.__logger.debug('Started update of folders')
            self.updateFolderDictionary()
            self.__logger.debug('Completed folder update')
            for _ in range(self.interval):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
        self.__shutdown_completed = True

    def stop(self):
        """
        Stop the periodic task and wait for the thread to terminate.
        """
        self.__shutdown_completed = False
        self._stop_event.set()
        while not self.__shutdown_completed:
            time.sleep(0.05)  # make function blocking to ensure staged shutdown
        self.logout()


    def login(self):
        self.session = requests.Session()
        api_info = self.get_api_info()
        self.auth_url = f"{self.url}/webapi/{api_info[AUTH_API]['path']}"
        params = {
            "api": AUTH_API,
            "version": "6",
            "method": "login",
            "account": self.username,
            "passwd": self.password,
            "session": "SynoFoto",
            "format": "sid"
        }
        #if otp_code:
         #   params["otp_code"] = otp_code

        response = self.session.get(self.auth_url, params=params, verify=False)

        response.raise_for_status()
        data = response.json()

        if not data["success"]:
            self.__logger.error("Login failed")
        self.sid = data["data"]["sid"]

        self.__logger.debug("Login successful")

        self.user_info()

    def get_api_info(self):
        url = f"{self.url}/webapi/entry.cgi"
        params = {
            "api": API_INFO,
            "version": "1",
            "method": "query",
            #"query": "SYNO.API.Auth"
            "query": "all"
        }
        headers = {
            "Accept": "application/json"
        }
        response = self.session.get(url,headers=headers, params=params,  verify=False)

        try:
            response.raise_for_status()
        except Exception as err:
             self.__logger.error(f"Other error occurred: {err}")  
        return response.json()["data"]
        
    def logout(self):
        if self.sid == None:
            self.__logger.debug("No active session.")
            return

        params = {
            "api": AUTH_API,
            "version": "6",
            "method": "logout",
            "session": "SynoPhotos"
        }
        response = self.session.get(self.auth_url, params=params, verify=False)
        response.raise_for_status()
        self.sid = None
 
        self.__logger.debug("Logged out successfully")

    def user_info(self):
        if self.sid == None:
            self.__logger.error("No active session. Please login first.")
        session = requests.Session()
        session.cookies.set("id", self.sid)
        api_info = self.get_api_info()
        PHOTO_USER = "SYNO.Foto.UserInfo"
        photo_url = f"{self.url}/webapi/{api_info[PHOTO_USER]['path']}"

        params = {
            "api": PHOTO_USER,
            "version": "1",
            "method": "me"
        }
        response = session.get(photo_url, params=params, verify=False)
        #print(response.url)
        response.raise_for_status()
        data = response.json()
        if not data["success"]:
            self.__logger.error("Failed to get user information")
        else:
            if 'id' in data['data']:
                self.mineId  = data['data']['id']

    def list_all_albums(self):
        if self.sid == None:
            self.__logger.error("No active session. Please login first.")
        session = requests.Session()
        session.cookies.set("id", self.sid)
        api_info = self.get_api_info()
        photo_url = f"{self.url}/webapi/{api_info[PHOTO_API]['path']}"
        params = {
            "api": PHOTO_API,
            "version": "4",
            "category": "normal_share_with_me",
            "method": "list",
            "offset": "0",
            "limit": "1000"
        }
        response = session.get(photo_url, params=params, verify=False)
        #print(response.url)
        response.raise_for_status()
        data = response.json()
        #print(data)
        self.__logger.debug(data)
        theAlbums = {}
        if not data["success"]:
            self.__logger.error("Failed to list album contents")
        elif len(data['data']['list']) != 0:
            for album in data['data']['list']:
                theAlbums[album['name']] = {}
                theAlbums[album['name']]['id'] = album['id']
                theAlbums[album['name']]['passphrase'] = album['passphrase']
                theAlbums[album['name']]['owner_user_id'] = album['owner_user_id']
                theAlbums[album['name']]['version'] = album['version']
                
        self.albumsInformation = theAlbums
        self.__logger.debug('The album list')
        self.__logger.debug(theAlbums)
        #print(self.albumsInformation)
        return

    def get_album(self, album_name, forceUpdate = False):

        if self.albumsInformation == {}:
            self.list_all_albums()

        if album_name in self.fileInfoDict and not forceUpdate:
            self.__logger.info(self.albumsInformation)
            if album_name in self.albumsInformation:
                if self.fileInfoDict[album_name]['version'] == self.albumsInformation[album_name]['version']:
                    # File information is up to date
                    self.listFileIndexes = self.fileInfoDict[album_name]['fileIds']
                    self.file_list = self.fileInfoDict[album_name]['fileInfo']
                    self.__logger.info('Album file list exists in saved file.')
                    return
       
        # We need to fetch the file information
        if self.sid == None:
            self.__logger.error("No active session. Please login first.")

        self.file_list = {}
        self.listFileIndexes = []
        
        if album_name in self.albumsInformation:
            session = requests.Session()
            session.cookies.set("id", self.sid)
            api_info = self.get_api_info()
            photo_url = f"{self.url}/webapi/{api_info[PHOTO_BROWSE_ALBUM_API]['path']}"

            params = {
                "api": PHOTO_BROWSE_ALBUM_API,
                "method": "list",
                "version": "4",
                "offset": "0",
                "limit": "1000",
                "id": 1,
                "passphrase": self.albumsInformation[album_name]['passphrase'],
                'additional': '["description","tag","exif","resolution","orientation","gps","video_meta","video_convert","thumbnail","address","geocoding_id","rating","motion_photo","provider_user_id","person"]'

            }
            response = session.get(photo_url, params=params, verify=False)
            self.__logger.debug(response.text)
            self.__logger.debug(response.url)
            response.raise_for_status()
            data = response.json()
            
            if not data["success"]:
                self.__logger.error("Failed to get album content")
            elif len(data['data']['list']) != 0:
                counter = 0
                counter100 = 0
                for file in data['data']['list']:
                    counter = counter+1
                    if counter == 100:
                        counter = 0
                        counter100 = counter100 +1
                        self.__logger.info('Number of processed files in hundreds: '+ str(counter100))
                        
                    if file['folder_id'] in self.folderDict:
                        theId = str(file['id'])
                        self.file_list[theId] = {}
                        if self.folderDict[file['folder_id']]['name'] == '/':
                            self.file_list[theId]['fname'] = '/' + file['filename']
                        else:
                            self.file_list[theId]['fname'] = self.folderDict[file['folder_id']]['name'] + '/' + file['filename']
                        if self.folderDict[file['folder_id']]['team'] == True:
                            self.file_list[theId]['fname'] = 'shared' + self.file_list[theId]['fname']
                        else:
                            self.file_list[theId]['fname'] = 'mine' + self.file_list[theId]['fname']
                                           
                        if 'time' in file:
                            self.file_list[theId]['exif_datetime'] = file['time']
                            self.file_list[theId]['last_modified'] = file['time']
                        else:
                            self.file_list[theId]['exif_datetime'] = datetime.datetime.now()
                            self.file_list[theId]['last_modified'] = datetime.datetime.now()

                        if 'orientation' in file['additional']:
                            self.file_list[theId]['orientation'] = file['additional']['orientation']
                        if 'address' in file['additional']:
                            if 'city' in file['additional']['address']:
                                self.file_list[theId]['location'] = file['additional']['address']['city']
                            elif 'town' in file['additional']['address']:
                                self.file_list[theId]['location'] = file['additional']['address']['town']
                            elif 'village ' in file['additional']['address']:
                                self.file_list[theId]['location'] = file['additional']['address']['village']
                            if 'country' in file['additional']['address']:
                                self.file_list[theId]['location'] = self.file_list[theId]['location'] + ',' + file['additional']['address']['country']

                        self.file_list[theId]['caption'] = self.folderDict[file['folder_id']]['name']
                        self.file_list[theId]['file_id'] = theId

                 
                        self.listFileIndexes.append(theId)
            tempAlbumInfo = {}
            tempAlbumInfo['version'] = self.albumsInformation[album_name]['version']
            tempAlbumInfo['fileIds'] = self.listFileIndexes 
            tempAlbumInfo['fileInfo'] = self.file_list
            self.fileInfoDict[album_name] = tempAlbumInfo
            self.save_folderdict_to_file(DEFAULT_FILEINFO_FILE)
            
        else:
            self.__logger.info('Album does not exist: ', album_name)
    

        self.__logger.debug('File list')
        self.__logger.debug(self.file_list)
        self.__logger.debug('File indexes')
        self.__logger.debug(self.listFileIndexes)


    def getFilePathFromFileList(self, fileIndex):
        if fileIndex in self.listFileIndexes:
            return self.file_list[fileIndex]['fname']
        else:
            self.__logger.debug('File index not in file index list')
            
        

#PHOTO_BROWSE_ALBUM_API

    def updateFolderDictionary(self):
        #self.folderDict = {}
        self.build_folder_dictionary(False)
        if self._stop_event.is_set():
            return
        self.build_folder_dictionary(True)
        if self._stop_event.is_set():
            return
        self.save_folderdict_to_file(FOLDER_INFO)

    def get_root_folder(self, team=False):
        if team == True:
            theAPI = PHOTO_BROWSE_TEAM_FOLDER_API
        else:
            theAPI = PHOTO_BROWSE_FOLDER_API
        if self.sid == None:
            self.__logger.error("No active session. Please login first.")
        session = requests.Session()
        session.cookies.set("id", self.sid)
        api_info = self.get_api_info()
        photo_url = f"{self.url}/webapi/{api_info[theAPI]['path']}"
        params = {
            "api": theAPI,
            "version": "2",
            "method": "get",
            "offset": 0,
            "limit": 1000
        }
        response = session.get(photo_url, params=params, verify=False)
        response.raise_for_status()
        data = response.json()

        rootFolder = {}
        if not data["success"]:
            self.__logger.error("Failed to list album contents")
        elif data['data']['folder'] != {}:
            theId = data['data']['folder']['id']
            rootFolder[theId] = {}
            rootFolder[theId]['name'] = data['data']['folder']['name']
            rootFolder[theId]['passphrase'] = data['data']['folder']['passphrase']
            rootFolder[theId]['team'] = team

        return rootFolder


    def build_folder_dictionary(self, team=False):
        self.folderDict.update(self.get_root_folder(team))

        # Get folders in parent folder
        folders = self.get_folders(None, team)
        self.folderDict.update(folders)
        self.walk_the_folders(folders, team)

    def walk_the_folders(self, theDict, team):
        if not theDict:
            return


        for key, value in theDict.items():
            if self._stop_event.is_set():
                break
            if isinstance(value, dict):  # Check if the value is a dictionary
                theFolders = self.get_folders(key, team)
                self.folderDict.update(theFolders)
                self.walk_the_folders(theFolders, team)  # Recursive call

    def get_folders(self, parent=None, team=False):
        if team == True:
            theAPI = PHOTO_BROWSE_TEAM_FOLDER_API
        else:
            theAPI = PHOTO_BROWSE_FOLDER_API
        if self.sid == None:
            self.__logger.error("No active session. Please login first.")
        session = requests.Session()
        session.cookies.set("id", self.sid)
        api_info = self.get_api_info()
        photo_url = f"{self.url}/webapi/{api_info[theAPI]['path']}"
        params = {
            "api": theAPI,
            "version": "2",
            "method": "list",
            "offset": 0,
            "limit": 1000
        }
        if parent != None:
            params["id"] = parent
    
        response = session.get(photo_url, params=params, verify=False)
        response.raise_for_status()
        data = response.json()

        theFolders = {}
        if not data["success"]:
            self.__logger.error("Failed to list team folders")
        elif len(data['data']['list']) != 0:
            for folder in data['data']['list']:
                 theFolders[folder['id']] = {}
                 theFolders[folder['id']]['name'] = folder['name']
                 theFolders[folder['id']]['passphrase'] = folder['passphrase']
                 theFolders[folder['id']]['team'] = team

        return theFolders
    

    def create_album_list(self):
        self.list_all_albums()
        #self.updateFolderDictionary()
        
        #print('Albums')
        #print(self.albumsInformation)

    def get_album_list(self, team=False):
        albumList = []
        for album in self.albumsInformation.keys():
            if team == True:
                if self.albumsInformation[album]['owner_user_id'] != self.mineId:
                    albumList.append(album)
            else:
                if self.albumsInformation[album]['owner_user_id'] == self.mineId:
                    albumList.append(album)
        return albumList

    def get_file_list(self, album):
        #print('The album')
        #print(album)
        self.get_album(album)
        #print('List indexes')
        #print(self.listFileIndexes)
        return self.listFileIndexes

    def get_file_info(self, theId):
        if theId in self.listFileIndexes:
            #print('File info')
            #print(theId)
            #print(self.file_list[theId])
            return self.file_list[theId]
        else:
            self.__logger.debug('File id is not present in index list', theId)
            return {}

if __name__ == "__main__":
    t = SynologyAccess()
    t.create_album_list()
    u=t.get_file_list('Marseillan okt 2022')
    print(u)
    #t.get_user_root_folder(True)
    #t.get_folder()
    #t.get_team_folder("1")
    #t.build_team_folder_dictionary()
    
    #t.build_folder_dictionary(True)
    print(t.get_album_list(True))
    for id in u:
        print(t.getFilePathFromFileList(id))
    time.sleep(5)
    t.stop()
