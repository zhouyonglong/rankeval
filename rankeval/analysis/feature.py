# Copyright (c) 2017, All Contributors (see CONTRIBUTORS file)
# Authors: Salvatore Trani <salvatore.trani@isti.cnr.it>, 
#          Claudio Lucchese <claudio.lucchese@isti.cnr.it>
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
This package implements feature importance analysis.
"""

import numpy as np
from collections import deque
from rankeval.core.model import RTEnsemble

try:
    from ._efficient_feature import feature_importance, _feature_importance_tree
except ImportError:

    def feature_importance(model, dataset):
        """
        This method computes the feature importance relative to the given model
        and dataset.

        Parameters
        ----------
        dataset : Dataset
            The dataset used to evaluate the model (typically the one used to train
            the model).
        model : RTEnsemble
            The model whose features we want to evaluate.

        Returns
        -------
        feature_importance : numpy.array
            A vector of importance values, one for each feature in the given
            model. The importance values reported are the sum of the
            improvements, in terms of MSE, of each feature, evaluated on the
            given dataset. The improvements are computed as the delta MSE before
            a split node and after, evaluating how much the MSE is improved as a
            result of the split.
        feature_count : numpy.array
            A vector of count values, one for each feature in the given
            model. The count values reported highlights the number of times each
            feature is used in a split node, i.e., to improve the MSE.
        """

        # initialize features importance
        feature_imp = np.zeros(dataset.n_features, dtype=np.float32)

        # initialize features count
        feature_count = np.zeros(dataset.n_features, dtype=np.uint16)

        # default scores on the root node of the first tree
        y_pred = np.zeros(dataset.n_instances)

        # iterate trees of the model
        for tree_id in np.arange(model.n_trees):
            _feature_importance_tree(model, dataset, tree_id,
                                     y_pred, feature_imp, feature_count)

        return feature_imp, feature_count


    def _feature_importance_tree(model, dataset, tree_id, y_pred,
                                 feature_imp, feature_count):
        """
        This method computes the feature importance relative to a single tree of
        the given model.

        Parameters
        ----------
        dataset : Dataset
            The dataset used to evaluate the model (typically the one used to train
            the model).
        model : RTEnsemble
            The model whose features we want to evaluate.
        tree_id: int
            Id of the root of the tree to be evaluated.
        y_pred : numpy.array
            Current instance predictions.
        feature_imp : numpy.array
            The feature importance array, to be updated with the evaluation of the
            current tree.
        feature_count : numpy.array
            The feature count array, to be updated with the evaluation of the
            current tree.

        Returns
        -------
        y_pred_tree : numpy.array
            A vector of delta instance scores relative to the current tree.
        """

        # The residual scores to fit
        y_target = dataset.y - y_pred

        # Set the default y_pred vector to the mean residual score
        y_pred_tree = np.full(dataset.n_instances, fill_value=y_target.mean())

        # queue with node_id to be visited and list of documents in the node
        root_node_id = model.trees_root[tree_id]
        node_queue = deque([(root_node_id, None)])

        while len(node_queue) > 0:
            # current node info
            node_id, doc_list = node_queue.popleft()
            feature_id = model.trees_nodes_feature[node_id]
            threshold = model.trees_nodes_value[node_id]

            feature_count[feature_id] += 1

            # this is good only for the internal nodes (non root)
            if doc_list is not None:
                left_docs = doc_list[dataset.X[doc_list, feature_id] <= threshold]
                right_docs = doc_list[dataset.X[doc_list, feature_id] > threshold]
            else:
                left_docs = np.where(dataset.X[:, feature_id] <= threshold)[0]
                right_docs = np.where(dataset.X[:, feature_id] > threshold)[0]

            # before updating leaves
            pre_split_mse = ((y_target[doc_list] - y_pred_tree[doc_list]) ** 2.0).sum()

            # update y_pred
            y_pred_tree[left_docs] = y_target[left_docs].mean()
            y_pred_tree[right_docs] = y_target[right_docs].mean()

            # after updating leaves
            post_split_mse = ((y_target[doc_list] - y_pred_tree[doc_list]) ** 2.0).sum()

            # compute new_mse
            delta_mse = pre_split_mse - post_split_mse

            # update feature importance
            feature_imp[feature_id] += delta_mse / dataset.n_instances

            # if children are not leaves, add in the queue of the nodes to visit
            if not model.is_leaf_node(model.trees_left_child[node_id]):
                node_queue.append((model.trees_left_child[node_id], left_docs))
            if not model.is_leaf_node(model.trees_right_child[node_id]):
                node_queue.append((model.trees_right_child[node_id], right_docs))

        # update the y_pred including the weight of the current tree
        y_pred += y_pred_tree * model.trees_weight[tree_id]

        return y_pred_tree
