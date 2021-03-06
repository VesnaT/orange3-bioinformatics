"""
This module cluster the projection of data (usually it is 2D projection) with
one of the standard algorithms and attach a certain number of labels per
cluster.

Example:

>>> from Orange.projection import TSNE
>>> from Orange.data import Table
>>> from orangecontrib.bioinformatics.utils import serverfiles
>>> from orangecontrib.bioinformatics.annotation.annotate_projection import \
...     annotate_projection
>>> from orangecontrib.bioinformatics.annotation.annotate_samples import \
...     AnnotateSamples
>>>
>>> # load data
>>> data = Table("https://datasets.orange.biolab.si/sc/aml-1k.tab.gz")
>>> marker_p = serverfiles.localpath_download(
...     'marker_genes','panglao_gene_markers.tab')
>>> markers = Table(marker_p)
>>>
>>> # annotate data with labels
>>> annotator = AnnotateSamples()
>>> annotations = annotator.annotate_samples(data, markers)
>>>
>>> # project data in 2D
>>> tsne = TSNE(n_components=2)
>>> tsne_model = tsne(data)
>>> embedding = tsne_model(data)
>>>
>>> # get clusters and annotations for clusters
>>> clusters, clusters_meta, eps = annotate_projection(annotations, embedding,
...     clustering_algorithm=DBSCAN, eps=1.2)

In case when user uses a DBSCAN algorithm and do not provide eps to the
`annotate_projection` function it is computed automatically with knn method.

>>> clusters, clusters_meta, eps = annotate_projection(annotations, embedding,
...     clustering_algorithm=DBSCAN)

"""


from collections import Counter

from Orange.clustering import DBSCAN
import numpy as np
from Orange.data import Domain, DiscreteVariable, Table
from scipy.spatial import distance
import shapely.geometry as geometry
from scipy.spatial import Delaunay
from shapely.ops import cascaded_union, polygonize
from math import sqrt


def cluster_data(coordinates, clustering_algorithm=DBSCAN, **kwargs):
    """
    This function receives data and cluster them.

    Parameters
    ----------
    coordinates : Orange.data.Table
        Visualisation coordinates - embeddings
    clustering_algorithm : callable
        Algorithm used for clustering.

    Returns
    -------
    Orange.data.Table
        List of cluster indices.
    """
    learner = clustering_algorithm(**kwargs)
    model = learner(coordinates)
    clustrs = model(coordinates)
    # TODO: this need to be changed when clustering in orange is changed

    # sort classes in descending order base on number of cases in the cluster
    if "-1" in clustrs.domain.attributes[0].values:  # -1 means not cluster
        nan_idx = clustrs.domain.attributes[0].values.index("-1")
    else:
        nan_idx = None
    sorted_clust_idx = [
        v for v, _ in Counter(clustrs.X[:, 0]).most_common() if v != nan_idx]

    # re-indexed array
    new_clustering = np.empty(len(clustrs))
    new_clustering[:] = np.nan  # nan for not clustered
    for i, v in enumerate(sorted_clust_idx):
        new_clustering[clustrs.X[:, 0] == v] = i

    # create the table
    new_domain = Domain([DiscreteVariable(
        "Clusters", values=[
            "C{}".format(i) for i in range(1, len(sorted_clust_idx) + 1)])])
    return Table(new_domain, new_clustering.reshape((-1, 1)))


def assign_labels(clusters, annotations, labels_per_cluster):
    """
    This function assigns a certain number of labels per cluster. Each cluster
    gets `labels_per_cluster` number of most common labels in cluster assigned.

    Parameters
    ----------
    clusters : Orange.data.Table
        Cluster indices for each item.
    annotations : Orange.data.Table
        Table with annotations and their probabilities.
    labels_per_cluster : int
        Number of labels that need to be assigned to each cluster.

    Returns
    -------
    dict
        Dictionary with cluster index as a key and list of annotations as a
        value. Each list include tuples with the annotation name and their
        proportion in the cluster.
    """
    labels = np.array(list(map(str, annotations.domain.attributes)))
    annotation_best_idx = np.argmax(annotations.X, axis=1)
    annotation_best = labels[annotation_best_idx]

    clusters_unique = set(clusters.domain[0].values)
    annotations_clusters = {}
    for cl in clusters_unique:
        mask = np.array(list(
            map(clusters.domain.attributes[0].repr_val,
                clusters.X[:, 0]))).flatten() == cl
        labels_cl = annotation_best[mask]
        counts = Counter(labels_cl)
        annotations_clusters[cl] = [
            (l, c / len(labels_cl))
            for l, c in counts.most_common(labels_per_cluster)]

    return annotations_clusters


def labels_locations(coordinates, clusters):
    """
    Function computes the location of the label for each cluster.
    The location is compute as a center point.

    Parameters
    ----------
    coordinates : Orange.data.Table
        Visualisation coordinates - embeddings
    clusters : Orange.data.Table
        Cluster indices for each item.

    Returns
    -------
    dict
        The coordinates for locating the label. Dictionary with cluster index
        as a key and tuple (x, y) as a value.
    """
    clusters_unique = set(
        clusters.domain[0].values) - {"-1"}  # -1 is not clustered
    locations = {}
    for cl in clusters_unique:
        mask = np.array(list(
            map(clusters.domain.attributes[0].repr_val,
                clusters.X[:, 0]))).flatten() == cl
        cl_coordinates = coordinates.X[mask, :]
        x, y = np.mean(cl_coordinates, axis=0)
        locations[cl] = (x, y)
    return locations


