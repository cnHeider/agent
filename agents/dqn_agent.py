#!/usr/bin/env python3
# coding=utf-8
__author__ = 'cnheider'
import time
from itertools import count

import numpy as np
import torch
import torch.nn.functional as F
from torch.autograd import Variable
from tqdm import tqdm

import utilities as U
from agents.value_agent import ValueAgent
from utilities.visualisation.term_plot import term_plot


class DQNAgent(ValueAgent):
  """

  """

  def __defaults__(self):
    self._memory = U.ReplayBuffer(1000)
    # self._memory = U.PrioritisedReplayMemory(config.REPLAY_MEMORY_SIZE)  # Cuda trouble

    self._use_cuda_if_available = False

    self._evaluation_function = F.smooth_l1_loss

    self._value_arch = U.MLP
    self._value_arch_parameters = {
  'input_size':  None,  # Obtain from environment
  'hidden_size': [64, 32, 16],
  'output_size': None,  # Obtain from environment
  'activation':  F.relu,
  'use_bias':    True
  }

    self._batch_size = 32

    self._discount_factor = 0.99
    self._learning_frequency = 1
    self._initial_observation_period = 0
    self._sync_target_model_frequency = 1000

    self._state_tensor_type = torch.FloatTensor
    self._value_type = torch.FloatTensor

    self._use_double_dqn = True
    self._clamp_gradient = False
    self._signal_clipping = True

    self._eps_start = 1.0
    self._eps_end = 0.01
    self._eps_decay = 500

    self._early_stopping_condition = None
    self._target_value_model = None

    self._optimiser_type = torch.optim.RMSprop
    self._optimiser = None
    self._optimiser_alpha = 0.9
    self._optimiser_learning_rate = 0.0025
    self._optimiser_epsilon = 1e-02
    self._optimiser_momentum = 0.0

  def build_model(self, env):
    self.infer_input_output_sizes(env)

    self._value_arch_parameters['input_size'] = self._input_size
    self._value_arch_parameters['output_size'] = self._output_size

    self._value_model, self._target_value_model, self._optimiser = self.__build_models__()

  def __build_models__(self):

    value_model = self._value_arch(**self._value_arch_parameters)

    target_value_model = self._value_arch(**self._value_arch_parameters)
    target_value_model.load_state_dict(value_model.state_dict())

    if self._use_cuda_if_available:
      value_model = value_model.cuda()
      target_value_model = target_value_model.cuda()

    optimiser = self._optimiser_type(value_model.parameters(),
                                     lr=self._optimiser_learning_rate,
                                     eps=self._optimiser_epsilon,
                                     alpha=self._optimiser_alpha,
                                     momentum=self._optimiser_momentum)

    return value_model, target_value_model, optimiser

  def optimise_wrt(self, error, **kwargs):
    """

    :param error:
    :type error:
    :return:
    """
    self._optimiser.zero_grad()
    error.backward()
    if self._clamp_gradient:
      for params in self._value_model.parameters():
        params.grad.data.clamp_(-1, 1)
    self._optimiser.step()

  def evaluate(self, batch, **kwargs):
    """

    :param batch:
    :type batch:
    :return:
    :rtype:
    """

    # Torchify batch
    states = U.to_var(batch.state, use_cuda=self._use_cuda_if_available).view(-1, self._input_size[0])
    action_indices = U.to_var(batch.action, 'long', use_cuda=self._use_cuda_if_available).view(-1, 1)
    true_signals = U.to_var(batch.signal, use_cuda=self._use_cuda_if_available)
    non_terminal_mask = U.to_tensor(batch.non_terminal, 'byte', use_cuda=self._use_cuda_if_available)
    non_terminal_successors = U.to_tensor([states
                                           for (states, non_terminal_mask)
                                           in zip(batch.successor_state, batch.non_terminal)
                                           if non_terminal_mask], 'float',
                                          use_cuda=self._use_cuda_if_available)
    if not len(non_terminal_successors) > 0:
      return 0  # Nothing to be learned, all states are terminal
    non_terminal_successors_var = U.to_var(non_terminal_successors, use_cuda=self._use_cuda_if_available,
                                           volatile=True)

    # Calculate Q of successors
    Q_successors = self._value_model(non_terminal_successors_var)
    Q_successors_max_action_indices = Q_successors.max(1)[1].view(-1, 1)
    if self._use_double_dqn:
      Q_successors = self._target_value_model(non_terminal_successors_var)
    Q_max_successor = Variable(torch.zeros(self._batch_size).type(self._value_type))
    Q_max_successor[non_terminal_mask] = Q_successors.gather(1, Q_successors_max_action_indices)

    # Integrate with the true signal
    Q_expected = true_signals + (self._discount_factor * Q_max_successor)

    # Calculate Q of state
    Q_state = self._value_model(states).gather(1, action_indices)

    return self._evaluation_function(Q_state, Q_expected)

  def update_models(self):
    # indices, transitions = self._memory.sample_transitions(self.C.BATCH_SIZE)
    transitions = self._memory.sample_transitions(self._batch_size)

    td_error = self.evaluate(transitions)
    self.optimise_wrt(td_error)

    error = td_error.data[0]
    # self._memory.batch_update(indices, errors.tolist())  # Cuda trouble

    return error

  def rollout(self, initial_state, environment, render=False):
    self._rollout_i += 1

    state = initial_state
    episode_signal = 0
    episode_length = 0
    episode_td_error = 0

    T = count(1)
    T = tqdm(T, f'Rollout #{self._rollout_i}', leave=False)

    for t in T:
      self._step_i += 1

      action = self.sample_action(state)
      next_state, signal, terminated, info = environment.step(action)

      if render:
        environment.render()

      if self._signal_clipping:
        signal = np.clip(signal, -1.0, 1.0)

      successor_state = None
      if not terminated:  # If environment terminated then there is no successor state
        successor_state = next_state

      self._memory.add_transition(state, action, signal, successor_state, not terminated)
      state = next_state

      td_l = 0

      if len(self._memory) >= self._batch_size and \
          self._step_i > self._initial_observation_period and \
          self._step_i % self._learning_frequency == 0:

        error = self.update_models()

        T.set_description(f'TD error: {error}')

      if self._use_double_dqn and self._step_i % self._sync_target_model_frequency == 0:
        self._target_value_model.load_state_dict(self._value_model.state_dict())
        T.write('Target Model Synced')

      episode_signal += signal
      episode_td_error += td_l

      if terminated:
        episode_length = t
        break

    return episode_signal, episode_length, episode_td_error

  def infer(self, state, *args, **kwargs):
    model_input = Variable(state, volatile=True).type(self._state_tensor_type)
    return self._value_model(model_input)

  def sample_action(self, state,**kwargs):
    """

    :param state:
    :return:
    """
    if self.epsilon_random(self._step_i) and self._step_i > self._initial_observation_period:
      return self.sample_model(state)
    return self.sample_random_process()

  def sample_model(self, state,**kwargs):
    model_input = U.to_var([state], volatile=True, use_cuda=self._use_cuda_if_available)
    action_value_estimates = self._value_model(model_input)
    max_value_action_idx = action_value_estimates.max(1)[1].data[0]
    # max_value_action_idx = np.argmax(action_value_estimates.data.cpu().numpy()[0])
    return max_value_action_idx

  def step(self, state, env):
    self._step_i += 1
    action = self.sample_action(state)
    return env.step(action)

  def train_episodic(self,
                     _environment,
                     rollouts=1000,
                     render=False,
                     render_frequency=400,
                     stat_frequency=400):
    """

    :param _environment:
    :type _environment:
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
    """
    running_signal = 0
    dur = 0
    td_error = 0
    running_signals = []
    durations = []
    td_errors = []

    E = range(1, rollouts)
    E = tqdm(E, leave=True)

    training_start_timestamp = time.time()

    for episode_i in E:
      initial_state = _environment.reset()

      if episode_i % stat_frequency == 0:
        t_episode = [i for i in range(1, episode_i + 1)]
        term_plot(t_episode,
                  running_signals,
                  'Running Signal',
                  printer=E.write,
                  percent_size=(1, .24))
        term_plot(t_episode,
                  durations,
                  'Duration',
                  printer=E.write, percent_size=(1,
                                                 .24))
        term_plot(t_episode,
                  td_errors,
                  'TD Error',
                  printer=E.write,
                  percent_size=(1, .24))
        E.set_description(f'Episode: {episode_i}, '
                          f'Running Signal: {running_signal}, '
                          f'Duration: {dur}, '
                          f'TD Error: {td_error}')

      if render and episode_i % render_frequency == 0:
        signal, dur, *stats = self.rollout(initial_state, _environment, render=render)
      else:
        signal, dur, *stats = self.rollout(initial_state, _environment)

      running_signal = running_signal * 0.99 + signal * 0.01
      running_signals.append(running_signal)
      durations.append(dur)
      td_error = stats[0]
      td_errors.append(td_error)

      if self._end_training:
        break

    time_elapsed = time.time() - training_start_timestamp
    end_message = f'Training done, time elapsed: {time_elapsed // 60:.0f}m {time_elapsed %60:.0f}s'
    print('\n{} {} {}\n'.format('-' * 9, end_message, '-' * 9))

    return self._value_model, []


