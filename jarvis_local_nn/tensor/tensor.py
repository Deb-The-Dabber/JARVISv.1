"""Minimal NumPy-backed autograd tensor library for JARVIS's local intent router.

Micrograd-style reverse-mode autograd over 2D arrays (batch x features).
Supports only the ops the intent router needs: add, matmul, relu, dropout,
and cross-entropy — kept deliberately tiny and dependency-free (NumPy only).
"""

import numpy as np


def _as_ndarray(data):
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 0:
        arr = arr.reshape(1)
    return arr


class Tensor:
    __slots__ = ("data", "grad", "requires_grad", "_backward", "_prev", "_op")

    def __init__(self, data, requires_grad=False, _children=(), _op=""):
        self.data = _as_ndarray(data)
        self.grad = None
        self.requires_grad = bool(requires_grad)
        self._backward = lambda: None
        self._prev = set(_children)
        self._op = _op

    @property
    def shape(self):
        return self.data.shape

    @property
    def ndim(self):
        return self.data.ndim

    def __repr__(self):
        return f"Tensor(shape={self.data.shape}, requires_grad={self.requires_grad})"

    def _init_grad(self):
        if self.requires_grad and self.grad is None:
            self.grad = np.zeros_like(self.data)

    def zero_grad(self):
        self.grad = None

    def backward(self):
        if not self.requires_grad:
            return
        self.grad = np.ones_like(self.data)
        topo = []
        visited = set()

        def _build(v):
            if id(v) not in visited:
                visited.add(id(v))
                for child in v._prev:
                    _build(child)
                topo.append(v)

        _build(self)
        for v in reversed(topo):
            v._backward()

    # ---- binary ops ----
    def __add__(self, other):
        other = other if isinstance(other, Tensor) else Tensor(other)
        out = Tensor(
            self.data + other.data,
            requires_grad=self.requires_grad or other.requires_grad,
            _children=(self, other),
            _op="+",
        )

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += _reduce_broadcast(out.grad, self.data.shape)
            if other.requires_grad:
                other._init_grad()
                other.grad += _reduce_broadcast(out.grad, other.data.shape)

        out._backward = _backward
        return out

    def __radd__(self, other):
        return self + other

    def __mul__(self, other):
        other = other if isinstance(other, Tensor) else Tensor(other)
        out = Tensor(
            self.data * other.data,
            requires_grad=self.requires_grad or other.requires_grad,
            _children=(self, other),
            _op="*",
        )

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += _reduce_broadcast(out.grad * other.data, self.data.shape)
            if other.requires_grad:
                other._init_grad()
                other.grad += _reduce_broadcast(out.grad * self.data, other.data.shape)

        out._backward = _backward
        return out

    def __rmul__(self, other):
        return self * other

    def __matmul__(self, other):
        other = other if isinstance(other, Tensor) else Tensor(other)
        out = Tensor(
            self.data @ other.data,
            requires_grad=self.requires_grad or other.requires_grad,
            _children=(self, other),
            _op="@",
        )

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += out.grad @ other.data.T
            if other.requires_grad:
                other._init_grad()
                other.grad += self.data.T @ out.grad

        out._backward = _backward
        return out

    def __sub__(self, other):
        return self + (-other)

    def __neg__(self):
        return self * -1.0

    def __truediv__(self, other):
        other = other if isinstance(other, Tensor) else Tensor(other)
        return self * other**-1.0

    def __pow__(self, exponent):
        if not isinstance(exponent, (int, float)):
            raise NotImplementedError("power with tensor exponent not supported")
        out = Tensor(self.data**exponent, requires_grad=self.requires_grad, _children=(self,), _op=f"**{exponent}")

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += exponent * (self.data ** (exponent - 1)) * out.grad

        out._backward = _backward
        return out

    # ---- reductions ----
    def sum(self):
        out = Tensor(self.data.sum(), requires_grad=self.requires_grad, _children=(self,), _op="sum")

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += np.full_like(self.data, out.grad)

        out._backward = _backward
        return out

    def mean(self):
        n = self.data.size
        out = Tensor(self.data.mean(), requires_grad=self.requires_grad, _children=(self,), _op="mean")

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += np.full_like(self.data, out.grad / n)

        out._backward = _backward
        return out

    def reshape(self, *shape):
        out = Tensor(self.data.reshape(*shape), requires_grad=self.requires_grad, _children=(self,), _op="reshape")

        def _backward():
            if self.requires_grad:
                self._init_grad()
                self.grad += out.grad.reshape(self.data.shape)

        out._backward = _backward
        return out


def _reduce_broadcast(grad, target_shape):
    """Reduce a gradient array that was broadcast to (grad.shape) back to target_shape."""
    g = grad
    while g.ndim > len(target_shape):
        g = g.sum(axis=0)
    for axis, dim in enumerate(target_shape):
        if dim == 1 and g.shape[axis] != 1:
            g = g.sum(axis=axis, keepdims=True)
    return g
