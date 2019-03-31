#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from abc import ABC

import torch
from tqdm import tqdm

from agents.abstract.agent import Agent

tqdm.monitor_interval = 0

__author__ = 'cnheider'


class TorchAgent(Agent, ABC):
  '''
All agent should inherit from this class
'''

  # region Private

  def __init__(self,
               *args,
               use_cuda=False,
               cuda_device_id=0,
               **kwargs):
    self._hidden_layers = None
    self._use_cuda = use_cuda
    self._device = torch.device(f'cuda:{cuda_device_id}'
                                if torch.cuda.is_available() and self._use_cuda else 'cpu')

    super().__init__(*args, **kwargs)

  @property
  def device(self):
    return self._device