def test_dqn_agent(config):
  import gym

  environment = gym.make(config.ENVIRONMENT_NAME)
  environment.seed(config.SEED)

  agent = DQNAgent(C)
  agent.build_model(environment)

  listener = U.add_early_stopping_key_combination(agent.stop_training)

  _trained_model = None
  listener.start()
  try:

    _trained_model, training_statistics, *_ = agent.train_episodic(environment, config.EPISODES,
                                                                   render=config.RENDER_ENVIRONMENT)
  finally:
    listener.stop()

  U.save_model(_trained_model, C)

  environment.close()


#
# def main2():
#   args = parser.parse_args()
#   torch.manual_seed(args.seed)
#
#   if not os.path.exists(args.dump_location):
#     os.makedirs(args.dump_location)
#
#   logging.basicConfig(
#       filename=args.dump_location +
#                'train.log',
#       level=logging.INFO)
#
#   assert args.evaluate == 0 or args.num_processes == 0, \
#     "Can't train while evaluating, either n=0 or e=0"
#
#   class Net(torch.nn.Module):
#     def __init__(self, args):
#       super(Net, self).__init__()
#       self.conv1 = torch.nn.Conv2d(1, 10, kernel_size=5)
#       self.conv2 = torch.nn.Conv2d(10, 20, kernel_size=5)
#       self.conv2_drop = torch.nn.Dropout2d()
#       self.fc1 = torch.nn.Linear(320, 50)
#       self.fc2 = torch.nn.Linear(50, 10)
#
#     def forward(self, x):
#       x = F.relu(F.max_pool2d(self.conv1(x), 2))
#       x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
#       x = x.view(-1, 320)
#       x = F.relu(self.fc1(x))
#       x = F.dropout(x, training=self.training)
#       x = self.fc2(x)
#       return F.log_softmax(x, dim=1)
#
#   def train(rank, args, model):
#     torch.manual_seed(args.seed + rank)
#
#     pass
#
#   def test(rank, args, model):
#     torch.manual_seed(args.seed + rank)
#
#     pass
#
#   shared_model = Net(args)
#
#   if args.load != "0":
#     shared_model.load_state_dict(torch.load(args.load))
#   shared_model.share_memory()
#
#   signal.signal(signal.SIGINT, signal.signal(signal.SIGINT, signal.SIG_IGN))
#   processes = []
#
#   p = TMP.Process(target=test, args=(args.num_processes, args, shared_model))
#   p.start()
#   processes.append(p)
#
#   for rank in range(0, args.num_processes):
#     p = TMP.Process(target=train, args=(rank, args, shared_model))
#     p.start()
#     processes.append(p)
#
#   try:
#     for p in processes:
#       p.join()
#   except KeyboardInterrupt:
#     print("Stopping training. " +
#           "Best model stored at {}model_best".format(args.dump_location))
#     for p in processes:
#       p.terminate()

