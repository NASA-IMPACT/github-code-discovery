# Importing the necessary libraries
from __future__ import annotations

import asyncio
import sys
from enum import Enum

import pandas as pd
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

load_dotenv()
# os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY")

# Define the model
openai_model = OpenAIModel("gpt-4.1-mini")
SAMPLE_AVERAGE_COST = 0.002273
INPUT_COST_PER_1M = 0.40
OUTPUT_COST_PER_1M = 1.60
# Check pricing here: https://platform.openai.com/docs/pricing


# Output Model
class NasaArea(str, Enum):
    EARTH_SCIENCE = "Earth Science Division"
    PLANETARY_SCIENCE = "Planetary Science Division"
    ASTROPHYSICS = "Astrophysics Division"
    HELIOPHYSICS = "Heliophysics Division"
    BIOLOGICAL_PHYSICAL_SCIENCES = "Biological and Physical Sciences Division"
    NOT_NASA_DIVISION = "Not a NASA Division"


# Output Schema
class ReadmeClassification(BaseModel):
    area: NasaArea = Field(
        ...,
        description="The NASA area the README content best fits into. If none, select 'Not a NASA Division'.",
    )
    reasoning: str | None = Field(
        None,
        description="A brief explanation for the classification choice.",
    )


# Context from SDE
evaluation_criteria = """
### Earth Science Division
#### Overview
NASA’s Earth Science Division develops and operates satellite, airborne, and ground-based programs to observe and analyze Earth’s atmosphere, oceans, land, ice sheets, and ecosystems in order to understand climate dynamics, natural hazards, and environmental change.
#### Study Areas & Examples
* Agriculture & Water Cycle Monitoring
  * Soil moisture and precipitation studies using SMAP and GRACE missions.
* Carbon Cycle & Atmospheric Composition
  * Tracking greenhouse gases with the Orbiting Carbon Observatory-2 (OCO-2).
* Sea-Level & Cryosphere Dynamics
  * Measuring ocean height and ice-sheet elevations with Sentinel-6/Jason CS and ICESat-2.
* Land Cover & Ecosystem Change
  * Assessing vegetation and land-use via MODIS instruments on Terra and Aqua.
* Disaster Preparedness & Response
  * Supporting flood, wildfire, and hurricane monitoring through the GOES weather satellites.
---
### Planetary Science Division
#### Overview
NASA’s Planetary Science Division explores planets, moons, asteroids, and comets throughout the solar system via robotic spacecraft, sample returns, and telescopic observations to unravel its formation history and search for signs of past or present life.
#### Study Areas & Examples
* Inner Solar System Exploration
  * MESSENGER at Mercury, Magellan at Venus, and Lunar Reconnaissance Orbiter at the Moon.
* Mars Habitability & Geology
  * Rovers Curiosity and Perseverance, and the InSight lander studying Martian surface and interior.
* Outer Planets & Ocean Worlds
  * Juno at Jupiter, Cassini at Saturn, and the forthcoming Europa Clipper mission.
* Small Bodies & Sample Return
  * OSIRIS-REx (asteroid Bennu), Hayabusa2 (asteroid Ryugu), Lucy (Trojan asteroids), and New Horizons (Pluto).
* Planetary Defense
  * Detecting and tracking near-Earth objects with NEOWISE and coordinating response via the Planetary Defense Coordination Office.
---
### Astrophysics Division
#### Overview
NASA’s Astrophysics Division seeks to understand the universe’s origin, structure, evolution, and potential for life by deploying space observatories and supporting theoretical research to address fundamental cosmic questions.
#### Study Areas & Examples
* Cosmic Origins
  * Mapping early galaxies and star formation with Hubble’s Cosmic Origins Spectrograph.
* Physics of the Cosmos
  * Investigating dark matter, dark energy, and black holes with the Chandra X-ray Observatory.
* Exoplanet Exploration
  * Discovering and characterizing exoplanets using Kepler and TESS missions.
* Flagship Observatories
  * Operating large telescopes—Hubble and James Webb—to observe deep-space phenomena.
---
### Heliophysics Division
#### Overview
NASA’s Heliophysics Division studies the Sun, solar wind, and heliosphere to understand space weather, magnetic reconnection, and their impacts on planetary environments and technology.
#### Study Areas & Examples
* Solar Dynamics
  * Investigating the solar corona and wind acceleration with Parker Solar Probe and Solar Dynamics Observatory.
* Space Weather & Magnetospheres
  * Monitoring geomagnetic storms and radiation belts using Van Allen Probes and the Magnetospheric Multiscale Mission (MMS).
* Heliosphere & Interstellar Boundary
  * Mapping the heliosphere’s edge with Voyager spacecraft and IBEX.
* Heliophysics System Observatory
  * Coordinating a fleet of missions to study solar-terrestrial interactions across the solar system.
---
### Biological and Physical Sciences Division
#### Overview
NASA’s Biological and Physical Sciences Division leverages microgravity and space radiation to conduct fundamental research in life sciences and physical sciences, supporting long-duration space exploration and improving life on Earth.
#### Study Areas & Examples
* Space Biology
  * Studying molecular, cellular, plant, animal, and human biology aboard the ISS to understand microgravity effects.
* Physical Sciences
  * Investigating biophysics, combustion, fluid dynamics, materials science, and fundamental physics in space.
* Technology & Applications
  * Developing quantum sensors, atomic clocks, and tissue-chip systems for both spaceflight and Earth applications.
* Data & Open Science
  * Sharing results via open platforms like GeneLab and the Physical Sciences Informatics System (PSI).
"""

