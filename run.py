import argparse
import random
from time import time
import numpy as np
import tensorflow.contrib.keras as keras
from gym.utils.play import play

from atari_wrappers import wrap_deepmind, make_atari
from replay_buffer import ReplayBuffer

REPLAY_BUFFER_SIZE = 1000
DISCOUNT_FACTOR_GAMMA = 0.99
BATCH_SIZE = 32
REPLAY_START_SIZE = 50000
MAX_TIME_STEPS = 5000000


def one_hot_encode(env, action):
    one_hot = np.zeros(env.action_space.n)
    one_hot[action] = 1
    return one_hot


def fit_batch(env, model, batch):
    observations, actions, rewards, next_observations, dones = batch
    # Predict the Q values of the next states. Passing ones as the action mask.
    next_q_values = model.predict([next_observations, np.ones((BATCH_SIZE, env.action_space.n))])
    # The Q values of terminal states is 0 by definition.
    next_q_values[dones] = 0.0
    # The Q values of each start state is the reward + gamma * the max next state Q value
    q_values = rewards + DISCOUNT_FACTOR_GAMMA * np.max(next_q_values, axis=1)
    # Passing the actions as the mask and multiplying the targets by the actions masks.
    one_hot_actions = np.array([one_hot_encode(env, action) for action in actions])
    model.fit(
        x=[observations, one_hot_actions],
        y=one_hot_actions * q_values[:, None],
        batch_size=BATCH_SIZE,
        verbose=0,
    )


def atari_model(env):
    n_actions = env.action_space.n
    obs_shape = env.observation_space.shape
    print('n_actions {}'.format(n_actions))
    print('obs_shape {}'.format(obs_shape))
    frames_input = keras.layers.Input(obs_shape, name='frames_input')
    actions_input = keras.layers.Input((n_actions,), name='actions_input')
    # Assuming that the input frames are still encoded from 0 to 255. Transforming to [0, 1].
    normalized = keras.layers.Lambda(lambda x: x / 255.0)(frames_input)
    conv_1 = keras.layers.Conv2D(filters=16, kernel_size=8, strides=4, activation='relu')(normalized)
    conv_2 = keras.layers.Conv2D(filters=32, kernel_size=4, strides=2, activation='relu')(conv_1)
    conv_flattened = keras.layers.Flatten()(conv_2)
    hidden = keras.layers.Dense(256, activation='relu')(conv_flattened)
    output = keras.layers.Dense(n_actions)(hidden)
    filtered_output = keras.layers.multiply([output, actions_input])
    model = keras.models.Model([frames_input, actions_input], filtered_output)
    optimizer = keras.optimizers.RMSprop(lr=0.00025, rho=0.95, epsilon=0.01)
    model.compile(optimizer, loss='mse')
    return model


def get_epsilon_for_iteration(step):
    # epsilon annealed linearly from 1 to 0.1 over first million of iterations and fixed at 0.1 thereafter
    return max(-9e-7 * step + 1, 0.1)


def greedy_action(env, model, observation):
    next_q_values = model.predict([np.array([observation]), np.ones((1, env.action_space.n))])
    return np.argmax(next_q_values)


def epsilon_greedy(env, model, observation, step):
    epsilon = get_epsilon_for_iteration(step)
    if random.random() < epsilon:
        action = env.action_space.sample()
    else:
        action = greedy_action(env, model, observation)
    return action


def train(env, max_time_steps):
    replay = ReplayBuffer(REPLAY_BUFFER_SIZE)
    model = atari_model(env)
    done = True
    episode = 0
    for step in range(max_time_steps):
        if done:
            if episode > 0:
                episode_end = time()
                seconds = episode_end - episode_start
                episode_steps = step - episode_start_step
                print("episode {} steps {}/{} return {} in {:.1f}s {:.1f} steps/s".format(
                    episode,
                    episode_steps,
                    step,
                    episode_return,
                    seconds,
                    episode_steps / seconds,
                ))
            episode_start = time()
            episode_start_step = step
            obs = env.reset()
            episode += 1
            episode_return = 0.0
        else:
            obs = next_obs
        action = epsilon_greedy(env, model, obs, step)
        # TODO: according to the paper, we should play 4 times here, this is UPDATE_FREQUENCY
        next_obs, reward, done, _ = env.step(action)
        episode_return += reward
        replay.add(obs, action, reward, next_obs, done)
        if step >= REPLAY_START_SIZE:
            batch = replay.sample(BATCH_SIZE)
            fit_batch(env, model, batch)


def main(args):
    assert REPLAY_START_SIZE >= BATCH_SIZE
    random.seed(args.seed)
    env = make_atari('{}NoFrameskip-v4'.format(args.env))
    env.seed(args.seed)
    if args.play:
        env = wrap_deepmind(env, frame_stack=False)
        play(env)
    else:
        env = wrap_deepmind(env, frame_stack=True)
        if args.test:
            train(env, max_time_steps=100)
        else:
            train(env, max_time_steps=MAX_TIME_STEPS)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--env', action='store', default='Breakout', help='Atari game name')
    parser.add_argument('--play', action='store_true', default=False, help='play with WSAD + Space')
    parser.add_argument('--seed', action='store', type=int, help='pseudo random number generator seed')
    parser.add_argument('--test', action='store_true', default=False, help='run tests')
    args = parser.parse_args()
    main(args)
