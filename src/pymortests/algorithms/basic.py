# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright 2013-2020 pyMOR developers and contributors. All rights reserved.
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from numbers import Number
import pytest
import numpy as np
from hypothesis import given, assume, reproduce_failure, settings, HealthCheck, example
from hypothesis import strategies as hyst

import pymor
from pymor.algorithms.basic import almost_equal, project_array, relative_error
from pymor.algorithms.gram_schmidt import gram_schmidt
if pymor.config.HAVE_NGSOLVE:
    from pymor.bindings.ngsolve import NGSolveVectorSpace
else:
    class NGSolveVectorSpace: pass
from pymor.operators.constructions import induced_norm
from pymor.operators.numpy import NumpyMatrixOperator
from pymor.tools.floatcmp import float_cmp
from pymor.vectorarrays.numpy import NumpyVectorSpace
from pymortests.fixtures.operator import operator_with_arrays_and_products
from pymortests.strategies import valid_inds, valid_inds_of_same_length
from pymortests.vectorarray import indexed
import pymortests.strategies as pyst


@pyst.given_vector_arrays(count=2,
                          tolerances=hyst.sampled_from([(1e-5, 1e-8), (1e-10, 1e-12), (0., 1e-8), (1e-5, 1e-8)]),
                          norms=hyst.sampled_from([('sup', np.inf), ('l1', 1), ('l2', 2)]))
def test_almost_equal(vector_arrays, tolerances, norms):
    v1, v2 = vector_arrays
    rtol, atol = tolerances
    n, o = norms
    try:
        dv1 = v1.to_numpy()
        dv2 = v2.to_numpy()
    except NotImplementedError:
        dv1 = dv2 = None
    for ind1, ind2 in valid_inds_of_same_length(v1, v2):
        try:
            r = almost_equal(v1[ind1], v2[ind2], norm=n, rtol=rtol, atol=atol)
        except NotImplementedError as e:
            if n == 'l1':
                pytest.xfail('l1_norm not implemented')
            else:
                raise e
        assert isinstance(r, np.ndarray)
        assert r.shape == (v1.len_ind(ind1),)
        if dv1 is not None:
            if dv2.shape[1] == 0:
                continue
            assert np.all(r == (np.linalg.norm(indexed(dv1, ind1) - indexed(dv2, ind2), ord=o, axis=1)
                                <= atol + rtol * np.linalg.norm(indexed(dv2, ind2), ord=o, axis=1)))


def test_almost_equal_product(operator_with_arrays_and_products):
    _, _, v1, _, product, _ = operator_with_arrays_and_products
    if len(v1) < 2:
        return
    v2 = v1.empty()
    v2.append(v1[:len(v1) // 2])
    for ind1, ind2 in valid_inds_of_same_length(v1, v2):
        for rtol, atol in ((1e-5, 1e-8), (1e-10, 1e-12), (0., 1e-8), (1e-5, 1e-8)):
            norm = induced_norm(product)

            r = almost_equal(v1[ind1], v2[ind2], norm=norm)
            assert isinstance(r, np.ndarray)
            assert r.shape == (v1.len_ind(ind1),)
            assert np.all(r == (norm(v1[ind1] - v2[ind2])
                                <= atol + rtol * norm(v2[ind2])))

            r = almost_equal(v1[ind1], v2[ind2], product=product)
            assert isinstance(r, np.ndarray)
            assert r.shape == (v1.len_ind(ind1),)
            assert np.all(r == (norm(v1[ind1] - v2[ind2])
                                <= atol + rtol * norm(v2[ind2])))


@pyst.given_vector_arrays(count=1, index_strategy=pyst.pairs_same_length,
                          tolerances=hyst.sampled_from([(1e-5, 1e-8), (1e-10, 1e-12), (0., 1e-8), (1e-5, 1e-8), (1e-12, 0.)]),
                          norm=hyst.sampled_from(['sup', 'l1', 'l2']))
@settings(print_blob=True)
def test_almost_equal_self(vectors_and_indices, tolerances, norm):
    v, (ind,_) = vectors_and_indices
    rtol, atol = tolerances
    n = norm
    try:
        r = almost_equal(v[ind], v[ind], norm=n)
    except NotImplementedError as e:
        if n == 'l1':
            pytest.xfail('l1_norm not implemented')
        else:
            raise e
    assert isinstance(r, np.ndarray)
    assert r.shape == (v.len_ind(ind),)
    assert np.all(r)
    # TODO drop assumptions
    # the first assumption here is a direct translation of the old loop abort
    assume(v.len_ind(ind) > 0 and np.max(v[ind].sup_norm() > 0))
    # the second one accounts for old input missing very-near zero data
    tol_min = np.min(np.abs(tolerances))
    v_n_min = np.min(getattr(v[ind], n + '_norm')())
    assume(v_n_min > tol_min)

    c = v.copy()
    c.scal(atol * (1 - 1e-10) / (np.max(getattr(v[ind], n + '_norm')())))
    assert np.all(almost_equal(c[ind], c.zeros(v.len_ind(ind)), atol=atol, rtol=rtol, norm=n))

    if atol > 0:
        c = v.copy()
        c.scal(2. * atol / (np.max(getattr(v[ind], n + '_norm')())))
        assert not np.all(almost_equal(c[ind], c.zeros(v.len_ind(ind)), atol=atol, rtol=rtol, norm=n))

    c = v.copy()
    c.scal(1. + rtol * 0.9)
    assert np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=n))

    if rtol > 0:
        c = v.copy()
        c.scal(2. + rtol * 1.1)
        assert not np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=n))

    c = v.copy()
    c.scal(1. + atol * 0.9 / np.max(getattr(v[ind], n + '_norm')()))
    assert np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=n))

    if atol > 0 or rtol > 0:
        c = v.copy()
        c.scal(1 + rtol * 1.1 + atol * 1.1 / np.max(getattr(v[ind], n + '_norm')()))
        assert not np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=n))


