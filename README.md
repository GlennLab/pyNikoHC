# Niko Home Control API Integration

A Python implementation to interact with the Niko Home Control system via MQTT and REST APIs.

## Features

- Complete implementation of the Niko Home Control API
- MQTT communication for real-time device control and monitoring
- REST API integration for measurement data retrieval
- Device management (control, status checking)
- Location-based device organization
- Comfort sensor identification
- System information retrieval
- Notification handling

## Requirements

- Python 3.7+
- Packages listed in `requirements.txt`

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/niko-home-control.git
   cd niko-home-control
   
2. Install the required packages:
   ```bash
    pip install -r requirements.txt

3. Set up your environment variables in .env file:
   ```text
    HOSTNAME=your.niko.host
    USERNAME=hobby
    JWT_TOKEN=your.jwt.token
    CA_CERT_PATH=path/to/ca_cert.pem
   
4. Run the application:
    ```python
    from dotenv import load_dotenv
    import os
    from niko_home_control import NikoHomeControlAPI
    
    # Load environment variables
    load_dotenv()
    
    # Initialize the API
    niko = NikoHomeControlAPI(
        host=os.getenv('HOSTNAME'),
        username=os.getenv('USERNAME'),
        jwt_token=os.getenv('JWT_TOKEN'),
        ca_cert_path=os.getenv('CA_CERT_PATH')
    )
    
    # Example: List all devices
    devices = niko.list_devices()
    for device in devices:
        print(f"{device['Name']} ({device['Uuid']})")
    
    # Example: Control a device
    niko.set_device_status("device-uuid", "On")
    
    # Example: Get system info
    system_info = niko.get_system_info()
    print(system_info)
    
    # Remember to close the connection
    niko.close()