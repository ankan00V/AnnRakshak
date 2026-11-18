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

## 3a. DPPQS Statistical Database — pesticide use and demand (primary source)

- Source: `ppqs.gov.in/statistical-database` (Directorate of Plant Protection, Quarantine & Storage), Excel sheets 01–04 and 10: state-wise consumption of chemical and bio-pesticides, state-wise estimated demand with the projection for the next year, and pesticide-wise consumption of indigenous pesticides; 2021-22 → 2025-26.
- Pulled by `data/ingest.py` (`ppqs_pesticides()`, raw sheets in `data/raw/ppqs/`) into the committed `backend/kb/ppqs_pesticides.json`.
- This is the table MoSPI's ENVSTATS series (§3) republishes. Where they overlap (2021-22 → 2023-24) all 78 state-years agree to the tonne, so the dashboard joins them: MoSPI for 2014-15 → 2020-21, DPPQS from 2021-22. Maharashtra 2025-26: 10,106 t chemical, #2 of 26 reporting states, 14.2% of India.
- **Not reported is not zero.** `NR` cells are left out; a state is ranked only among the states that reported that year.
- **Demand is not compared with use.** Demand is in tonnes of formulation; use mixes technical grade and formulation as each state reports it. The Inputs page shows the projection on its own.
- **Pesticide-wise 2025-26 is partial** (16 States/UTs, from the kharif 2026 agenda report), so national trends stop at 2024-25. Pesticide-wise totals cover indigenous pesticides only and are not added to the state totals.

## 3b. CIB&RC Major Uses of Pesticides — every chemical rung checked (16 Nov 2026)

- Source: `ppqs.gov.in/divisions/cib-rc/major-uses-of-pesticides`, the Central Insecticides Board & Registration Committee's lists of uses registered under the Insecticides Act, 1968 — insecticides, fungicides, herbicides, bio-fungicides, bio-insecticides and growth regulators, **as on 30.09.2026**. Each row: crop, pest, a.i. and formulation per hectare, water per hectare, waiting period before harvest.
- Raw PDFs in `data/raw/cibrc/` (`data/verify_doses.py --fetch`). Their tables break apart in text extraction, so each of the 59 chemical rungs was matched to its row by reading it, and the decisions are written into `data/verify_doses.py`, which applies them.
- **Result: 42 rungs stand on a registered use, 17 were removed.** Of the 42, 12 now name a different product because the one we had was not registered for that crop and pest (e.g. rice brown spot: flutriafol 23% SC and mancozeb 68% + hexaconazole 4% WG; rice bacterial leaf blight: copper hydroxide 53.8% DF; brown planthopper: buprofezin 70% DF), and 8 had their dose or water volume corrected to the registered amount per hectare.
- Removed, because nothing in the list registers that product on that crop for that pest: copper oxychloride on rice, cotton and soybean; propiconazole on maize and on rice false smut; emamectin and spinetoram on maize; carbendazim for cotton wilt and soybean septoria; validamycin on maize; metalaxyl + mancozeb on rice and soybean; mancozeb on cotton and for maize gray leaf spot / Curvularia. Several of those problems have **no registered foliar spray at all** (maize gray leaf spot and Curvularia leaf spot, banded leaf and sheath blight, cotton wilt and bacterial blight, rice bacterial leaf streak and downy mildew, soybean downy mildew, bacterial blight, septoria and target spot): their advice is the cultural and biological rungs and an expert, which is what the list supports.
- Every remaining rung carries `registration` (source, crop, pest, formulation per ha, water per ha, waiting days) and `verified: true`; the waiting period is shown to the farmer. `tests/test_engine.py` refuses a chemical rung without a registration, on another crop, or with a dose outside the registered range per hectare.

## 3c. Organic options — the CIB&RC bio-pesticide lists (17 Nov 2026)

