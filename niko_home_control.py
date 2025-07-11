import json
import time
from typing import List, Dict, Any, Optional, Callable, Union

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv

load_dotenv()


class NikoHomeControlAPI:
    """
    Complete implementation of the Niko Home Control API based on the official documentation.
    Provides methods to interact with the Niko Home Control system via MQTT and REST.
    """

    def __init__(self, host: str, username: str, jwt_token: str, ca_cert_path: str = None):
        """
        Initialize the Niko Home Control API.

        Args:
            host: The hostname or IP address of the Niko Home Control controller
            username: MQTT username provided by Niko (typically "hobby")
            jwt_token: JWT token provided by Niko
            ca_cert_path: Path to CA certificate file (optional)
        """
        self.host = host
        self.username = username
        self.jwt_token = jwt_token
        self.ca_cert_path = ca_cert_path
        self._connected = False

        # MQTT client setup with Callback API v2
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.username_pw_set(username, jwt_token)
        if ca_cert_path:
            self.mqtt_client.tls_set(ca_cert_path)

        # Callback handlers
        self.device_callbacks = []
        self.location_callbacks = []
        self.notification_callbacks = []
        self.system_callbacks = []
        self.error_callbacks = []

        # Assign MQTT callbacks
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect

        # Base URLs
        self.mqtt_port = 8884
        self.rest_base_url = f"https://{host}/measurements/v1"

        # Connect to MQTT broker with retry logic
        self._connect_mqtt()

    def _connect_mqtt(self, retries: int = 3, delay: float = 1.0):
        """Connect to MQTT broker with retry logic."""
        for attempt in range(retries):
            try:
                self.mqtt_client.connect(self.host, self.mqtt_port)
                self.mqtt_client.loop_start()

                # Wait for connection to establish
                wait_time = 0
                while not self._connected and wait_time < 5:
                    time.sleep(0.1)
                    wait_time += 0.1

                if self._connected:
                    return

                self.mqtt_client.disconnect()

            except Exception as e:
                print(f"Connection attempt {attempt + 1} failed: {str(e)}")
                if attempt < retries - 1:
                    time.sleep(delay)

        raise ConnectionError("Failed to connect to MQTT broker after several attempts")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when MQTT connects."""
        if reason_code == 0:
            self._connected = True
            print("Connected to MQTT broker")
            # Subscribe to event topics
            client.subscribe("hobby/control/devices/evt")
            client.subscribe("hobby/control/locations/evt")
            client.subscribe("hobby/notification/evt")
            client.subscribe("hobby/system/evt")
            client.subscribe("hobby/control/devices/err")
            client.subscribe("hobby/control/locations/err")
            client.subscribe("hobby/notification/err")
            client.subscribe("hobby/system/err")
        else:
            print(f"Connection failed with code {reason_code}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        """Callback when MQTT disconnects."""
        self._connected = False
        print(f"Disconnected from MQTT broker (reason: {reason_code}, flags: {disconnect_flags})")

    def _on_message(self, client, userdata, message):
        """Callback when MQTT message is received."""
        try:
            payload = json.loads(message.payload.decode())
            method = payload.get("Method")
            params = payload.get("Params", {})
            error_code = payload.get("ErrCode")
            error_message = payload.get("ErrMessage")

            # Handle error messages
            if error_code:
                for callback in self.error_callbacks:
                    callback({
                        "topic": message.topic,
                        "method": method,
                        "error_code": error_code,
                        "error_message": error_message
                    })
                return

            # Handle different parameter formats
            if isinstance(params, list):
                # When Params is a list, extract devices/locations from the first item
                if params and isinstance(params[0], dict):
                    devices = params[0].get("Devices", [])
                    locations = params[0].get("Locations", [])
                    notifications = params[0].get("Notifications", [])
                    time_info = params[0].get("TimeInfo", {})
                    system_info = params[0].get("SystemInfo", {})
            else:
                # When Params is a dict (older format)
                devices = params.get("Devices", [])
                locations = params.get("Locations", [])
                notifications = params.get("Notifications", [])
                time_info = params.get("TimeInfo", {})
                system_info = params.get("SystemInfo", {})

            # Route messages to appropriate handlers
            if method and method.startswith("devices."):
                for callback in self.device_callbacks:
                    callback({
                        "method": method,
                        "devices": devices,
                        "topic": message.topic
                    })

            elif method and method.startswith("locations."):
                for callback in self.location_callbacks:
                    callback({
                        "method": method,
                        "locations": locations,
                        "topic": message.topic
                    })

            elif method == "time.published":
                for callback in self.system_callbacks:
                    callback({
                        "method": method,
                        "time_info": time_info,
                        "topic": message.topic
                    })

            elif method == "systeminfo.published":
                for callback in self.system_callbacks:
                    callback({
                        "method": method,
                        "system_info": system_info,
                        "topic": message.topic
                    })

            elif method == "notifications.raised":
                for callback in self.notification_callbacks:
                    callback({
                        "method": method,
                        "notifications": notifications,
                        "topic": message.topic
                    })

        except json.JSONDecodeError:
            print(f"Failed to decode MQTT message: {message.payload}")
        except Exception as e:
            print(f"Error processing message: {str(e)}")

    def ensure_connection(self):
        """Ensure we have an active MQTT connection."""
        if not self._connected:
            self._connect_mqtt()

    # Callback registration methods
    def register_device_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for device events."""
        self.device_callbacks.append(callback)

    def register_location_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for location events."""
        self.location_callbacks.append(callback)

    def register_notification_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for notification events."""
        self.notification_callbacks.append(callback)

    def register_system_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for system events."""
        self.system_callbacks.append(callback)

    def register_error_callback(self, callback: Callable[[Dict], None]):
        """Register a callback for error messages."""
        self.error_callbacks.append(callback)

    # Device Management Methods
    def list_devices(self) -> List[Dict]:
        """
        Get a list of all devices in the installation.

        Returns:
            List of device dictionaries
        """
        payload = {
            "Method": "devices.list"
        }
        response = self._mqtt_request(
            "hobby/control/devices/cmd",
            "hobby/control/devices/rsp",
            payload
        )

        if not response or "Params" not in response:
            return []

        # Extract devices from response
        devices = []
        for param in response["Params"]:
            if isinstance(param, dict) and "Devices" in param:
                devices.extend(param["Devices"])

        return devices

    def control_device(self, device_uuid: str, properties: Union[Dict[str, Any], List[Dict[str, Any]]],
                       wait_for_response: bool = False) -> Optional[Dict]:
        """
        Control a device by setting its properties.

        Args:
            device_uuid: UUID of the device to control
            properties: Either a single property dictionary or list of property dictionaries
            wait_for_response: Whether to wait for a response from the device

        Returns:
            Response payload if wait_for_response is True, None otherwise

        Note:
            The properties must be formatted as a list of property dictionaries according to the Niko API spec.
            For example, [{"Position": "50"}] or [{"Status": "On" }, {"Brightness": "75"}]
        """
        self.ensure_connection()

        # Ensure properties is a list (convert single dict to list if needed)
        if isinstance(properties, dict):
            properties = properties

        payload = {
            "Method": "devices.control",
            "Params": [{
                "Devices": [{
                    "Uuid": device_uuid,
                    "Properties": properties  # This is now always a list
                }]
            }]
        }

        if wait_for_response:
            return self._mqtt_request(
                "hobby/control/devices/cmd",
                "hobby/control/devices/rsp",
                payload
            )
        else:
            result = self.mqtt_client.publish(
                "hobby/control/devices/cmd",
                json.dumps(payload))
            result.wait_for_publish()
            return None

    def set_device_position(self, device_uuid: str, position: int, wait_for_response: bool = False) -> Optional[Dict]:
        """
        Convenience method to set device position (for blinds, etc.)

        Args:
            device_uuid: UUID of the device
            position: Position value (0-100)
            wait_for_response: Whether to wait for a response

        Returns:
            Response payload if wait_for_response is True, None otherwise
        """
        return self.control_device(
            device_uuid,
            [{"Position": str(position)}],  # As list with one property dict
            wait_for_response=wait_for_response
        )

    def set_device_status(self, device_uuid: str, status: str, wait_for_response: bool = False) -> Optional[Dict]:
        """
        Convenience method to set device status (on/off)

        Args:
            device_uuid: UUID of the device
            status: Status value ("On" or "Off")
            wait_for_response: Whether to wait for a response

        Returns:
            Response payload if wait_for_response is True, None otherwise
        """
        return self.control_device(
            device_uuid,
            [{"Status": status}],  # As list with one property dict
            wait_for_response=wait_for_response
        )

    def set_device_brightness(self, device_uuid: str, brightness: int, wait_for_response: bool = False) -> Optional[
        Dict]:
        """
        Convenience method to set device brightness (for dimmers)

        Args:
            device_uuid: UUID of the device
            brightness: Brightness value (0-100)
            wait_for_response: Whether to wait for a response

        Returns:
            Response payload if wait_for_response is True, None otherwise
        """
        return self.control_device(
            device_uuid,
            [{"Brightness": str(brightness)}],  # As list with one property dict
            wait_for_response=wait_for_response
        )

    def get_device_status(self, device_uuid: str) -> Dict | None:
        """
        Get the current status of a device.

        Args:
            device_uuid: UUID of the device

        Returns:
            Dictionary with current status, position, and other properties

        Example:
            status = api.get_device_status("device-uuid")
            print(f"Status: {status['status']}, Position: {status['position']}")
        """
        devices = self.list_devices()
        for device in devices:
            if device.get('Uuid') == device_uuid:
                return device
        return None

    def get_dimmer_status(self, device_uuid: str) -> Dict:
        """
        Get the current status of a dimmer device.

        Args:
            device_uuid: UUID of the dimmer device

        Returns:
            Dictionary with current status, brightness, and other properties

        Example:
            status = api.get_dimmer_status("dimmer-uuid")
            print(f"Status: {status['status']}, Brightness: {status['brightness']}")
        """
        devices = self.list_devices()
        for device in devices:
            if device.get('Uuid') == device_uuid:
                if device.get('Model') != 'dimmer':
                    raise ValueError("Device is not a dimmer")

                status = "Unknown"
                brightness = 0
                aligned = False

                # Extract current properties
                for prop in device.get('Properties', []):
                    if 'Status' in prop:
                        status = prop['Status']
                    if 'Brightness' in prop:
                        brightness = int(prop['Brightness'])
                    if 'Aligned' in prop:
                        aligned = prop['Aligned'] == 'True'

                return {
                    'status': status,
                    'brightness': brightness,
                    'aligned': aligned,
                    'online': device.get('Online') == 'True',
                    'name': device.get('Name'),
                    'location': next((p['LocationName'] for p in device.get('Parameters', [])
                                      if 'LocationName' in p), None)
                }

        raise ValueError(f"Dimmer with UUID {device_uuid} not found")

    # Location Methods
    def list_locations(self) -> List[Dict]:
        """Get a list of all locations in the installation."""
        payload = {
            "Method": "locations.list"
        }
        response = self._mqtt_request(
            "hobby/control/locations/cmd",
            "hobby/control/locations/rsp",
            payload
        )

        if not response or "Params" not in response:
            return []

        # Extract locations from response
        locations = []
        for param in response["Params"]:
            if isinstance(param, dict) and "Locations" in param:
                locations.extend(param["Locations"])

        return locations

    def list_devices_in_location(self, location_uuid: str) -> List[Dict]:
        """
        Get a list of devices in a specified location.

        Args:
            location_uuid: UUID of the location to query

        Returns:
            List of devices in the location
        """
        payload = {
            "Method": "locations.listitems",
            "Params": [{
                "Locations": [{"Uuid": location_uuid}]
            }]
        }

        try:
            response = self._mqtt_request(
                "hobby/control/locations/cmd",
                "hobby/control/locations/rsp",
                payload,
                timeout=5.0
            )

            if not response or "Params" not in response:
                return []

            # The response structure is different from what we expect
            # We to need to properly extract the devices
            for param in response["Params"]:
                if isinstance(param, dict):
                    if "Locations" in param:
                        for location in param["Locations"]:
                            if location.get("Uuid") == location_uuid:
                                return location.get("Items", [])
                    elif "Devices" in param:  # Some systems might return devices directly
                        return param["Devices"]

            return []

        except Exception as e:
            print(f"Error listing devices in location: {str(e)}")
            return []

    # System Information Methods
    def get_system_info(self) -> Dict:
        """
        Get system information.

        Returns:
            Dictionary containing system information
        """
        payload = {
            "Method": "systeminfo.publish"
        }
        response = self._mqtt_request(
            "hobby/system/cmd",
            "hobby/system/rsp",
            payload
        )

        if not response or "Params" not in response:
            return {}

        # Extract system info from response
        for param in response["Params"]:
            if isinstance(param, dict) and "SystemInfo" in param:
                system_info_list = param["SystemInfo"]
                if isinstance(system_info_list, list) and len(system_info_list) > 0:
                    return system_info_list[0]

        return {}

    def get_time_info(self) -> Dict:
        """
        Get time information from the system.

        Returns:
            Dictionary containing time information
        """
        payload = {
            "Method": "time.publish"
        }
        response = self._mqtt_request(
            "hobby/system/cmd",
            "hobby/system/rsp",
            payload
        )

        if not response or "Params" not in response:
            return {}

        # Extract time info from response
        for param in response["Params"]:
            if isinstance(param, dict) and "TimeInfo" in param:
                return param["TimeInfo"]

        return {}

    # Notification Methods
    def list_notifications(self) -> List[Dict]:
        """Get a list of all notifications."""
        payload = {
            "Method": "notifications.list"
        }
        response = self._mqtt_request(
            "hobby/notification/cmd",
            "hobby/notification/rsp",
            payload
        )

        if not response or "Params" not in response:
            return []

        # Extract notifications from response
        notifications = []
        for param in response["Params"]:
            if isinstance(param, dict) and "Notifications" in param:
                notifications.extend(param["Notifications"])

        return notifications

    def update_notification(self, notification_uuid: str, status: str) -> bool:
        """
        Update the notification status.

        Args:
            notification_uuid: UUID of the notification to update
            status: New status ("read" or "new")

        Returns:
            True if the update was successful, False otherwise
        """
        payload = {
            "Method": "notifications.update",
            "Params": {
                "Notifications": [{
                    "Uuid": notification_uuid,
                    "Status": status
                }]
            }
        }
        try:
            result = self.mqtt_client.publish(
                "hobby/notification/cmd",
                json.dumps(payload))
            result.wait_for_publish()
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            return False

    # Measurement Data Methods (REST API)
    def get_latest_measurements(self, device_uuid: str) -> Dict:
        """
        Get the latest measurements for a specific device.

        Args:
            device_uuid: The UUID of the device to get measurements for

        Returns:
            Dictionary containing the latest measurements for the device

        Raises:
            requests.exceptions.HTTPError: If the request fails
        """
        url = f"{self.rest_base_url}/devices/{device_uuid}?latest=true"
        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        response = requests.get(url, headers=headers, verify=self.ca_cert_path is not None)
        response.raise_for_status()
        return response.json()

    def get_raw_measurements(self, device_uuid: str, property_name: str,
                             start_time: str = None, end_time: str = None) -> Dict:
        """
        Get raw measurement values for a given device property.

        Args:
            device_uuid: UUID of the device
            property_name: Name of the property to get measurements for
            start_time: Start time in ISO-8601 format (optional)
            end_time: End time in ISO-8601 format (optional)

        Returns:
            Dictionary containing measurement data

        Raises:
            requests.exceptions.HTTPError: If the request fails
        """
        url = f"{self.rest_base_url}/devices/{device_uuid}/properties/{property_name}"
        params = {}
        if start_time:
            params["IntervalStart"] = start_time
        if end_time:
            params["IntervalEnd"] = end_time

        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        response = requests.get(url, params=params, headers=headers, verify=self.ca_cert_path is not None)
        response.raise_for_status()
        return response.json()

    def get_aggregated_measurements(self, device_uuid: str, property_name: str, interval: str,
                                    start_time: str = None, end_time: str = None,
                                    aggregation: str = "sum") -> Dict:
        """
        Get aggregated measurement values for a given device property.

        Args:
            device_uuid: UUID of the device
            property_name: Name of the property to get measurements for
            interval: Aggregation interval ("hour", "day", "month", "year")
            start_time: Start time in ISO-8601 format (optional)
            end_time: End time in ISO-8601 format (optional)
            aggregation: Aggregation function ("sum", "avg", "min", "max")

        Returns:
            Dictionary containing measurement data

        Raises:
            requests.exceptions.HTTPError: If the request fails
        """
        url = f"{self.rest_base_url}/devices/{device_uuid}/properties/{property_name}/{interval}"
        params = {"Aggregation": aggregation}
        if start_time:
            params["IntervalStart"] = start_time
        if end_time:
            params["IntervalEnd"] = end_time

        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        response = requests.get(url, params=params, headers=headers, verify=self.ca_cert_path is not None)
        response.raise_for_status()
        return response.json()

    def get_total_measurements(self, device_uuid: str,
                               start_time: str = None, end_time: str = None,
                               aggregation: str = "sum") -> Dict:
        """
        Get aggregated measurement values for all properties of a given device.

        Args:
            device_uuid: UUID of the device
            start_time: Start time in ISO-8601 format (optional)
            end_time: End time in ISO-8601 format (optional)
            aggregation: Aggregation function ("sum", "avg", "min", "max")

        Returns:
            Dictionary containing measurement data

        Raises:
            requests.exceptions.HTTPError: If the request fails
        """
        url = f"{self.rest_base_url}/devices/{device_uuid}/total"
        params = {"Aggregation": aggregation}
        if start_time:
            params["IntervalStart"] = start_time
        if end_time:
            params["IntervalEnd"] = end_time

        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        response = requests.get(url, params=params, headers=headers, verify=self.ca_cert_path is not None)
        response.raise_for_status()
        return response.json()

    def get_devices_by_location(self) -> Dict[str, Dict]:
        """
        Get a comprehensive overview of all devices organized by location.

        Returns:
            Dictionary with location names as keys, containing:
            {
                'uuid': location UUID,
                'icon': location icon,
                'devices': [
                    {
                        'uuid': device UUID,
                        'name': device name,
                        'type': device type,
                        'model': device model,
                        'status': current status,
                        'properties': device properties
                    },
                    ...
                ]
            }
        """
        location_overview = {}

        try:
            # Get all locations
            locations = self.list_locations()
            print(f"Found {len(locations)} locations in the system")

            # First, get ALL devices to minimize API calls
            all_devices = self.list_devices()
            print(f"Found {len(all_devices)} total devices in system")

            # Create a device lookup dictionary by UUID
            device_lookup = {d['Uuid']: d for d in all_devices}

            for location in locations:
                location_uuid = location['Uuid']
                location_name = location['Name']
                location_icon = location.get('Icon', 'unknown')

                print(f"\nProcessing location: {location_name} ({location_uuid})")

                # Initialize location entry
                location_overview[location_name] = {
                    'uuid': location_uuid,
                    'icon': location_icon,
                    'devices': []
                }

                try:
                    # Get device UUIDs in this location
                    location_devices = self.list_devices_in_location(location_uuid)

                    if not location_devices:
                        print(f"No devices found in {location_name}")
                        continue

                    print(f"Found {len(location_devices)} devices in {location_name}")

                    for loc_device in location_devices:
                        device_uuid = loc_device['Uuid']

                        try:
                            # Get full device details from our lookup
                            full_device = device_lookup.get(device_uuid)

                            if not full_device:
                                print(f"Warning: Device {device_uuid} not found in full device list")
                                continue

                            # Extract device details
                            device_details = {
                                'uuid': device_uuid,
                                'name': full_device.get('Name', 'Unnamed Device'),
                                'type': full_device.get('Type', 'unknown'),
                                'model': full_device.get('Model', 'unknown'),
                                'online': full_device.get('Online', 'False') == 'True',
                                'traits': full_device.get('Traits', []),
                                'parameters': full_device.get('Parameters', []),
                                'properties': {},
                                'status': 'unknown'
                            }

                            # Process properties (handling different API response formats)
                            props = full_device.get('Properties', [])
                            if isinstance(props, list):
                                # Handle a list of property dictionaries
                                for prop_dict in props:
                                    if isinstance(prop_dict, dict):
                                        device_details['properties'].update(prop_dict)
                            elif isinstance(props, dict):
                                # Handle single property dictionary
                                device_details['properties'].update(props)

                            # Determine status
                            if 'Status' in device_details['properties']:
                                device_details['status'] = device_details['properties']['Status']
                            elif 'BasicState' in device_details['properties']:
                                device_details['status'] = device_details['properties']['BasicState']

                            location_overview[location_name]['devices'].append(device_details)

                            # Print summary
                            print(f"  - {device_details['name']} ({device_details['type']})")
                            print(f"    Model: {device_details['model']}")
                            print(f"    Status: {device_details['status']}")
                            print(f"    Online: {device_details['online']}")
                            if device_details['properties']:
                                print("    Properties:")
                                for k, v in device_details['properties'].items():
                                    print(f"      {k}: {v}")

                        except Exception as device_error:
                            print(f"Error processing device {device_uuid}: {str(device_error)}")
                            continue

                except Exception as location_error:
                    print(f"Error processing location {location_name}: {str(location_error)}")
                    continue

        except Exception as e:
            print(f"Fatal error generating location overview: {str(e)}")

        return location_overview

    def _mqtt_request(self, request_topic: str, response_topic: str, payload: Dict,
                      timeout: float = 5.0) -> Optional[Dict]:
        """
        Helper method to send MQTT request and wait for response.

        Args:
            request_topic: Topic to publish the request to
            response_topic: Topic to subscribe to for the response
            payload: Payload to send
            timeout: Timeout in seconds

        Returns:
            Response payload as dictionary or None if no response received

        Raises:
            TimeoutError: If no response is received within a timeout period
        """
        self.ensure_connection()

        response = None
        response_received = False

        def on_message(client, userdata, msg):
            nonlocal response, response_received
            try:
                response = json.loads(msg.payload.decode())
                response_received = True
            except json.JSONDecodeError:
                pass

        # Temporarily subscribe to response topics
        self.mqtt_client.subscribe(response_topic)
        original_callback = self.mqtt_client.on_message
        self.mqtt_client.on_message = on_message

        try:
            # Send request
            pub_result = self.mqtt_client.publish(request_topic, json.dumps(payload))
            pub_result.wait_for_publish()

            # Wait for response
            start_time = time.time()
            while not response_received and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if not response_received:
                raise TimeoutError(f"No response received from MQTT broker within {timeout} seconds")

            return response

        finally:
            # Restore original message handler
            self.mqtt_client.on_message = original_callback
            self.mqtt_client.unsubscribe(response_topic)

    def identify_comfort_sensors(self) -> List[Dict]:
        """
        Identify all comfort sensors (devices with both temperature and humidity measurements).

        Returns:
            List of dictionaries containing sensor information:
            [{
                'uuid': device UUID,
                'name': device name,
                'type': device type,
                'location': location name (if available),
                'properties': list of available properties
            }]
        """
        all_devices = self.list_devices()
        comfort_sensors = []

        for device in all_devices:
            # Check if the device has properties we care about
            properties = device.get('Properties', [])

            # Convert properties to a more usable format if needed
            props = {}
            for prop in properties:
                if isinstance(prop, dict):
                    props.update(prop)

            # Check for both temperature and humidity capabilities
            has_temp = 'AmbientTemperature' in props
            has_humidity = 'Humidity' in props

            if has_temp and has_humidity:
                sensor_info = {
                    'uuid': device.get('Uuid'),
                    'name': device.get('Name', 'Unknown'),
                    'type': device.get('Type', 'Unknown'),
                    'properties': props
                }

                # Try to get location information if available
                if 'Location' in device:
                    sensor_info['location'] = device['Location'].get('Name', 'Unknown')

                comfort_sensors.append(sensor_info)

        return comfort_sensors

    def close(self):
        """Clean up resources."""
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except Exception as e:
            print(f"Error during disconnect: {str(e)}")
        finally:
            self._connected = False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
