# Datasets in use

Raw files live in `data/raw/` (gitignored). `data/ingest.py` turns them into
`data/processed/` (gitignored) plus one small committed reference file,
`backend/kb/imd_rainfall_normals.json`. Re-run after adding anything:

```
.venv/bin/python data/ingest.py
```

## 1. ICAR Crop Disease and Insect-pest Image Dataset for Rice and Maize

- Source: data.gov.in catalog "Crop Disease and Pest Image Data" (ICAR-IASRI), resource nid 604953507, ICAR Data Use License.
- File received: `Rice_and_Maize_Dataset.zip`, 970,886,204 bytes, sha256 `2302ec2bc4421009eec040e96acc311d25314b2b3945c2332f726514684cedaf`.
- Extracted to `data/raw/icar_rice_maize/{Rice,Maize}/…` — 852 images, 17 folders, ~50 each, field photos up to 6000×4000.
- **17 exact duplicates** (same bytes, different filename) are dropped by ingest → **835 unique images**. Without this, duplicates can land in both train and test and inflate accuracy.

| Folder | Training class | KB target |
|---|---|---|
| Rice/Disease/01_Bacterial_leaf_blight | rice_bacterial_leaf_blight | rice_bacterial_leaf_blight |
| Rice/Disease/02_Brown_spot | rice_brown_spot | rice_brown_spot |
| Rice/Disease/03_False_smut | rice_false_smut | rice_false_smut |
| Rice/Disease/04_leaf_sheath_blight | rice_sheath_blight | rice_sheath_blight |
| Rice/Healthy | rice_healthy | (healthy) |
| Rice/Insect-pests/05_Leaf_folder | rice_leaf_folder | rice_leaf_folder |
| Rice/Insect-pests/06_Rice_skipper | rice_skipper | rice_skipper |
| Rice/Insect-pests/07_White_stem_borer | rice_white_stem_borer | rice_white_stem_borer |
| Rice/Insect-pests/08_Yellow_stem_borer | rice_yellow_stem_borer | rice_yellow_stem_borer |
| Maize/Disease/01_maydis_leaf_blight | maize_maydis_leaf_blight | maize_maydis_leaf_blight |
| Maize/Disease/02_turcicum_leaf_blight | maize_turcicum_leaf_blight | maize_turcicum_leaf_blight |
| Maize/Disease/03_curvularia_leaf_spot | maize_curvularia_leaf_spot | maize_curvularia_leaf_spot |
| Maize/Disease/04_sorghum_downy_mildew | maize_downy_mildew | maize_downy_mildew |
| Maize/Healthy | maize_healthy | (healthy) |
| Maize/Insect-pests/01_aphid | maize_aphid | maize_aphid |
| Maize/Insect-pests/02_fall_armyworm | maize_fall_armyworm | maize_fall_armyworm |
| Maize/Insect-pests/03_FAW_symptoms | maize_fall_armyworm_damage | maize_fall_armyworm (merged at inference) |

What the dataset does **not** contain, and what that means:
- **No rice blast, tungro or brown planthopper; no maize common rust, banded leaf & sheath blight or stem borer.** These stay in the knowledge base as risk-alert / inspection targets, not photo labels. A blast photo shown to this model will be forced into one of its 17 classes — the confidence gate, the vegetation check and expert escalation are what stand between that and a wrong spray.
- Pest classes are mostly photos of the **adult insect** (moths, skippers, aphids) or larvae, some in petri dishes; only fall armyworm has a separate damage class. Farmers usually photograph damage, so field accuracy on pests will be lower than test accuracy until damage photos are collected through expert confirmations.
- ~50 images per class is small. Use transfer learning, strong augmentation and cross-validated metrics; report them as such.

## 2. IMD rainfall (data.gov.in catalog "Rainfall in India")

