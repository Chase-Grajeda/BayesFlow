

import tensorflow as tf

from bayesflow.computational_utilities import maximum_mean_discrepancy

def kl_latent_space_gaussian(z, log_det_J):
    """ Computes the Kullback-Leibler divergence between true and approximate
    posterior assumes a Gaussian latent space as a source distribution.

    Parameters
    ----------
    z          : tf.Tensor of shape (batch_size, ...)
        The (latent transformed) target variables
    log_det_J  : tf.Tensor of shape (batch_size, ...)
        The logartihm of the Jacobian determinant of the transformation.

    Returns
    -------
    loss : tf.Tensor
        A single scalar value representing the KL loss, shape (,)

    Examples
    --------
    Parameter estimation

    >>> kl_latent_space(z, sim_data)
    """

    loss = tf.reduce_mean(0.5 * tf.math.square(tf.norm(z, axis=-1)) - log_det_J)
    return loss


def kl_latent_space_student(v, z, log_det_J):
    """ Computes the Kullback-Leibler divergence between true and approximate
    posterior assuming latent student t-distribution as a source distribution.

    Parameters
    ----------
    v          : tf Tensor of shape (batch_size, ...)
        The degrees of freedom of the latent student t-distribution
    z          : tf.Tensor of shape (batch_size, ...)
        The (latent transformed) target variables
    log_det_J  : tf.Tensor of shape (batch_size, ...)
        The logartihm of the Jacobian determinant of the transformation.

    Returns
    -------
    loss : tf.Tensor
        A single scalar value representing the KL loss, shape (,)
    """
    
    d = z.shape[-1]
    loss = 0.
    loss -= d * tf.math.lgamma(0.5*(v + 1))
    loss += d * tf.math.lgamma(0.5*v + 1e-15)
    loss += (0.5*d) * tf.math.log(v + 1e-15)
    loss += 0.5*(v+1) * tf.reduce_sum(tf.math.log1p(z**2 / v), axis=-1)
    loss -= log_det_J
    mean_loss = tf.reduce_mean(loss)
    return mean_loss


def kl_dirichlet(model_indices, alpha):
    """ Computes the KL divergence between a Dirichlet distribution with parameter vector alpha and a uniform Dirichlet.

    Parameters
    ----------
    model_indices : tf.Tensor of shape (batch_size, n_models)
        one-hot-encoded true model indices
    alpha         : tf.Tensor of shape (batch_size, n_models)
        positive network outputs in ``[1, +inf]``

    Returns
    -------
    kl : tf.Tensor
        A single scalar representing :math:`D_{KL}(\mathrm{Dir}(\\alpha) | \mathrm{Dir}(1,1,\ldots,1) )`, shape (,)
    """

    # Extract number of models
    J = int(model_indices.shape[1])

    # Set-up ground-truth preserving prior
    alpha = alpha * (1 - model_indices) + model_indices
    beta = tf.ones((1, J), dtype=tf.float32)
    alpha0 = tf.reduce_sum(alpha, axis=1, keepdims=True)

    # Computation of KL
    kl = tf.reduce_sum((alpha - beta) * (tf.math.digamma(alpha) - tf.math.digamma(alpha0)), axis=1, keepdims=True) + \
        tf.math.lgamma(alpha0) - tf.reduce_sum(tf.math.lgamma(alpha), axis=1, keepdims=True) + \
        tf.reduce_sum(tf.math.lgamma(beta), axis=1, keepdims=True) - tf.math.lgamma(
        tf.reduce_sum(beta, axis=1, keepdims=True))
    loss = tf.reduce_mean(kl)
    return loss


def mmd_summary_space(summary_outputs, z_dist=tf.random.normal):
    """ Computes the MMD(p(summary_otuputs) | z_dist) to re-shape the summary network outputs in
    an information-preserving manner.

    Parameters
    ----------
    summary_outputs   : tf Tensor of shape (batch_size, ...)
        The degrees of freedom of the latent student t-distribution

    """

    z_samples = z_dist(summary_outputs.shape) 
    mmd_loss = maximum_mean_discrepancy(summary_outputs, z_samples)
    return mmd_loss


def log_loss(model_indices, alpha):
    """ Computes the logloss given output probs and true model indices m_true.

    Parameters
    ----------
    model_indices : tf.Tensor of shape (batch_size, n_models)
        one-hot-encoded true model indices
    alpha         : tf.Tensor of shape (batch_size, n_models)
        positive network outputs in ``[1, +inf]``

    Returns
    -------
    loss : tf.Tensor
        A single scalar Monte-Carlo approximation of the log-loss, shape (,)
    """

    # Obtain probs
    model_probs = alpha / tf.reduce_sum(alpha, axis=1, keepdims=True)

    # Numerical stability
    model_probs = tf.clip_by_value(model_probs, 1e-15, 1 - 1e-15)

    # Actual loss + regularization (if given)
    loss = -tf.reduce_mean(tf.reduce_sum(model_indices * tf.math.log(model_probs), axis=1))
    return loss

