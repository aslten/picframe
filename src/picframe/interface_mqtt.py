"""MQTT interface of picframe."""

import logging
import json
import os
import paho.mqtt.client as mqtt
from picframe import __version__


class InterfaceMQTT:
    """MQTT interface of picframe.

    This interface interacts via mqtt with the user to steer the image display.

    Attributes
    ----------
    controller : Controler
        Controller for picframe

    Methods
    -------
    __init__(self, controller, mqtt_config)
        Initializes an instance of InterfaceMQTT.
    start(self)
        Starts the MQTT interface.
    stop(self)
        Stops the MQTT interface.
    on_connect(self, client, userdata, flags, rc)
        Callback function for MQTT connection.
    __get_dev_element(self)
        Returns the device element for MQTT configuration.
    __setup_sensor(self, client, topic, icon, available_topic, has_attributes=False, entity_category=None)
        Sets up a sensor for MQTT.
    __setup_text(self, client, topic, icon, available_topic, entity_category=None)
        Sets up a text entity for MQTT.
    __setup_number(self, client, topic, min, max, step, icon, available_topic)
        Sets up a number entity for MQTT.
    """

    def __init__(self, controller, mqtt_config):
        """
        Initializes an instance of InterfaceMQTT.

        Args:
            controller (Controller): The controller object.
            mqtt_config (dict): A dictionary containing MQTT configuration parameters.

        Raises:
            Exception: If MQTT setup fails.

        """
        self.__logger = logging.getLogger("interface_mqtt.InterfaceMQTT")
        self.__logger.info('creating an instance of InterfaceMQTT')
        self.__controller = controller
        try:
            device_id = mqtt_config['device_id']
            self.__client = mqtt.Client(client_id=device_id, clean_session=True)
            login = mqtt_config['login']
            password = mqtt_config['password']
            self.__client.username_pw_set(login, password)
            tls = mqtt_config['tls']
            if tls:
                self.__client.tls_set(tls)
            server = mqtt_config['server']
            port = mqtt_config['port']
            self.__client.connect(server, port, 60)
            self.__client.will_set("homeassistant/switch/"
                                   + mqtt_config['device_id']
                                   + "/available",
                                   "offline", qos=0, retain=True)
            self.__client.on_connect = self.on_connect
            self.__client.on_message = self.on_message
            self.__device_id = mqtt_config['device_id']
            self.__device_url = mqtt_config['device_url']
        except Exception as e:
            self.__logger.error("MQTT not set up because of: {}".format(e))
            raise

    def start(self):
        """
        Starts the MQTT client and publishes the state.

        This method sets the `publish_state` attribute of the controller and starts the MQTT client's loop.

        Raises:
            Exception: If the MQTT client fails to start.

        """
        try:
            self.__controller.publish_state = self.publish_state
            self.__client.loop_start()
        except Exception as e:
            self.__logger.error("MQTT not started because of: {}".format(e))
            raise

    def stop(self):
        """
        Returns a dictionary representing the device element.

        The dictionary contains the following keys:
        - ids: A list containing the device ID.
        - name: The device ID.
        - mdl: The model of the device, set to "PictureFrame".
        - sw: The software version, set to the value of __version__.
        - mf: The manufacturer of the device, set to "pi3d PictureFrame project".
        - cu (optional): The device URL, only included if __device_url is set.

        Returns:
        A dictionary representing the device element.
        """
        try:
            self.__controller.publish_state = None
            self.__client.loop_stop()
        except Exception as e:
            self.__logger.error("MQTT stopping failed because of: {}".format(e))

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback function that is called when the client successfully connects to the MQTT broker.

        Parameters:
            client (mqtt.Client): The MQTT client instance.
            userdata: The user data passed to the client when connecting.
            flags: Response flags sent by the broker.
            rc (int): The connection result code.

        Returns:
            None
        """
        if rc != 0:
            self.__logger.warning("Can't connect with mqtt broker. Reason = {0}".format(rc))
            return
        self.__logger.info('Connected with mqtt broker')

        # send last will and testament
        available_topic = "homeassistant/switch/" + self.__device_id + "/available"
        client.publish(available_topic, "online", qos=0, retain=True)

        # sensors
        self.__setup_text(client, "date_from", "mdi:calendar-arrow-left", available_topic, entity_category="config")
        self.__setup_text(client, "date_to", "mdi:calendar-arrow-right", available_topic, entity_category="config")
        self.__setup_text(client, "location_filter", "mdi:map-search", available_topic, entity_category="config")
        self.__setup_text(client, "tags_filter", "mdi:image-search", available_topic, entity_category="config")
        self.__setup_sensor(client, "image_counter", "mdi:camera-burst", available_topic, entity_category="diagnostic")
        self.__setup_sensor(client, "image", "mdi:file-image",
                            available_topic, has_attributes=True, entity_category="diagnostic")

        # numbers
        self.__setup_number(client, "brightness", 0.0, 1.0, 0.1, "mdi:brightness-6", available_topic)
        self.__setup_number(client, "time_delay", 1, 400, 1, "mdi:image-plus", available_topic)
        self.__setup_number(client, "fade_time", 1, 50, 1, "mdi:image-size-select-large", available_topic)
        self.__setup_number(client, "matting_images", 0.0, 1.0, 0.01, "mdi:image-frame", available_topic)

        # selects
        _, dir_list = self.__controller.get_directory_list()
        dir_list.sort()
        self.__setup_select(client, "directory", dir_list, "mdi:folder-multiple-image", available_topic, init=True)
        command_topic = self.__device_id + "/directory"
        client.subscribe(command_topic, qos=0)

        _, shared_album_list = self.__controller.get_album_list(True)
        shared_album_list.sort()
        self.__setup_select(client, "shared_album", shared_album_list, "mdi:folder-multiple-image", available_topic, init=True)
        command_topic = self.__device_id + "/shared_album"
        client.subscribe(command_topic, qos=0)

        _, mine_album_list = self.__controller.get_album_list(False)
        mine_album_list.sort()
        self.__setup_select(client, "mine_album", mine_album_list, "mdi:folder-multiple-image", available_topic, init=True)
        command_topic = self.__device_id + "/mine_album"
        client.subscribe(command_topic, qos=0)

        # switches
        self.__setup_switch(client, "text_refresh", "mdi:refresh", available_topic, entity_category="config")
        self.__setup_switch(client, "name_toggle", "mdi:subtitles", available_topic,
                            self.__controller.text_is_on("name"), entity_category="config")
        self.__setup_switch(client, "title_toggle", "mdi:subtitles", available_topic,
                            self.__controller.text_is_on("title"), entity_category="config")
        self.__setup_switch(client, "caption_toggle", "mdi:subtitles", available_topic,
                            self.__controller.text_is_on("caption"), entity_category="config")
        self.__setup_switch(client, "date_toggle", "mdi:calendar-today", available_topic,
                            self.__controller.text_is_on("date"), entity_category="config")
        self.__setup_switch(client, "location_toggle", "mdi:crosshairs-gps", available_topic,
                            self.__controller.text_is_on("location"), entity_category="config")
        self.__setup_switch(client, "directory_toggle", "mdi:folder", available_topic,
                            self.__controller.text_is_on("directory"), entity_category="config")
        self.__setup_switch(client, "text_off", "mdi:badge-account-horizontal-outline",
                            available_topic, entity_category="config")
        self.__setup_switch(client, "display", "mdi:panorama", available_topic,
                            self.__controller.display_is_on)
        self.__setup_switch(client, "clock", "mdi:clock-outline", available_topic,
                            self.__controller.clock_is_on, entity_category="config")
        self.__setup_switch(client, "shuffle", "mdi:shuffle-variant", available_topic,
                            self.__controller.shuffle)
        self.__setup_switch(client, "paused", "mdi:pause", available_topic,
                            self.__controller.paused)
        self.__setup_switch(client, "use_album", "mdi:folder", available_topic,
                            self.__controller.useAlbum, entity_category="config")
        self.__setup_switch(client, "use_mine_album", "mdi:folder", available_topic,
                            self.__controller.useMineAlbum, entity_category="config")

        # buttons
        self.__setup_button(client, "delete", "mdi:delete", available_topic)
        self.__setup_button(client, "back", "mdi:skip-previous", available_topic)
        self.__setup_button(client, "next", "mdi:skip-next", available_topic)
        self.__setup_button(client, "refresh_album_list", "mdi:folder-refresh", available_topic)
        self.__setup_button(client, "refresh_file_list", "mdi:folder-refresh", available_topic)

        client.subscribe(self.__device_id + "/purge_files", qos=0)  # close down without killing!
        client.subscribe(self.__device_id + "/stop", qos=0)  # close down without killing!

    def __get_dev_element(self):
        """
        Returns a dictionary representing the device element.

        The dictionary contains the following keys:
        - ids: A list containing the device ID.
        - name: The device ID.
        - mdl: The model of the device, set to "PictureFrame".
        - sw: The software version, set to the value of __version__.
        - mf: The manufacturer of the device, set to "pi3d PictureFrame project".
        - cu (optional): The device URL, only included if __device_url is set.

        Returns:
        A dictionary representing the device element.
        """
        dev =  {
            "ids": [self.__device_id],
            "name": self.__device_id,
            "mdl": "PictureFrame",
            "sw": __version__,
            "mf": "pi3d PictureFrame project"
        }
        if self.__device_url:
            dev["cu"] = self.__device_url
        return dev    

    def __setup_sensor(self, client, topic, icon, available_topic, has_attributes=False, entity_category=None):
        """
        Set up a sensor in Home Assistant.

        Args:
            client: The MQTT client used to publish and subscribe to topics.
            topic: The topic of the sensor.
            icon: The icon to be displayed for the sensor.
            available_topic: The availability topic of the sensor.
            has_attributes: A boolean indicating whether the sensor has attributes.
            entity_category: The category of the sensor entity.

        Returns:
            None
        """
        sensor_topic_head = "homeassistant/sensor/" + self.__device_id
        config_topic = sensor_topic_head + "_" + topic + "/config"
        name = self.__device_id + "_" + topic
        dict = {"name": topic,
                "icon": icon,
                "value_template": "{{ value_json." + topic + "}}",
                "avty_t": available_topic,
                "uniq_id": name,
                "dev": self.__get_dev_element()}
        if has_attributes is True:
            dict["state_topic"] = sensor_topic_head + "_" + topic + "/state"
            dict["json_attributes_topic"] = sensor_topic_head + "_" + topic + "/attributes"
        else:
            dict["state_topic"] = sensor_topic_head + "/state"
        if entity_category:
            dict["entity_category"] = entity_category

        config_payload = json.dumps(dict)
        client.publish(config_topic, config_payload, qos=0, retain=True)
        client.subscribe(self.__device_id + "/" + topic, qos=0)
    
    def __setup_text(self, client, topic, icon, available_topic, entity_category=None):
        """
        Sets up the text sensor configuration and publishes it to the MQTT broker.

        Args:
            client (mqtt.Client): The MQTT client instance.
            topic (str): The topic of the text sensor.
            icon (str): The icon to be displayed for the text sensor.
            available_topic (str): The availability topic for the text sensor.
            entity_category (str, optional): The entity category of the text sensor.

        Returns:
            None
        """
        text_topic_head = "homeassistant/text/" + self.__device_id
        config_topic = text_topic_head + "_" + topic + "/config"
        name = self.__device_id + "_" + topic
        dict = {"name": topic,
                "icon": icon,
                "value_template": "{{ value_json." + topic + "}}",
                "state_topic": "homeassistant/sensor/" + self.__device_id + "/state",
                "command_topic": text_topic_head + "_" + topic + "/cmd",
                "avty_t": available_topic,
                "uniq_id": name,
                "dev": self.__get_dev_element()}
        if entity_category:
            dict["entity_category"] = entity_category

        config_payload = json.dumps(dict)
        client.publish(config_topic, config_payload, qos=0, retain=True)
        client.subscribe(self.__device_id + "/" + topic, qos=0)

    def __setup_number(self, client, topic, min, max, step, icon, available_topic):
        """
        Set up a number entity in Home Assistant.

        Args:
            client (mqtt.Client): The MQTT client used for communication.
            topic (str): The topic of the number entity.
            min (float): The minimum value of the number entity.
            max (float): The maximum value of the number entity.
            step (float): The step value for incrementing or decrementing the number entity.
            icon (str): The icon to be displayed for the number entity.
            available_topic (str): The topic used to indicate the availability of the number entity.

        Returns:
            None
        """
        number_topic_head = "homeassistant/number/" + self.__device_id
        config_topic = number_topic_head + "_" + topic + "/config"
        command_topic = self.__device_id + "/" + topic
        state_topic = "homeassistant/sensor/" + self.__device_id + "/state"
        name = self.__device_id + "_" + topic
        config_payload = json.dumps({"name": topic,
                                     "min": min,
                                     "max": max,
                                     "step": step,
                                     "icon": icon,
                                     "entity_category": "config",
                                     "state_topic": state_topic,
                                     "command_topic": command_topic,
                                     "value_template": "{{ value_json." + topic + "}}",
                                     "avty_t": available_topic,
                                     "uniq_id": name,
                                    "dev": self.__get_dev_element()})
        client.publish(config_topic, config_payload, qos=0, retain=True)
        client.subscribe(command_topic, qos=0)

    def __setup_select(self, client, topic, options, icon, available_topic, init=False):
        """
        Set up a select component in Home Assistant.

        Args:
            client (mqtt.Client): The MQTT client used to publish and subscribe to topics.
            topic (str): The topic of the select component.
            options (list): The list of options for the select component.
            icon (str): The icon to be displayed for the select component.
            available_topic (str): The availability topic for the select component.
            init (bool, optional): Whether to subscribe to the command topic during initialization. Defaults to False.
        """
        select_topic_head = "homeassistant/select/" + self.__device_id
        config_topic = select_topic_head + "_" + topic + "/config"
        command_topic = self.__device_id + "/" + topic
        state_topic = "homeassistant/sensor/" + self.__device_id + "/state"
        name = self.__device_id + "_" + topic

        config_payload = json.dumps({"name": topic,
                                     "entity_category": "config",
                                     "icon": icon,
                                     "options": options,
                                     "state_topic": state_topic,
                                     "command_topic": command_topic,
                                     "value_template": "{{ value_json." + topic + "}}",
                                     "avty_t": available_topic,
                                     "uniq_id": name,
                                     "dev": self.__get_dev_element()})
        client.publish(config_topic, config_payload, qos=0, retain=True)
        if init:
            client.subscribe(command_topic, qos=0)

    def __setup_switch(self, client, topic, icon,
                       available_topic, is_on=False, entity_category=None):
        """
        Sets up a switch in Home Assistant.

        Args:
            client (mqtt.Client): The MQTT client object.
            topic (str): The topic of the switch.
            icon (str): The icon to be displayed for the switch.
            available_topic (str): The availability topic for the switch.
            is_on (bool, optional): The initial state of the switch. Defaults to False.
            entity_category (str, optional): The category of the entity. Defaults to None.
        """
        switch_topic_head = "homeassistant/switch/" + self.__device_id
        config_topic = switch_topic_head + "_" + topic + "/config"
        command_topic = switch_topic_head + "_" + topic + "/set"
        state_topic = switch_topic_head + "_" + topic + "/state"
        dict = {"name": topic,
                "icon": icon,
                "command_topic": command_topic,
                "state_topic": state_topic,
                "avty_t": available_topic,
                "uniq_id": self.__device_id + "_" + topic,
                "dev": self.__get_dev_element()}
        if entity_category:
            dict["entity_category"] = entity_category
        config_payload = json.dumps(dict)

        client.subscribe(command_topic, qos=0)
        client.publish(config_topic, config_payload, qos=0, retain=True)
        client.publish(state_topic, "ON" if is_on else "OFF", qos=0, retain=True)

    def __setup_button(self, client, topic, icon,
                       available_topic, entity_category=None):
        """
        Set up a button configuration for the Home Assistant integration.

        Args:
            client (mqtt.Client): The MQTT client used for communication.
            topic (str): The topic of the button.
            icon (str): The icon to be displayed for the button.
            available_topic (str): The availability topic for the button.
            entity_category (str, optional): The category of the entity. Defaults to None.

        Returns:
            None
        """
        button_topic_head = "homeassistant/button/" + self.__device_id
        config_topic = button_topic_head + "_" + topic + "/config"
        command_topic = button_topic_head + "_" + topic + "/set"
        dict = {"name": topic,
                "icon": icon,
                "command_topic": command_topic,
                "payload_press": "ON",
                "avty_t": available_topic,
                "uniq_id": self.__device_id + "_" + topic,
                "dev": self.__get_dev_element()}
        if entity_category:
            dict["entity_category"] = entity_category
        config_payload = json.dumps(dict)

        client.subscribe(command_topic, qos=0)
        client.publish(config_topic, config_payload, qos=0, retain=True)

    def on_message(self, client, userdata, message):  # noqa: C901
        """
        Callback function that is called when a message is received.

        Args:
            client: The MQTT client instance.
            userdata: The user data passed to the MQTT client.
            message: An instance of the MQTTMessage class representing the received message.

        Returns:
            None

        Raises:
            None
        """
        msg = message.payload.decode("utf-8")
        switch_topic_head = "homeassistant/switch/" + self.__device_id
        button_topic_head = "homeassistant/button/" + self.__device_id



        # ##### switches ######
        # display
        if message.topic == switch_topic_head + "_display/set":
            state_topic = switch_topic_head + "_display/state"
            if msg == "ON":
                self.__controller.display_is_on = True
                client.publish(state_topic, "ON", retain=True)
            elif msg == "OFF":
                self.__controller.display_is_on = False
                client.publish(state_topic, "OFF", retain=True)
        # clock
        if message.topic == switch_topic_head + "_clock/set":
            state_topic = switch_topic_head + "_clock/state"
            if msg == "ON":
                self.__controller.clock_is_on = True
                client.publish(state_topic, "ON", retain=True)
            elif msg == "OFF":
                self.__controller.clock_is_on = False
                client.publish(state_topic, "OFF", retain=True)
        # shuffle
        elif message.topic == switch_topic_head + "_shuffle/set":
            state_topic = switch_topic_head + "_shuffle/state"
            if msg == "ON":
                self.__controller.shuffle = True
                client.publish(state_topic, "ON", retain=True)
            elif msg == "OFF":
                self.__controller.shuffle = False
                client.publish(state_topic, "OFF", retain=True)
        # paused
        elif message.topic == switch_topic_head + "_paused/set":
            state_topic = switch_topic_head + "_paused/state"
            if msg == "ON":
                self.__controller.paused = True
                client.publish(state_topic, "ON", retain=True)
            elif msg == "OFF":
                self.__controller.paused = False
                client.publish(state_topic, "OFF", retain=True)
        # back buttons
        elif message.topic == button_topic_head + "_back/set":
            if msg == "ON":
                self.__controller.back()
        # next buttons
        elif message.topic == button_topic_head + "_next/set":
            if msg == "ON":
                self.__controller.next()
        # delete
        elif message.topic == button_topic_head + "_delete/set":
            if msg == "ON":
                self.__controller.delete()
         # refresh album list
        elif message.topic == button_topic_head + "_refresh_album_list/set":
            if msg == "ON":
                self.__controller.refresh_album_list()# title on
         # refresh file list
        elif message.topic == button_topic_head + "_refresh_file_list/set":
            if msg == "ON":
                self.__controller.refresh_file_list()# title on
        elif message.topic == switch_topic_head + "_title_toggle/set":
            state_topic = switch_topic_head + "_title_toggle/state"
            if msg in ("ON", "OFF"):
                self.__controller.set_show_text("title", msg)
                client.publish(state_topic, msg, retain=True)
        # caption on
        elif message.topic == switch_topic_head + "_caption_toggle/set":
            state_topic = switch_topic_head + "_caption_toggle/state"
            if msg in ("ON", "OFF"):
                self.__controller.set_show_text("caption", msg)
                client.publish(state_topic, msg, retain=True)
        # name on
        elif message.topic == switch_topic_head + "_name_toggle/set":
            state_topic = switch_topic_head + "_name_toggle/state"
            if msg in ("ON", "OFF"):
                self.__controller.set_show_text("name", msg)
                client.publish(state_topic, msg, retain=True)
        # date_on
        elif message.topic == switch_topic_head + "_date_toggle/set":
            state_topic = switch_topic_head + "_date_toggle/state"
            if msg in ("ON", "OFF"):
                self.__controller.set_show_text("date", msg)
                client.publish(state_topic, msg, retain=True)
        # location_on
        elif message.topic == switch_topic_head + "_location_toggle/set":
            state_topic = switch_topic_head + "_location_toggle/state"
            if msg in ("ON", "OFF"):
                self.__controller.set_show_text("location", msg)
                client.publish(state_topic, msg, retain=True)
        # directory_on
        elif message.topic == switch_topic_head + "_directory_toggle/set":
            state_topic = switch_topic_head + "_directory_toggle/state"
            if msg in ("ON", "OFF"):
                self.__controller.set_show_text("folder", msg)
                client.publish(state_topic, msg, retain=True)

        # album_on
        elif message.topic == switch_topic_head + "_use_album/set":
            state_topic = switch_topic_head + "_use_album/state"
            if msg == "ON":
                self.__controller.useAlbum = True
                client.publish(state_topic, "ON", retain=True)
            elif msg == "OFF":
                self.__controller.useAlbum = False
                client.publish(state_topic, "OFF", retain=True)

        # mine_album_on
        elif message.topic == switch_topic_head + "_use_mine_album/set":
            state_topic = switch_topic_head + "_use_mine_album/state"

            if msg == "ON":
                self.__controller.useMineAlbum = True
                client.publish(state_topic, "ON", retain=True)
            elif msg == "OFF":
                self.__controller.useMineAlbum = False
                client.publish(state_topic, "OFF", retain=True)
                
        # text_off
        elif message.topic == switch_topic_head + "_text_off/set":
            state_topic = switch_topic_head + "_text_off/state"
            if msg == "ON":
                self.__controller.set_show_text()
                client.publish(state_topic, "OFF", retain=True)
                state_topic = switch_topic_head + "_directory_toggle/state"
                client.publish(state_topic, "OFF", retain=True)
                state_topic = switch_topic_head + "_location_toggle/state"
                client.publish(state_topic, "OFF", retain=True)
                state_topic = switch_topic_head + "_date_toggle/state"
                client.publish(state_topic, "OFF", retain=True)
                state_topic = switch_topic_head + "_name_toggle/state"
                client.publish(state_topic, "OFF", retain=True)
                state_topic = switch_topic_head + "_title_toggle/state"
                client.publish(state_topic, "OFF", retain=True)
                state_topic = switch_topic_head + "_caption_toggle/state"
                client.publish(state_topic, "OFF", retain=True)
        # text_refresh
        elif message.topic == switch_topic_head + "_text_refresh/set":
            state_topic = switch_topic_head + "_text_refresh/state"
            if msg == "ON":
                client.publish(state_topic, "OFF", retain=True)
                self.__controller.refresh_show_text()

        # #### values ########
        # change subdirectory
        elif message.topic == self.__device_id + "/directory":
            self.__logger.info("Recieved subdirectory: %s", msg)
            self.__controller.subdirectory = msg
        # change shared album
        elif message.topic == self.__device_id + "/shared_album":
            self.__logger.info("Recieved shared album: %s", msg)
            self.__controller.albumName = msg
        # change mine album
        elif message.topic == self.__device_id + "/mine_album":
            self.__logger.info("Recieved mine album: %s", msg)
            self.__controller.mineAlbumName = msg
        # date_from
        elif message.topic == self.__device_id + "/date_from":
            self.__logger.info("Recieved date_from: %s", msg)
            self.__controller.date_from = msg
        # date_to
        elif message.topic == self.__device_id + "/date_to":
            self.__logger.info("Recieved date_to: %s", msg)
            self.__controller.date_to = msg
        # fade_time
        elif message.topic == self.__device_id + "/fade_time":
            self.__logger.info("Recieved fade_time: %s", msg)
            self.__controller.fade_time = float(msg)
        # time_delay
        elif message.topic == self.__device_id + "/time_delay":
            self.__logger.info("Recieved time_delay: %s", msg)
            self.__controller.time_delay = float(msg)
        # brightness
        elif message.topic == self.__device_id + "/brightness":
            self.__logger.info("Recieved brightness: %s", msg)
            self.__controller.brightness = float(msg)
        # matting_images
        elif message.topic == self.__device_id + "/matting_images":
            self.__logger.info("Received matting_images: %s", msg)
            self.__controller.matting_images = float(msg)
        # location filter
        elif message.topic == self.__device_id + "/location_filter":
            self.__logger.info("Recieved location filter: %s", msg)
            self.__controller.location_filter = msg
        # tags filter
        elif message.topic == self.__device_id + "/tags_filter":
            self.__logger.info("Recieved tags filter: %s", msg)
            self.__controller.tags_filter = msg

        # set the flag to purge files from database
        elif message.topic == self.__device_id + "/purge_files":
            self.__controller.purge_files()

        # stop loops and end program
        elif message.topic == self.__device_id + "/stop":
            self.__controller.stop()

    def publish_state(self, image=None, image_attr=None):
        """
        Publishes the state of the device to the MQTT broker.

        Args:
            image (str, optional): The path to the image file. Defaults to None.
            image_attr (dict, optional): The attributes of the image. Defaults to None.

        Returns:
            None
        """
        sensor_topic_head = "homeassistant/sensor/" + self.__device_id
        switch_topic_head = "homeassistant/switch/" + self.__device_id
        available_topic = switch_topic_head + "/available"

        sensor_state_payload = {}
        image_state_payload = {}
        # image
        # image attributes
        if image_attr is not None:
            attributes_topic = sensor_topic_head + "_image/attributes"
            self.__logger.debug("Send image attributes: %s", image_attr)
            self.__client.publish(attributes_topic, json.dumps(image_attr), qos=0, retain=False)
        # image sensor
        if image is not None:
            _, tail = os.path.split(image)
            image_state_payload["image"] = tail
            image_state_topic = sensor_topic_head + "_image/state"
            self.__logger.info("Send image state: %s", image_state_payload)
            self.__client.publish(image_state_topic, json.dumps(image_state_payload), qos=0, retain=False)

        # sensor
        # directory sensor
        actual_dir, dir_list = self.__controller.get_directory_list()
        sensor_state_payload["directory"] = actual_dir
        # shared album sensor
        actual_shared_album, shared_album_list = self.__controller.get_album_list(True)
        sensor_state_payload["shared_album"] = actual_shared_album
        # mine album sensor
        actual_mine_album, mine_album_list = self.__controller.get_album_list(False)
        sensor_state_payload["mine_album"] = actual_mine_album
        # image counter sensor
        sensor_state_payload["image_counter"] = str(self.__controller.get_number_of_files())
        # date_from
        sensor_state_payload["date_from"] = int(self.__controller.date_from)
        # date_to
        sensor_state_payload["date_to"] = int(self.__controller.date_to)
        # location_filter
        sensor_state_payload["location_filter"] = self.__controller.location_filter
        # tags_filter
        sensor_state_payload["tags_filter"] = self.__controller.tags_filter
        # number state
        # time_delay
        sensor_state_payload["time_delay"] = self.__controller.time_delay
        # fade_time
        sensor_state_payload["fade_time"] = self.__controller.fade_time
        # brightness
        sensor_state_payload["brightness"] = self.__controller.brightness
        # matting_images
        sensor_state_payload["matting_images"] = self.__controller.matting_images

        # pulish sensors
        dir_list.sort()
        self.__setup_select(self.__client, "directory", dir_list,
                            "mdi:folder-multiple-image", available_topic, init=False)

        shared_album_list.sort()
        self.__setup_select(self.__client, "shared_album", shared_album_list,
                            "mdi:folder-multiple-image", available_topic, init=False)

        mine_album_list.sort()
        self.__setup_select(self.__client, "mine_album", mine_album_list,
                            "mdi:folder-multiple-image", available_topic, init=False)

        self.__logger.info("Send sensor state: %s", sensor_state_payload)
        sensor_state_topic = sensor_topic_head + "/state"
        self.__client.publish(sensor_state_topic, json.dumps(sensor_state_payload), qos=0, retain=False)

        # publish state of switches
        # pause
        state_topic = switch_topic_head + "_paused/state"
        payload = "ON" if self.__controller.paused else "OFF"
        self.__client.publish(state_topic, payload, retain=True)
        # shuffle
        state_topic = switch_topic_head + "_shuffle/state"
        payload = "ON" if self.__controller.shuffle else "OFF"
        self.__client.publish(state_topic, payload, retain=True)
        # display
        state_topic = switch_topic_head + "_display/state"
        payload = "ON" if self.__controller.display_is_on else "OFF"
        self.__client.publish(state_topic, payload, retain=True)
        # useAlbum
        state_topic = switch_topic_head + "_use_album/state"

        payload = "ON" if self.__controller.useAlbum else "OFF"
        self.__client.publish(state_topic, payload, retain=True)
        # useMineAlbum
        state_topic = switch_topic_head + "_use_mine_album/state"
        payload = "ON" if self.__controller.useMineAlbum else "OFF"
        self.__client.publish(state_topic, payload, retain=True)

        # send last will and testament
        self.__client.publish(available_topic, "online", qos=0, retain=True)
