import functools
import sympy as sp
import numpy as np
from numpy.polynomial import laguerre as lag
from scipy.special import eval_laguerre
from mpi4py_fft import fftw
from shenfun.spectralbase import SpectralBase, work, Transform, islicedict, slicedict
from shenfun.utilities import inheritdocstrings

#pylint: disable=method-hidden,no-else-return,not-callable,abstract-method,no-member,cyclic-import


@inheritdocstrings
class LaguerreBase(SpectralBase):
    """Base class for all Laguerre bases

    Parameters
    ----------
        N : int
            Number of quadrature points
        quad : str, optional
            Type of quadrature

            - LG - Laguerre-Gauss

        padding_factor : float, optional
            Factor for padding backward transforms.
        dealias_direct : bool, optional
            Set upper 1/3 of coefficients to zero before backward transform
    Note
    ----
    We are using Laguerre functions and not the regular Laguerre polynomials
    as basis functions. A Laguerre function is defined as

    .. math::

        L_k = P_k \cdot \exp(-x/2)

    where :math:`L_k` and :math:`P_k` are the Laguerre function and Laguerre
    polynomials of order k, respectively.

    """

    def __init__(self, N, quad="LG", padding_factor=1, dealias_direct=False):
        SpectralBase.__init__(self, N, quad=quad, domain=(0., np.inf),
                              padding_factor=padding_factor, dealias_direct=dealias_direct)
        self.forward = functools.partial(self.forward, fast_transform=False)
        self.backward = functools.partial(self.backward, fast_transform=False)
        self.scalar_product = functools.partial(self.scalar_product, fast_transform=False)

    @staticmethod
    def family():
        return 'laguerre'

    def reference_domain(self):
        return (0., np.inf)

    def domain_factor(self):
        return 1

    def points_and_weights(self, N=None, map_true_domain=False, weighted=True, **kw):
        if N is None:
            N = self.N
        if self.quad == "LG":
            points, weights = lag.laggauss(N)
            if weighted:
                weights *= np.exp(points)
        else:
            raise NotImplementedError

        return points, weights

    def vandermonde(self, x):
        V = lag.lagvander(x, self.N-1)
        return V

    def evaluate_basis(self, x, i=0, output_array=None):
        x = np.atleast_1d(x)
        if output_array is None:
            output_array = np.zeros(x.shape)
        output_array = eval_laguerre(i, x, out=output_array)
        output_array *= np.exp(-x/2)
        return output_array

    def evaluate_basis_derivative_all(self, x=None, k=0, argument=0):
        if x is None:
            x = self.mesh(False, False)
        V = self.vandermonde(x)
        M = V.shape[1]
        if k == 1:
            D = np.zeros((M, M))
            D[:-1, :] = lag.lagder(np.eye(M), 1)
            W = np.dot(V, D)
            W -= 0.5*V
            V = W*np.exp(-x/2)[:, np.newaxis]

        elif k == 2:
            D = np.zeros((M, M))
            D[:-2, :] = lag.lagder(np.eye(M), 2)
            D[:-1, :] -= lag.lagder(np.eye(M), 1)
            W = np.dot(V, D)
            W += 0.25*V
            V = W*np.exp(-x/2)[:, np.newaxis]

        elif k == 0:
            V *= np.exp(-x/2)[:, np.newaxis]

        else:
            raise NotImplementedError

        return self._composite_basis(V)

    def evaluate_basis_all(self, x=None, argument=0):
        if x is None:
            x = self.mesh(False, False)
        V = self.vandermonde(x)
        V *= np.exp(-x/2)[:, np.newaxis]
        return self._composite_basis(V, argument)

    def _composite_basis(self, V, argument=0):
        """Return composite basis, where ``V`` is primary Vandermonde matrix."""
        return V

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            assert len(axis) == 1
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        U = fftw.aligned(shape, dtype=dtype)
        V = fftw.aligned(shape, dtype=dtype)
        U.fill(0)
        V.fill(0)
        self.axis = axis
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)
        self.si = islicedict(axis=self.axis, dimensions=self.dimensions)
        self.sl = slicedict(axis=self.axis, dimensions=self.dimensions)

    def get_refined(self, N):
        return self.__class__(N,
                              quad=self.quad,
                              padding_factor=self.padding_factor,
                              dealias_direct=self.dealias_direct)

    def get_dealiased(self, padding_factor=1.5, dealias_direct=False):
        return self.__class__(self.N,
                              quad=self.quad,
                              padding_factor=padding_factor,
                              dealias_direct=dealias_direct)

