#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
from abc import abstractmethod
from typing import Any

from torch.autograd import Variable
from warg import NamedOrderedDictionary

__author__ = 'cnheider'

import torch

import utilities as U
from agents.abstract.torch_agent import TorchAgent
import tensorboardX as tx


class PolicyAgent(TorchAgent):
  '''
All policy iteration agents should inherit from this class
'''

  # region Private

  def __init__(self, *args, **kwargs):
    self._policy_arch = None
    self._policy_arch_params = None
    self._policy_model = None

    self._deterministic = True

    super().__init__(*args, **kwargs)

  def build(self, env, **kwargs):
    super().build(env, **kwargs)
    with tx.SummaryWriter(str(self._base_log_dir))as writer:
      dummy_in = torch.rand(
          1, *self._observation_space.shape)

      model = copy.deepcopy(self._policy_model)
      model.to('cpu')
      writer.add_graph(model,dummy_in,verbose=self._verbose)

  # endregion

  # region Public

  def save(self, C):
    U.save_model(self._policy_model, C)

  def load(self, model_file, evaluation=False):
    print(f'Loading model: {model_file}')
    self._policy_model = self._policy_arch(**self._policy_arch_params)
    self._policy_model.load_state_dict(torch.load(model_file))
    if evaluation:
      self._policy_model = self._policy_model.eval()
      self._policy_model.train(False)
    if self._use_cuda:
      self._policy_model = self._policy_model.cuda()

  # endregion

  # region Protected

  def _maybe_infer_input_output_sizes(self, env, **kwargs):
    super()._maybe_infer_input_output_sizes(env)

    self._policy_arch_params['input_size'] = self._input_size
    self._policy_arch_params['output_size'] = self._output_size

  def _maybe_infer_hidden_layers(self, **kwargs):
    super()._maybe_infer_hidden_layers()

    self._policy_arch_params['hidden_layers'] = self._hidden_layers

  def _train(self, *args, **kwargs) -> NamedOrderedDictionary:
    return self.train_episodically(*args, **kwargs)

  # endregion

  # region Abstract

  @abstractmethod
  def _sample_model(self, state, *args, **kwargs) -> Any:
    raise NotImplementedError

  @abstractmethod
  def train_episodically(self, rollout, *args, **kwargs) -> NamedOrderedDictionary:
    raise NotImplementedError

  # endregion
