# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2019 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

"""Module for SVD method of operators represented by |VectorArrays|."""

import numpy as np
import scipy.linalg as spla

from pymor.algorithms.gram_schmidt import gram_schmidt
from pymor.core.defaults import defaults
from pymor.core.exceptions import AccuracyError
from pymor.core.logger import getLogger
from pymor.operators.interfaces import OperatorInterface
from pymor.vectorarrays.interfaces import VectorArrayInterface


@defaults('rtol', 'atol', 'l2_err', 'orthonormalize', 'check', 'check_tol')
def method_of_snapshots(A, product=None, modes=None, rtol=4e-8, atol=0., l2_err=0.,
                        orthonormalize=True, check=True, check_tol=1e-10):
    """Method of snapshots.

    Viewing the |VectorArray| `A` as a `A.dim` x `len(A)` matrix,
    the return value of this method is the |VectorArray| of left-singular
    vectors of the singular value decomposition of `A`, where the inner product
    on R^(`dim(A)`) is given by `product` and the inner product on R^(`len(A)`)
    is the Euclidean inner product.

    Parameters
    ----------
    A
        The |VectorArray| for which the POD is to be computed.
    product
        Inner product |Operator| w.r.t. which the POD is computed.
    modes
        If not `None`, only the first `modes` POD modes (singular vectors) are
        returned.
    rtol
        Singular values smaller than this value multiplied by the largest singular
        value are ignored.
    atol
        Singular values smaller than this value are ignored.
    l2_err
        Do not return more modes than needed to bound the l2-approximation
        error by this value. I.e. the number of returned modes is at most ::

            argmin_N { sum_{n=N+1}^{infty} s_n^2 <= l2_err^2 }

        where `s_n` denotes the n-th singular value.
    orthonormalize
        If `True`, orthonormalize the computed POD modes again using
        the :func:`~pymor.algorithms.gram_schmidt.gram_schmidt` algorithm.
        If `False`, do not orthonormalize.
    check
        If `True`, check the computed POD modes for orthonormality.
    check_tol
        Tolerance for the orthonormality check.

    Returns
    -------
    U
        |VectorArray| of left singular vectors.
    s
        Sequence of singular values.
    Vh
        |NumPy array| of right singular vectors.
    """
    assert isinstance(A, VectorArrayInterface)
    assert product is None or isinstance(product, OperatorInterface)
    assert modes is None or modes <= len(A)

    if A.dim == 0 or len(A) == 0:
        return A.space.empty(), np.array([]), np.zeros((0, len(A)))

    logger = getLogger('pymor.algorithms.svd_va.method_of_snapshots')

    with logger.block(f'Computing Gramian ({len(A)} vectors) ...'):
        B = A.gramian(product)

    with logger.block('Computing eigenvalue decomposition ...'):
        eigvals = (None
                   if modes is None or l2_err > 0.
                   else (len(B) - modes, len(B) - 1))

        evals, V = spla.eigh(B, overwrite_a=True, turbo=True, eigvals=eigvals)
        evals = evals[::-1]
        V = V.T[::-1, :]

        tol = max(rtol ** 2 * evals[0], atol ** 2)
        above_tol = np.where(evals >= tol)[0]
        if len(above_tol) == 0:
            return A.space.empty(), np.array([]), np.zeros((0, len(A)))
        last_above_tol = above_tol[-1]

        errs = np.concatenate((np.cumsum(evals[::-1])[::-1], [0.]))
        below_err = np.where(errs <= l2_err**2)[0]
        first_below_err = below_err[0]

        selected_modes = min(first_below_err, last_above_tol + 1)
        if modes is not None:
            selected_modes = min(selected_modes, modes)

        s = np.sqrt(evals[:selected_modes])
        V = V[:selected_modes]
        Vh = V.conj()

    with logger.block(f'Computing left-singular vectors ({len(V)} vectors) ...'):
        U = A.lincomb(V / s[:, np.newaxis])

    if orthonormalize:
        with logger.block('Re-orthonormalizing left singular vectors ...'):
            gram_schmidt(U, product=product, copy=False, check=False)
        if len(U) < len(s):
            raise AccuracyError('additional orthonormalization removed basis vectors')

    if check:
        logger.info('Checking orthonormality ...')
        err = np.max(np.abs(U.inner(U, product) - np.eye(len(U))))
        if err >= check_tol:
            raise AccuracyError(f'result not orthogonal (max err={err})')

    return U, s, Vh


@defaults('rtol', 'atol', 'l2_err', 'check', 'check_tol')
def qr_svd(A, product=None, modes=None, rtol=4e-8, atol=0., l2_err=0., check=True, check_tol=1e-10):
    """SVD of a |VectorArray| using Gram-Schmidt process.

    If `product` is given, left singular vectors will be orthogonal with
    respect to it. Otherwise, the Euclidean inner product is used.

    Parameters
    ----------
    A
        The |VectorArray| for which the SVD is to be computed.
        The vectors are interpreted as columns in a matrix.
    product
        Inner product |Operator| w.r.t. which the left singular vectors
        are computed.
    modes
        If not `None`, only the first `modes` POD modes (singular vectors) are
        returned.
    rtol
        Singular values smaller than this value multiplied by the largest singular
        value are ignored.
    atol
        Singular values smaller than this value are ignored.
    l2_err
        Do not return more modes than needed to bound the l2-approximation
        error by this value. I.e. the number of returned modes is at most ::

            argmin_N { sum_{n=N+1}^{infty} s_n^2 <= l2_err^2 }

        where `s_n` denotes the n-th singular value.
    check
        If `True`, check the computed POD modes for orthonormality.
    check_tol
        Tolerance for the orthonormality check.

    Returns
    -------
    U
        |VectorArray| of left singular vectors.
    s
        Sequence of singular values.
    Vh
        |NumPy array| of right singular vectors.
    """
    assert isinstance(A, VectorArrayInterface)
    assert product is None or isinstance(product, OperatorInterface)
    assert modes is None or modes <= len(A)

    if A.dim == 0 or len(A) == 0:
        return A.space.empty(), np.array([]), np.zeros((0, len(A)))

    logger = getLogger('pymor.algorithms.svd_va.qr_svd')

    with logger.block('Computing QR decomposition ...'):
        Q, R = gram_schmidt(A, product=product, return_R=True, check=False)

    with logger.block('Computing SVD of R ...'):
        U2, s, Vh = spla.svd(R, lapack_driver='gesvd')

    with logger.block('Choosing the number of modes ...'):
        tol = max(rtol * s[0], atol)
        above_tol = np.where(s >= tol)[0]
        if len(above_tol) == 0:
            return A.space.empty(), np.array([]), np.zeros((0, len(A)))
        last_above_tol = above_tol[-1]

        errs = np.concatenate((np.cumsum(s[::-1] ** 2)[::-1], [0.]))
        below_err = np.where(errs <= l2_err**2)[0]
        first_below_err = below_err[0]

        selected_modes = min(first_below_err, last_above_tol + 1)
        if modes is not None:
            selected_modes = min(selected_modes, modes)

        U2 = U2[:, :selected_modes]
        s = s[:selected_modes]
        Vh = Vh[:selected_modes]

    with logger.block(f'Computing left singular vectors ({selected_modes} modes) ...'):
        U = Q.lincomb(U2.T)

    if check:
        logger.info('Checking orthonormality ...')
        err = np.max(np.abs(U.inner(U, product) - np.eye(len(U))))
        if err >= check_tol:
            raise AccuracyError(f'result not orthogonal (max err={err})')

    return U, s, Vh