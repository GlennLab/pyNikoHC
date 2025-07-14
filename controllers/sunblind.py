import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Callable, Optional, Tuple

from solar.sun_analyser import WallSunlightAnalyzer


@dataclass
class Screen:
    """
    Data structure to represent a motorized sunblind (screen).

    Attributes:
        name: Friendly name of the screen
        uuid: Device UUID used by Niko Home Control
        wall_azimuth: Orientation of the wall in degrees (0 = North)
        set_position_callback: Function to control the screen position
        full_close_threshold: Heat % threshold to fully close
        min_step: Minimum percentage change for movement (5%)
        last_position: Last known position of the screen
    """
    name: str
    uuid: Optional[str]
    wall_azimuth: float
    set_position_callback: Callable[[str, int], None]
    full_close_threshold: float = 20.0
    min_step: int = 5  # Minimum 5% movement step
    last_position: int = 100  # Default to fully open


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

    def _calculate_target_position(self, current_heat: float, screen: Screen) -> Tuple[int, bool]:
        """
        Calculate target position with minimum 5% steps.
        Returns (position, needs_movement)
        """
        if current_heat >= screen.full_close_threshold:
            return 0, abs(screen.last_position - 0) >= screen.min_step

        target = 100 - int((current_heat / screen.full_close_threshold) * 100)
        target = max(0, min(100, target))

        # Apply minimum step
        if abs(target - screen.last_position) < screen.min_step:
            return screen.last_position, False
        return target, True

    def _control_screen(self, screen: Screen):
        """Control screen with minimum 5% movement steps."""
        analyzer = self._get_analyzer(screen.wall_azimuth)
        current_heat = self._calculate_heat_gain(analyzer, datetime.now())

        target_pos, needs_move = self._calculate_target_position(current_heat, screen)
        self.logger.debug(f"{screen.name}: Heat: {current_heat:.1f}%, Target: {target_pos}%, Needs move: '{needs_move}")

        if needs_move:
            self.logger.info(
                f"{screen.name}: Moving from {screen.last_position}% to {target_pos}% "
                f"(heat: {current_heat:.1f}%)"
            )
            screen.set_position_callback(screen.uuid, target_pos)
            screen.last_position = target_pos
        else:
            self.logger.debug(
                f"{screen.name}: No movement needed "
                f"(current: {screen.last_position}%, target: {target_pos}%, heat: {current_heat:.1f}%)"
            )

    def register_screen(self, name: str, uuid: Optional[str], wall_azimuth: float,
                        set_position_callback: Callable[[str, int], None],
                        full_close_threshold: float = 20.0,
                        min_step: int = 5):
        """Register a screen with minimum step control."""
        if min_step < 5:
            self.logger.warning(f"Minimum step forced to 5% for {name} (requested {min_step}%)")
            min_step = 5

        self.screens[name] = Screen(
            name=name,
            uuid=uuid,
            wall_azimuth=wall_azimuth,
            set_position_callback=set_position_callback,
            full_close_threshold=full_close_threshold,
            min_step=min_step
        )
        self.logger.info(f"Registered screen: {name} (azimuth: {wall_azimuth}°, min step: {min_step}%)")
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