- Source: the same CIB&RC Major Uses lists, the **bio-insecticides** and **bio-fungicides** files (as on 30.09.2026): living products (Trichoderma, Pseudomonas, Bacillus subtilis, Bt, Beauveria, Metarhizium, Verticillium, HaNPV) and neem (azadirachtin) products, each with crop, pest, dose per hectare, water and waiting period.
- Matched to our targets by reading each row, as for the chemical rungs; the table is `data/organic_options.py`, which writes an `organic` list into the advisories and the 12 products into `pesticides.json` (`organic: true`, `kind` bio-agent or botanical).
- **29 options on 17 problems**: rice blast, brown spot, bacterial leaf blight, sheath blight, leaf folder, both stem borers, brown planthopper; maize fall armyworm; cotton American and pink bollworm, whitefly, leaf curl, jassid, aphid, bacterial blight; soybean tobacco caterpillar. Spray, seed-treatment and seedling-root-dip uses are kept apart; seed treatments are offered for the next sowing.
- Left out because the list gives no dose: Trichoderma viride 5% LF for rice brown spot (water volume only). The other problems have no bio product registered on that crop for that pest, and the app says so rather than offering one.
- The spray check now recognises these products: neem on rice leaf folder is a registered use; Trichoderma on rice blast is not. `tests/test_engine.py` holds every option to its registered crop and its dose per hectare.

## 3d. Made at home — neem preparations from government IPM guidance (18 Nov 2026)

- What: neem seed kernel extract (NSKE) 5% and neem oil sprays, shown under the registered organic products as "Made at home". They are not registered products, so each rests on a government source that names the preparation, the strength and the pest. The table is `data/homemade_options.py`, which writes `backend/kb/homemade.json` (the two recipes) and a `homemade` list into the advisories.
- Sources, raw copies in `data/raw/ipm/`:
  - NCIPM & DPPQS, *Integrated Pest Management Package* for rice, maize, cotton and soybean (`niphm.gov.in/IPMPackages/<Crop>.pdf`). Soybean: NSKE 5% for early-stage larvae and sucking pests; raw neem oil 1% at 30, 45 and 60 days after sowing for rust. The rice, maize and cotton packages name only registered neem formulations, which §3c already covers.
  - DPPQS advisory on brown planthopper (`ppqs.gov.in/sites/default/files/rce_bph_advisory.pdf`): neem oil 5 ml with 2 ml liquid detergent per litre at the base of the plants; NSKE 5% while the count is below the threshold.
  - APEDA Farmer Connect, IPM with recommended pesticides (Government of India): cotton aphid, jassid, thrips and whitefly, NSKE 5%; cotton leaf curl, control the whitefly; soybean defoliators and sucking insects, NSKE 5%.
  - ICAR-IIMR, *Identification and management of fall armyworm* (on Vikaspedia): 5% NSKE while the young larvae scrape the leaf surface.
  - NSKE recipe: TNAU Agritech (on Vikaspedia). 5 kg of kernels from seed under 8 months old to 100 litres with detergent, i.e. 500 g to a 10-litre tank; spray after 3:30 pm.
- **10 options on 9 problems**: maize fall armyworm; cotton whitefly, aphid, jassid and leaf curl (through the whitefly); soybean tobacco caterpillar, yellow mosaic (through the whitefly) and rust; rice brown planthopper (neem oil, and NSKE below the threshold).
- Left out: the soybean package's cow-urine, cow-milk and asafoetida sprays. They are in a government document, but nothing in it or behind it measures what they do. Also left out: neem cake for maize nematodes, which is not a problem the app advises on.
- `tests/test_engine.py` requires each option to name its source and to read in Hindi and Marathi, not English left standing in; it also checks that NSKE reaches the farmer as 50 g a litre.

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

## 6. Paddy Doctor — rice in the field, on a phone (September 2026)

