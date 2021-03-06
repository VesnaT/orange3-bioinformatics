import unittest

import Orange
import numpy as np
from Orange.clustering import DBSCAN, KMeans
from Orange.data import Domain, ContinuousVariable, Table, DiscreteVariable

from orangecontrib.bioinformatics.annotation.annotate_projection import \
    annotate_projection, labels_locations, get_epsilon, compute_concave_hulls


class TestAnnotateProjection(unittest.TestCase):

    def setUp(self):
        domain = Domain([ContinuousVariable("x"), ContinuousVariable("y")])
        data = np.array([[1., 1.], [1., 1.5], [1.5, 1.], [1.2, 1.2], [1.7, 1.8],
                         [10., 10.], [10., 10.5], [10.5, 11.], [10.5, 10.7],
                         [10.5, 10.6], [10.5, 10.7], [10.5, 10.7]])
        self.data = Table(domain, data)

        domain_ann = Domain([ContinuousVariable("a"), ContinuousVariable("b"),
                            ContinuousVariable("c")])
        data_ann = np.array([[0.9, 1, 0.4], [0.9, 0.4, 0.2], [0.9, 0.4, 0.2],
                             [0.9, 1, 0.2], [0.9, 0.4, 0.2],
                             [0.2, 0.4, 0.7], [0.1, 0.4, 0.6], [0.2, 0.9, 0.2],
                             [0.1, 0.4, 0.6], [0.1, 0.8, 0.6], [0.1, 0.8, 0.6],
                             [0.1, 0.8, 0.6]])
        self.annotations = Table(domain_ann, data_ann)

    def test_annotate_projection(self):
        clusters, clusters_meta, eps = annotate_projection(
            self.annotations, self.data, clustering_algorithm=DBSCAN,
            labels_per_cluster=2, eps=3)

        self.assertLessEqual(int(Orange.__version__.split(".")[1]), 22)
        # TODO: uncomment when new Orange released, and remove version check
        # self.assertListEqual(
        #     list(map(clusters.domain.attributes[0].repr_val, clusters.X[:, 0])),
        #     ["0", "0", "0", "0", "0", "1", "1", "1", "1", "1"])

        # self.assertEqual(len(clusters_meta), 2)
        # self.assertEqual(len(clusters_meta["C0"]), 3)
        # self.assertEqual(len(clusters_meta["C1"]), 3)
        # self.assertEqual(clusters_meta["C1"][0][0][0], 'c')
        # self.assertAlmostEqual(clusters_meta["C1"][0][0][1], 0.6, 5)
        # self.assertEqual(clusters_meta["C1"][0][1][0], 'b')
        # self.assertAlmostEqual(clusters_meta["C1"][0][1][1], 0.4, 5)

        # self.assertEqual(2, len(clusters_meta["C1"][1]))
        # self.assertEqual(2, clusters_meta["C1"][2].shape[1])
        # self.assertEqual(
        #     type(np.ndarray), type(clusters_meta["C1"][2].shape[1]))
        # self.assertEqual(float, type(eps))

    def test_example_not_clustered(self):
        self.data[-1] = [23, 23]
        clusters, clusters_meta, eps = annotate_projection(
            self.annotations, self.data, clustering_algorithm=DBSCAN,
            eps=2, min_samples=3)

        self.assertLessEqual(int(Orange.__version__.split(".")[1]), 22)
        # TODO: uncomment when new Orange released, and remove version check
        # self.assertListEqual(
        #     list(map(clusters.domain.attributes[0].repr_val, clusters.X[:, 0])),
        #     ["0", "0", "0", "0", "0", "1", "1", "1", "1", "-1"])

        # self.assertEqual(len(clusters_meta), 2)
        # self.assertEqual(len(clusters_meta["C0"]), 3)
        # self.assertEqual(len(clusters_meta["C1"]), 3)
        # self.assertEqual(clusters_meta["C1"][0][0][0], 'c')
        # self.assertAlmostEqual(clusters_meta["C1"][0][0][1], 0.75, 5)
        # self.assertEqual(clusters_meta["C1"][0][1][0], 'b')
        # self.assertAlmostEqual(clusters_meta["C1"][0][1][1], 0.25, 5)

    def test_other_clustering(self):
        clusters, clusters_meta, locs = annotate_projection(
            self.annotations, self.data,
            clustering_algorithm=KMeans, n_clusters=2,
            labels_per_cluster=2)
        self.assertEqual(2, len(set(clusters.X.flatten())))
        self.assertEqual(3, len(clusters_meta["C1"]))
        self.assertEqual(3, len(clusters_meta["C2"]))
        self.assertEqual(2, len(clusters_meta["C1"][0]))
        self.assertEqual(2, len(clusters_meta["C2"][0]))

    def test_labels_location(self):
        clusters = Table(Domain([DiscreteVariable("cl", values=["1", "2"])]),
                         [[0]] * 6 + [[1]] * 6)
        locs = labels_locations(self.data, clusters)

        self.assertEqual(dict, type(locs))
        self.assertEqual(tuple, type(locs["1"]))
        self.assertEqual(tuple, type(locs["2"]))

    def test_get_epsilon(self):
        data = Table("iris")
        eps = get_epsilon(data)

        self.assertGreaterEqual(eps, 0.9)

    def test_compute_concave_hulls(self):
        data = Table("iris")[:, 2:4]
        clusters = Table(
            Domain([DiscreteVariable("cl", values=["1", "2", "3"])]),
            [[0]] * 50 + [[1]] * 50 + [[2]] * 50
        )
        hulls = compute_concave_hulls(data, clusters, epsilon=0.5)

        self.assertEqual(3, len(hulls))
        self.assertEqual(2, hulls["1"].shape[1])  # hull have x and y
        self.assertEqual(2, hulls["2"].shape[1])  # hull have x and y
        self.assertEqual(2, hulls["3"].shape[1])  # hull have x and y
