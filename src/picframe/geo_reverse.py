import json
import urllib.request
import locale
import logging
import time
import urllib.error

URL = "https://nominatim.openstreetmap.org/reverse?format=geojson&lat={}&lon={}&zoom={}&email={}&accept-language={}"


class GeoReverse:
    def __init__(self, geo_key, zoom=18, key_list=None):
        self.__logger = logging.getLogger("geo_reverse.GeoReverse")
        self.__geo_key = geo_key
        self.__zoom = zoom
        self.__key_list = key_list
        self.__geo_locations = {}
        self.__last_request = 0.0
        self.__geocoding_disabled = False
        self.__language = locale.getlocale()[0][:2]

    def get_address(self, lat, lon):
        if self.__geocoding_disabled:
            return ""

        now = time.monotonic()
        if now - self.__last_request < 60.0:
            return ""

        self.__last_request = now
        try:
            url = URL.format(lat, lon, self.__zoom, self.__geo_key, self.__language)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "aslten-picframe/1.0 (+https://github.com/aslten/picframe)"}
            )
            with urllib.request.urlopen(request, timeout=3.0) as req:
                data = json.loads(req.read().decode())
            adr = data['features'][0]['properties']['address']
            # some experimentation might be needed to get a good set of alternatives in key_list
            adr_list = []
            if self.__key_list is not None:
                for part in self.__key_list:
                    for option in part:
                        if option in adr:
                            adr_list.append(adr[option])
                            break  # add just the first one from the options
            else:
                adr_list = adr.values()
            return ", ".join(adr_list)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                self.__geocoding_disabled = True
                self.__logger.warning(
                    "GPS-uppslag avaktiverade efter HTTP %s", e.code
                )
            else:
                self.__logger.error("GPS-uppslag: HTTP %s", e.code)
            return ""
        except Exception as e:  # TODO return different thing for different exceptions
            self.__logger.error("lat=%f, lon=%f -> %s", lat, lon, e)
            return ""