Ingested by `data/ingest_paddy.py` into `data/processed/paddy_640/` with
`data/processed/paddy_images.csv`. **8,920 unique images over 10 classes** from
10,407 originals; 1,487 near-duplicates dropped, none of them already ours.
Tamil Nadu paddy fields, 2021, photographed on a phone with the variety and the
crop's age recorded — 8,919 of the 8,920 are whole plants in the field.

| Class | Images | | Class | Images |
|---|---|---|---|---|
| healthy | 1,583 | | tungro | 952 |
| leaf blast | 1,489 | | brown spot | 794 |
| hispa | 1,317 | | downy mildew | 508 |
| yellow stem borer (dead heart) | 1,256 | | bacterial leaf blight | 426 |
| bacterial panicle blight | 312 | | bacterial leaf streak | 283 |

Why it was worth importing: rice healthy had 1,530 images and **not one taken in
a field** — single leaves on white paper — so background randomisation had only
34 rice field photos to paste onto, and held-out rice recall fell to 0.59 once
the backdrop was swapped. These are the backgrounds rice was short of.

Four of the ten classes had no advisory when the set arrived — hispa, downy
mildew, bacterial leaf streak and bacterial panicle blight. They were written
into `backend/kb` the same day, because the model must never name something the
app cannot then explain. Dead heart is filed under yellow stem borer: the
dataset does not say which borer left it, and in Tamil Nadu paddy it is nearly
always that one.

  Petchiammal et al., *Paddy Doctor: A Visual Image Dataset for Automated Paddy
  Disease Classification and Benchmarking* (CODS-COMAD 2023); imported from the
  Kaggle mirror `imbikramsaha/paddy-doctor`.

## 7. ASDID — soybean's second camera and second country (September 2026)

Ingested by `data/ingest_asdid.py` into `data/processed/asdid_640/` with
`data/processed/asdid_images.csv`. **9,573 unique images over 8 classes** from
9,648 originals; 75 near-duplicates dropped, none of them already ours. Auburn
University, 2020-21 seasons, three Alabama research stations, a Canon DSLR and a
Moto phone; leaves photographed on the plant at several canopy heights, or
detached and laid on trimmed grass or white card.

| Class | Images (field) | | Class | Images (field) |
|---|---|---|---|---|
| rust | 1,623 (1,222) | | target spot* | 1,067 (513) |
| healthy | 1,622 (1,268) | | potassium deficiency* | 1,024 (791) |
| cercospora leaf blight* | 1,587 (1,356) | | downy mildew* | 637 (436) |
| frogeye leaf spot | 1,531 (1,222) | | bacterial blight* | 482 (382) |

\* new to the app: advisories, weather rules and look-alike cues were written
into `backend/kb` with this import.

Why a non-Indian source for soybean, when the rule elsewhere is Indian photos
first: every soybean photo the model had ever seen came from `mh_soya`, one
Maharashtra dataset, and frogeye leaf spot had 169 of them. Held-out recall on
frogeye and septoria sat under the 0.70 bar that keeps soybean's photo
diagnosis switched off, and the 22 Sep retrain showed the cause was single-source
data, not confusion between crops — the model already puts ~99% of its
probability on the right crop (`ml/eval_crop_scope.py`). A second camera, a
second country and a second season are the thing that was missing. Frogeye goes
from 169 photos to 1,700 and healthy from 204 to 1,826; the healthy field shots
also give background randomisation a real pool of soybean backdrops.

What this data is **not**: Alabama is not Maharashtra. Cercospora leaf blight,
target spot and bacterial blight all occur in Indian soybean, but the varieties,
the light and the soil are different, so the ASDID classes are capped like Paddy
Doctor's (900 train / 120 val / 200 test) rather than let in whole, the Indian
photos keep their weight inside every shared class, and the advisories for the
five new problems carry the usual expert trigger. Potassium deficiency is not a
disease at all — it is in the model so the app can say "this is a nutrient
shortage, do not spray" instead of naming a disease that is not there.

  Wadkar, Bagal, Kumar et al., *Soybean disease identification using original
  field images and transfer learning with convolutional neural networks*,
  Computers and Electronics in Agriculture 203 (2022) 107449. CC0, from the
  Zenodo mirror (record 7304859); Dryad serves the same files behind a bot wall.