| File in `data/raw/rainfall/` | Original download | data.gov.in resource |
|---|---|---|
| imd_subdivision_monthly_1901_2017.xls | datafile.xls | Sub Divisional Monthly Rainfall from 1901 to 2017 |
| imd_all_india_area_weighted_monthly_1901_2015.xls | datafile-2.xls | All India area weighted monthly, seasonal and annual rainfall (mm) 1901-2015 |
| imd_36_subdivisions_area_weighted_monthly_1901_2015.xls | datafile-3.xls | Area weighted monthly, seasonal and annual rainfall (mm) for 36 meteorological subdivisions 1901-2015 |
| imd_subdivision_actual_departure_stats_1901_2015.xls | datafile-14.xls | Subdivision wise Rainfall and its departure from 1901 to 2015 |
| imd_all_india_monsoon_jjas_1901_2019.xls | datafile-15.xls | Rainfall in all India and its departure from normal during Monsoon session (June-Sept) 1901-2019 |
| monsoon_regions/all_india_jjas_1901_2015.xls | datafile-4.xls | Rainfall in All India and its departure from normal, Monsoon (June-Sept) 1901-2015 |
| monsoon_regions/south_peninsula_jjas_1901_2015.xls | datafile-5.xls | … South Peninsula (10 subdivisions) … 1901-2015 |
| monsoon_regions/central_india_jjas_1901_2015.xls | datafile-6.xls | … Central India (10 subdivisions) … 1901-2015 |
| monsoon_regions/north_east_india_jjas_1901_2015.xls | datafile-7.xls | … North East India (7 subdivisions) … 1901-2015 |
| monsoon_regions/north_west_india_jjas_1901_2015.xls | datafile-8.xls | … North West India (9 subdivisions) … 1901-2015 |
| monsoon_regions/north_west_india_jjas_1901_2016.xls | datafile-9.xls | … North West India … 1901-2016 |
| monsoon_regions/north_east_india_jjas_1901_2016.xls | datafile-10.xls | … North East India … 1901-2016 |
| monsoon_regions/central_india_jjas_1901_2016.xls | datafile-11.xls | … Central India … 1901-2016 |
| monsoon_regions/south_peninsula_jjas_1901_2016.xls | datafile-12.xls | … South Peninsula … 1901-2016 |
| monsoon_regions/all_india_jjas_1901_2016.xls | datafile-13.xls | … All India … 1901-2016 |

Region identity was checked, not assumed: each file's 1901 actual ÷ (1 + departure) gives its long-period normal — All India ≈ 871 mm, Central ≈ 982, South Peninsula ≈ 703, North-East ≈ 1286, North-West ≈ 666 — and the order matches the catalog listing.

Quirks handled in ingest: the `.xls` exports trip xlrd's strict stream check (data intact, read with `ignore_workbook_corruption`); IMD spells Marathwada "MATATHWADA" in some releases; capitalisation differs between releases.

Maharashtra = four IMD subdivisions — Konkan & Goa, Madhya Maharashtra, Marathwada, Vidarbha. Their 1901-2015 monthly normals (mean, SD) and a district → subdivision map are in `backend/kb/imd_rainfall_normals.json`; the risk engine uses them to say whether this month's rain is abnormal for the farm's subdivision.

## 3. MoSPI eSankhyiki — pesticide consumption (ENVSTATS)

- Source: `api.mospi.gov.in/api/env/getEnvStatsRecords`, indicator 56 (chemical pesticides) and 58 (bio-pesticide formulations), originally DPPQS; state-wise, 2016-17 → 2023-24.
- Pulled by `data/ingest.py` (through `curl`: this host's TLS setup times out Python's handshake) into the committed `backend/kb/mospi_pesticides.json`.
- **Unit correction:** the API labels values "Million tonnes"; the DPPQS source is MT (metric tonnes, technical grade) — 8,719 million tonnes in one state is impossible. Stored as tonnes, noted in the file.
- Maharashtra 2023-24: 8,719 t chemical, #3 of 31 states, ≈11% of the summed national total. Bio-pesticide figures drop sharply in 2022-23 in the source; shown as published, not verified.

## 4. ICAR Technology repository

- Source: data.gov.in resource "ICAR Technology Repository" (columns: Technology Name, Brief Description, Benefits/Utility, Contact Details), Government Open Data License.
- Received Sep 15 as rows pasted into chat; the CSV file itself is not yet in `data/raw/icar_technologies/`.
- Curated into `backend/kb/icar_technologies.json`: **24 entries** for our four crops, and 7 ICAR institutes with phone and email. The entries are:
  - NBAIR bio-controls for fall armyworm: Bt-25, Metarhizium Ma-35 and SpfrNPV.
  - NRRI Tricho-cards and Bracon cards for leaf folder and yellow stem borer.
  - NBAIR spray- and heat-tolerant Trichogramma and Chrysoperla.
  - CICR sucking-pest-tolerant cotton varieties.
  - The NRRI leaf colour chart, NRRI's riceXpert app and the NCIPM apps.
  - Four AICRPAM crop-weather calendars for Maharashtra.
- Each entry keeps the repository's Technology Name verbatim (`source_name`). `data/ingest.py` checks every entry against the CSV once the file is present.
- How the text is written:
  - Summaries are ours.
  - `claim` fields repeat only what the repository reports, and name who reported it.
  - `link_reason` marks links we drew ourselves, for example "the leaf colour chart prevents excess nitrogen, which invites blight".
