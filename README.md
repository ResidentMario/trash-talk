# trash talk

This repo contains notebooks and other resources associated with the "Trash Talk" project&mdash;an analysis of pickups performed by Rubbish Revolution, a smart trash grabber startup, in a survey zone on Polk Street in the Russian Hill neighborhood of San Francisco.

The data (which is not yet available publicly) consists of GPS coordinates, categories, and other associated information about pieces of trash picked up by the Rubbish Revolution crew during "rubbish runs". Runs were performed on a three-times-a-week basis (with some lapses) from approximately September 2018 through July 2019 (at the time of writing, they are still going).

This affords us a rich dataset with thousands of points of categorical trash pickups, but also some unique geospatial challenges. Chief among these is the fact that GPS points are inaccurate and scattered, and must be re-grounded in the surrounding geospatial context (the street centerline, nearly blocks, the side of the street the trash occurred on, and nearby building frontages) before it can really be analyzed. I wrote a set of routines for performing the geospatial operations required, which live in the [`streetmapper`](https://github.com/ResidentMario/streetmapper) module. In case the `streetmapper` code changes later, this project used the [`72c332` commit](https://github.com/ResidentMario/streetmapper/tree/72c3321d92e10db96e2f0b14f232b679e8778b6c) of `streetmappper` (for instructions on installing a Python module as of a specific commit see e.g. [here](https://stackoverflow.com/questions/13685920/install-specific-git-commit-with-pip)).

The top-level `notebooks` folder is concerned with prototyping the `streetmapper` library. A blog post summarizing the challenges involved is forthcoming.

The actual analysis used the following public data sources:

* `Building Footprints.zip`&mdash;The San Francisco building footprints dataset, as reported by the city. ([source](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Building-Footprints/ynuv-fyni))
* `Census 210_ Blocks for San Francisco.geojson`&mdash;The San Francisco block footprints dataset, as reported in the 2010 US Census. ([source](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Census-2010-Blocks-for-San-Francisco/2uzy-uv2r))
* `Streets - Active and Retired.geojson`&mdash;The San Francisco street centerlines dataset. ([source](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Streets-Active-and-Retired/3psu-pn9h))

As well as a private dataset of Rubbish Revolution trash pickups (a public, anonymized version of this dataset may exist in the future).

The analysis code lives in a series of Jupyter notebooks in the `notebooks/analysis` folder.

A blog post summarizing the findings is forthcoming.