few_shot_example_1_input = r"# Object-Based Image Analysis (OBIA) and Machine Learning (ML) Applied to High Spatial Accuracy Forest Mapping in Paraná, Southern Brazil This repository organizes the Mapped codes for Machine Learning in GEE Requisites: Google Earth Engine (GEE)"
few_shot_example_1_output = f"""{{
  "area": "{NasaArea.EARTH_SCIENCE.value}"
}}"""

few_shot_example_2_input = r"#Data and code generated for DryFlux #Final Submission to Nature Communications Earth & Environment on Oct2021 Ecohydrological water-carbon coupling improves dryland carbon flux prediction of average uptake, interannual variability, and drought Authors: Barnes, Mallory L.; Farella, Martha M.; Scott, Russell L.; Moore, David J.P.; Ponce-Campos. Guillermo E.; Biederman, Joel A.; MacBean, Natasha; Litvak, Marcy E.; and Breshears, David D. Year: 2021 Title: Data and code for DryFlux Corresponding Author for Code: Martha Farella, Indiana University, O'Neill School of Public and Environmental Affairs, farellam@iu.edu License: MIT DOI: --------------------------------------------- ## Summary Contains code and data used for DryFlux and the analysis presented in Nature Communications Earth & Environment manuscript, Ecohydrological water-carbon coupling improves dryland carbon flux prediction of average uptake, interannual variability, and drought --------------------------------------------- ## Files and Folders code: code used in the analysis presented in the manuscript. MATMAPelev.R: get metadata for the Flux tower sites. 1.download SRTM elevation tiles and extract values for site locations 2. download WorldClim MAT/MAP tiles and extract data for site locations; 3. combine 1 and 2 into a single dataframe; 4. determine the OzFlux sites that fall within the 'dryland regions' defined by United Nations Environment World Monitoring Centre; 5. get boundaries for US, mexico, and Australia territories SPEI: code used to compute SPEI and extract meterological variables for flux tower locations. CRU data downloaded from: https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.04/cruts.2004151855.v4.04/ meterological variables downloaded included: precipitation (pre), tmin (tmn), tmax (tmx), vapor pressure (vap), potential evapotranspiration (pet), and Tavg (tmp) for time periods: 1991-2000; 2001-2010; 2011-2019; citation: Harris et al. (2020) doi:10.1038/s41597-020-0453-3 combineNCD.R: combine the seperate cru .nc files into a single file that contains oberservations from 1991 - 2019 for each variable needed to calculate spei (pet and precip) computeSPEI.R: This script computes the global SPEI dataset at different time scales. One netCDF file covering the whole globe and time period is generated for each time scale, e.g. spei01.nc for a time scale of 1 month, etc. Output files are stored on DryFlux/data/outputNcdf functions.R: dependencies for 'computeSPEI.R' SPEIextract: code used to extract cru data values for flux tower locations, pre-process for downstream analysis, and create rasters for upscaling; lines 13:90 are for SPEI extraction; lines 92:144 are for the other meterological variables; lines 146:177 are for last month precip and Tavg; lines 179:340 are for OzFlux sites; lines 345:438 raster layer creation MODISprocessing.R: used to convert hdf files to a single .csv file for each year where ndvi and evi values are extracted for flux tower locations and data formatted (single row/observation for each site/date) for downstream analysis also create .tif EVI and NDVI raster layers; .hdf data products downloaded from: https://e4ftl01.cr.usgs.gov/MOLT/MOD13C1.006/ 16th day global 0.5deg CMG MOD13C1; Date downloaded is the date closest to the 15th/16th of each month; citation: Didan, K. (2015). MOD13C1 MODIS/Terra Vegetation Indices 16-Day L3 Global 0.05Deg CMG V006 [Data set]. NASA EOSDIS Land Processes DAAC. Accessed 2020-10-13 from https://doi.org/10.5067/MODIS/MOD13C1.006 daylength.R: determine daylength of sites based on dates of CRU dates; create daylength rasters; daylength calculated using the 'daylength' function in the 'geosphere' R package; daylength calculated on the 15th or 16th of each month in accordance with CRU dates for each flux tower location.; raster stack created for the whole world with daylengths for each of the 348 CRU dates CleanFlux.R: get fluxtower GPP values for mid-month time frames from the daily Fluxtower MatLab files MOD17A2Hdl.txt: code used on google EarthEngine to download individual .csv files of MODIS 8-day global 500m GPP data products (MOD17A2H) for each flux tower site. MODIS_GPP.R: get MODIS GPP values in format needed for downstream analysis. MODIS 8-day global 500m GPP data products (MOD17A2H) downloaded with google EarthEngine using code on 'MOD17A2Hdl.txt'. Fluxcom_extract.R: extract daily Fluxcom predictions for tower locs, then calc mid-month GPP vals; daily Fluxcom GPP predictions requested from Fluxcom data administrator OxFlux.R: get OzFlux GPP values formatted for downstream analysis data_prepro.R: combine all response and explanatory variables together into a single dataset for model building, testing, and analysis RF.R: Build the Random Forest Machine Learning Models, save model outputs and evaluate performance applyRF_loop.R: Apply the random forest model to raster layers to predict global GPP across all months RFevaluation.R: Evaluate model performance. Create a dataframe with observed and predicted GPP values from DryFlux, MODIS, and Fluxcom. Create Fig1a-c, Fig2a-b, Table S2 and S5, Figs. S2, S3, S5, and S6 RFseasonal.R: Evaluate seasonal trends in RF predictions at SW USA and OzFluxsites. Create Fig1d-f, Figs. S4 and S7 RFspatial_maps.R: calcualte mid-monthly composites of Fluxcom GPP predictiosn, calculate annual GPP estimates for Fluxcom and DryFlux, create annual difference maps (Fig2c,d; Fig3c,d), calcualte DryFlux GPP z-scores globally and create maps (Figs3a,b) data: data used in analysis presented in the manuscript contents of this folder include: site_locs.csv : site meta data for Southwestern NA sites including: site ID, site name, lat/long, vegetation classification (determined from MODIS IGBP land cover classification at flux tower location), MAT (from FluxNet), MAP (from FluxNet), and elevation (from FluxNet) global_locs.csv: site meta data from FluxNET for the global dryland sites site_meta.csv: WorldClim MAP/MAT, and STRM elevation meta-data for SW USA sites (output from 'MATMAPelev.R') global_meta.csv: WorldClim MAP/MAT, and STRM elevation meta-data for the global dryland sites (output from 'MATMAPelev.R') dates.csv: dates of CRU data RFdata.csv: output from 'data_prepro.R' all of the data needed for Random Forest analysis on the SW USA sites. global_RFdata.csv: output from 'data_prepro.R' all of the data needed for Random Forest analysis on the Global dryland sites Flux_raw: MatLab files for each fluxtower site containing daily NEP, GEP, Reco, ET, precip, Tair, VPD, Rnet, and Rsolar"
few_shot_example_2_output = f"""{{
  "area": "{NasaArea.EARTH_SCIENCE.value}"
}}"""