if __name__ == '__main__':
  import argparse
  import configs.dqn_config as C

  parser = argparse.ArgumentParser(description='DQN Agent')
  parser.add_argument('--ENVIRONMENT_NAME', '-E', type=str, default=C.ENVIRONMENT_NAME,
                      metavar='ENVIRONMENT_NAME',
                      help='Name of the environment to run')
  parser.add_argument('--PRETRAINED_PATH', '-T', metavar='PATH', type=str, default='',
                      help='Path of pre-trained model')
  parser.add_argument('--RENDER_ENVIRONMENT', '-R', action='store_true',
                      default=C.RENDER_ENVIRONMENT,
                      help='Render the environment')
  parser.add_argument('--NUM_WORKERS', '-N', type=int, default=4, metavar='NUM_WORKERS',
                      help='Number of threads for agent (default: 4)')
  parser.add_argument('--SEED', '-S', type=int, default=1, metavar='SEED',
                      help='Random seed (default: 1)')
  parser.add_argument('--skip_confirmation', '-skip', action='store_true',
                      default=False,
                      help='Skip confirmation of config to be used')
  args = parser.parse_args()

  for k, arg in args.__dict__.items():
    setattr(C, k, arg)

  print(f'Using config: {C}')
  if not args.skip_confirmation:
    for k, arg in U.get_upper_vars_of(C).items():
      print(f'{k} = {arg}')
    input('\nPress any key to begin... ')

  try:
    test_dqn_agent(C)
  except KeyboardInterrupt:
    print('Stopping')
