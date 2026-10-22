"""Habitable-zone and Earth-similarity calculations.

Habitable zone limits follow Kopparapu et al. (2014), "Habitable Zones around Main-sequence
Stars: Dependence on Planetary Mass", using the 1 Earth-mass coefficients.
"""

import math
from dataclasses import dataclass, field

SUN_TEFF = 5780.0

# (S_eff_sun, a, b, c, d) per limit
_HZ_COEFFS = {
    "recent_venus": (1.776, 2.136e-4, 2.533e-8, -1.332e-11, -3.097e-15),
    "runaway_greenhouse": (1.107, 1.332e-4, 1.580e-8, -8.308e-12, -1.931e-15),
    "maximum_greenhouse": (0.356, 6.171e-5, 1.698e-9, -3.198e-12, -5.575e-16),
    "early_mars": (0.320, 5.547e-5, 1.526e-9, -2.874e-12, -5.011e-16),
}

ZONE_CONSERVATIVE = "Conservative HZ"
ZONE_OPTIMISTIC = "Optimistic HZ"
ZONE_HOT = "Too hot"
ZONE_COLD = "Too cold"
ZONE_UNKNOWN = "Unknown"


def effective_flux(limit: str, teff: float) -> float:
    """Stellar flux (relative to Earth's) at a habitable zone limit for a star of temperature teff."""
    s0, a, b, c, d = _HZ_COEFFS[limit]
    t = min(max(teff, 2600.0), 7200.0) - SUN_TEFF  # fit is valid for 2600-7200 K
    return s0 + a * t + b * t ** 2 + c * t ** 3 + d * t ** 4


@dataclass(frozen=True)
class HabitableZone:
    """Flux limits (S_earth) and orbital distances (AU) of the habitable zone."""
    flux: dict[str, float]
    distance: dict[str, float]

    @classmethod
    def for_star(cls, teff: float, luminosity: float) -> "HabitableZone":
        flux = {limit: effective_flux(limit, teff) for limit in _HZ_COEFFS}
        distance = {limit: math.sqrt(luminosity / s) for limit, s in flux.items()}
        return cls(flux, distance)

    def classify(self, insolation: float) -> str:
        if self.flux["maximum_greenhouse"] <= insolation <= self.flux["runaway_greenhouse"]:
            return ZONE_CONSERVATIVE
        if self.flux["early_mars"] <= insolation <= self.flux["recent_venus"]:
            return ZONE_OPTIMISTIC
        return ZONE_HOT if insolation > self.flux["recent_venus"] else ZONE_COLD


def earth_similarity_index(radius: float, insolation: float) -> float:
    """Simplified ESI from radius and stellar flux (Schulze-Makuch et al. 2011, PHL variant)."""
    r_term = ((radius - 1) / (radius + 1)) ** 2
    s_term = ((insolation - 1) / (insolation + 1)) ** 2
    return 1 - math.sqrt(0.5 * (r_term + s_term))


def size_class(radius: float | None) -> str:
    if radius is None:
        return "Unknown"
    if radius < 0.8:
        return "Sub-Earth"
    if radius <= 1.25:
        return "Earth-size"
    if radius <= 1.75:
        return "Super-Earth"
    return "Sub-Neptune"


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


@dataclass
class Planet:
    name: str
    host: str
    spectype: str | None
    teff: float | None
    st_radius: float | None
    st_mass: float | None
    luminosity: float | None  # solar units
    distance_pc: float | None
    star_count: int | None
    planet_count: int | None
    radius: float | None  # Earth radii
    mass: float | None  # Earth masses
    mass_provenance: str | None
    insolation: float | None  # Earth flux
    eq_temp: float | None  # K
    period: float | None  # days
    semi_major_axis: float | None  # AU
    eccentricity: float | None
    disc_year: int | None
    method: str | None
    facility: str | None
    ra: float | None
    dec: float | None
    estimated: set[str] = field(default_factory=set)
    hz: HabitableZone | None = None
    zone: str = ZONE_UNKNOWN
    esi: float | None = None

    @classmethod
    def from_row(cls, row: dict) -> "Planet":
        lum_log = _num(row.get("st_lum"))
        planet = cls(
            name=row["pl_name"],
            host=row.get("hostname") or "",
            spectype=row.get("st_spectype") or None,
            teff=_num(row.get("st_teff")),
            st_radius=_num(row.get("st_rad")),
            st_mass=_num(row.get("st_mass")),
            luminosity=10 ** lum_log if lum_log is not None else None,
            distance_pc=_num(row.get("sy_dist")),
            star_count=row.get("sy_snum"),
            planet_count=row.get("sy_pnum"),
            radius=_num(row.get("pl_rade")),
            mass=_num(row.get("pl_bmasse")),
            mass_provenance=row.get("pl_bmassprov") or None,
            insolation=_num(row.get("pl_insol")),
            eq_temp=_num(row.get("pl_eqt")),
            period=_num(row.get("pl_orbper")),
            semi_major_axis=_num(row.get("pl_orbsmax")),
            eccentricity=_num(row.get("pl_orbeccen")),
            disc_year=row.get("disc_year"),
            method=row.get("discoverymethod") or None,
            facility=row.get("disc_facility") or None,
            ra=_num(row.get("ra")),
            dec=_num(row.get("dec")),
        )
        planet._derive()
        return planet

    def _derive(self) -> None:
        """Fill gaps with physically-derived estimates, then evaluate habitability."""
        if self.luminosity is None and self.st_radius and self.teff:
            self.luminosity = self.st_radius ** 2 * (self.teff / 5772.0) ** 4
            self.estimated.add("luminosity")
        if self.semi_major_axis is None and self.period and self.st_mass:
            self.semi_major_axis = (self.st_mass * (self.period / 365.25) ** 2) ** (1 / 3)
            self.estimated.add("semi_major_axis")
        if self.insolation is None and self.luminosity and self.semi_major_axis:
            self.insolation = self.luminosity / self.semi_major_axis ** 2
            self.estimated.add("insolation")
        if self.eq_temp is None and self.insolation:
            self.eq_temp = 278.6 * self.insolation ** 0.25  # zero albedo
            self.estimated.add("eq_temp")
        if self.radius is None and self.mass:
            self.radius = self.mass ** 0.279  # Chen & Kipping (2017), rocky regime
            self.estimated.add("radius")

        if self.teff and self.luminosity:
            self.hz = HabitableZone.for_star(self.teff, self.luminosity)
            if self.insolation is not None:
                self.zone = self.hz.classify(self.insolation)
        if self.radius and self.insolation is not None:
            self.esi = earth_similarity_index(self.radius, self.insolation)

    @property
    def in_habitable_zone(self) -> bool:
        return self.zone in (ZONE_CONSERVATIVE, ZONE_OPTIMISTIC)

    @property
    def distance_ly(self) -> float | None:
        return self.distance_pc * 3.26156 if self.distance_pc is not None else None

    @property
    def size_class(self) -> str:
        return size_class(self.radius)
