# Draft technical data request — not sent

Suggested recipient: DAERA/NIEA Freshwater Monitoring and Assessment, using the water-information contact on the dataset. An AFBI follow-up may be needed for the mid-lough buoy and White Horse Flats programme.

We are assessing whether Sentinel observations can support independently validated, spatially resolved turbidity estimates for Lough Neagh. We have downloaded the public high-frequency records for Rea's Wood (L1278), Washing Bay (L1279) and Toome (L1284). We are not publishing model-derived NTU: the public data are provisional, and preliminary whole-date/station holdouts do not support a reliable product.

Could you provide or clarify:

1. The complete turbidity observations, including records absent from the public view, with `threshold_exceeded`, `reviewed`, `Published` and any calibration/fouling/maintenance flags. What are the threshold rules, and do the public maxima near 40 NTU reflect an upper publication threshold? Can a validated research extract be supplied?
2. The interpretation of exact zeros and the long continuous zero runs; instrument detection/floor treatment and any offset correction; how conflicting duplicate timestamps should be resolved.
3. Deployment histories, surveyed coordinates, movement/relocation, sample-depth changes, sensor identities, firmware and cleaning/calibration logs. Current commissioning fields are in 2026, while public measurements begin in 2025. Did the earlier records use the same sites and instruments? Is the Toome coordinate in the outlet channel the actual probe position?
4. Original logger timezone, timestamp meaning (instantaneous reading or averaging interval), daylight-saving treatment and clock checks. The API describes UTC; please confirm the source logger chronology, including early irregularly spaced records.
5. Turbidity optical method, wavelength, scattering geometry, calibration standards and field/laboratory comparison data. We need to preserve the distinction between instrument-reported NTU and published satellite algorithms reporting FNU.
6. Older Lough Neagh turbidity observations with exact sample times, locations, depths, units and QA. Please distinguish NTU/FNU from suspended solids, Secchi depth and water colour. The current public feed starts in January 2025; an observation archive overlapping Sentinel from 2015 onward or EOCIS 2016–2023 would be particularly useful.
7. Access to comparable AFBI offshore-buoy, shore-to-offshore transect and lake-monitoring observations. Do these include validated turbidity, water-leaving reflectance, suspended solids, chlorophyll/phycocyanin and bathymetry/clarity?
8. Reuse/attribution requirements, revision policy and whether future validated observations and flags can be supplied through a stable download/API.

We can provide the exact source IDs, timestamp examples, provisional matched dataset and analysis code. No personal information is needed; the request concerns environmental observations and instrument metadata.
