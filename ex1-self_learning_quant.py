from __future__ import print_function

import numpy as np
np.random.seed(1335)  # for reproducibility
np.set_printoptions(precision=5, suppress=True, linewidth=150)
import os
import pandas as pd
import backtest as twp
from matplotlib import pyplot as plt
from sklearn import metrics, preprocessing
from keras.models import Sequential
from keras.layers.core import Dense, Dropout, Activation
from keras.optimizers import RMSprop
import random, timeit
from talib.abstract import *


'''
Name:        The Self Learning Quant, Example 1

Author:      Daniel Zakrisson

Created:     30/03/2016
Copyright:   (c) Daniel Zakrisson 2016
Licence:     BSD
'''


def load_data():
    '''
    datapath = '../util/stock_dfs/'
    all = pd.DataFrame()
    for f in os.listdir(datapath):
        filepath = os.path.join(datapath, f)
        if filepath.endswith('.csv'):
            print(filepath)
            Res = pd.read_csv(filepath).set_index('Date')
            all = all.append(Res)

    return all
    '''

#Initialize first state, all items are placed deterministically
def init_state(data):
    close = indata['Close'].values
    diff = np.diff(close)
    diff = np.insert(diff, 0, 0)
    sma15 = SMA(indata, timeperiod=15)
    sma60 = SMA(indata, timeperiod=60)
    rsi = RSI(indata, timeperiod=14)
    atr = ATR(indata, timeperiod=14)

    # --- Preprocess data
    xdata = np.column_stack((close, diff, sma15, close - sma15, sma15 - sma60, rsi, atr))

    xdata = np.nan_to_num(xdata)
    if test == False:
        scaler = preprocessing.StandardScaler()
        xdata = np.expand_dims(scaler.fit_transform(xdata), axis=1)
        joblib.dump(scaler, 'data/scaler.pkl')
    elif test == True:
        scaler = joblib.load('data/scaler.pkl')
        xdata = np.expand_dims(scaler.fit_transform(xdata), axis=1)
    state = xdata[0:1, 0:1, :]

    return state, xdata, close


#Take Action
def take_action(state, xdata, action, signal, time_step):
    #this should generate a list of trade signals that at evaluation time are fed to the backtester
    #the backtester should get a list of trade signals and a list of price data for the assettg
    
    #make necessary adjustments to state and then return it
    time_step += 1
    
    #if the current iteration is the last state ("terminal state") then set terminal_state to 1
    if time_step == xdata.shape[0]:
        state = xdata[time_step-1:time_step, :]
        terminal_state = 1
        signal.loc[time_step] = 0
        return state, time_step, signal, terminal_state

    #move the market data window one step forward
    state = xdata[time_step-1:time_step, :]
    #take action
    if action != 0:
        if action == 1:
            signal.loc[time_step] = 100
        elif action == 2:
            signal.loc[time_step] = -100
        elif action == 3:
            signal.loc[time_step] = 0
    terminal_state = 0

    return state, time_step, signal, terminal_state

#Get Reward, the reward is returned at the end of an episode
def get_reward(new_state, time_step, action, xdata, signal, terminal_state, epoch=0):
    reward = 0
    signal.fillna(value=0, inplace=True)
    if terminal_state == 0:
        #get reward for the most current action
        if signal[time_step] != signal[time_step-1] and terminal_state == 0:
            i=1
            while signal[time_step-i] == signal[time_step-1-i] and time_step - 1 - i > 0:
                i += 1
            reward = (xdata[time_step-1, 0] - xdata[time_step - i-1, 0]) * signal[time_step - 1]*-100 + i*np.abs(signal[time_step - 1])/10.0
        if signal[time_step] == 0 and signal[time_step - 1] == 0:
            reward -= 10

    #calculate the reward for all actions if the last iteration in set
    if terminal_state == 1:
        #run backtest, send list of trade signals and asset data to backtest function
        bt = twp.Backtest(pd.Series(data=[x[0] for x in xdata]), signal, signalType='shares')
        reward = bt.pnl.iloc[-1]

    return reward

