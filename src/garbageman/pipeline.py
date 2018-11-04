import pandas as pd
import numpy as np
import geopandas as gpd
import logging
from shapely.geometry import Polygon, mapping
from tqdm import tqdm

# TODO
logger = logging.getLogger('garbageman')


def join_bldgs_blocks(buildings, blocks, building_id_key="sf16_BldgID"):
    """
    Performs a geospatial join, attempting to geometrically assign buildings to specific blocks.

    Parameters
    ----------
    buildings: gpd.GeoDataFrame
        A tabular `GeoDataFrame` whose `geometry` corresponds with all buildings in the area of interest.

    blocks: gpd.GeoDataFrame
        A tabular `GeoDataFrame` whose `geometry` corresponds with all blocks in the area of interest.

    building_id_key: str, default "sf16_BldgID"
        The key corresponding with the building ID.

    Returns
    -------
    (matches, multimatches, nonmatches) : tuple
        A tuple of three `GeoDataFrame`. The first element is of buildings-block pairs that are unique, the second
        element is buildings that span multiple blocks, and the third is buildings that span no blocks (at least
        according to the data given).
    """
    #logger.info("Geospatial join of buildings and blocks in progress.")
    all_matches = gpd.sjoin(buildings, blocks, how="left", op='intersects')
    matches = all_matches.groupby(building_id_key).filter(lambda df: len(df) == 1).reset_index()
    multimatches = all_matches.groupby(building_id_key).filter(lambda df: len(df) > 1).reset_index()
    nonmatches = all_matches[pd.isnull(all_matches['index_right'])]
    # logger.info("Geospatial join of buildings and blocks done.")

    return matches, multimatches, nonmatches


def simplify(shp, tol=0.05):
    """
    Generate a simplified shape for shp, within a 5 percent tolerance.

    Used for blockface alignment.
    """
    simp = None
    for thresh in [0.001, 0.0005, 0.0004, 0.0003, 0.0002, 0.0001]:
        simp = shp.simplify(thresh)
        if shp.difference(simp).area / shp.area < tol:
            break

    return simp


def blockfaces_for_block(block):
    """
    Generate a GeoDataFrame of block faces from a block definition.
    """
    orig = block.geometry.buffer(0)  # MultiPolygon -> Polygon
    simp = simplify(orig)

    orig_coords = mapping(orig)['coordinates'][0]
    simp_coords = mapping(simp)['coordinates'][0]

    simp_out = []
    orig_out = []

    orig_coords_idx = 0

    # generate coordinate strides
    for idx in range(1, len(simp_coords)):
        simp_blockface_start_coord, simp_blockface_end_coord = simp_coords[idx - 1], simp_coords[idx]

        orig_blockface_start_coord_idx = orig_coords_idx
        orig_coords_idx += 1
        while orig_coords[orig_coords_idx] != simp_blockface_end_coord:
            orig_coords_idx += 1
        orig_blockface_end_coord_idx = orig_coords_idx + 1

        simp_out.append((simp_blockface_start_coord, simp_blockface_end_coord))
        orig_out.append(orig_coords[orig_blockface_start_coord_idx:orig_blockface_end_coord_idx])

    # id will be a mutation of the block id
    block_id = block.geoid10

    out = []
    from shapely.geometry import LineString

    # frame id, block id, original geometry, and simplified geometry
    for n, (simp_blockface_coord_seq, orig_blockface_coord_seq) in enumerate(zip(simp_out, orig_out)):
        blockface_num = n + 1
        out.append({
            "geoid10_n": f"{block_id}_{blockface_num}",
            "geoid10": block_id,
            "simplified_geometry": LineString(simp_blockface_coord_seq),
            "geometry": LineString(orig_blockface_coord_seq)
        })

    out = gpd.GeoDataFrame(out)

    return out


def drop_noncontiguous_blocks(blocks):
    """
    Remove all blocks in the list of blocks which are composed of multiple geometries. This unusual case is the result
    of the inclusion of island features in the census blocks covering a city.
    """
    return blocks[blocks.geometry.map(lambda g: isinstance(g.buffer(0), Polygon))]


def build_streets_geospatial_index(streets):
    """
    Create a geospatial index of streets using the RTree package. Input to `find_matching_street`, which uses this
    index to perform the actual join.
    """
    import rtree
    index = rtree.index.Index()

    for idx, street in streets.iterrows():
        x, y = street.geometry.envelope.exterior.coords.xy
        index.insert(idx, (min(x), min(y), max(x), max(y)))

    return index


def find_matching_street(blockface, streets, index):
    """
    Finds the street that matches a blockface. May have multiple results or zero results.
    """
    def n_nearest_streets(block, mult=2):
        """
        Returns a frame of streets nearest the given block. mult controls how many times more
        streets will be looked up than the block has sides; because we need to return a lot of
        results, just to make sure we get every street fronting the block.
        """
        x, y = block.geometry.envelope.exterior.coords.xy
        n = (len(x) - 1) * 2
        idxs = index.nearest((min(x), min(y), max(x), max(y)), n)
        return streets.iloc[list(idxs)]

    streets_matched = n_nearest_streets(blockface)
    sub_matches = []
    for idx, street in streets_matched.iterrows():
        if street.geometry.buffer(0.00005).contains(blockface.geometry):
            return gpd.GeoDataFrame([street], geometry=[street.geometry])
        elif blockface.geometry.buffer(0.00005).contains(street.geometry):
            sub_matches.append(street)

    if len(sub_matches) > 0:
        return gpd.GeoDataFrame(sub_matches)


# TODO: parameterize the join key
def merge_street_segments_blockfaces_blocks(blockfaces, streets, index):
    """
    Matches street segments to blockfaces
    """
    matches = []

    for idx, blockface in tqdm(blockfaces.iterrows()):
        matches.append(find_matching_street(blockface, streets, index))

    matches_merge = []

    for idx, (_, dat) in tqdm(enumerate(blockfaces.iterrows())):
        corresponding_street_segments = matches[idx]
        geoid10 = np.nan if corresponding_street_segments is None else dat.geoid10

        if pd.notnull(geoid10):
            corresponding_street_segments = corresponding_street_segments.assign(
                geoid10=geoid10, geoid10_n=dat.geoid10_n
            )

        matches_merge.append(corresponding_street_segments)

    street_segments = pd.concat(matches_merge)
    del matches_merge
    return street_segments