## 8. Hand-downloaded rice and soybean sets (September 2026)

Ingested by `data/ingest_downloads.py` from `~/Downloads` into
`data/processed/local_640/` with `data/processed/local_images.csv`.
**7,013 unique images over 7 classes**, out of roughly 20,000 read.

| Source | Kept | What it is |
|---|---|---|
| `riceleafbd` | 1,451 | RiceLeafBD — real-field phone photos, Bangladesh: BLB, brown spot, tungro, healthy |
| `rice_bd_field` | 1,373 | Rice Leaf and Crop Disease Detection Dataset, `orginal` folders only |
| `soy_brazil` | 3,874 | Brazilian soybean canopies: caterpillar damage 3,081, healthy 793 |
| `crops_multi` | 218 | a mixed multi-crop download; only its rice and healthy maize concern us |
| `rice_leaf_5932` | 97 | the 5,932-image rice leaf set — **5,835 of them we already had** |

That last row is the de-duplication earning its keep: a set that looks like
6,000 new images was 98% photos already in `more_640`. Counting downloads is
not counting data.

Left out, and why:
- **Diabrotica speciosa (2,205)** — a South American beetle. Naming it would be
  naming something an Indian farmer's field cannot have.
- **Maize streak virus (401)** — African, same reason. And "Maize leaf blight"
  (493) does not say turcicum or maydis, which are separate targets here with
  different advisories.
- **A folder labelled only "Rice" (585)** — panicles on white paper with no
  problem named. A label cannot be invented.
- **Every augmented copy (8,258)** — training makes its own; a flipped copy of
  a test photo sitting in the training split is how a model scores well on
  nothing.
- Segmentation masks, rice-panicle detection boxes, potato, tomato, cashew.

The Brazilian caterpillar is not the same species as ours. What the model learns
is chewed leaves, and the advisory behind our target (tobacco caterpillar) is
the one an Indian farmer needs when a defoliator is in the crop; the class is
named `soybean_caterpillar_damage` for that reason.

## 9. Cotton from Mendeley Data (September 2026)

Ingested by `data/ingest_cotton.py` into `data/processed/cotton_640/` with
`data/processed/cotton_images.csv`. **2,984 unique images over 8 classes** from
three sets: `b3jy2p6k8w` (SAR-CLD-2024) kept 1,996, `74jsdxtmx2` (severity
levels) 958, and `t9hgvk2h9p` just 30 — 98% of it was already ours as
`cotton_orig`.

What it changes: cotton had six classes from two sources, and three things the
app talks about had no photograph behind them.

| Class | Images (field) | Why it matters |
|---|---|---|
| `cotton_jassid` | 223 (190) | an advisory, weather rules and inspection tasks since September, and until now not one image |
| `cotton_leaf_reddening` | 571 (498) | **not a disease** — cold nights, magnesium or nitrogen shortage, waterlogging |
| `cotton_herbicide_damage` | 279 (86) | **not a disease** — drift or sprayer residue |
| `cotton_healthy` | 1,049 (965) | cotton's backdrop pool for background randomisation, 269 -> 913 |
| `cotton_leaf_curl` | 438 (334) | was 225 from one source |
| `cotton_bacterial_blight` | 370 (279) | |

The two that are not diseases are the point. A farmer who reads reddening or
spray damage as a disease buys a fungicide that cannot work, so both advisories
lead with "do not spray a fungicide for this", and herbicide damage sends a
badly hit field to an officer — a claim against whoever sprayed rests on that
report. "Leaf variegation" (117) was left out: variegation has viral and
genetic causes and the app would have nothing certain to say.

## 10. Three sets for the classes that were too thin (30 Sep 2026)

