import tensorflow as tf
from functools import partial


def mean_squared_loss(model, params, x):
    """
    Computes the heteroscedastic loss.

    ----------
    Arguments:
    model  : tf.keras.Model instance -- a neural network with a single output vector (posterior means)
    params : tf.Tensor of shape (batch_size, n_out_dim) -- data-generating params, as sampled from prior
    x      : tf.Tensor of shape (batch_size, N, x_dim)  -- synthetic data sets generated by the params

    ----------
    Returns:
    loss : tf.Tensor of shape (,) -- a single scalar value representing the squared loss
    """
    
    params_pred = model(x)
    loss = tf.reduce_mean(tf.reduce_sum((params - params_pred)**2, axis=1))
    return loss

def heteroscedastic_loss(model, params, x):
    """
    Computes the heteroscedastic loss.

    ----------
    Arguments:
    model  : tf.keras.Model instance -- a neural network with two outputs (predicted_mean vector, predicted var)
    params : tf.Tensor of shape (batch_size, n_out_dim) -- data-generating params, as sampled from prior
    x      : tf.Tensor of shape (batch_size, N, x_dim)  -- synthetic data sets generated by the params

    ----------
    Returns:
    loss : tf.Tensor of shape (,) -- a single scalar value representing thr heteroscedastic loss
    """
    
    pred_mean, pred_var = model(x)
    logvar = tf.reduce_sum(0.5 * tf.math.log(pred_var), axis=-1)
    squared_error = tf.reduce_sum(0.5 * tf.math.square(params - pred_mean) / pred_var, axis=-1)
    loss = tf.reduce_mean(squared_error + logvar)
    return loss

def kl_latent_space(network, params, sim_data):
    """
    Computes the heteroscedastic loss.
    ----------

    Arguments:
    network   : tf.keras.Model -- a BayesFlow instance
    params    : tf.Tensor of shape (batch_size, n_params) -- data-generating params, as sampled from prior
    sim_data  : tf.Tensor of shape (batch_size, n_obs, data_dim)  -- synthetic data sets generated by the params
    ----------

    Returns:
    loss : tf.Tensor of shape (,) -- a single scalar value representing thr heteroscedastic loss
    """
    
    z, log_det_J = network(params, sim_data)
    loss = tf.reduce_mean(0.5 * tf.square(tf.norm(z, axis=-1)) - log_det_J)
    return loss


def log_loss(network, model_indices, sim_data, lambd=1.0):
    """
    Computes the logloss given output probs and true model indices m_true.
    ----------

    Arguments:
    network       : tf.keras.Model -- an evidential network (with real outputs in [1, +inf])
    model_indices : tf.Tensor of shape (batch_size, n_models) -- true model indices
    sim_data      : tf.Tensor of shape (batch_size, n_obs, data_dim) or (batch_size, summary_dim) 
                    -- synthetic data sets generated by the params or summary statistics thereof
    lambd         : float in [0, 1] -- the weight of the KL regularization term
    ----------

    Output:
    loss : tf.Tensor of shape (,) -- a single scalar Monte-Carlo approximation of the regularized Bayes risk
    """

    # Compute evidences
    alpha = network(sim_data)

    # Obtain probs
    model_probs = alpha / tf.reduce_sum(alpha, axis=1, keepdims=True)
    
    # Numerical stability
    model_probs = tf.clip_by_value(model_probs, 1e-15, 1 - 1e-15)

    # Actual loss + regularization (if given)
    loss = -tf.reduce_mean(tf.reduce_sum(model_indices * tf.math.log(model_probs), axis=1))
    if lambd > 0:
        kl = kl_dirichlet(model_indices, alpha)
        loss = loss + lambd * kl
    return loss


def kl_dirichlet(model_indices, alpha):
    """
    Computes the KL divergence between a Dirichlet distribution with parameter vector alpha and a uniform Dirichlet.
    ----------

    Arguments:
    model_indices : tf.Tensor of shape (batch_size, n_models) -- one-hot-encoded true model indices
    alpha         : tf.Tensor of shape (batch_size, n_models) -- positive network outputs in [1, +inf]
    ----------

    Output:
    kl: tf.Tensor of shape (,)  -- a single scalar representing KL( Dir(alpha) | Dir(1,1,...,1) )
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
         tf.reduce_sum(tf.math.lgamma(beta), axis=1, keepdims=True) - tf.math.lgamma(tf.reduce_sum(beta, axis=1, keepdims=True))
    loss = tf.reduce_mean(kl)
    return loss


def maximum_mean_discrepancy(source_samples, target_samples, weight=1., minimum=0., **args):
    """
    This Maximum Mean Discrepancy (MMD) loss is calculated with a number of
    different Gaussian kernels.
    ----------

    Arguments:
    x : tf.Tensor of shape  [N, num_features].
    y:  tf.Tensor of shape  [M, num_features].
    weight: the weight of the MMD loss.
    ----------

    Output:
    loss_value : tf.Tensor of shape (,) - a scalar MMD
    """

    sigmas = [
        1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1, 5, 10, 15, 20, 25, 30, 35, 100,
        1e3, 1e4, 1e5, 1e6
    ]
    gaussian_kernel = partial(_gaussian_kernel_matrix, sigmas=sigmas)
    loss_value = _mmd_kernel(source_samples, target_samples, kernel=gaussian_kernel)
    loss_value = tf.maximum(minimum, loss_value) * weight
    return loss_value

def _gaussian_kernel_matrix(x, y, sigmas):
    """
    Computes a Guassian Radial Basis Kernel between the samples of x and y.
    We create a sum of multiple gaussian kernels each having a width sigma_i.
    ----------

    Arguments:
    x :  tf.Tensor of shape [M, num_features]
    y :  tf.Tensor of shape [N, num_features]
    sigmas : list of floats which denotes the widths of each of the
      gaussians in the kernel.
    ----------

    Output:
    tf.Tensor of shape [num_samples{x}, num_samples{y}] with the RBF kernel.
    """

    beta = 1. / (2. * (tf.expand_dims(sigmas, 1)))
    norm = lambda x: tf.reduce_sum(tf.square(x), 1)
    dist = tf.transpose(norm(tf.expand_dims(x, 2) - tf.transpose(y)))
    s = tf.matmul(beta, tf.reshape(dist, (1, -1)))
    return tf.reshape(tf.reduce_sum(tf.exp(-s), 0), tf.shape(dist))
    

def _mmd_kernel(x, y, kernel=_gaussian_kernel_matrix):
    """
    Computes the Maximum Mean Discrepancy (MMD) of two samples: x and y.
    Maximum Mean Discrepancy (MMD) is a distance-measure between the samples of
    the distributions of x and y.
    ----------

    Arguments:
    x      : tf.Tensor of shape [num_samples, num_features]
    y      : tf.Tensor of shape [num_samples, num_features]
    kernel : a function which computes the kernel in MMD. 
    ----------

    Output:
    loss : tf.Tensor of shape (,) denoting the squared maximum mean discrepancy loss.
    """

    loss = tf.reduce_mean(kernel(x, x))
    loss += tf.reduce_mean(kernel(y, y))
    loss -= 2 * tf.reduce_mean(kernel(x, y))
    return loss