@inheritdocstrings
class Basis(LaguerreBase):
    r"""Basis for regular Laguerre functions

    Parameters
    ----------
        N : int
            Number of quadrature points
        quad : str, optional
            Type of quadrature

            - LG - Laguerre-Gauss
        padding_factor : float, optional
            Factor for padding backward transforms.
        dealias_direct : bool, optional
            Set upper 1/3 of coefficients to zero before backward transform

    Note
    ----
    We are using Laguerre functions and not the regular Laguerre polynomials
    as basis functions. A Laguerre function is defined as

    .. math::

        L_k = P_k \cdot \exp(-x/2)

    where :math:`L_k` and :math:`P_k` are the Laguerre function and Laguerre
    polynomials of order k, respectively.
    """

    def __init__(self, N, quad="LG", padding_factor=1, dealias_direct=False):
        LaguerreBase.__init__(self, N, quad=quad, padding_factor=padding_factor,
                              dealias_direct=dealias_direct)
        self.plan(int(N*padding_factor), 0, np.float, {})

    def eval(self, x, u, output_array=None):
        x = np.atleast_1d(x)
        if output_array is None:
            output_array = np.zeros(x.shape)
        output_array[:] = lag.lagval(x, u)*np.exp(-x/2)
        return output_array

    def sympy_basis(self, i=0):
        x = sp.symbols('x')
        return sp.laguerre(i, x)*sp.exp(-x/2)

    @property
    def is_orthogonal(self):
        return True

    def get_orthogonal(self):
        return self

@inheritdocstrings
class ShenDirichletBasis(LaguerreBase):
    """Shen Laguerre basis for Dirichlet boundary conditions

    Parameters
    ----------
        N : int
            Number of quadrature points
        quad : str, optional
            Type of quadrature

            - LG - Laguerre-Gauss
        padding_factor : float, optional
            Factor for padding backward transforms.
        dealias_direct : bool, optional
            Set upper 1/3 of coefficients to zero before backward transform

    """
    def __init__(self, N, quad="LG", bc=(0., 0.), padding_factor=1,
                 dealias_direct=False):
        LaguerreBase.__init__(self, N, quad=quad, padding_factor=padding_factor,
                              dealias_direct=dealias_direct)
        self.LT = Basis(N, quad)
        self.plan(int(N*padding_factor), 0, np.float, {})

    @staticmethod
    def boundary_condition():
        return 'Dirichlet'

    def _composite_basis(self, V, argument=0):
        assert self.N == V.shape[1]
        P = np.zeros(V.shape)
        P[:, :-1] = V[:, :-1] - V[:, 1:]
        return P

    def to_ortho(self, input_array, output_array=None):
        if output_array is None:
            output_array = np.zeros_like(input_array.__array__())
        s0 = self.sl[slice(0, -1)]
        s1 = self.sl[slice(1, None)]
        output_array[s0] = input_array[s0]
        output_array[s1] -= input_array[s0]
        return output_array

    def slice(self):
        return slice(0, self.N-1)

    def sympy_basis(self, i=0):
        x = sp.symbols('x')
        return (sp.laguerre(i, x)-sp.laguerre(i+1, x))*sp.exp(-x/2)

    def evaluate_basis(self, x, i=0, output_array=None):
        x = np.atleast_1d(x)
        if output_array is None:
            output_array = np.zeros(x.shape)
        output_array[:] = eval_laguerre(i, x) - eval_laguerre(i+1, x)
        output_array *= np.exp(-x/2)
        return output_array

    def eval(self, x, u, output_array=None):
        x = np.atleast_1d(x)
        if output_array is None:
            output_array = np.zeros(x.shape)
        w_hat = work[(u, 0, True)]
        w_hat[1:] = u[:-1]
        output_array[:] = lag.lagval(x, u) - lag.lagval(x, w_hat)
        output_array *= np.exp(-x/2)
        return output_array

    def plan(self, shape, axis, dtype, options):
        if isinstance(axis, tuple):
            assert len(axis) == 1
            axis = axis[0]

        if isinstance(self.forward, Transform):
            if self.forward.input_array.shape == shape and self.axis == axis:
                # Already planned
                return

        self.LT.plan(shape, axis, dtype, options)
        U, V = self.LT.forward.input_array, self.LT.forward.output_array
        self.axis = axis
        self.forward = Transform(self.forward, None, U, V, V)
        self.backward = Transform(self.backward, None, V, V, U)
        self.scalar_product = Transform(self.scalar_product, None, U, V, V)
        self.si = islicedict(axis=self.axis, dimensions=self.dimensions)
        self.sl = slicedict(axis=self.axis, dimensions=self.dimensions)

    def get_orthogonal(self):
        return Basis(self.N, quad=self.quad)