The 29 Sep candidate passed thirteen of fourteen deploy checks and missed the
last — accuracy when the app advises — by four photographs. Two of those four
were the same class, rice leaf folder, read once as white stem borer at 0.95
confidence. Leaf folder had 49 images and sheath blight 50, both ICAR-only,
inside a model carrying 46 classes trained on 47,000 photographs. A class that
thin cannot hold its ground, and the gate was right to refuse it. These three
sets were fetched for exactly those classes.

| Source | Kept | What it is |
|---|---|---|
| `paddy_pests` (`data/ingest_pests.py`) | 149 | rice leaf folder, from Mendeley `y5hwbhrn5m` |
| `dhan_shomadhan` (`data/ingest_dhan.py`) | 561 | Bangladeshi rice, Mendeley `znsxdctwtt` |
| `rice_bd_fungal` (`data/ingest_ricebd.py`) | 1,281 | Sirajganj and Pabna, 2023, Mendeley `hx6f852hw4` |

What it changed, for the two classes it was fetched for:

| Class | Before | After |
|---|---|---|
| `rice_sheath_blight` | 50 | **555** (234 + 271 new) |
| `rice_leaf_folder` | 49 | **198** |

Blast, tungro, brown spot, hispa, bacterial leaf blight and healthy gain
Bangladeshi diversity alongside them, and rice's pool of field backdrops for
background randomisation grows from 1,114 to 1,235.

Left out, and why — the same rule each time, that the model must never learn to
name a problem `backend/kb` cannot then explain:

- **Stem borer, 172 photos.** Every one an adult moth, posed. Our stem borer
  classes mean dead hearts and white ears; a moth portrait teaches neither.
- **Leaf scald (234 + 231) and narrow brown leaf spot (166).** Both are real
  diseases that occur in India. Neither has an advisory yet. An advisory first,
  then the import.
- **Green leafhopper, rice bug, whorl maggot, brown planthopper.** Not targets
  the app advises on, and the same reference-macro framing as the stem borers.

Two notes for anyone re-running these. Dhan-Shomadhan misspells its folders and
inconsistently — sheath blight arrives as both `Shath Blight` and
`Sheath Blight`, tungro as `Rice Tungro` and `Rice Turgro` — so the mapping is
written out by hand rather than matched on text, where a typo would quietly
drop a class. And the pest set ships near-duplicate crops of single
photographs, so its de-duplication uses a wider hamming distance than the
others: two crops of one photo landing either side of a train/test split would
flatter the result and teach nothing.

The pest set had been looked at once before and turned down whole, on the
strength of its brown planthopper folder. That judgement was right for that
folder and wrong as a judgement of the set: its leaf folder photographs are
mostly damage — the rolled leaf, the white scraped streaks, the caterpillar in
place — which is the signature the app names. The unit of judgement is the
folder, not the download.

## 11. Third wave — Hugging Face, two more Mendeley sets, false smut (17 Nov 2026)

Fetched for the classes still short of photographs, and for one specific
failure: a farmer's wider photo of a false smut panicle was named bacterial
leaf blight. False smut had 50 photographs, all close-ups from one set.

| Source | Kept | What it is |
|---|---|---|
| `data/ingest_hf.py` | 1,116 | Hugging Face: maize gray leaf spot (1,034, `muAtarist/maize_foliar_diseases`), ear rot (32) and fall armyworm (29) from `sairiamu/maize_desease_dataset`, cotton Alternaria (19, AgML) |
| `data/ingest_mendeley2.py` | 1,785 | Mendeley `3myfctrgk3` (MLD, Jhenaidah, Bangladesh): fall armyworm 520, gray leaf spot 490, healthy 340. `5wp23rgtpy` (MNS University, Multan): cotton aphid 338. `sb4wwjs8bz` (Bangladesh, 2026), converted raw photos only: healthy 67, common rust 19, gray leaf spot 11 |
| `data/ingest_vnrice.py` | 87 | Rice false smut: Mendeley `gpsft4c2zy` (Sambalpur University, Odisha; CC BY 4.0) 43, and the false smut class of `minhhungg/rice-disease-dataset` (Apache-2.0) 44 |

