import pandas as pd
import numpy as np
import geopandas as gpd
import logging
from shapely.geometry import Polygon, LineString, MultiPolygon, Point, mapping
from tqdm import tqdm
import rtree

# TODO
logger = logging.getLogger('garbageman')


def join_bldgs_blocks(buildings, blocks, building_id_key="sf16_BldgID"):
    """
    Performs a geo-spatial join on buildings and blocks. Each of the `buildings` searches for `blocks` that it
    intersects with. In a good case, the building is found to be located within a particular block. In a bad case, the
    building is found to match with no blocks (if the space it is located on seemingly isn't included in `blocks`) or
    with many blocks (if its footprint intersects with more than one block).

    This function therefore returns a tuple of three items: `matches` for buildings uniquely joined to blocks,
    `multimatches` for buildings joined to multiple blocks, a `nonmatches` for buildings joined to no blocks.

    Parameters
    ----------
    buildings: gpd.GeoDataFrame
        A tabular `GeoDataFrame` whose `geometry` consists of building footprints in the area of interest.

    blocks: gpd.GeoDataFrame
        A tabular `GeoDataFrame` whose `geometry` corresponds with all block footprints in the area of interest.

    building_id_key: str, default "sf16_BldgID"
        A unique ID for the buildings. This field must be present in the `buildings` dataset, and it must be uniquely
        keyed.

    Returns
    -------
    (matches, multimatches, nonmatches) : tuple
        A tuple of three `GeoDataFrame`. The first element is of buildings-block pairs that are unique, the second
        element is buildings that span multiple blocks, and the third is buildings that span no blocks (at least
        according to the data given).
    """
    # logger.info("Geospatial join of buildings and blocks in progress.")
    all_matches = (gpd.sjoin(buildings, blocks, how="left", op='intersects')
                   .rename(columns={'index_right': 'index_block'})
                   .set_index("index"))
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
    return blocks[blocks.geometry.map(lambda g: isinstance(g.buffer(0), Polygon))]


def blockfaces_for_blocks(blocks):
    contiguous_blocks = drop_noncontiguous_blocks(blocks)
    blockfaces = pd.concat(contiguous_blocks.apply(lambda b: blockfaces_for_block(b), axis='columns').values)
    blockfaces = blockfaces.drop(columns=['simplified_geometry'])  # write compatibility
    return blockfaces


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


def filter_on_block_id(block_id, block_id_key="geoid10"):
    def select(df):
        return (df.set_index(block_id_key)
                .filter(like=block_id, axis='rows')
                .reset_index()
                )

    return select


def get_block_data(block_id, street_segments, blockfaces, buildings):
    ss = street_segments.pipe(filter_on_block_id(block_id))
    bf = blockfaces.pipe(filter_on_block_id(block_id))
    bldgs = buildings.pipe(filter_on_block_id(block_id))
    return ss, bf, bldgs


def plot_block(block_id):
    street_segments, blockfaces, buildings = get_block_data(block_id)

    ax = street_segments.plot(color='red', linewidth=1)
    blockfaces.plot(color='black', ax=ax, linewidth=1)
    buildings.plot(ax=ax, color='lightsteelblue', linewidth=1, edgecolor='steelblue')
    return ax


def simplify_linestring(inp):
    inp = inp.convex_hull
    coords = np.round(mapping(inp)['coordinates'], decimals=4)
    out = LineString(coords)
    return out


def simplify_bldg(bldg):
    if isinstance(bldg, MultiPolygon):
        bldg = bldg.buffer(0)

    if isinstance(bldg, MultiPolygon):
        raise NotImplemented  # TODO

    coords = [xyz[:2] for xyz in mapping(bldg.convex_hull)['coordinates'][0]]
    bldg = Polygon(bldg)

    return bldg


def pairwise_combinations(keys):
    return itertools.combinations({'a': 12, 'b': 15, 'c': 13}.keys(), r=2)


