import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Callable, Optional

from solar.sun_analyser import WallSunlightAnalyzer


@dataclass
class Screen:
    """
    Data structure to represent a motorized sunblind (screen).

    Attributes:
        name: Friendly name of the screen (e.g. "Living Room").
        uuid: Device UUID used by Niko Home Control.
        wall_azimuth: Orientation of the wall in degrees (0 = North).
        set_position_callback: Callback function to control the screen.
        full_close_threshold: Heat % threshold to fully close the screen.
        open_step_threshold: Sensitivity for reopening the screen.
    """
    name: str
    uuid: Optional[str]
    wall_azimuth: float
    set_position_callback: Callable[[str, int], None]
    full_close_threshold: float = 20.0
    open_step_threshold: float = 5.0


class SunblindController:
    """
    Manages multiple screens and adjusts them based on sun position and calculated heat gain.

    Methods:
        register_screen: Register a new screen with control logic.
        start: Begin the automatic sunblind control loop.
        stop: Stop the control loop.
    """

    def __init__(self, latitude: float, longitude: float):
        """Initialize the controller with geographic coordinates."""
        self.latitude = latitude
        self.longitude = longitude
        self.screens: Dict[str, Screen] = {}
        self.analyzers: Dict[float, WallSunlightAnalyzer] = {}
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.thread = None

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def _get_analyzer(self, azimuth: float) -> WallSunlightAnalyzer:
        """Return a WallSunlightAnalyzer for a specific wall azimuth, cached per azimuth."""
        if azimuth not in self.analyzers:
            self.analyzers[azimuth] = WallSunlightAnalyzer(
                latitude=self.latitude,
                longitude=self.longitude,
                wall_azimuth=azimuth
            )
        return self.analyzers[azimuth]

    def _calculate_heat_gain(self, analyzer: WallSunlightAnalyzer, dt: datetime) -> float:
        """
        Calculate estimated heat gain for a given wall and time.

        Returns:
            A float between 0 and 100 representing heat load.
        """
        sun_info = analyzer.calculate_angles(dt)

        if sun_info['solar_elevation'] < 0 or sun_info['is_back_side']:
            return 0.0

        elevation = max(sun_info['solar_elevation'], 1)
        angle_to_horizontal = 90 - elevation
        atmospheric_correction = math.exp(-0.2 * (1 / math.sin(math.radians(elevation))))

        heat = (
            math.cos(math.radians(sun_info['angle_of_attack'])) *
            math.sin(math.radians(angle_to_horizontal)) *
            atmospheric_correction
        )
        return min(100.0, max(0.0, heat * 100))

    def _control_screen(self, screen: Screen):
        """
        Determine the current heat load and adjust the screen accordingly.
        Close if above threshold, otherwise set a proportional opening.
        """
        analyzer = self._get_analyzer(screen.wall_azimuth)
        sun_info = analyzer.calculate_angles(datetime.now())
        current_heat = self._calculate_heat_gain(analyzer, datetime.now())

        self.logger.debug(
            f"{screen.name} - Elevation: {sun_info['solar_elevation']:.1f}°, "
            f"Azimuth: {sun_info['solar_azimuth']:.1f}°, "
            f"Heat: {current_heat:.1f}%"
        )

        if current_heat >= screen.full_close_threshold:
            self.logger.info(f"{screen.name}: Volledig sluiten (warmte: {current_heat:.1f}%)")
            screen.set_position_callback(screen.uuid, 0)
        else:
            open_percentage = min(100, int(
                100 - ((current_heat / screen.full_close_threshold) * 100)
            ))
            open_percentage = max(0, open_percentage)

            self.logger.info(f"{screen.name}: Zetten op {open_percentage}% open (warmte: {current_heat:.1f}%)")
            screen.set_position_callback(screen.uuid, open_percentage)

    def register_screen(self, name: str, uuid: Optional[str], wall_azimuth: float,
                        set_position_callback: Callable[[str, int], None],
                        full_close_threshold: float = 20.0,
                        open_step_threshold: float = 5.0):
        """Register a new screen with its orientation and control callback."""
        self.screens[name] = Screen(
            name=name,
            uuid=uuid,
            wall_azimuth=wall_azimuth,
            set_position_callback=set_position_callback,
            full_close_threshold=full_close_threshold,
            open_step_threshold=open_step_threshold
        )
        self.logger.info(f"Screen geregistreerd: {name} (azimuth: {wall_azimuth}°)")

    def start(self):
        """Start the background monitoring and control thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.logger.info("Controller gestart")

    def _run_loop(self):
        """Main loop to regularly update each screen."""
        while self.running:
            for screen in self.screens.values():
                try:
                    self._control_screen(screen)
                except Exception as e:
                    self.logger.error(f"Fout bij aansturen {screen.name}: {str(e)}")
            time.sleep(60)

    def stop(self):
        """Stop the background thread gracefully."""
        self.running = False
        if self.thread:
            self.thread.join()
        self.logger.info("Controller gestopt")

