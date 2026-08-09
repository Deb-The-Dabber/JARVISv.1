"""Tiny nn module: Linear layer + MLP for the intent router."""

import numpy as np

from .functional import dropout, relu
from .tensor import Tensor


class Linear:
    def __init__(self, in_features: int, out_features: int, seed: int | None = None):
        rng = np.random.default_rng(seed)
        # Kaiming-style init scaled for ReLU
        self.weight = Tensor(
            rng.normal(0.0, np.sqrt(2.0 / in_features), (in_features, out_features)),
            requires_grad=True,
        )
        self.bias = Tensor(np.zeros((1, out_features)), requires_grad=True)

    def __call__(self, x: Tensor) -> Tensor:
        return x @ self.weight + self.bias

    def parameters(self):
        return [self.weight, self.bias]

    def to_numpy(self):
        return {"w": self.weight.data.copy(), "b": self.bias.data.copy()}

    def load_numpy(self, w, b):
        self.weight.data = np.asarray(w, dtype=np.float64)
        self.bias.data = np.asarray(b, dtype=np.float64)


class MLP:
    """Multi-layer perceptron: input -> Linear->ReLU(+dropout)*n -> Linear->out."""

    def __init__(
        self,
        in_features: int,
        hidden_sizes,
        out_features: int,
        dropout_p: float = 0.0,
        seed: int | None = None,
    ):
        self.dropout_p = dropout_p
        sizes = [in_features] + list(hidden_sizes)
        self.layers = [Linear(sizes[i], sizes[i + 1], seed=seed) for i in range(len(sizes) - 1)]
        self.head = Linear(sizes[-1], out_features, seed=seed)

    def forward(self, x, training: bool = False) -> Tensor:
        if not isinstance(x, Tensor):
            x = Tensor(x)
        h = x
        for layer in self.layers:
            h = relu(layer(h))
            if training and self.dropout_p > 0.0:
                h = dropout(h, self.dropout_p, training=True)
        return self.head(h)

    def __call__(self, x: Tensor, training: bool = False) -> Tensor:
        return self.forward(x, training=training)

    def parameters(self):
        params = []
        for layer in self.layers:
            params.extend(layer.parameters())
        params.extend(self.head.parameters())
        return params

    def to_numpy(self):
        return {"layers": [layer.to_numpy() for layer in self.layers], "head": self.head.to_numpy()}

    def load_numpy(self, state):
        for layer, d in zip(self.layers, state["layers"]):
            layer.load_numpy(d["w"], d["b"])
        self.head.load_numpy(state["head"]["w"], state["head"]["b"])