- Where it is used:
  - **Farmer advisory:** "Proven by ICAR" shows the farmer-audience entries, with the institute to call.
  - **Expert case:** "ICAR technologies & referral" lists the suspected targets first, then crop-level tools.
  - **Officials' outlook:** "ICAR inputs to stock" per building pest, flagging the NRRI 45-day indent.
- Data-quality notes:
  - The NCIPM email is published as `dirctor.ncipm@icar.gov.in`, which looks like a typo. It is kept as published and flagged in the UI.
  - The repository text is double-encoded in places (`Â“`, `Â•`, `&#8722;`). This was cleaned in the KB, and ingest compares names on plain words only.

## 5. Second wave of image sources — cotton, soybean, more maize and rice (September 2026)

Ingested by `data/ingest_more.py` into `data/processed/more_640/` with
`data/processed/more_images.csv` (path, training class, KB target, crop, source,
backdrop, perceptual hash). **10,174 unique images over 22 classes** after
de-duplication. Each image is compared (dHash, Hamming ≤ 3) against everything
already in `icar_640` and `extra_640`, and against the other new images
(≤ 4), so no photo can sit in a training split and a test split at once;
4,807 near-duplicates were dropped, 851 of them copies of ICAR images we
already had.

| Source id | What it is | Classes kept | Backdrop |
|---|---|---|---|
| `mh_soya` | MH-SoyaHealthVision — Indian (Maharashtra) soybean leaf photos; the UAV half of the set is **not** used, a drone view is not what a farmer's phone sees | 2,782 over 6: rust, yellow mosaic, caterpillar damage, frogeye leaf spot, Septoria brown spot, healthy | field |
| `crops_mix` | A mixed crop-disease compilation (rice, cotton, maize; its wheat and sugarcane folders skipped) | 5,782 over 14: cotton bacterial blight, leaf curl, wilt, aphid, healthy; maize rust, gray leaf spot, ear rot, fall armyworm, healthy; rice blast, brown spot, bacterial leaf blight, tungro | mostly field |
| `cotton_orig` | A cotton leaf set photographed against plain backdrops (Fusarium and Verticillium wilt folders merged, see below) | 1,043 over 4: bacterial blight, Alternaria leaf spot, wilt, healthy | mostly lab/plain |
| `idadp` | IDADP maize set (Chinese field station photos) | 399 over 4: ear rot, common rust, maydis leaf blight, healthy | field |
| `soy_leaves` | A second, smaller soybean leaf set (segmented leaves, Brazilian origin) | 168 over 3: rust, Septoria brown spot, yellow mosaic | plain |

Classes with fewer than 100 unique images after de-duplication are recorded in
the CSV but **not trained**: cotton mealybug (83), American bollworm (50),
whitefly (46), pink bollworm (28), maize stem borer (92) and turcicum leaf
blight from this wave (92). They stay knowledge-base inspection targets with
weather and trap rules, exactly as before.

What this data is **not**, and what we do about it:
- **Fusarium and Verticillium wilt are merged** into one `cotton_wilt` target.
  They cannot be told apart from a leaf photo, and the field response is the
  same. The advisory says so, and sends sudden field-wide wilting after heavy
  rain (parawilt) to an expert instead.
- **Cotton leaf curl** is mainly a north-Indian disease; the photos come from
  there. On a Maharashtra farm the advisory asks for expert confirmation before
  anything is done.
- **Two sources are not Indian** (`idadp`, `soy_leaves`). They are used only for
  classes where Indian photos are thin, and never as the only source for a class
  the app advises on.
- **`cotton_orig` and parts of `crops_mix` are lab/plain backdrops.** They are
  trained with background randomisation (a leaf pasted onto a held-out healthy
  field photo of the same crop) and the deploy gate checks that each new class
  still survives a background swap, so the model cannot pass by learning the
  backdrop.
- Provenance is recorded per image in the CSV; the archives were downloaded by
  the team from public dataset repositories. Where an archive carried no
  licence file, the images are used for training only and none are redistributed
  in this repository (`data/processed/` is gitignored).

## Still to come (see MANUAL_DOWNLOADS.md)

District-wise crop production (APY), temperature series, Kisan Call Centre queries, district rainfall normals 1951-2000, and the ICAR technology CSV file (for the cross-check).

Reachable without manual download: MoSPI eSankhyiki API (`api.mospi.gov.in`) — ENVSTATS has state-wise chemical vs bio-pesticide consumption, useful as the officials' dashboard baseline for "more targeted pesticide use".