Every photo is de-duplicated against everything already in `data/processed`
(dHash, Hamming ≤ 3) and within its import (≤ 4), so most of what these sets
share with ours added nothing. That is the expected result, and checking for
it was the point. AgML's Bangladesh cotton set came back almost entirely
duplicate; its augmented configurations are skipped outright. Mendeley archives
and files are checked against the SHA-256 the API publishes. Hugging Face
Parquet shards are read a row group at a time over HTTP range requests
(`data/hf_range.py`), so only the labels we map are downloaded.
`HF_TOKEN` is read from `.env`.

**Most of the Vietnamese rice set was imported, examined and turned down.**
Most of its photos are generated copies rather than photographs: 925 of 1,560
sheath blight, 204 of 209 bacterial leaf blight and 319 of 394 tungro have the
smeared border of a shifted image, and many pest photos are mirrored copies of
each other (the mirrored text gives them away). A copy teaches nothing new and
leaks one photograph into both the training and the test split. What remained
was web-scraped: collages, QR codes, stock watermarks. Its leaf folder and
yellow stem borer classes show the adult moth, where ours show the damage. Its
false smut class was the exception, so it is the only class kept, and every
photo kept from that set passes a smeared-border check and a mirrored-copy
check.

Left out: every "Leaf Blight" / "Corn Leaf Blight" folder (Mendeley MLD and
sb4, CCMT, Hugging Face), because none says which blight. Ours are turcicum
(northern) and maydis (southern), with different advice, and an unsorted pile
would teach the model to confuse them. Eyespot, maize streak and bacterial
leaf streak are not targets the app advises on.

What it changed (model `…+wave3-…-20261117`, against the model it replaced):

| | Before | After |
|---|---|---|
| ICAR field test, top-1 / macro F1 | 0.889 / 0.639 | 0.889 / **0.692** |
| Accuracy when the app advises | 0.973 | 0.973 |
| Extra-source test, top-1 | 0.867 | **0.900** |
| Rice bacterial leaf blight | 0.390 | 0.583 |
| Rice blast | 0.826 | 0.909 |
| Rice sheath blight | 0.792 | 0.909 |
| Maize turcicum leaf blight | 0.833 | 0.933 |
| Rice false smut (14 held-out photos) | — | 1.000 |

The farmer's close-up of false smut is now named at 0.98 and passes the
familiarity check. A wider shot of an early infection, with small orange balls
scattered through a green panicle, is named false smut at 0.60–0.85 but still
scores below the familiarity threshold and goes to an expert. Early-stage,
distant photographs of false smut are the next thing to find.

## 12. What was looked for on 18 Nov 2026, and what it settled

**Unsorted maize blight: turned down after looking.** About 700 photos were
left out of §11 because their sets say "Leaf Blight" or "Corn Leaf Blight"
without saying which: 489 in MLD (`3myfctrgk3`) and 220 in `sb4wwjs8bz`. The
plan was for the deployed model to propose turcicum or maydis and for a person
to check every proposal. The model proposed none: 213 were already in our data,
87 it found unfamiliar, and the rest it read as gray leaf spot (353), fall
armyworm damage (122), healthy (108) and others. Looking at them settles why.
MLD's are green leaves with small whitish-tan flecks and short streaks, not the
long cigar-shaped lesions of northern blight or the straight-sided tan lesions
of southern blight. The sb4 photos are mostly red-purple streaking along the
midrib, yellowing and dried tips, which looks like stress or senescence rather
than either blight. Naming them as either would be a guess. Northern blight
came instead from a set labelled by disease (§13). Southern blight (maydis)
still has no field set; the ICAR-IIMR Ludhiana set (below) is the lead.