def evaluate_Q(eval_data, eval_model):
    #This function is used to evaluate the perofrmance of the system each epoch, without the influence of epsilon and random actions
    signal = pd.Series(index=np.arange(len(eval_data)))
    state, xdata = init_state(eval_data)
    status = 1
    terminal_state = 0
    time_step = 1
    while(status == 1):
        #We start in state S
        #Run the Q function on S to get predicted reward values on all the possible actions
        qval = eval_model.predict(state.reshape(1,2), batch_size=1)
        action = (np.argmax(qval))
        #Take action, observe new state S'
        new_state, time_step, signal, terminal_state = take_action(state, xdata, action, signal, time_step)
        #Observe reward
        eval_reward = get_reward(new_state, time_step, action, xdata, signal, terminal_state, i)
        state = new_state
        if terminal_state == 1: #terminal state
            status = 0
    return eval_reward





if __name__ == "__main__":
    #This neural network is the the Q-function, run it like this:
    #model.predict(state.reshape(1,64), batch_size=1)

    model = Sequential()
    model.add(Dense(4, init='lecun_uniform', input_shape=(2,)))
    model.add(Activation('relu'))
    #model.add(Dropout(0.2)) I'm not using dropout in this example

    model.add(Dense(4, init='lecun_uniform'))
    model.add(Activation('relu'))
    #model.add(Dropout(0.2))

    model.add(Dense(4, init='lecun_uniform'))
    model.add(Activation('linear')) #linear output so we can have range of real-valued outputs

    rms = RMSprop()
    model.compile(loss='mse', optimizer=rms)


    start_time = timeit.default_timer()

    indata = load_data()
    epochs = 10
    gamma = 0.9 #a high gamma makes a long term reward more valuable
    epsilon = 1
    learning_progress = []
    #stores tuples of (S, A, R, S')
    h = 0
    signal = pd.Series(index=np.arange(len(indata)))
    for i in range(epochs):

        state, xdata = init_state(indata)
        status = 1
        terminal_state = 0
        time_step = 1
        #while learning is still in progress
        while(status == 1):
            #We start in state S
            #Run the Q function on S to get predicted reward values on all the possible actions
            qval = model.predict(state.reshape(1,2), batch_size=1)
            if (random.random() < epsilon) and i != epochs - 1: #maybe choose random action if not the last epoch
                action = np.random.randint(0,4) #assumes 4 different actions
            else: #choose best action from Q(s,a) values
                action = (np.argmax(qval))
            #Take action, observe new state S'
            new_state, time_step, signal, terminal_state = take_action(state, xdata, action, signal, time_step)
            #Observe reward
            reward = get_reward(new_state, time_step, action, xdata, signal, terminal_state, i)
            #Get max_Q(S',a)
            newQ = model.predict(new_state.reshape(1,2), batch_size=1)
            maxQ = np.max(newQ)
            y = np.zeros((1,4))
            y[:] = qval[:]
            if terminal_state == 0: #non-terminal state
                update = (reward + (gamma * maxQ))
            else: #terminal state (means that it is the last state)
                update = reward
            y[0][action] = update #target output
            model.fit(state.reshape(1,2), y, batch_size=1, nb_epoch=1, verbose=0)
            state = new_state
            if terminal_state == 1: #terminal state
                status = 0
        eval_reward = evaluate_Q(indata, model)
        print("Epoch #: %s Reward: %f Epsilon: %f" % (i,eval_reward, epsilon))
        learning_progress.append((eval_reward))
        if epsilon > 0.1:
            epsilon -= (1.0/epochs)

    elapsed = np.round(timeit.default_timer() - start_time, decimals=2)
    print("Completed in %f" % (elapsed,))

    #plot results
    bt = twp.Backtest(pd.Series(data=[x[0] for x in xdata]), signal, signalType='shares')
    bt.data['delta'] = bt.data['shares'].diff().fillna(0)

    print(bt.data)

    plt.figure()
    bt.plotTrades()
    plt.suptitle('epoch' + str(i))
    plt.savefig('final_trades_ex1'+'.png', bbox_inches='tight', pad_inches=1, dpi=72) #assumes there is a ./plt dir
    plt.close('all')

    plt.figure()
    plt.subplot(3,1,1)
    bt.plotTrades()
    plt.subplot(3,1,2)
    bt.pnl.plot(style='x-')
    plt.subplot(3,1,3)
    plt.plot(learning_progress)

    plt.show()


