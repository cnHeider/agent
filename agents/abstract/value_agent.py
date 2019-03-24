#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import copy
import time
from abc import abstractmethod
from typing import Any

import draugr
from tqdm import tqdm
from warg import NamedOrderedDictionary

__author__ = 'cnheider'

import math
import random

import numpy as np
import torch
import tensorboardX as tx
import utilities as U
from agents.abstract.torch_agent import TorchAgent


class ValueAgent(TorchAgent):
  '''
All value iteration agents should inherit from this class
'''

  # region Public

  def __init__(self, config=None, *args, **kwargs):
    self._exploration_epsilon_start = 0.99
    self._exploration_epsilon_end = 0.04
    self._exploration_epsilon_decay = 10000
    self._initial_observation_period = 0

    self._value_arch_parameters = {}
    self._value_arch = None
    self._value_model = None

    self._naive_max_policy = False

    super().__init__(config, *args, **kwargs)

  def sample_action(self, state, **kwargs):
    self._step_i += 1
    if (self.epsilon_random(self._step_i)
        and self._step_i > self._initial_observation_period
    ):
      if self._verbose:
        print('Sampling from model')
      return self._sample_model(state)
    if self._verbose:
      print('Sampling from random process')
    return self.sample_random_process()

  def sample_random_process(self):
    sample = np.random.choice(self._action_size[0])
    return sample

  def build(self, env, **kwargs):
    super().build(env, **kwargs)
    with tx.SummaryWriter(str(self._base_log_dir))as writer:
      dummy_in = torch.rand(
          1, *self._observation_space.shape)

      model = copy.deepcopy(self._value_model)
      model.to('cpu')
      writer.add_graph(model, dummy_in, True)

  def epsilon_random(self, steps_taken):
    '''
:param steps_taken:
:return:
'''
    assert 0 <= self._exploration_epsilon_end <= self._exploration_epsilon_start

    if steps_taken == 0:
      return False

    sample = random.random()

    a = self._exploration_epsilon_start - self._exploration_epsilon_end

    b = math.exp(-1. * steps_taken / (self._exploration_epsilon_decay + self._divide_by_zero_safety))
    self._current_eps_threshold = self._exploration_epsilon_end + a * b

    if self._verbose:
      print(f'{sample} > {self._current_eps_threshold} = {sample > self._current_eps_threshold},'
            f' where a ={a} and b={b}')
    return sample > self._current_eps_threshold

  def save(self, C):
    U.save_model(self._value_model, C)

  def load(self, model_path, evaluation):
    print('Loading latest model: ' + model_path)
    self._value_model = self._value_arch(**self._value_arch_parameters)
    self._value_model.load_state_dict(torch.load(model_path))
    if evaluation:
      self._value_model = self._value_model.eval()
      self._value_model.train(False)
    if self._use_cuda:
      self._value_model = self._value_model.cuda()
    else:
      self._value_model = self._value_model.cpu()

  def train_episodically(self,
                         _environment,
                         *,
                         rollouts=1000,
                         render=False,
                         render_frequency=100,
                         stat_frequency=100,
                         **kwargs
                         ) -> NamedOrderedDictionary:
    '''
      :param _environment:
      :type _environment:,0
      :param rollouts:
      :type rollouts:
      :param render:
      :type render:
      :param render_frequency:
      :type render_frequency:
      :param stat_frequency:
      :type stat_frequency:
      :return:
      :rtype:
    '''

    E = range(1, rollouts)
    E = tqdm(E, leave=False)

    with tx.writer.SummaryWriter(str(self._base_log_dir / ('session' + str(int(time.time())))))as stats:
      for episode_i in E:
        initial_state = _environment.reset()

        if render and episode_i % render_frequency == 0:
          signal, dur, td_error, *extras = self.rollout(initial_state,
                                                        _environment,
                                                        render=render
                                                        )
        else:
          signal, dur, td_error, *extras = self.rollout(initial_state, _environment)

        stats.add_scalar('duration', dur, episode_i)
        stats.add_scalar('signal', signal, episode_i)
        stats.add_scalar('td_error', td_error, episode_i)
        stats.add_scalar('_current_eps_threshold', self._current_eps_threshold, episode_i)

        if self._end_training:
          break

    return NamedOrderedDictionary(model=self._value_model)

  def train_episodically_old(self,
                             _environment,
                             *,
                             rollouts=1000,
                             render=False,
                             render_frequency=100,
                             stat_frequency=100,
                             **kwargs
                             ) -> NamedOrderedDictionary:
    '''
      :param _environment:
      :type _environment:,0
      :param rollouts:
      :type rollouts:
      :param render:
      :type render:
      :param render_frequency:
      :type render_frequency:
      :param stat_frequency:
      :type stat_frequency:
      :return:
      :rtype:
    '''

    stats = draugr.StatisticCollection(stats=('signal',
                                              'duration',
                                              'td_error',
                                              'epsilon'))

    E = range(1, rollouts)
    E = tqdm(E, leave=False)

    for episode_i in E:
      initial_state = _environment.reset()

      if episode_i % stat_frequency == 0:
        draugr.styled_terminal_plot_stats_shared_x(stats, printer=E.write)
        E.set_description(f'Epi: {episode_i}, '
                          f'Sig: {stats.signal.running_value[-1]:.3f}, '
                          f'Dur: {stats.duration.running_value[-1]:.1f}, '
                          f'TD Err: {stats.td_error.running_value[-1]:.3f}, '
                          f'Eps: {stats.epsilon.running_value[-1]:.3f}'
                          )

      if render and episode_i % render_frequency == 0:
        signal, dur, td_error, *extras = self.rollout(initial_state,
                                                      _environment,
                                                      render=render
                                                      )
      else:
        signal, dur, td_error, *extras = self.rollout(initial_state, _environment)

      stats.append(signal, dur, td_error, self._current_eps_threshold)

      if self._end_training:
        break

    return NamedOrderedDictionary(model=self._value_model, stats=stats)

  # endregion

  # region Abstract

  @abstractmethod
  def _sample_model(self, state, *args, **kwargs) -> Any:
    raise NotImplementedError

  # endregion

  def _maybe_infer_input_output_sizes(self, env, **kwargs):
    super()._maybe_infer_input_output_sizes(env)

    self._value_arch_parameters['input_size'] = self._observation_size
    self._value_arch_parameters['output_size'] = self._action_size

  def _maybe_infer_hidden_layers(self, **kwargs):
    super()._maybe_infer_hidden_layers()

    self._value_arch_parameters['hidden_layers'] = self._hidden_layers

  # region Protected

  def _train(self, *args, **kwargs) -> NamedOrderedDictionary:
    return self.train_episodically(*args, **kwargs)

  # endregion