few_shot_example_3_input = r"# GRIZZLY Details of the code can be found here https://arxiv.org/abs/1710.09397. This code has two part. First to generate the 1D profiles around different sources. Second is to use those around the dark matter halos in the simulation box and use the density and velocity fields to generate the brightness temperature maps. Author: Raghunath Ghara Date: 12 Jan 2019"
few_shot_example_3_output = f"""{{
  "area": "{NasaArea.ASTROPHYSICS.value}"
}}"""

few_shot_example_4_input = r"# rfpipe A fast radio interferometric transient search library. Extends on [rtpipe](http://github.com/caseyjlaw/rtpipe). This library supports real-time analysis for the realfast project and offline analysis of VLA data on a single workstation. Integration with the real-time VLA and cluster processing is provided by [realfast](http://github.com/realfastvla/realfast). Planned future development include: - Supporting other search algorithms. - Supporting other interferometers by adding data and metadata reading functions. [![Docs](https://img.shields.io/badge/Made%20with-Sphinx-1f425f.svg)](https://realfastvla.github.io/rfpipe) [![Build Status](https://travis-ci.org/realfastvla/rfpipe.svg?branch=main)](https://travis-ci.org/realfastvla/rfpipe) [![codecov](https://codecov.io/gh/realfastvla/rfpipe/branch/main/graph/badge.svg)](https://codecov.io/gh/realfastvla/rfpipe) [![PyPI pyversions](https://img.shields.io/pypi/pyversions/ansicolortags.svg)](https://pypi.python.org/pypi/rfpipe/) [![ASCL](https://img.shields.io/badge/ascl-1710.002-blue.svg?colorB=262255)](https://ascl.net/1710.002) ## Installation `rfpipe` requires the [anaconda](http://anaconda.com) installer on Linux and OSX. The most reliable installation is for Python3.6 and adding conda-forge: ``` conda config --add channels conda-forge conda create -n realfast python=3.6 numpy scipy cython matplotlib numba pyfftw bokeh source activate realfast pip install --extra-index-url https://casa-pip.nrao.edu:443/repository/pypi-group/simple casatools pip install -e git+git://github.com/realfastvla/rfpipe#egg=rfpipe ``` ## Dependencies - numpy/scipy/matplotlib - casa6 python libraries (for quanta and measures; available on Python 3.6 via pip) - numba (for multi-core and gpu acceleration) - rtpipe (for flagging; will be removed soon) - astropy - sdmpy - pyfftw - pyyaml - attrs - rfgpu (optional; for GPU FFTs) - vys/vysmaw and vysmaw_reader (optional; to read vys data from VLA correlator) ## Citation If you use rfpipe, please support open software by citing the record on the [Astrophysics Source Code Library](ascl.net) at http://ascl.net/1710.002. In AASTeX, you can do this like so: ``` \software{..., rfpipe \citep2017ascl.soft10002L}, ...} ```"
few_shot_example_4_output = f"""{{
  "area": "{NasaArea.ASTROPHYSICS.value}"
}}"""

