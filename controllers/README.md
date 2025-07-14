# Sunblind Controller

A smart sunblind automation system based on real-time solar position and estimated heat gain. It integrates with **Niko Home Control** to manage motorized blinds based on sunlight exposure and wall orientation.

---

## 🌞 Features

- 🌐 Sun position and elevation calculated with `pvlib`
- 🔥 Heat gain algorithm optimized for low sun angles (morning/evening)
- 🧱 Multi-wall support using wall azimuth per screen
- 🪟 Automatic blind control based on dynamic thresholds
- ⚙️ Flexible callback system for integrating with Niko or simulation
- 📊 Optional visualizations via `sun_analyser.py` using `matplotlib`

---

## 🛠️ Installation

### Requirements

- Python 3.9+
- Install dependencies:

```bash
pip install -r requirements.txt
```


## 🚀 Usage

Run the controller:

```python
from niko_home_control import NikoHomeControlAPI
from controllers.sunblind import SunblindController
import os
import time

niko = NikoHomeControlAPI(
        host=os.getenv("HOSTNAME"),
        username="hobby",
        jwt_token=os.getenv("JWT_TOKEN"),
        ca_cert_path="ca-chain.cert.pem"
    )

# Define callback factory for a named screen
def create_position_callback(name: str):
    def callback(uuid: str, position: int):
        try:
            if uuid:
                niko.set_device_position(uuid, position)
                print(f"{name} → Positie: {position}%")
            else:
                print(f"{name} (simulatie) → Positie: {position}%")
        except Exception as e:
            print(f"Fout bij aansturen {name}: {str(e)}")
    return callback

controller = SunblindController(latitude=50.9383, longitude=4.0393)

# Register each screen with its wall azimuth
controller.register_screen("Bureau", "8cf27bc3-1214-4572-bbcb-d885b1229725", 164.8, create_position_callback("Bureau"), min_step=10)
controller.register_screen("Slaapkamer", "7587f559-f5bc-4723-a9a6-76d6df082973", 256.8, create_position_callback("Slaapkamer"), min_step=10)
controller.register_screen("Living", "4jc0de30-224e-4bd1-b980-b3c9b830b4e6", 256.8, create_position_callback("Living"), min_step=10)

# Start background control
controller.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    controller.stop()
```

The controller will keep monitoring and adjusting your screens automatically. Use CTRL+C to stop it gracefully.