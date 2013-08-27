# This file is part of the pyMor project (http://www.pymor.org).
# Copyright Holders: Felix Albrecht, Rene Milk, Stephan Rave
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)

from __future__ import absolute_import, division, print_function

import numpy as np
from scipy.linalg import solve_triangular


from pymor.la.interfaces import VectorArrayInterface
from pymor.la import NumpyVectorArray
from pymor.operators import OperatorInterface, OperatorBase
from pymor.tools import float_cmp_all


class EmpiricalInterpolatedOperator(OperatorBase):

    def __init__(self, operator, interpolation_dofs, collateral_basis, name=None):
        assert isinstance(operator, OperatorInterface)
        assert isinstance(collateral_basis, VectorArrayInterface)
        assert operator.dim_source == operator.dim_range == collateral_basis.dim
        assert operator.type_range == type(collateral_basis)
        assert hasattr(operator, 'restricted')

        self.build_parameter_type(inherits=(operator,))
        self.dim_source = operator.dim_source
        self.dim_range = operator.dim_range
        self.type_source = operator.type_source
        self.type_range = operator.type_range
        self.linear = operator.linear
        self.name = name or '{}_interpolated'.format(operator.name)

        interpolation_dofs = np.array(interpolation_dofs, dtype=np.int32)
        self.interpolation_dofs = interpolation_dofs

        if len(interpolation_dofs) > 0:
            restricted_operator, source_dofs  = operator.restricted(interpolation_dofs)
            interpolation_matrix = collateral_basis.components(interpolation_dofs).T
            self.restricted_operator = restricted_operator
            self.source_dofs = source_dofs
            self.interpolation_matrix = interpolation_matrix
            self.collateral_basis = collateral_basis.copy()

    def apply(self, U, ind=None, mu=None):
        mu = self.parse_parameter(mu)
        if len(self.interpolation_dofs) == 0:
            count = len(ind) if ind is not None else len(U)
            return self.type_range.zeros(dim=self.dim_range, count=count)

        U_components = NumpyVectorArray(U.components(self.source_dofs, ind=ind), copy=False)
        AU = self.restricted_operator.apply(U_components, mu=mu)
        interpolation_coefficients = solve_triangular(self.interpolation_matrix, AU._array.T,
                                                      lower=True, unit_diagonal=True).T
        # interpolation_coefficients = np.linalg.solve(self.interpolation_matrix, AU._array.T).T
        return self.collateral_basis.lincomb(interpolation_coefficients)

    def projected(self, source_basis, range_basis, product=None, name=None):
        assert source_basis is not None or self.dim_source == 0
        assert range_basis is not None
        assert source_basis is None or self.dim_source == source_basis.dim
        assert self.dim_range == range_basis.dim
        assert source_basis is None or self.type_source == type(source_basis)
        assert self.type_range == type(range_basis)

        if product is None:
            projected_collateral_basis = NumpyVectorArray(self.collateral_basis.dot(range_basis, pairwise=False))
        else:
            projected_collateral_basis = NumpyVectorArray(product.apply2(self.collateral_basis, range_basis,
                                                                         pairwise=False))

        return ProjectedEmpiciralInterpolatedOperator(self.restricted_operator, self.interpolation_matrix,
                                                      NumpyVectorArray(source_basis.components(self.source_dofs),
                                                                       copy=False),
                                                      projected_collateral_basis, name)


class ProjectedEmpiciralInterpolatedOperator(OperatorBase):

    def __init__(self, restricted_operator, interpolation_matrix, source_basis_dofs,
                 projected_collateral_basis, name=None):
        self.dim_source = len(source_basis_dofs)
        self.dim_range = projected_collateral_basis.dim
        self.type_source = self.type_range = NumpyVectorArray
        self.linear = restricted_operator.linear
        self.build_parameter_type(inherits=(restricted_operator,))
        self.restricted_operator = restricted_operator
        self.interpolation_matrix = interpolation_matrix
        self.source_basis_dofs = source_basis_dofs
        self.projected_collateral_basis = projected_collateral_basis
        self.name = name or '{}_projected'.format(restricted_operator.name)

    def apply(self, U, ind=None, mu=None):
        mu = self.parse_parameter(mu)
        U_components = self.source_basis_dofs.lincomb(U._array, ind=ind)
        AU = self.restricted_operator.apply(U_components, mu=mu)
        interpolation_coefficients = solve_triangular(self.interpolation_matrix, AU._array.T,
                                                      lower=True, unit_diagonal=True).T
        return self.projected_collateral_basis.lincomb(interpolation_coefficients)

    def projected_to_subbasis(self, dim_source=None, dim_range=None, dim_collateral=None, name=None):
        assert dim_source is None or dim_source <= self.dim_source
        assert dim_range is None or dim_range <= self.dim_range
        assert dim_collateral is None or dim_collateral <= self.restricted_operator.dim_range
        name = name or '{}_projected_to_subbasis'.format(self.name)

        interpolation_matrix = self.interpolation_matrix[:dim_collateral, :dim_collateral]

        if dim_collateral is not None:
            restricted_operator, source_dofs = self.restricted_operator.restricted(np.arange(dim_collateral))
        else:
            restricted_operator = self.restricted_operator

        old_pcb = self.projected_collateral_basis
        projected_collateral_basis = NumpyVectorArray(old_pcb.data[:dim_collateral, :dim_range], copy=False)

        old_sbd = self.source_basis_dofs
        source_basis_dofs = NumpyVectorArray(old_sbd.data[:dim_source], copy=False) if dim_collateral is None \
            else NumpyVectorArray(old_sbd.data[:dim_source, source_dofs], copy=False)

        return ProjectedEmpiciralInterpolatedOperator(restricted_operator, interpolation_matrix,
                                                      source_basis_dofs, projected_collateral_basis, name=name)