few_shot_examples = f"""
--- Example 1 ---
Input README Snippet:
{few_shot_example_1_input.strip()}
Expected Classification:
{few_shot_example_1_output}

--- Example 2 ---
Input README Snippet:
{few_shot_example_2_input.strip()}
Expected Classification:
{few_shot_example_2_output}

--- Example 3 ---
Input README Snippet:
{few_shot_example_3_input.strip()}
Expected Classification:
{few_shot_example_3_output}

--- Example 4 ---
Input README Snippet:
{few_shot_example_4_input.strip()}
Expected Classification:
{few_shot_example_4_output}
--- End of Examples ---
"""

# Define Pydantic Agent
readme_agent = Agent(
    model=openai_model,
    retries=3,
    output_type=ReadmeClassification,
    instructions=f"""
You are an expert assistant specialized in classifying technical README files according to NASA's research divisions.
Your task is to analyze the provided README content and determine which NASA research area it primarily belongs to.
You must use the EVALUATION CRITERIA provided below.
If there are signals or indirect references that suggest alignment with a NASA research area, classify accordingly and provide reasoning.

EVALUATION CRITERIA:
{evaluation_criteria}

Examples:
{few_shot_examples}
""",
)


# To run the Agent
async def classify_readme(
    agent_instance: Agent,
    readme_content: str,
) -> ReadmeClassification:
    user_prompt = f"""
    Please classify the following README content:
    ---
    {readme_content}
    ---
    """
    try:
        result = await agent_instance.run(user_prompt)
        usage = result.usage()
        prompt_tokens = usage.request_tokens
        completion_tokens = usage.response_tokens
        logger.info(
            f"Prompt Tokens: {prompt_tokens}, Completion Tokens: {completion_tokens}",
        )
        prompt_cost = (prompt_tokens / 1_000_000) * INPUT_COST_PER_1M
        completion_cost = (completion_tokens / 1_000_000) * OUTPUT_COST_PER_1M
        total_cost = prompt_cost + completion_cost
        logger.info(f"Cost: ${total_cost:.6f}")
        return (
            result.output,
            total_cost,
        )  # The output is an instance of ReadmeClassification
    except Exception as e:
        logger.error(f"Error during classification: {e}")
        return ReadmeClassification(
            area=NasaArea.NOT_NASA_DIVISION,
            reasoning=f"Error during classification: {str(e)}",
        )


