"""Functional ops for the tiny tensor library: relu, dropout, softmax, cross-entropy."""

import numpy as np

from .tensor import Tensor


def relu(x: Tensor) -> Tensor:
    out = Tensor(np.maximum(x.data, 0.0), requires_grad=x.requires_grad, _children=(x,), _op="relu")

    def _backward():
        if x.requires_grad:
            x._init_grad()
            x.grad += (x.data > 0.0) * out.grad

    out._backward = _backward
    return out


def dropout(x: Tensor, p: float = 0.0, training: bool = True) -> Tensor:
    """Inverted dropout (scale by 1/(1-p)). Returns x unchanged when not training or p==0."""
    if not training or p <= 0.0:
        return x
    keep = 1.0 - p
    mask = (np.random.rand(*x.data.shape) < keep) / keep
    out = Tensor(x.data * mask, requires_grad=x.requires_grad, _children=(x,), _op="dropout")

    def _backward():
        if x.requires_grad:
            x._init_grad()
            x.grad += mask * out.grad

    out._backward = _backward
    return out


def cross_entropy(logits: Tensor, targets) -> Tensor:
    """Mean cross-entropy between logits (N, C) and integer targets (N,)."""
    x = logits.data
    shifted = x - x.max(axis=1, keepdims=True)
    logsumexp = np.log(np.exp(shifted).sum(axis=1, keepdims=True))
    softmax = np.exp(shifted - logsumexp)
    n = x.shape[0]
    out = Tensor(
        (-shifted[range(n), np.asarray(targets)] + logsumexp[range(n), 0]).mean(),
        requires_grad=logits.requires_grad,
        _children=(logits,),
        _op="cross_entropy",
    )

    def _backward():
        if logits.requires_grad:
            logits._init_grad()
            one_hot = np.zeros_like(x)
            one_hot[range(n), np.asarray(targets)] = 1.0
            logits.grad += (softmax - one_hot) / n

    out._backward = _backward
    return out
