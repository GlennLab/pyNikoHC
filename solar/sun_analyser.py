import math
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.dates import DateFormatter, HourLocator
import pandas as pd
import pvlib


class WallSunlightAnalyzer:
    """
    Analyzes sunlight angles, intensity, and heat gain for a wall at a given azimuth.
    Includes visualizations for daily and yearly profiles.
    """

    def __init__(self, latitude: float, longitude: float, wall_azimuth: float, language: str = 'nl'):
        self.latitude = latitude
        self.longitude = longitude
        self.wall_azimuth = wall_azimuth
        self.language = language.lower()
        self.location = pvlib.location.Location(latitude, longitude, tz='Europe/Brussels')

    def _label(self, key):
        labels = {
            'nl': {
                'light': 'Lichtsterkte',
                'h_angle': 'Invalshoek horizontaal',
                'elevation': 'Zonnehoogte',
                'v_angle': 'Invalshoek verticaal',
                'heat': 'Warmte-inval',
                'sunrise': 'Zonsopkomst',
                'sunset': 'Zonsondergang',
                'time': 'Tijdstip (uren)',
                'value': 'Procent (%)',
                'angle': 'Hoek'
            },
            'en': {
                'light': 'Light Intensity',
                'h_angle': 'Angle of Attack Horizontal',
                'elevation': 'Solar Elevation',
                'v_angle': 'Angle of Attack Vertical',
                'heat': 'Heat Gain',
                'sunrise': 'Sunrise',
                'sunset': 'Sunset',
                'time': 'Time (hours)',
                'value': 'Percentage (%)',
                'angle': 'Angle'
            }
        }
        return labels.get(self.language, labels['nl']).get(key, key)

    def _calculate_sunrise_sunset(self, date: datetime):
        date = datetime(date.year, date.month, date.day)
        times = pd.date_range(date, date + timedelta(days=1), freq='1min', tz='Europe/Brussels')
        solpos = self.location.get_solarposition(times)
        daylight = solpos[solpos['apparent_elevation'] > 0]

        if daylight.empty:
            raise ValueError("No sunrise/sunset: sun doesn't rise on this day")

        sunrise = daylight.index[0].to_pydatetime().replace(tzinfo=None)
        sunset = daylight.index[-1].to_pydatetime().replace(tzinfo=None)
        return sunrise, sunset

    @staticmethod
    def _calculate_angle_of_attack(solar_azimuth, solar_elevation, wall_azimuth):
        az_diff = (solar_azimuth - wall_azimuth + 180) % 360 - 180
        is_back = abs(az_diff) > 90

        az_rad = math.radians(abs(az_diff))
        el_rad = math.radians(solar_elevation)

        angle = 90 - math.degrees(math.acos(max(0, math.cos(az_rad) * math.cos(el_rad))))
        return max(angle, 0), is_back

    def calculate_angles(self, dt: datetime):
        times = pd.DatetimeIndex([dt], tz='Europe/Brussels')
        solpos = self.location.get_solarposition(times)
        row = solpos.iloc[0]
        azimuth = row['azimuth']
        elevation = row['apparent_elevation']
        angle, is_back = self._calculate_angle_of_attack(azimuth, elevation, self.wall_azimuth)

        return {
            'datetime': dt,
            'solar_azimuth': azimuth,
            'solar_elevation': elevation,
            'angle_of_attack': angle,
            'is_back_side': is_back
        }

    @staticmethod
    def _calculate_solar_intensity(info):
        if info['is_back_side']:
            return 0.0

        a = math.radians(info['angle_of_attack'])
        e = math.radians(info['solar_elevation'])
        raw_intensity = math.cos(a) * math.sin(e)
        return max(0.0, raw_intensity * 100)

    @staticmethod
    def _calculate_heat_gain(info):
        if info['is_back_side']:
            return 0.0

        elevation = info['solar_elevation']
        angle_to_horizontal = 90 - elevation
        angle_to_horizontal_rad = math.radians(angle_to_horizontal)

        angle_on_wall_rad = math.radians(info['angle_of_attack'])
        atmospheric_correction = math.exp(-0.2 * (1 / math.sin(math.radians(elevation + 0.1))))

        heat = (
            math.cos(angle_on_wall_rad) *
            math.sin(angle_to_horizontal_rad) *
            atmospheric_correction
        )
        return max(0.0, min(100.0, heat * 100))

    def _generate_daily_data(self, date: datetime):
        sunrise, sunset = self._calculate_sunrise_sunset(date)
        times = pd.date_range(sunrise, sunset, freq='2min')
        data = [self.calculate_angles(t.to_pydatetime()) for t in times]
        return times.to_pydatetime(), data

    def calculate_hitting_time(self, date: datetime):
        sunrise, sunset = self._calculate_sunrise_sunset(date)
        current = sunrise
        hitting_start = hitting_end = None

        while current <= sunset:
            info = self.calculate_angles(current)
            if not info['is_back_side'] and info['angle_of_attack'] < 90:
                if hitting_start is None:
                    hitting_start = current
                hitting_end = current
            elif hitting_start:
                break
            current += timedelta(minutes=1)

        return hitting_start, hitting_end

    def plot_daily_profile(self, date: datetime):
        plt.style.use('seaborn-v0_8-white')
        times, data = self._generate_daily_data(date)
        intensities = [self._calculate_solar_intensity(d) for d in data]
        angles = [d['angle_of_attack'] if not d['is_back_side'] else 0 for d in data]
        elevations = [d['solar_elevation'] for d in data]
        heat_gains = [self._calculate_heat_gain(d) for d in data]

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10), sharex=True)

        ax1.plot(times, intensities, 'b', label=self._label('light'))
        ax2.plot(times, elevations, 'g', label=self._label('elevation'))
        ax2.plot(times, [90 - e for e in elevations], 'c--', label=self._label('v_angle'))
        ax3.plot(times, angles, 'r', label=self._label('h_angle'))
        ax4.plot(times, heat_gains, 'm', label=self._label('heat'))
        ax4.fill_between(times, 0, heat_gains, color='red', alpha=0.1)

        for ax in (ax1, ax2, ax3, ax4):
            ax.legend()
            ax.grid(True)
            ax.axvline(self._calculate_sunrise_sunset(date)[0], color='g', linestyle=':', label=self._label('sunrise'))
            ax.axvline(self._calculate_sunrise_sunset(date)[1], color='g', linestyle=':', label=self._label('sunset'))

        ax1.set_ylabel('%')
        ax2.set_ylabel(f'{self._label("angle") }(°)')
        ax3.set_ylabel(f'{self._label("angle") }(°)')
        ax4.set_ylabel('%')
        ax4.xaxis.set_major_locator(HourLocator())
        ax4.xaxis.set_major_formatter(DateFormatter('%H:%M'))

        plt.suptitle(f"{self._label('heat')} – {date.strftime('%d-%m-%Y')} | Azimut: {self.wall_azimuth}°")

        plt.tight_layout()
        plt.show()

    def plot_comprehensive_daily_profile(self, date: datetime):
        """
        Plot all four key metrics (light, elevation, angle, heat) in one graph.
        Labels are language-dependent (NL/EN).
        """
        plt.style.use('seaborn-v0_8-white')  # Of 'ggplot', 'fivethirtyeight', 'bmh'
        times, data = self._generate_daily_data(date)
        intensities = [self._calculate_solar_intensity(d) for d in data]
        angles = [d['angle_of_attack'] if not d['is_back_side'] else 0 for d in data]
        elevations = [d['solar_elevation'] for d in data]
        heat_gains = [self._calculate_heat_gain(d) for d in data]

        fig, ax = plt.subplots(figsize=(14, 8))
        time_hours = [(t.hour + t.minute / 60) for t in times]

        # Plot metrics
        ax.plot(time_hours, intensities, 'b-', label=f"{self._label('light')} (%)", linewidth=2)
        ax.plot(time_hours, elevations, 'g-', label=f"{self._label('elevation')} (°)", linewidth=2)
        ax.plot(time_hours, angles, 'r-', label=f"{self._label('h_angle')} (°)", linewidth=2)
        ax.plot(time_hours, heat_gains, 'm-', label=f"{self._label('heat')} (%)", linewidth=3)
        ax.fill_between(time_hours, 0, heat_gains, color='red', alpha=0.1)

        # Peak markers
        for metric, color in zip([intensities, elevations, angles, heat_gains], ['blue', 'green', 'red', 'magenta']):
            peak_idx = np.argmax(metric)
            ax.plot(time_hours[peak_idx], metric[peak_idx], 'o', color=color, markersize=8)
            ax.annotate(f'{metric[peak_idx]:.1f}',
                        (time_hours[peak_idx], metric[peak_idx]),
                        textcoords="offset points", xytext=(0, 10), ha='center', color=color)

        # Sunrise/sunset markers
        sunrise, sunset = self._calculate_sunrise_sunset(date)
        sunrise_hour = sunrise.hour + sunrise.minute / 60
        sunset_hour = sunset.hour + sunset.minute / 60
        ax.axvline(sunrise_hour, color='g', linestyle=':', label=self._label('sunrise'))
        ax.axvline(sunset_hour, color='g', linestyle=':', label=self._label('sunset'))

        # Labels
        ax.set_xlabel(self._label('time'))
        ax.set_ylabel(self._label('value'))
        ax.set_title(f"{self._label('heat')} – {date.strftime('%d-%m-%Y')} | Azimut: {self.wall_azimuth}°")
        ax.legend()
        ax.grid(True)
        ax.set_xlim(0, 24)
        ax.set_xticks(np.arange(0, 25, 2))

        # Secondary y-axis
        ax2 = ax.twinx()
        ax2.set_ylim(0, 90)
        ax2.set_ylabel(f"{self._label('angle')} (°)", color='darkred')
        ax2.tick_params(axis='y', labelcolor='darkred')
        for angle in [30, 60, 90]:
            ax2.axhline(angle, color='darkred', linestyle='--', alpha=0.3)

        # Info box
        if self.language == 'nl':
            text = (
                "Belangrijke relaties:\n"
                "- Lagere zonnehoogte → langere lichtweg → meer warmteabsorptie\n"
                "- Optimale invalshoek (30-60°) voor maximale warmteoverdracht\n"
                "- Lichtintensiteit piekt wanneer de zon loodrecht op de muur staat"
            )
        else:
            text = (
                "Key insights:\n"
                "- Lower sun elevation → longer light path → more heat absorption\n"
                "- Optimal incidence angle (30–60°) gives max heat transfer\n"
                "- Light intensity peaks when sun hits the wall directly"
            )

        ax.text(0.02, 0.95, text, transform=ax.transAxes,
                bbox=dict(facecolor='white', alpha=0.8), verticalalignment='top')

        plt.tight_layout()
        plt.show()