def test_almost_equal_self_product(operator_with_arrays_and_products):
    _, _, v, _, product, _ = operator_with_arrays_and_products
    norm = induced_norm(product)
    for ind in valid_inds(v):
        for rtol, atol in ((1e-5, 1e-8), (1e-10, 1e-12), (0., 1e-8), (1e-5, 1e-8), (1e-12, 0.)):
            r = almost_equal(v[ind], v[ind], norm=norm)
            assert isinstance(r, np.ndarray)
            assert r.shape == (v.len_ind(ind),)
            assert np.all(r)
            if v.len_ind(ind) == 0 or np.max(v[ind].sup_norm() == 0):
                continue

            r = almost_equal(v[ind], v[ind], product=product)
            assert isinstance(r, np.ndarray)
            assert r.shape == (v.len_ind(ind),)
            assert np.all(r)
            if v.len_ind(ind) == 0 or np.max(v[ind].sup_norm() == 0):
                continue

            c = v.copy()
            c.scal(atol * (1 - 1e-10) / (np.max(norm(v[ind]))))
            assert np.all(almost_equal(c[ind], c.zeros(v.len_ind(ind)), atol=atol, rtol=rtol, norm=norm))
            assert np.all(almost_equal(c[ind], c.zeros(v.len_ind(ind)), atol=atol, rtol=rtol, product=product))

            if atol > 0:
                c = v.copy()
                c.scal(2. * atol / (np.max(norm(v[ind]))))
                assert not np.all(almost_equal(c[ind], c.zeros(v.len_ind(ind)), atol=atol, rtol=rtol, norm=norm))
                assert not np.all(almost_equal(c[ind], c.zeros(v.len_ind(ind)), atol=atol, rtol=rtol, product=product))

            c = v.copy()
            c.scal(1. + rtol * 0.9)
            assert np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=norm))
            assert np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, product=product))

            if rtol > 0:
                c = v.copy()
                c.scal(2. + rtol * 1.1)
                assert not np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=norm))
                assert not np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, product=product))

            c = v.copy()
            c.scal(1. + atol * 0.9 / np.max(np.max(norm(v[ind]))))
            assert np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=norm))
            assert np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, product=product))

            if atol > 0 or rtol > 0:
                c = v.copy()
                c.scal(1 + rtol * 1.1 + atol * 1.1 / np.max(np.max(norm(v[ind]))))
                assert not np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, norm=norm))
                assert not np.all(almost_equal(c[ind], v[ind], atol=atol, rtol=rtol, product=product))


@pyst.given_vector_arrays(count=2, compatible=False)
def test_almost_equal_incompatible(vector_arrays):
    v1, v2 = vector_arrays
    for ind1, ind2 in valid_inds_of_same_length(v1, v2):
        for n in ['sup', 'l1', 'l2']:
            c1, c2 = v1.copy(), v2.copy()
            with pytest.raises(Exception):
                almost_equal(c1[ind1], c2[ind2], norm=n)


@given(pyst.base_vector_arrays(count=2))
@settings(deadline=None)
def test_project_array(arrays):
    U, basis = arrays
    U_p = project_array(U, basis, orthonormal=False)
    onb = gram_schmidt(basis)
    U_p2 = project_array(U, onb, orthonormal=True)
    err = relative_error(U_p, U_p2)
    tol = np.finfo(np.float64).eps * np.linalg.cond(basis.gramian()) * 100.
    assert np.all(err < tol)


def test_project_array_with_product():
    np.random.seed(123)
    U = NumpyVectorSpace.from_numpy(np.random.random((1, 10)))
    basis = NumpyVectorSpace.from_numpy(np.random.random((3, 10)))
    product = np.random.random((10, 10))
    product = NumpyMatrixOperator(product.T.dot(product))
    U_p = project_array(U, basis, product=product, orthonormal=False)
    onb = gram_schmidt(basis, product=product)
    U_p2 = project_array(U, onb, product=product, orthonormal=True)
    tol = 3e-10
    assert np.all(relative_error(U_p, U_p2, product) < tol)
