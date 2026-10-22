# Terrabrowser

A desktop app for browsing potentially habitable exoplanets, using live data from the
[NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/) TAP API.

## Running

Requires Python 3.10+ and only the standard library (tkinter).

```
python main.py          # or: python -m terrabrowser
python -m unittest      # run tests
```

## How it works

- **Data**: small planets (radius ≤ 2.5 R⊕, or mass ≤ 10 M⊕ when the radius is unknown) are queried
  from the archive's `pscomppars` table. Results are cached in `~/.terrabrowser/planets.json` for 24 hours,
  and the cache is used as a fallback when offline. Use **Refresh data** to force a new download.
- **Habitable zone**: the conservative (runaway/maximum greenhouse) and optimistic (recent Venus/early Mars)
  limits come from Kopparapu et al. (2014), computed from each star's temperature and luminosity.
- **Earth Similarity Index**: the simplified radius + stellar-flux ESI used by the Planetary Habitability Lab.
- **Estimates**: missing values are derived where possible (luminosity from stellar radius and
  temperature, orbit from period via Kepler's third law, flux from luminosity and orbit, equilibrium
  temperature from flux, radius from mass). They are shown with a `~` prefix.
