"""
Created on Fri Sep 23 16:39:35 2016
@author: The Gene Prioritization dev team
"""
import os
import numpy as np
import pandas as pd
from scipy.stats import pearsonr as pcc
from sklearn.preprocessing import normalize
from sklearn.linear_model import LassoCV
import knpackage.toolbox as kn


def perform_lasso_cv_regression(spreadsheet, drug_response, normalize=True, max_iter=1e6):
    """ perform lasso with cross validation

    Args:
        spreadsheet:        features x samples matrix (np.array)
        drug_response:      1 x samples array (np.array)
        normalize_lasso:    (default=true) normalize inputs before
        max_iter:           (default 1e6) integer limit for iterations to converge

    Returns:
        lassoCV.coef_:      features coefficient array == drug correlation with gene
    """
    lasso_cv_obj = LassoCV(normalize=normalize, max_iter=max_iter)
    lasso_cv_residual = lasso_cv_obj.fit(spreadsheet.T, drug_response[0])

    return lasso_cv_residual.coef_

def run_correlation_lasso(run_parameters):
    ''' pearson cc:  call sequence to perform gene prioritization

    Args:
        run_parameters: dict object with keys:
                run_parameters["spreadsheet_name_full_path"]
                run_parameters["drug_response_full_path"]

    Returns: (writes gene_drug_lasso.timestamp.df
    '''
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    drug_response = np.array(kn.get_spreadsheet_df(run_parameters["drug_response_full_path"]).values)
    pc_array = perform_lasso_cv_regression(spreadsheet_df.values, drug_response)
    result_df = pd.DataFrame(pc_array, index=spreadsheet_df.index.values,
                             columns=['lassoCV']).abs().sort_values("lassoCV", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_lassoCV")

    return


def run_net_correlation_lasso(run_parameters):
    ''' pearson cc:  call sequence to perform gene prioritization with network smoothing

    Args:
        run_parameters: dict object with keys:
                run_parameters["spreadsheet_name_full_path"]    (samples x genes spreadsheet)
                run_parameters["drug_response_full_path"]       (one drug response spreadsheet)
                run_parameters['gg_network_name_full_path']     (gene, gene, weight,...   network)

    Returns:
        result_df: result dataframe of gene prioritization. Values are pearson
        correlation coefficient values in descending order.
    '''
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    network_df = kn.get_network_df(run_parameters['gg_network_name_full_path'])
    node_1_names, node_2_names = kn.extract_network_node_names(network_df)
    unique_gene_names = kn.find_unique_node_names(node_1_names, node_2_names)
    genes_lookup_table = kn.create_node_names_dict(unique_gene_names)

    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_1')
    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_2')

    network_df = kn.symmetrize_df(network_df)
    network_mat = kn.convert_network_df_to_sparse(
        network_df, len(unique_gene_names), len(unique_gene_names))

    network_mat = normalize(network_mat, norm="l1", axis=0)
    spreadsheet_df = kn.update_spreadsheet_df(spreadsheet_df, unique_gene_names)
    spreadsheet_mat = spreadsheet_df.as_matrix()

    sample_smooth, iterations = kn.smooth_matrix_with_rwr(spreadsheet_mat, network_mat, run_parameters)

    drug_response = np.array(kn.get_spreadsheet_df(run_parameters["drug_response_full_path"]).values)
    pc_array = perform_lasso_cv_regression(sample_smooth, drug_response)
    result_df = pd.DataFrame(pc_array, index=spreadsheet_df.index.values,
                             columns=['lassoCV']).abs().sort_values("lassoCV", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_network_lassoCV")

    return


def run_bootstrap_correlation_lasso(run_parameters):
    """ pearson cc: call sequence to perform gene prioritization using bootstrap sampling

    Args:
        run_parameters: dict object with keys:
            run_parameters["spreadsheet_name_full_path"]    (samples x genes spreadsheet)
            run_parameters["drug_response_full_path"]       (one drug response spreadsheet)

    Returns:
        result_df: result dataframe of gene prioritization. Values are pearson
        correlation coefficient values in descending order.
    """
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    drug_response = np.array(kn.get_spreadsheet_df(run_parameters["drug_response_full_path"]).values)
    sample_smooth = spreadsheet_df.values

    borda_count = np.int_(np.zeros(sample_smooth.shape[0]))
    for bootstrap_number in range(0, int(run_parameters["number_of_bootstraps"])):
        sample_random, sample_permutation = sample_a_matrix_pearson(
            sample_smooth, np.float64(run_parameters["rows_sampling_fraction"]),
            np.float64(run_parameters["cols_sampling_fraction"]))

        pc_array = perform_lasso_cv_regression(sample_random, np.array([drug_response[0, sample_permutation]]))

        borda_count = sum_vote_to_borda_count(borda_count, pc_array)

    borda_count = borda_count / max(borda_count)
    result_df = pd.DataFrame(borda_count, index=spreadsheet_df.index.values,
                             columns=['lassoCV']).abs().sort_values("lassoCV", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_bootstrap_lassoCV")

    return


def run_bootstrap_net_correlation_lasso(run_parameters):
    """ pearson cc: call sequence to perform gene prioritization using bootstrap sampling and network smoothing

    Args:
        run_parameters: dict object with keys:
            run_parameters["spreadsheet_name_full_path"]    (samples x genes spreadsheet)
            run_parameters["drug_response_full_path"]       (one drug response spreadsheet)
            run_parameters['gg_network_name_full_path']     (gene, gene, weight,...   network)

    Returns:
        result_df: result dataframe of gene prioritization. Values are pearson
        correlation coefficient values in descending order.
    """
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    network_df = kn.get_network_df(run_parameters['gg_network_name_full_path'])
    node_1_names, node_2_names = kn.extract_network_node_names(network_df)
    unique_gene_names = kn.find_unique_node_names(node_1_names, node_2_names)
    genes_lookup_table = kn.create_node_names_dict(unique_gene_names)

    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_1')
    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_2')

    network_df = kn.symmetrize_df(network_df)
    network_mat = kn.convert_network_df_to_sparse(
        network_df, len(unique_gene_names), len(unique_gene_names))

    network_mat = normalize(network_mat, norm="l1", axis=0)
    spreadsheet_df = kn.update_spreadsheet_df(spreadsheet_df, unique_gene_names)
    spreadsheet_mat = spreadsheet_df.as_matrix()

    sample_smooth, iterations = kn.smooth_matrix_with_rwr(spreadsheet_mat, network_mat, run_parameters)

    drug_response = np.array(kn.get_spreadsheet_df(run_parameters["drug_response_full_path"]).values)

    borda_count = np.int_(np.zeros(sample_smooth.shape[0]))
    for bootstrap_number in range(0, int(run_parameters["number_of_bootstraps"])):
        sample_random, sample_permutation = sample_a_matrix_pearson(
            sample_smooth, np.float64(run_parameters["rows_sampling_fraction"]),
            np.float64(run_parameters["cols_sampling_fraction"]))

        pc_array = perform_lasso_cv_regression(sample_random, np.array([drug_response[0, sample_permutation]]))

        borda_count = sum_vote_to_borda_count(borda_count, pc_array)

    borda_count = borda_count / max(borda_count)
    result_df = pd.DataFrame(borda_count, index=spreadsheet_df.index.values,
                             columns=['lassoCV']).abs().sort_values("lassoCV", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_network_bootstrap_lassoCV")

    return

#                                                                                                   lassoCV code above

#                                                                                                   Pearson code below
def perform_pearson_correlation(spreadsheet, drug_response):
    """ Find pearson correlation coefficient(PCC) for each gene expression (spreadsheet row)
            with the drug response.

    Args:
        spreadsheet: genes x samples gene expression data
        drug_response: one drug response for each sample

    Returns:
        pc_array: row-spreadsheet-features-ordered array of pearson correlation coefficients
    """
    pc_array = np.zeros(spreadsheet.shape[0])
    for row in range(0, spreadsheet.shape[0]):
        pcc_value = pcc(spreadsheet[row, :], drug_response)[0]
        pc_array[row] = pcc_value

    return pc_array


def run_correlation(run_parameters):
    ''' pearson cc:  call sequence to perform gene prioritization

    Args:
        run_parameters: dict object with keys:
                run_parameters["spreadsheet_name_full_path"]
                run_parameters["drug_response_full_path"]

    Returns:
        result_df:  result - dataframe of gene prioritization. Values are pearson
                    correlation coefficient values in descending order.
    '''
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    drug_response = kn.get_spreadsheet_df(run_parameters["drug_response_full_path"])

    pc_array = perform_pearson_correlation(spreadsheet_df.values, drug_response.values[0])
    result_df = pd.DataFrame(pc_array, index=spreadsheet_df.index.values,
                             columns=['PCC']).abs().sort_values("PCC", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_correlation")

    return


def run_bootstrap_correlation(run_parameters):
    """ pearson cc: call sequence to perform gene prioritization using bootstrap sampling

    Args:
        run_parameters: dict object with keys:
            run_parameters["spreadsheet_name_full_path"]    (samples x genes spreadsheet)
            run_parameters["drug_response_full_path"]       (one drug response spreadsheet)

    Returns:
        result_df: result dataframe of gene prioritization. Values are pearson
        correlation coefficient values in descending order.
    """
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    drug_response_df = kn.get_spreadsheet_df(run_parameters["drug_response_full_path"])
    sample_smooth = spreadsheet_df.values

    borda_count = np.int_(np.zeros(sample_smooth.shape[0]))
    for bootstrap_number in range(0, int(run_parameters["number_of_bootstraps"])):
        sample_random, sample_permutation = sample_a_matrix_pearson(
            sample_smooth, np.float64(run_parameters["rows_sampling_fraction"]),
            np.float64(run_parameters["cols_sampling_fraction"]))

        drug_response = drug_response_df.values[0, None]
        drug_response = drug_response[0, sample_permutation]
        pc_array = perform_pearson_correlation(sample_random, drug_response)

        borda_count = sum_vote_to_borda_count(borda_count, pc_array)

    borda_count = borda_count / max(borda_count)
    result_df = pd.DataFrame(borda_count, index=spreadsheet_df.index.values,
                             columns=['PCC']).abs().sort_values("PCC", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_bootstrap_correlation")

    return


def run_net_correlation(run_parameters):
    ''' pearson cc:  call sequence to perform gene prioritization with network smoothing

    Args:
        run_parameters: dict object with keys:
                run_parameters["spreadsheet_name_full_path"]    (samples x genes spreadsheet)
                run_parameters["drug_response_full_path"]       (one drug response spreadsheet)
                run_parameters['gg_network_name_full_path']     (gene, gene, weight,...   network)

    Returns:
        result_df: result dataframe of gene prioritization. Values are pearson
        correlation coefficient values in descending order.
    '''
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    network_df = kn.get_network_df(run_parameters['gg_network_name_full_path'])
    node_1_names, node_2_names = kn.extract_network_node_names(network_df)
    unique_gene_names = kn.find_unique_node_names(node_1_names, node_2_names)
    genes_lookup_table = kn.create_node_names_dict(unique_gene_names)

    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_1')
    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_2')

    network_df = kn.symmetrize_df(network_df)
    network_mat = kn.convert_network_df_to_sparse(
        network_df, len(unique_gene_names), len(unique_gene_names))

    network_mat = normalize(network_mat, norm="l1", axis=0)
    spreadsheet_df = kn.update_spreadsheet_df(spreadsheet_df, unique_gene_names)
    spreadsheet_mat = spreadsheet_df.as_matrix()

    sample_smooth, iterations = kn.smooth_matrix_with_rwr(spreadsheet_mat, network_mat, run_parameters)

    drug_response = kn.get_spreadsheet_df(run_parameters["drug_response_full_path"])

    pc_array = perform_pearson_correlation(sample_smooth, drug_response.values[0])
    result_df = pd.DataFrame(pc_array, index=spreadsheet_df.index.values,
                             columns=['PCC']).abs().sort_values("PCC", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_network_correlation")

    return

def run_bootstrap_net_correlation(run_parameters):
    """ pearson cc: call sequence to perform gene prioritization using bootstrap sampling and network smoothing

    Args:
        run_parameters: dict object with keys:
            run_parameters["spreadsheet_name_full_path"]    (samples x genes spreadsheet)
            run_parameters["drug_response_full_path"]       (one drug response spreadsheet)
            run_parameters['gg_network_name_full_path']     (gene, gene, weight,...   network)

    Returns:
        result_df: result dataframe of gene prioritization. Values are pearson
        correlation coefficient values in descending order.
    """
    spreadsheet_df = kn.get_spreadsheet_df(run_parameters["spreadsheet_name_full_path"])
    network_df = kn.get_network_df(run_parameters['gg_network_name_full_path'])
    node_1_names, node_2_names = kn.extract_network_node_names(network_df)
    unique_gene_names = kn.find_unique_node_names(node_1_names, node_2_names)
    genes_lookup_table = kn.create_node_names_dict(unique_gene_names)

    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_1')
    network_df = kn.map_node_names_to_index(network_df, genes_lookup_table, 'node_2')

    network_df = kn.symmetrize_df(network_df)
    network_mat = kn.convert_network_df_to_sparse(
        network_df, len(unique_gene_names), len(unique_gene_names))

    network_mat = normalize(network_mat, norm="l1", axis=0)
    spreadsheet_df = kn.update_spreadsheet_df(spreadsheet_df, unique_gene_names)
    spreadsheet_mat = spreadsheet_df.as_matrix()

    sample_smooth, iterations = kn.smooth_matrix_with_rwr(spreadsheet_mat, network_mat, run_parameters)

    drug_response = kn.get_spreadsheet_df(run_parameters["drug_response_full_path"])

    borda_count = np.int_(np.zeros(sample_smooth.shape[0]))
    for bootstrap_number in range(0, int(run_parameters["number_of_bootstraps"])):
        sample_random, sample_permutation = sample_a_matrix_pearson(
            sample_smooth, np.float64(run_parameters["rows_sampling_fraction"]),
            np.float64(run_parameters["cols_sampling_fraction"]))

        drug_response = drug_response.values[0, None]
        pc_array = perform_pearson_correlation(sample_random, drug_response[0, sample_permutation])

        borda_count = sum_vote_to_borda_count(borda_count, pc_array)

    borda_count = borda_count / max(borda_count)
    result_df = pd.DataFrame(borda_count, index=spreadsheet_df.index.values,
                             columns=['PCC']).abs().sort_values("PCC", ascending=0)

    write_results_dataframe(result_df, run_parameters["results_directory"], "gene_drug_network_bootstrap_correlation")

    return

def sum_vote_to_borda_count(borda_count, corr_array):
    """ incrementally update count by borda weighted vote in a subsample of the full borda size

    Args:
        vote_rank: (np.int_(vote_rank)) python rank array same size as borda_count (0 == first, 1 == second,...)
        borda_count: (np.int_(borda_count) ) the current running total of Borda weighted votes

    Returns:
        borda_count: input borda_count with borda weighted vote rankings added
    """
    vote_rank = np.argsort(corr_array)
    rank_array = np.int_(sorted(np.arange(0, vote_rank.size) + 1, reverse=True))
    borda_count[np.int_(vote_rank)] += rank_array

    return borda_count


def write_results_dataframe(result_df, run_dir, write_file_name):
    """
    Args:
        result_df:
        run_dir:
        write_file_name

    """
    target_file_base_name = os.path.join(run_dir, write_file_name)
    file_name = kn.create_timestamped_filename(target_file_base_name) + '.txt'
    result_df.to_csv(file_name, header=True, index=True, sep='\t')

    return

def sample_a_matrix_pearson(spreadsheet_mat, rows_fraction, cols_fraction):
    """ percent_sample x percent_sample random sample, from spreadsheet_mat.

    Args:
        spreadsheet_mat: gene x sample spread sheet as matrix.
        percent_sample: decimal fraction (slang-percent) - [0 : 1].

    Returns:
        sample_random: A specified precentage sample of the spread sheet.
        sample_permutation: the array that correponds to columns sample.
    """
    features_size = int(np.round(spreadsheet_mat.shape[0] * (1-rows_fraction)))
    features_permutation = np.random.permutation(spreadsheet_mat.shape[0])
    features_permutation = features_permutation[0:features_size].T

    patients_size = int(np.round(spreadsheet_mat.shape[1] * cols_fraction))
    sample_permutation = np.random.permutation(spreadsheet_mat.shape[1])
    sample_permutation = sample_permutation[0:patients_size]

    sample_random = spreadsheet_mat[:, sample_permutation]
    sample_random[features_permutation[:, None], :] = 0

    return sample_random, sample_permutation