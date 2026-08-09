"""Adam optimizer for the tiny tensor library."""

import numpy as np


class Adam:
    def __init__(self, parameters, lr: float = 1e-3, betas=(0.9, 0.999), eps: float = 1e-8):
        self.params = [p for p in parameters if p.requires_grad]
        self.lr = lr
        self.beta1, self.beta2 = betas
        self.eps = eps
        self.t = 0
        self.m = {}
        self.v = {}
        for p in self.params:
            self.m[id(p)] = np.zeros_like(p.data)
            self.v[id(p)] = np.zeros_like(p.data)

    def step(self):
        self.t += 1
        for p in self.params:
            if p.grad is None:
                continue
            pid = id(p)
            self.m[pid] = self.beta1 * self.m[pid] + (1 - self.beta1) * p.grad
            self.v[pid] = self.beta2 * self.v[pid] + (1 - self.beta2) * (p.grad**2)
            m_hat = self.m[pid] / (1 - self.beta1**self.t)
            v_hat = self.v[pid] / (1 - self.beta2**self.t)
            p.data -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)

    def zero_grad(self):
        for p in self.params:
            p.zero_grad()