**The thinnest classes: nothing public.** Maize aphid, Curvularia leaf spot
and downy mildew, rice skipper and white stem borer each have 6 to 8 photos.
Searched Mendeley, Hugging Face, Zenodo and the dataset-survey literature:
- `sb4wwjs8bz`'s description lists a Curvularia class, but no such files are in it.
- No open field set exists for maize aphid or maize downy mildew.
- Mendeley `hnfjs42d5g` (Bangladesh, 2025) has dead hearts and white heads, but
  those symptoms are shared by every stem borer and do not say white from yellow,
  so the label would be a guess.

These classes will come from the field. Team photos go through the app;
an expert confirms them; `ml/export_confirmed.py` turns the confirmations into
training data. The one labelled downy mildew set found ("Bulai Daun",
Indonesian, on Roboflow Universe) needs a Roboflow account to download.

What to photograph: at least 30 photos per class, from at least 3 fields. Use
a phone in daylight, from about a hand's length, with one problem per photo.
Take a few wider shots as well, because the app is now asked for those.

| Class | Photograph | Not to be confused with |
|---|---|---|
| Maize aphid | Colonies of small blue-green aphids on the whorl, tassel and upper leaves; sticky honeydew and sooty mould under them | Fall armyworm frass in the whorl |
| Curvularia leaf spot | Small round to oval spots, 1-2 mm, pale centre with a dark brown ring and a yellow halo | Maydis blight (longer, straight-sided lesions) |
| Maize downy mildew | Chlorotic stripes running the leaf's length, white downy growth on the underside in the early morning, plants stunted | Nutrient striping (no down on the underside) |
| Rice skipper | Leaf ends rolled and tied lengthwise into tubes, green caterpillar with a large head inside | Leaf folder (folds leaf lengthwise, white scraped streaks) |
| Rice white stem borer | Dead hearts and white ears together with the adult: a white moth with no dot on the wing (yellow stem borer has a black dot). Species can only be named from the moth or the larva | Yellow stem borer |

Each photo should be confirmed in the expert console by someone who saw the
plant, not only the photo.

**`ml/export_confirmed.py` had a leak, now closed.** Of the 26 photos experts
had confirmed in the app's database, 8 were held-out test photos (the team
checks the app with dataset photos) and 10 were the same upload confirmed again.
Trained on, the first kind is a test answer learnt by heart. Both are now left
out by perceptual hash, so the export holds 8 clean photos.

**Plants that are not our crops: `data/fetch_ood.py`.** 600 photos, none
trained on, for testing the photo checks: bean leaves (`AI-Lab-Makerere/beans`),
field weeds (DeepWeeds, `Project-AgML/rangeland_weeds_australia`) and
PlantVillage's crops other than maize and soybean. They showed two things:
- **The zoom-in was tested, and it does not answer.** Reading a wide, unfamiliar
  photo from its most familiar part was proposed to rescue a farmer's wide shot
  of false smut. On held-out photos the model found unfamiliar, it was right
  10 times in 29 when it went on to advise, and it carried 158 of these 600
  other-plant photos through to advice. It now only marks the part to
  photograph up close (`vision.closer_region`), and the photo still goes to an
  expert.
- **The familiarity check alone passes about a third of other-plant photos**:
  beans 66 of 200, weeds 79, PlantVillage 44. What then stops a bean leaf
  becoming rice advice is the farm's registered crop (CROP_MISMATCH) and the
  per-class bars, not familiarity. Worth a negative "not our crop" set in the
  familiarity bank, measured on these photos.

## 13. CD&S — northern leaf blight in the field (18 Nov 2026)

| Source | Kept | What it is |
|---|---|---|
| `data/ingest_cds.py` | 497 | CD&S dataset (Ahmad, Saraswat, El Gamal & Johal, Purdue; arXiv 2110.12084; OSF `s6ru5`), `Dataset_Original` northern leaf blight, train and test folders |

