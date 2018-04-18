#!/usr/bin/env python3
# coding=utf-8
__author__ = 'cnheider'

import torch

import utilities as U
from agents.agent import Agent


class PolicyAgent(Agent):
  """
  All policy iteration agents should inherit from this class
  """

  def __init__(self, *args, **kwargs):
    self._policy_arch = None
    self._policy_arch_params = None
    self._policy = None
    super().__init__(*args, **kwargs)

  def infer_input_output_sizes(self, env, **kwargs):
    super().infer_input_output_sizes(env)

    self._policy_arch_params['input_size'] = self._input_size
    self._policy_arch_params['output_size'] = self._output_size

  def save_model(self, C):
    U.save_model(self._policy, C)

  def load_model(self, model_path, evaluation=False):
    print('loading latest model: ' + model_path)
    self._policy = self._policy_arch(**self._policy_arch_params)
    self._policy.load_state_dict(torch.load(model_path))
    if evaluation:
      self._policy = self._policy.eval()
      self._policy.train(False)
    if self._use_cuda_if_available:
      self._policy = self._policy.cuda()
