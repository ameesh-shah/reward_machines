"""
Q-Learning based method
"""

import random, time
import numpy as np
from baselines import logger
from baselines.common.vec_env import VecEnv

def get_qmax(Q,s,actions,q_init):
    if s not in Q:
        Q[s] = dict([(a,q_init) for a in actions])
    return max(Q[s].values())

def get_best_action(Q,s,actions,q_init):
    qmax = get_qmax(Q,s,actions,q_init)
    best = [a for a in actions if Q[s][a] == qmax]
    return random.choice(best)

def learn(env,
          network=None,
          seed=None,
          lr=0.1,
          total_timesteps=100000,
          epsilon=0.1,
          print_freq=10000,
          gamma=0.9,
          q_init=2.0,
          use_crm=False,
          use_rs=False,
          model=None):
    """Train a tabular q-learning model.

    Parameters
    -------
    env: gym.Env
        environment to train on
    network: string or a function
        This is just a placeholder to be consistent with the openai-baselines interface, but we don't really use state-approximation in tabular q-learning
    seed: int or None
        prng seed. The runs with the same seed "should" give the same results. If None, no seeding is used.
    lr: float
        learning rate
    total_timesteps: int
        number of env steps to optimizer for
    epsilon: float
        epsilon-greedy exploration
    print_freq: int
        how often to print out training progress
        set to None to disable printing
    gamma: float
        discount factor
    q_init: float
        initial q-value for unseen states
    use_crm: bool
        use counterfactual experience to train the policy
    use_rs: bool
        use reward shaping
    """

    # Running Q-Learning
    reward_total = 0
    step = 0
    num_episodes = 0
    Q = {} if model is None else model
    actions = list(range(env.action_space.n))

    while step < total_timesteps:
        s = tuple(env.reset())
        if s not in Q: Q[s] = dict([(a,q_init) for a in actions])
        while True:
            # Selecting and executing the action
            a = random.choice(actions) if random.random() < epsilon else get_best_action(Q,s,actions,q_init)
            sn, r, done, info = env.step(a)
            sn = tuple(sn)

            # Updating the q-values
            experiences = []
            if use_crm:
                # Adding counterfactual experience (this will alrady include shaped rewards if use_rs=True)
                for _s,_a,_r,_sn,_done in info["crm-experience"]:
                    experiences.append((tuple(_s),_a,_r,tuple(_sn),_done))
            elif use_rs:
                # Include only the current experince but shape the reward
                experiences = [(s,a,info["rs-reward"],sn,done)]
            else:
                # Include only the current experience (standard q-learning)
                experiences = [(s,a,r,sn,done)]

            for _s,_a,_r,_sn,_done in experiences:
                if _s not in Q: Q[_s] = dict([(b,q_init) for b in actions])
                if _done: _delta = _r - Q[_s][_a]
                else:     _delta = _r + gamma*get_qmax(Q,_sn,actions,q_init) - Q[_s][_a]
                Q[_s][_a] += lr*_delta

            # moving to the next state
            reward_total += r
            step += 1
            if step%print_freq == 0:
                logger.record_tabular("steps", step)
                logger.record_tabular("episodes", num_episodes)
                logger.record_tabular("total reward", reward_total)
                logger.dump_tabular()
                reward_total = 0
            if done:
                num_episodes += 1
                break
            s = sn

    return Q

def get_policy_counterexamples(model, env, num_iters, is_tabular=True):
    logger.log("Running trained model to collect counterexamples")
    counterexamples = []

    dones = np.zeros((1,))

    for sample in range(num_iters):
        done_any = False
        episode_rew = np.zeros(env.num_envs) if isinstance(env, VecEnv) else np.zeros(1)
        trace = []
        state = tuple(env.reset())
        while not done_any:
            positive_example = False
            actions = list(range(env.action_space.n))
            q_init = 2.0 ##TODO: un-hardcode this, if need be.
            action = get_best_action(model,state,actions,q_init)

            trace.append((state, action))
            obs, rew, done, _ = env.step(action)
            state = tuple(obs)
            episode_rew += rew
            done_any = done.any() if isinstance(done, np.ndarray) else done
            if done_any:
                for i in np.nonzero(done)[0]:
                    if episode_rew[i] > 0:
                        # positive example
                        positive_example = True
                if not positive_example:
                    counterexamples.append(trace)
    logger.log("Counterexample search process completed.")
    return counterexamples