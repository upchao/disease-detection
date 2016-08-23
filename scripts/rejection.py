"""Analysis of how the rejection of test samples based on model uncertainty
   affects the performance of the rest of the data that remains automatically
   classified"""
from __future__ import print_function
import matplotlib.pyplot as plt
import numpy as np
import cPickle as pickle
import pandas as pd
import seaborn as sns
from sklearn.metrics import roc_auc_score

from util import roc_curve_plot

from matplotlib import rcParams
rcParams.update({'figure.autolayout': True})

plt.ion()
sns.set_context('paper', font_scale=1.4)

A4_WIDTH_SQUARE = (8.27, 8.27)


def load_labels():
    df_test = pd.read_csv('data/kaggle_dr/retinopathy_solution.csv')
    y_test = df_test.level.values
    return y_test


def load_predictions():
    """Load test predictions obtained with scripts/predict.py"""
    with open('data/processed/c9ade47_100_mc_KaggleDR_test_JFnet.pkl',
              'rb') as h:
        pred_test = pickle.load(h)
    probs = pred_test['det_out']
    probs_mc = pred_test['stoch_out']
    return probs, probs_mc


def binary_labels(labels, min_positive_level=1):
    labels_bin = np.zeros_like(labels)
    labels_bin[labels < min_positive_level] = 0
    labels_bin[labels >= min_positive_level] = 1
    return labels_bin


def binary_probs(probs, min_positive_level=1):
    return probs[:, min_positive_level:].sum(axis=1)


def detection_task(y, probs, probs_mc, disease_level):
    y_diseased = binary_labels(y, disease_level)
    probs_diseased = binary_probs(probs, disease_level)
    probs_mc_diseased = binary_probs(probs_mc, disease_level)
    return y_diseased, probs_diseased, probs_mc_diseased


def posterior_statistics(probs_mc_bin):
    predictive_mean = probs_mc_bin.mean(axis=1)
    predictive_std = probs_mc_bin.std(axis=1)
    return predictive_mean, predictive_std


def argmax_labels(probs):
    return (probs >= 0.5).astype(int)


def accuracy(y_true, probs):
    y_pred = argmax_labels(probs)
    assert len(y_true) == len(y_pred)
    return (y_true == y_pred).sum() / float(len(y_true))


def stratified_mask(y, y_prior, shuffle=False):
    """Get mask such that y[mask] has the same size and class freq. as y_prior

    Parameters
    ==========
    y : array with labels
    y_prior: subset of y, defining the relative class frequencies
    shuffle: bool, False by default
        random selection from the pool of each class

    Returns
    =======
    select: bool. array of the same size as y with len(y_prior) True entries


    """
    classes = np.unique(y_prior)
    k_n = {k: (y_prior == k).sum() for k in classes}
    mask = np.array(len(y) * [False])
    for k, n in k_n.iteritems():
        idx_k = np.where(y == k)[0]
        if shuffle:
            np.random.shuffle(idx_k)
        select_n_from_k = idx_k[:n]
        mask[select_n_from_k] = True
    return mask


def performance_over_uncertainty_tol(uncertainty, y, probs, measure):
    uncertainty_tol = np.linspace(np.percentile(uncertainty, 10),
                                  uncertainty.max(),
                                  100)
    p = np.zeros_like(uncertainty_tol)
    p_rand = np.zeros_like(uncertainty_tol)
    p_strat = np.zeros_like(uncertainty_tol)
    frac_retain = np.zeros_like(uncertainty_tol)
    n_samples = len(uncertainty)
    for i, ut in enumerate(uncertainty_tol):
        accept = (uncertainty <= ut)
        rand_sel = np.random.permutation(accept)
        strat_sel = stratified_mask(y, y[accept], shuffle=True)
        p[i] = measure(y[accept], probs[accept])
        p_rand[i] = measure(y[rand_sel], probs[rand_sel])
        p_strat[i] = measure(y[strat_sel], probs[strat_sel])
        frac_retain[i] = accept.sum() / float(n_samples)

    return uncertainty_tol, frac_retain, p, p_rand, p_strat


def acc_rejection_figure(y, y_score, uncertainties, disease_onset,
                         save=False, format='.svg', fig=None):
    if fig is None:
        fig = plt.figure(figsize=(A4_WIDTH_SQUARE[0],
                                  A4_WIDTH_SQUARE[0] / 2.0))

    ax121 = plt.subplot(1, 2, 1)
    ax122 = plt.subplot(1, 2, 2)
    ax121.set_title('(a)')
    ax122.set_title('(b)')
    ax121.set_ylim(0.88, 1)
    ax122.set_ylim(0.88, 1)

    for k, v in uncertainties.iteritems():
        v_tol, frac_retain, acc, acc_rand, acc_strat = \
            performance_over_uncertainty_tol(v, y, y_score, accuracy)
        ax121.plot(v_tol, acc, label=k)
        ax122.plot(frac_retain, acc, label=k)

    ax121.set_xlabel('tolerated model uncertainty')
    ax121.set_ylabel('accuracy')
    ax121.legend(loc='best')

    ax122.plot(frac_retain, acc_rand, label='randomly rejected')
    ax122.plot(frac_retain, acc_strat, label='prior preserved')
    ax122.set_xlabel('fraction of retained data')
    ax122.legend(loc='best')

    if save:
        fig.savefig('acc_' + str(disease_onset) + format)


