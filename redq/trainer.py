from common.util import hard_update_network, soft_update_network, second_to_time_str
from torch.nn.functional import max_pool1d_with_indices
from common.trainer import BaseTrainer
import numpy as np
from tqdm import tqdm
import os
import cv2
from time import time
class REDQTrainer(BaseTrainer):
    def __init__(self, agent, env, eval_env, buffer, logger, 
            batch_size=256,
            max_trajectory_length=500,
            test_interval=10,
            num_test_trajectories=5,
            max_iteration=100000,
            start_timestep=1000,
            save_model_interval=10000,
            save_video_demo_interval=10000,
            steps_per_iteration=1,
            load_dir="",
            **kwargs):
        self.agent = agent
        self.buffer = buffer
        self.logger = logger
        self.env = env 
        self.eval_env = eval_env
        #hyperparameters
        self.batch_size = batch_size
        self.max_trajectory_length = max_trajectory_length
        self.test_interval = test_interval
        self.num_test_trajectories = num_test_trajectories
        self.max_iteration = max_iteration
        self.start_timestep = start_timestep
        self.save_model_interval = save_model_interval
        self.save_video_demo_interval = save_video_demo_interval
        if load_dir != "" and os.path.exists(load_dir):
            self.agent.load(load_dir)

    def train(self):
        tot_num_updates = 0
        train_traj_rewards = [0]
        train_traj_lengths = []
        durations = []
        done = False
        state = self.env.reset()
        traj_reward = 0
        traj_length = 0
        for ite in range(self.max_iteration):
            iteration_start_time = time()
            #rollout in environment and add to buffer
            action = self.agent.select_action(state)
            next_state, reward, done, _ = self.env.step(action)
            traj_length  += 1
            traj_reward += reward
            if traj_length >= self.max_trajectory_length - 1:
                done = True
            self.buffer.add_tuple(state, action, next_state, reward, float(done))
            state = next_state
            if done or traj_length >= self.max_trajectory_length - 1:
                state = self.env.reset()
                train_traj_rewards.append(traj_reward / self.env.reward_scale)
                train_traj_lengths.append(traj_length)
                self.logger.log_var("return/train",traj_reward / self.env.reward_scale, ite)
                self.logger.log_var("length/train_length",traj_length, ite)
                traj_length = 0
                traj_reward = 0
            if ite < self.start_timestep:
                continue
            #update network
            data_batch = self.buffer.sample_batch(self.batch_size)
            q_losses, policy_loss, entropy_loss, alpha = self.agent.update(data_batch)
            self.logger.log_var("loss/q_min",np.min(q_losses),ite)
            self.logger.log_var("loss/q_max",np.max(q_losses),ite)
            self.logger.log_var("loss/q_mean",np.mean(q_losses),ite)
            self.logger.log_var("loss/q_std",np.std(q_losses),ite)
            self.logger.log_var("loss/policy",policy_loss,ite)
            self.logger.log_var("loss/entropy",entropy_loss,ite)
            self.logger.log_var("others/entropy_alpha",alpha,ite)
            self.agent.try_update_target_network()
            tot_num_updates += 1
       
            iteration_end_time = time()
            duration = iteration_end_time - iteration_start_time
            durations.append(duration)

            if ite % self.test_interval == 0:
                avg_test_reward, avg_test_length = self.test()
                self.logger.log_var("return/test", avg_test_reward, ite)
                self.logger.log_var("length/test_length", avg_test_length, ite)
                self.logger.log_var("durations", duration, ite)
                time_remaining_str = second_to_time_str(int((self.max_iteration - ite + 1) * np.mean(durations[-100:])))
                summary_str = "iteration {}:\ttrain return {:.02f}\ttest return {:02f}\teta: {}".format(ite, train_traj_rewards[-1],avg_test_reward,time_remaining_str)
                self.logger.log_str(summary_str)
            if ite % self.save_model_interval == 0:
                self.agent.save_model(self.logger.log_dir, ite)
            if ite % self.save_video_demo_interval == 0:
                self.save_video_demo(ite)

    def test(self):
        rewards = []
        lengths = []
        for episode in range(self.num_test_trajectories):
            traj_reward = 0
            traj_length = 0
            state = self.eval_env.reset()
            for step in range(self.max_trajectory_length):
                action = self.agent.select_action(state, evaluate=True)
                next_state, reward, done, _ = self.eval_env.step(action)
                traj_reward += reward
                state = next_state
                traj_length += 1 
                if done:
                    break
            lengths.append(traj_length)
            traj_reward /= self.eval_env.reward_scale
            rewards.append(traj_reward)
        return np.mean(rewards), np.mean(lengths)

    def save_video_demo(self, ite, width=128, height=128, fps=30):
        video_demo_dir = os.path.join(self.logger.log_dir,"demos")
        if not os.path.exists(video_demo_dir):
            os.makedirs(video_demo_dir)
        video_size = (height, width)
        video_save_path = os.path.join(video_demo_dir, "ite_{}.avi".format(ite))

        #initilialize video writer
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        video_writer = cv2.VideoWriter(video_save_path, fourcc, fps, video_size)

        #rollout to generate pictures and write video
        state = self.eval_env.reset()
        img = self.eval_env.render(mode="rgb_array", width=width, height=height)
        traj_imgs =[img.astype(np.uint8)]
        for step in range(self.max_trajectory_length):
            action = self.agent.select_action(state, evaluate=True)
            next_state, reward, done, _ = self.eval_env.step(action)
            img = self.eval_env.render(mode="rgb_array", width=width, height=height)
            video_writer.write(img)
            if done:
                break
                
        video_writer.release()
            


