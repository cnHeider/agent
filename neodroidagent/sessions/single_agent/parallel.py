#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Type, Union

from neodroid.environments.unity.vector_unity_environment import VectorUnityEnvironment
from neodroid.wrappers import NeodroidGymWrapper
from neodroidagent.sessions import EnvironmentSession, Environment, Procedure, Episodic
from trolls.multiple_environments_wrapper import SubProcessEnvironments, make_gym_env
from warg.kw_passing import super_init_pass_on_kws

__author__ = 'Christian Heider Nielsen'
__doc__ = ''


@super_init_pass_on_kws
class ParallelSession(EnvironmentSession):

  def __init__(self,
               environment: Union[str, Environment],
               procedure: Union[Type[Procedure], Procedure] = Episodic,
               *,
               default_num_train_envs=6,
               auto_reset_on_terminal_state=False,
               connect_to_running=False,
               **kwargs):
    if isinstance(environment, str):
      if '-v' in environment and not connect_to_running:
        assert default_num_train_envs > 0
        environment = [make_gym_env(environment) for _ in
                       range(default_num_train_envs)]
        environment = NeodroidGymWrapper(
          SubProcessEnvironments(environment,
                                 auto_reset_on_terminal=auto_reset_on_terminal_state
                                 ))
      else:
        environment = VectorUnityEnvironment(name=environment,
                                             connect_to_running=connect_to_running)

    super().__init__(environment, procedure, **kwargs)


if __name__ == '__main__':
  import neodroidagent.configs.agent_test_configs.pg_test_config as C
  from neodroidagent.agents.torch_agents.model_free.on_policy import PGAgent

  env = VectorUnityEnvironment(name=C.ENVIRONMENT_NAME,
                               connect_to_running=C.CONNECT_TO_RUNNING)
  env.seed(C.SEED)

  ParallelSession('', Episodic)(PGAgent,
                                config=C,
                                environment=env)