def roc_auc_rejection_figure(y, y_score, uncertainties, disease_onset,
                             save=False, format='.svg', fig=None):
    if fig is None:
        fig = plt.figure(figsize=A4_WIDTH_SQUARE)

    ax220 = plt.subplot2grid((2, 2), (0, 0))
    ax221 = plt.subplot2grid((2, 2), (0, 1))
    ax2223 = plt.subplot2grid((2, 2), (1, 0), colspan=2)

    ax220.set_title('(a)')
    ax221.set_title('(b)')
    ax2223.set_title('(c)')

    for k, v in uncertainties.iteritems():
        v_tol, frac_retain, auc, auc_rand, auc_strat = \
            performance_over_uncertainty_tol(v, y, y_score,
                                             roc_auc_score)

        ax220.plot(v_tol, auc, label=k)
        ax221.plot(frac_retain, auc, label=k)

        ax2223
        fractions = [0.9, 0.8, 0.7]
        for f in fractions:
            thr = v_tol[frac_retain >= f][0]
            roc_curve_plot(y[v <= thr],
                           y_score[v <= thr],
                           legend_prefix='%d%% data retained, %s' % (f * 100,
                                                                     k))

    ax220.set_xlabel('tolerated model uncertainty')
    ax220.set_ylabel('roc_auc')
    ax220.legend(loc='best')

    ax221.plot(frac_retain, auc_rand, label='randomly rejected')
    ax221.plot(frac_retain, auc_strat, label='prior preserved')
    ax221.set_xlabel('fraction of retained data')
    ax221.legend(loc='best')

    ax2223
    roc_curve_plot(y, y_score, legend_prefix='without rejection',
                   plot_BDA=True)

    if save:
        fig.savefig('roc_' + str(disease_onset) + format)


def error_conditional_uncertainty(y, y_score, uncertainty, disease_onset,
                                  label='pred_std', save=False, format='.png',
                                  ax=None):
    """Plot conditional pdfs for correct and erroneous argmax predictions"""
    if ax is None:
        fig = plt.figure(figsize=A4_WIDTH_SQUARE)
    else:
        fig = plt.gcf()

    y_pred = argmax_labels(y_score)
    corr = (y_pred == y)
    error = (y_pred != y)

    ax = sns.kdeplot(uncertainty[corr], ax=ax, shade=True, cut=0,
                     label=label + '[corr]')
    ax = sns.kdeplot(uncertainty[error], ax=ax, shade=True, cut=0,
                     label=label + '[error]')

    ax.set_xlabel('model uncertainty')
    ax.set_ylabel('density')
    ax.legend(loc='best')

    if save:
        fig.savefig('error_cond_pdf_' + str(disease_onset) + format)

    return ax


def class_conditional_uncertainty(y, uncertainty, disease_onset,
                                  save=False, format='.svg'):
    plt.figure(figsize=map(lambda x: x / 2.0, A4_WIDTH_SQUARE))
    plt.title('Disease onset: {}'.format(disease_onset))
    HEALTHY, DISEASED = 0, 1

    sns.distplot(uncertainty[y == HEALTHY], label='healthy')
    sns.distplot(uncertainty[y == DISEASED], label='diseased')
    plt.xlabel('model uncertainty')
    plt.ylabel('density')
    plt.legend(loc='best')
    plt.ylim(0, 80)

    if save:
        plt.savefig('class_cond_uncertainty_' + str(disease_onset) + format)


def main():
    y = load_labels()
    probs, probs_mc = load_predictions()

    disease_onset_levels = [1]
    for dl in disease_onset_levels:
        y_bin, probs_bin, probs_mc_bin = detection_task(y, probs, probs_mc, dl)
        pred_mean, pred_std = posterior_statistics(probs_mc_bin)
        uncertainties = {'pred_std': pred_std}

        fig = plt.figure(figsize=(A4_WIDTH_SQUARE[0],
                         A4_WIDTH_SQUARE[1] / 2.0))
        ax = fig.gca()
        ax.set_xlim(0, 0.275)
        ax.set_ylim(0, 30)
        error_conditional_uncertainty(y_bin, pred_mean, pred_std, dl,
                                      label='pred_std', save=True, ax=ax)

        acc_rejection_figure(y_bin, pred_mean, uncertainties, dl,
                             save=True, format='.png')

        roc_auc_rejection_figure(y_bin, pred_mean, uncertainties, dl,
                                 save=True, format='.png')

if __name__ == '__main__':
    main()