def get_epsilon(coordinates, k=10, skip=0.1):
    """
    The function computes the epsilon parameter for DBSCAN through method
    proposed in the paper.

    Parameters
    ----------
    coordinates : Orange.data.Table
        Visualisation coordinates - embeddings
    k : int
        Number kth observed neighbour
    skip : float
        Percentage of skipped neighborus.

    Returns
    -------
    float
        Epsilon parameter for DBSCAN
    """
    x = coordinates.X
    if len(x) > 1000:  # subsampling is required
        i = len(x) // 1000
        x = x[::i]

    d = distance.squareform(distance.pdist(x))
    kth_point = np.argpartition(d, k+1, axis=1)[:, k+1]
    # k+1 since first one is item itself
    kth_dist = np.sort(d[np.arange(0, len(kth_point)), kth_point])

    # currently mark proportion equal to skip as a noise
    return kth_dist[-int(np.round(len(kth_dist) * skip))]


def compute_concave_hulls(coordinates, clusters, epsilon):
    """
    Function computes the points of the concave hull around points.

    Parameters
    ----------
    coordinates : Orange.data.Table
        Visualisation coordinates - embeddings
    clusters : Orange.data.Table
       Cluster indices for each item.
    epsilon : float
        Epsilon used by DBSCAN to cluster the data

    Returns
    -------
    dict
       The points of the concave hull. Dictionary with cluster index
       as a key and np.ndaray of points as a value -
       [[x1, y1], [x2, y2], [x3, y3], ...]
    """

    def get_shape(points, epsilon):
        """
        Compute the shape (concave hull) of a set of a cluster.
        """
        if len(points) < 4:
            # When you have a triangle, there is no sense in computing the hull
            return geometry.MultiPoint(list(points)).convex_hull

        def add_edge(edges, edge_points, coords, i, j):
            """
            Add a line between the i-th and j-th points,
            if not in the list already
            """
            if (i, j) in edges or (j, i) in edges:
                # already added
                return
            edges.add((i, j))
            edge_points.append(coords[[i, j]])

        tri = Delaunay(points)
        edges = set()
        edge_points = []
        # loop over triangles:
        # ia, ib, ic = indices of corner points of the triangle
        for ia, ib, ic in tri.vertices:
            pa = points[ia]
            pb = points[ib]
            pc = points[ic]

            # Lengths of sides of triangle
            a = sqrt((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2)
            b = sqrt((pb[0] - pc[0]) ** 2 + (pb[1] - pc[1]) ** 2)
            c = sqrt((pc[0] - pa[0]) ** 2 + (pc[1] - pa[1]) ** 2)

            # filter - longest edge of triangle smaller than epsilon
            if max(a, b, c) <= epsilon:
                add_edge(edges, edge_points, points, ia, ib)
                add_edge(edges, edge_points, points, ib, ic)
                add_edge(edges, edge_points, points, ic, ia)

        m = geometry.MultiLineString(edge_points)
        triangles = list(polygonize(m))
        return cascaded_union(triangles)

    hulls = {}
    clusters_array = np.array(list(map(
        clusters.domain.attributes[0].repr_val, clusters.X[:, 0])))
    for cl in set(clusters_array) - {"None", "?"}:
        points = coordinates.X[clusters_array == cl]

        # subsample when more than 1000 points
        # it keeps time finding hull under 0.3 s on my computer
        if points.shape[0] > 1000:
            points = points[np.random.randint(points.shape[0], size=1000), :]

        # epsilon * 2 seems to be good parameter for lines to be smooth enough
        concave_hull = get_shape(points, epsilon=epsilon * 2)
        # expand_and_smooth the curve - selecting epsilon for the distance
        # shows approximately what is DBSCAN neighbourhood
        concave_hull = concave_hull.buffer(epsilon, resolution=16)

        hulls[cl] = np.array(list(map(list, concave_hull.exterior.coords.xy))).T

    return hulls


def annotate_projection(annotations, coordinates,
                        clustering_algorithm=DBSCAN,
                        labels_per_cluster=3, **kwargs):
    """
    Function cluster the data based on coordinates, and assigns a certain number
    of labels per cluster. Each cluster gets `labels_per_cluster` number of most
    common labels in cluster assigned.

    Parameters
    ----------
    annotations : Orange.data.Table
        Table with annotations and their probabilities.
    coordinates : Orange.data.Table
        Visualisation coordinates - embeddings
    clustering_algorithm : callable, optional (default = DBSCAN)
        Algorithm used in clustering.
    labels_per_cluster : int, optional (default = 3)
        Number of labels that need to be assigned to each cluster.

    Returns
    -------
    Orange.data.Table
        List of cluster indices.
    dict
        Dictionary with cluster index as a key and list of annotations as a
        value. Each list include tuples with the annotation name and their
        proportion in the cluster.
    dict
        The coordinates for locating the label. Dictionary with cluster index
        as a key and tuple (x, y) as a value.
    """
    assert len(annotations) == len(coordinates)
    assert len(coordinates) > 0  # sklearn clustering want to have one example
    assert len(annotations.domain) > 0
    assert len(coordinates.domain) > 0

    eps = kwargs.get("eps", get_epsilon(coordinates))
    if clustering_algorithm == DBSCAN:
        kwargs["eps"] = eps

    # get clusters
    clusters = cluster_data(coordinates, clustering_algorithm, **kwargs)

    # assign top n labels to group
    annotations_cl = assign_labels(clusters, annotations, labels_per_cluster)

    labels_loc = labels_locations(coordinates, clusters)

    concave_hull = compute_concave_hulls(coordinates, clusters, eps)

    clusters_meta = {}
    for cl in annotations_cl.keys():
        clusters_meta[cl] = (
            annotations_cl[cl], labels_loc[cl], concave_hull[cl])

    return clusters, clusters_meta, eps
