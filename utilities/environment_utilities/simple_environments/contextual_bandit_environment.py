# !/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = 'cnheider'

import numpy as np


class ContextualBandit(object):

  def __init__(self):
    self.state = 0
    # List out our bandits. Currently arms 4, 2, and 1 (respectively) are the most optimal.
    self.bandits = np.array([[0.2, 0, -0.0, -5], [0.1, -5, 1, 0.25], [-5, 5, 5, 5]])
    self.num_bandits = self.bandits.shape[0]
    self.num_actions = self.bandits.shape[1]

  def get_bandit(self):
    self.state = np.random.randint(
        0, len(self.bandits)
        )  # Returns a random state for each episode.
    return self.state

  def pull_arm(self, action):
    # Get a random number.
    bandit = self.bandits[self.state, action]
    result = np.random.randn(1)
    if result > bandit:
      # return a positive signal.
      return 1
    else:
      # return a negative signal.
      return -1

# cBandit = contextual_bandit()
# while i < total_episodes:
#   s = cBandit.getBandit()  # Get a state from the environment.
#
#   # Choose either a random action or one from our network.
#   if np.random.rand(1) < e:
#     action = np.random.randint(cBandit.num_actions)
#   else:
#     action = sess.run(myAgent.chosen_action, feed_dict={myAgent.state_in: [s]})
#
#   signal = cBandit.pullArm(action)  # Get our signal for taking an action given a bandit.