# Flatten function
def flatten(text):
    return " ".join(text.split())


async def classify_all_readmes(agent_instance, texts, urls):
    async def classify_one(i, text, link):
        logger.info(f"Processing sample {i + 1}/{len(texts)}")
        classification_output, total_cost = await classify_readme(
            agent_instance,
            text,
        )
        return {
            "URL": link,
            "text": text,
            "area": classification_output.area.value,
            "reasoning": classification_output.reasoning,
            "cost": f"{total_cost:.4f}",
        }

    tasks = [
        classify_one(i, text, link) for i, (text, link) in enumerate(zip(texts, urls))
    ]
    results = await asyncio.gather(*tasks)
    return results


def run_classification_pipeline(
    input_csv_path: str,
    output_csv_path: str,
    text_column: str = "readme_text",
    url_column: str = "repo_url",
):
    """
    Run the README classification pipeline.

    Args:
        input_csv_path (str): Path to CSV containing columns 'repo_url' and 'readme_text'.
        output_csv_path (str): Path where the result CSV will be saved.
    """
    logger.info("Running Relevancy Classifier Pipeline")
    # Load dataset
    try:
        positive_df = pd.read_csv(input_csv_path)
        if positive_df.empty:
            logger.error(f"Input CSV at '{input_csv_path}' is empty. Aborting.")
    except Exception as e:
        logger.error(f"Failed to load input CSV: {e}, No GitHub links to process")
        sys.exit(1)

    logger.info(f"Loaded {len(positive_df)} rows from {input_csv_path}")
    positive_df[text_column] = positive_df[text_column].fillna("")
    positive_texts = [flatten(text) for text in positive_df[text_column].values]
    positive_repo_urls = list(positive_df[url_column].values)

    sample_count = len(positive_df)
    logger.info(f"Total Samples: {sample_count}")

    model_options = {
        "1": "gpt-4o-mini",
        "2": "gpt-o4-mini",
        "3": "gpt-o3",
        "4": "gpt-4.1",
        "5": "gpt-4.1-mini",
    }

    print("Select an OpenAI model:")
    for k, v in model_options.items():
        print(f"{k}: {v}")

    selected_key = input(
        "Enter the number corresponding to your model choice: ",
    ).strip()
    selected_model_name = model_options.get(selected_key, "gpt-4.1-mini")
    logger.info(f"Selected model: {selected_model_name}")
    openai_model.name = selected_model_name

    estimated_total_cost = SAMPLE_AVERAGE_COST * sample_count
    logger.info(
        f"Estimated Classification Cost: ${estimated_total_cost:.4f} (${SAMPLE_AVERAGE_COST:.4f} per README)",
    )

    # Ask user for confirmation to continue
    user_input = (
        input("Do you want to proceed with classification? (Y/N): ").strip().lower()
    )
    if user_input != "y":
        logger.info("Aborting classification pipeline as per user input.")
        sys.exit(0)

    # Run classification
    processed_data = asyncio.run(
        classify_all_readmes(readme_agent, positive_texts, positive_repo_urls),
    )

    # Save results
    results_df = pd.DataFrame(processed_data)
    results_df.to_csv(output_csv_path, index=False)

    total_actual_cost = sum(row["cost"] for row in processed_data if "cost" in row)
    logger.info(f"Done! Saved results to {output_csv_path}")
    logger.info(f"Total Actual Classification Cost: ${total_actual_cost:.4f}")

    # Classification Results
    logger.info(f"Classification Results: {results_df['area'].value_counts()}")
