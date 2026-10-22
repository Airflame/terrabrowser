import unittest

from terrabrowser.habitability import (
    HabitableZone, Planet, ZONE_CONSERVATIVE, ZONE_COLD, ZONE_HOT, earth_similarity_index,
)


def row(**overrides):
    base = {"pl_name": "Test b", "hostname": "Test", "st_teff": 5772, "st_lum": 0.0,
            "pl_rade": 1.0, "pl_insol": 1.0, "pl_eqt": 255.0}
    base.update(overrides)
    return base


class HabitableZoneTest(unittest.TestCase):
    def test_sun_conservative_limits(self):
        hz = HabitableZone.for_star(5772, 1.0)
        self.assertAlmostEqual(hz.distance["runaway_greenhouse"], 0.95, places=2)
        self.assertAlmostEqual(hz.distance["maximum_greenhouse"], 1.68, places=2)

    def test_classification(self):
        hz = HabitableZone.for_star(5772, 1.0)
        self.assertEqual(hz.classify(1.0), ZONE_CONSERVATIVE)
        self.assertEqual(hz.classify(1.9), ZONE_HOT)  # Venus
        self.assertEqual(hz.classify(0.1), ZONE_COLD)


class EsiTest(unittest.TestCase):
    def test_earth_is_one(self):
        self.assertAlmostEqual(earth_similarity_index(1.0, 1.0), 1.0)

    def test_decreases_away_from_earth(self):
        self.assertLess(earth_similarity_index(2.0, 1.0), earth_similarity_index(1.2, 1.0))


class PlanetTest(unittest.TestCase):
    def test_earth_twin(self):
        p = Planet.from_row(row())
        self.assertEqual(p.zone, ZONE_CONSERVATIVE)
        self.assertAlmostEqual(p.esi, 1.0)
        self.assertFalse(p.estimated)

    def test_insolation_derived_from_orbit(self):
        p = Planet.from_row(row(pl_insol=None, pl_orbsmax=2.0))
        self.assertAlmostEqual(p.insolation, 0.25)
        self.assertIn("insolation", p.estimated)

    def test_orbit_derived_from_period(self):
        p = Planet.from_row(row(pl_insol=None, st_mass=1.0, pl_orbper=365.25))
        self.assertAlmostEqual(p.semi_major_axis, 1.0)

    def test_radius_estimated_from_mass(self):
        p = Planet.from_row(row(pl_rade=None, pl_bmasse=1.0))
        self.assertAlmostEqual(p.radius, 1.0)
        self.assertIn("radius", p.estimated)


if __name__ == "__main__":
    unittest.main()
