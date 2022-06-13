from operator import itemgetter

import torch
import gym
from operator import itemgetter
import numpy as np
from unstable_baselines.common import util
from unstable_baselines.common.agents import BaseAgent
from unstable_baselines.common.networks import MLPNetwork
from unstable_baselines.common.networks import PolicyNetworkFactory
from unstable_baselines.common.networks import get_optimizer


class VPGAgent(torch.nn.Module, BaseAgent):
    """ Vanilla Policy Gradient Agent
    https://proceedings.neurips.cc/paper/2001/file/4b86abe48d358ecf194c56c69108433e-Paper.pdf

    BaseAgent Args
    --------------
    observation_space: gym.Space

    action_sapce: gym.Space

    kwargs Args
    -----------
    gamma: float
        Discount factor.

    train_v_iters: int
        The number of times that the state-value network is updated in the agent.update 
        function, while the policy network is only updated once.

    action_bound_method: str, optional("clip", "tanh"),
        Method for mappolicyng the raw action generated by policy network to the environment 
        action space.
    """

    def __init__(self,
                 observation_space: gym.Space,
                 action_space: gym.Space,
                 train_v_iters: int,
                 gamma: float,
                 action_bound_method: str,
                 **kwargs):
        
        super(VPGAgent, self).__init__()
        # save parameters
        self.args = kwargs
        
        self.observation_space = observation_space
        self.action_space = action_space
        obs_dim = observation_space.shape[0]
        action_dim = action_space.shape[0]

        # initialize networks and optimizer
        self.v_network = MLPNetwork(obs_dim, 1, **kwargs['v_network']).to(util.device)
        self.v_optimizer = get_optimizer(kwargs['v_network']['optimizer_class'], self.v_network, kwargs['v_network']['learning_rate'])
        self.policy_network = PolicyNetworkFactory.get(obs_dim, action_space, **kwargs['policy_network']).to(util.device)
        self.policy_optimizer = get_optimizer(kwargs['policy_network']['optimizer_class'], self.policy_network, kwargs['policy_network']['learning_rate'])

        # register networks
        self.networks = {
            'v_network': self.v_network,
            'policy_network': self.policy_network
        }

        # hyper-parameters
        self.gamma = gamma
        self.train_v_iters = train_v_iters
        self.action_bound_method = action_bound_method

    

    def estimate_value(self, obs):
        """ Estimate the obs value.
        """
        if len(obs.shape) == 1:
            obs = obs[None,]
    
        if not isinstance(obs, torch.Tensor):
            obs = torch.FloatTensor(obs).to(util.device)
        with torch.no_grad():
            value = self.v_network(obs)
        return value.detach().cpu().numpy()
    
    def update(self, data_batch: dict):
        """ Update the policy network and the value network.

        Args
        ----
        data_batch: dict
            obs, act, ret, adv, logp
        """
        obs = data_batch['obs']
        act = data_batch['action']
        ret = data_batch['ret']
        adv = data_batch['advantage']
        log_prob = data_batch['log_prob']
        
        # Train policy with a single step of gradient descent
        log_prob, entropy = \
            itemgetter("log_prob", "entropy")(self.policy_network.evaluate_actions(obs, act, action_type='scaled'))
        loss_policy = -(log_prob * adv).mean()
        self.policy_optimizer.zero_grad()
        loss_policy.backward()
        self.policy_optimizer.step()

        # Train value function
        for i in range(self.train_v_iters):
            estimation = self.v_network(obs)
            loss_v = ((estimation - ret)**2).mean()
            self.v_optimizer.zero_grad()
            loss_v.backward()
            self.v_optimizer.step()

        return {
            "loss/policy": loss_policy,
            "loss/v": loss_v
        }

    @torch.no_grad()
    def select_action(self, obs, deterministic=False):
        if len(obs.shape) == 1:
            ret_single = True
            obs = [obs]
        if type(obs) != torch.tensor:
            obs = torch.FloatTensor(np.array(obs)).to(util.device)
        action, log_prob = itemgetter("action_scaled", "log_prob")(self.policy_network.sample(obs, deterministic=deterministic))
        if ret_single:
            action = action[0]
            log_prob = log_prob[0]
        return {
            'action': action.detach().cpu().numpy(),
            'log_prob' : log_prob
            }