import torch
import torch.nn as nn

def get_optimizer(optimizer_fn, network, learning_rate):
    optimizer_fn = optimizer_fn.lower()
    if optimizer_fn == "adam":
        optimizer = torch.optim.Adam(self.Q_network.parameters(),lr = learning_rate)
    elif optimizer_fn== "sgd":
        optimizer = torch.optim.SGD(self.Q_network.parameters(),lr = learning_rate)
    else:
        assert 0,"Unimplemented optimizer {}".format(optimizer_class)
    return optimizer


def get_network(param_shape: List[int], deconv=False):
    if len(param_shape) == 4:
        if deconv:
            in_channel, kernel_size, stride, out_channel = param_shape
            return torch.nn.ConvTranspose2d(in_channel, out_channel, kernel_size=kernel_size, stride=stride)
        else:
            in_channel, kernel_size, stride, out_channel = param_shape
            return torch.nn.Conv2d(in_channel, out_channel, kernel_size=kernel_size, stride=stride)
    elif len(param_shape) == 2:
        in_dim, out_dim = param_shape
        return torch.nn.Linear(in_dim, out_dim)
    else:
        assert 0, "network parameters {} illegal".format(param_shape)


def get_act_cls(act_fn_name):
    act_fn_name = act_fn_name.lower()
    if act_fn_name == "tanh":
        act_cls = torch.nn.Tanh
    elif act_fn_name == "sigmoid":
        act_cls = torch.nn.Sigmoid
    elif act_fn_name == 'relu':
        act_cls = torch.nn.ReLU
    elif act_fn_name == 'identity':
        act_cls = torch.nn.Identity
    else:
        assert 0, "activation function {} not implemented".format(act_fn_name)
    return act_cls


class QNetwork(nn.Module):
    def __init__(self,input_dim, out_dim, hidden_dims, act_fn="relu", out_act_fn="identity"):
        if type(hidden_dims) == int:
            hidden_dims = [hidden_dims]
        hidden_dims = [input_dim] + hidden_dims 
        self.networks = []
        act_cls = get_act_cls(act_fn)
        out_act_cls = get_act_cls(out_act_fn)
        for i in range(len(hidden_dims)-1):
            curr_shape, next_shape = hidden_dims[i], hidden_dims[i+1]
            curr_network = get_network([curr_shape, next_shape])
            self.networks.extend([curr_network, act_cls()])
        final_network = get_network([hidden_dims[-1],out_dim])
        self.networks.extend([final_network, out_act_cls()])
        self.networks = nn.ModuleList(self.network_layers)
    
    def forward(self, state, action):
        input = torch.cat([state, action], 1)
        return self.networks(input)


class VNetwork(nn.Module):
    def __init__(self,input_dim, out_dim, hidden_dims, act_fn="relu", out_act_fn="identity"):
        if type(hidden_dims) == int:
            hidden_dims = [hidden_dims]
        hidden_dims = [input_dim] + hidden_dims 
        self.networks = []
        act_cls = get_act_cls(act_fn)
        out_act_cls = get_act_cls(out_act_fn)
        for i in range(len(hidden_dims)-1):
            curr_shape, next_shape = hidden_dims[i], hidden_dims[i+1]
            curr_network = get_network([curr_shape, next_shape])
            self.networks.extend([curr_network, act_cls()])
        final_network = get_network([hidden_dims[-1],out_dim])
        self.networks.extend([final_network, out_act_cls()])
        self.networks = nn.ModuleList(self.network_layers)
    
    def forward(self, state):
        return self.networks(state)


class PolicyNetwork(nn.Module):
    def __init__(self,input_dim, action_dim, hidden_dims, act_fn="relu", out_act_fn="identity", action_space=None, deterministic=False):
        if type(hidden_dims) == int:
            hidden_dims = [hidden_dims]
        hidden_dims = [input_dim] + hidden_dims 
        self.networks = []
        act_cls = get_act_cls(act_fn)
        out_act_cls = get_act_cls(out_act_fn)
        for i in range(len(hidden_dims)-1):
            curr_shape, next_shape = hidden_dims[i], hidden_dims[i+1]
            curr_network = get_network([curr_shape, next_shape])
            self.networks.extend([curr_network, act_cls()])
        final_network = get_network([hidden_dims[-1], action_dim * 2])
        self.networks.extend([final_network, out_act_cls()])
        self.networks = nn.ModuleList(self.network_layers)
        #action rescaler
        if action_space == None:
            self.action_scale = torch.tensor(1.)
            self.action_bias = torch.tensor(0.)
        else:
            self.action_scale = torch.FloatTensor( (action_space.high - action_space.low) / 2.)
            self.action_bias = torch.FloatTensor( (action_space.high + action_space.low) / 2.)
        self.action_dim = action_dim
        self.noise = torch.Tensor(action_dim) # for deterministic policy
        self.deterministic = deterministic    

    def forward(self, state):
        out = self.networks(state)
        action_mean = out[:self.action_dim]
        action_log_std = out[self.action_dim:]
        if self.deterministic:
            return action_mean
        else:
            return action_mean, action_log_std
    
    def sample(self, state):
        out = self.networks(state)
        action_mean = out[:self.action_dim]
        
        if self.deterministic:
            action_mean = torch.tanh(action_mean) * self.action_scale + self.action_bias
            noise = self.noise.normal_(0., std=0.1)
            noise = noise.clamp(-0.25, 0.25)
            action = action_mean + noise
            return action, torch.tensor(0.), action_mean
        else:
            action_log_std = out[self.action_dim:]
            action_std = torch.exp(action_log_std)
            dist = torch.distribution.Normal(action_mean, action_std)

            #to reperameterize, use rsample
            mean_sample = dist.rsample()
            action_log_prob = dist.log_prob(action_sample)
            action = torch.tanh(mean_sample) * self.action_scale + self.action_bias
            log_prob = dist.log_prob(mean_sample)
            #enforce action bound
            log_prob -= torch.log(self.action_scale * (1 - torch.tanh(mean_sample).pow(2)) + 1e-6)
            log_prob = log_prob.sum(1, keepdim=True)
            mean = torch.tanh(action_mean) * self.action_scale + self.action_bias

            return action, log_prob, mean
    
    def to(self, device):
        self.action_scale = self.action_scale.to(device)
        self.action_bias = self.action_bias.to(device)
        self.noise = self.noise.to(device)
        return super(PolicyNetwork, self).to(device)




        