def collect_strides(point_observations):
    point_obs_keys = list(point_observations.keys())
    curr_obs_start_offset = point_obs_keys[0]
    curr_obs_start_bldg = point_observations[point_obs_keys[0]]
    strides = dict()

    for point_obs in point_obs_keys[1:]:
        bldg_observed = point_observations[point_obs]
        if bldg_observed != curr_obs_start_bldg:
            strides[(curr_obs_start_offset, point_obs)] = curr_obs_start_bldg
            curr_obs_start_offset = point_obs
            curr_obs_start_bldg = bldg_observed
        else:
            continue

    strides[(curr_obs_start_offset, '1.00')] = bldg_observed

    return strides


def get_stride_boundaries(strides, step_size=0.02):
    boundaries = list()

    keys = list(strides.keys())
    for idx, key in enumerate(keys[1:]):
        curr = strides[key]
        boundaries.append((key[0], str(float(key[0]) + step_size)))

    return boundaries


def cut(line, distance):
    # Cuts a line in two at a distance from its starting point
    if distance <= 0.0 or distance >= 1.0:
        return [LineString(line)]
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p), normalized=True)
        if pd == distance:
            return [
                LineString(coords[:i + 1]),
                LineString(coords[i:])]
        if pd > distance:
            cp = line.interpolate(distance, normalized=True)
            return [
                LineString(coords[:i] + [(cp.x, cp.y)]),
                LineString([(cp.x, cp.y)] + coords[i:])]


def reverse(l):
    l_x, l_y = l.coords.xy
    l_x, l_y = l_x[::-1], l_y[::-1]
    return LineString(zip(l_x, l_y))


def chop_line_segment_using_offsets(line, offsets):
    offset_keys = list(offsets.keys())
    out = []

    for off_start, off_end in offset_keys:
        out_line = LineString(line.coords)
        orig_length = out_line.length

        # Reverse to cut off the start.
        out_line = reverse(out_line)
        out_line = cut(out_line, 1 - float(off_start))
        out_line = reverse(out_line)
        intermediate_length = out_line.length

        # Calculate the new cutoff end point, and apply it to the line.
        l_1_2 = (float(off_end) - float(off_start)) * orig_length
        l_1_3 = (1 - float(off_start)) * orig_length
        new_off_end = l_1_2 - l_1_3

        # Perform the cut.
        out_line = cut(out_line, new_off_end)

        if cut_result is None:
            return np.nan
        elif len(cut_result) == 1:
            out.append(cut_result[0])
        else:
            to_out, rest = cut(line, float(off_end))
            out.append(to_out)

    return out


def frontages_for_blockface(bldgs, blockface, step_size=0.01):
    index = rtree.Rtree()

    if len(bldgs) == 0:
        return gpd.GeoDataFrame()

    for idx, bldg in bldgs.iterrows():
        index.insert(idx, bldg.geometry.bounds)

    bldg_frontage_points = dict()

    search_space = np.arange(0, 1, step_size)
    next_search_space = []
    while len(search_space) > 0:
        for offset in search_space:
            search_point = blockface.geometry.interpolate(offset, normalized=True)
            nearest_bldg = list(index.nearest(search_point.bounds, 1))[0]
            bldg_frontage_points[str(offset)[:6]] = nearest_bldg

        strides = collect_strides(bldg_frontage_points)
        search_space = next_search_space

    # convert the list of strides to a proper GeoDataFrame
    out = []
    for sk in strides.keys():
        srs = bldgs.loc[strides[sk], ['geoid10', 'sf16_BldgID']]
        srs['geoid10_n'] = blockface['geoid10_n']
        srs['geom_offset_start'] = sk[0]
        srs['geom_offset_end'] = sk[1]
        out.append(srs)

    out = gpd.GeoDataFrame(out)

    geoms = chop_line_segment_using_offsets(blockface.geometry, strides)
    out['geometry'] = geoms

    return out