Handheld photos from maize field trials, sorted by disease by the
researchers. All 497 were new to our data. A sample was checked by eye: long,
cigar-shaped tan lesions, northern leaf blight as it looks in the field. The
set's other folders are the same photos with the background removed or
replaced, so they are not used. Its gray leaf spot is not used either
(already plentiful), and its northern leaf spot is not a problem the app
advises on. Each file is checked against the SHA-256 OSF publishes for it.

Looked at for the same class and not used: the Cornell NLB set (Wiesner-Hanks
et al. 2018, OSF `p67rz`). Its lesion annotations are gone from OSF (all three
CSVs return 404), and the paper says some photos have no visible lesion; the
study that first used them split them roughly 1,028 with lesions to 768
without. Without the annotations, labelling the set as blight would be wrong
for about 4 photos in 10.

## Evaluated and turned down

- **Paddy Field Pest Image Dataset** (Mendeley `y5hwbhrn5m`, 833 originals):
  brown planthopper, stem borer, leaf folder and three more. The images are
  textbook macro shots of the insects — some are labelled plates from extension
  manuals, several are near-duplicate crops of one photo. A farmer's phone never
  frames a shot like that, so it would teach the model "macro insect photo",
  not "planthopper in my field". Brown planthopper stays an inspection target
  with weather rules and a counting task, which is how that pest is actually
  found: by shaking the hill, not by photographing a leaf.
- **BOLLWM** (Wadhwani AI, ~13k Indian cotton images): pink and American
  bollworm moths in pheromone traps, with boxes. It fits our trap rules rather
  than photo diagnosis, and it is a different product decision — noted, not
  taken.
- **ICAR-IIMR maize** (Sci Rep 2022; MLB, TLB, banded leaf and sheath blight,
  healthy; 5,939 field images from Ludhiana): the one set that would give BLSB
  a photograph. Not in a repository — "available from the corresponding author
  on reasonable request" (sudeep@icar.gov.in). Worth an email.

## AIKosh — searched, and what it settled (1 Oct 2026)

AIKosh is the Government of India's AI datasets repository (`aikosh.indiaai.gov.in`),
reached through its official Python SDK with the team's own API key in `.env`
(`data/aikosh_search.py`). It was searched for exactly the classes the model is
thinnest on: maize maydis leaf blight, curvularia, downy mildew and aphid; rice
false smut, skipper and white stem borer.

**It has no new crop imagery for any of them.** Its one crop-disease image
dataset is the ICAR rice and maize set this repo is already built on — 971 MB
there against the 933 MB copy in `data/raw/icar_rice_maize`, the same release.
That is a negative result worth writing down, because it closes a line of
enquiry that looked promising: the remaining thin classes will not be fixed
from this source.

Two things it did give us.

**Provenance.** The ICAR images now have an official government home to cite —
AIKosh dataset `2448fb9b-d9c5-4f68-a3e2-dea280d6a73d`, published by DARE/ICAR —
rather than "downloaded by the team from a public repository". For the dataset
the deploy checks are measured on, that matters.

**A lead for Krishi, not for the model.** "Farmer Query Signal Intent Dataset"
(`25169990-a8fb-41b4-978c-8113a7e418a6`, Symbiosis) is hand-written
agricultural queries in Hindi. Krishi's intent routing has never had a labelled
set of real farmer questions to be measured against, and this is one.

## Still to come (see MANUAL_DOWNLOADS.md)

District-wise crop production (APY), temperature series, Kisan Call Centre queries, district rainfall normals 1951-2000, and the ICAR technology CSV file (for the cross-check).

Reachable without manual download: MoSPI eSankhyiki API (`api.mospi.gov.in`) — ENVSTATS has state-wise chemical vs bio-pesticide consumption, useful as the officials' dashboard baseline for "more targeted pesticide use".
