import numpy as np
import pandas as pd
import logging
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime, timedelta

DATA_PATH = '/LG_HG2_Original_Dataset_McMasterUniversity_Jan_2020/'

class LgData():
    def __init__(self, base_path="./"):
        self.path = base_path + DATA_PATH
        self.logger = logging.getLogger()

    def get_discharge_whole_cycle(self, train_names, test_names, output_capacity=False, scale_test=False, output_time=False):
        train = self._get_data(train_names, output_capacity, output_time)
        test = self._get_data(test_names, output_capacity, output_time)
        train, test = self._scale_x(train, test, scale_test=scale_test)        
        return (train, test)
        
    def _get_data(self, names, output_capacity, output_time=False):
        cycles = []
        for name in names:
            cycle = pd.read_csv(self.path + name + '.csv', skiprows=30)
            cycle.columns = ['Time Stamp','Step','Status','Prog Time','Step Time','Cycle',
                            'Cycle Level','Procedure','Voltage','Current','Temperature','Capacity','WhAccu','Cnt','Empty']
            cycle = cycle[(cycle["Status"] == "TABLE") | (cycle["Status"] == "DCH")]

            max_discharge = abs(min(cycle["Capacity"]))
            cycle["SoC Capacity"] = max_discharge + cycle["Capacity"]
            cycle["SoC Percentage"] = cycle["SoC Capacity"] / max(cycle["SoC Capacity"])
            x = cycle[["Voltage", "Current", "Temperature"]].to_numpy()

            if output_time:
                cycle['Prog Time'] = cycle['Prog Time'].apply(self._time_string_to_seconds)
                cycle['Time in Seconds'] = cycle['Prog Time'] - cycle['Prog Time'][0]

            if output_capacity:
                if output_time:
                    y = cycle[["SoC Capacity", "Time in Seconds"]].to_numpy()
                else:
                    y = cycle[["SoC Capacity"]].to_numpy()
            else:
                if output_time:
                    y = cycle[["SoC Percentage", "Time in Seconds"]].to_numpy()
                else:
                    y = cycle[["SoC Percentage"]].to_numpy()

            if np.isnan(np.min(x)) or np.isnan(np.min(y)):
                self.logger.info("There is a NaN in cycle " + name + ", removing row")
                x = x[~np.isnan(x).any(axis=1)]
                y = y[~np.isnan(y).any(axis=1)].reshape(-1, y.shape[1])

            cycles.append((x, y))

        return cycles

    def _time_string_to_seconds(self, input_string):
        time_parts = input_string.split(':')
        second_parts = time_parts[2].split('.')
        return timedelta(hours=int(time_parts[0]), 
            minutes=int(time_parts[1]), 
            seconds=int(second_parts[0]), 
            microseconds=int(second_parts[1])).total_seconds()

    def _scale_x(self, train, test, scale_test=False):
        for index_feature in range(len(train[0][0][0])):
            feature_min = min([min(cycle[0][:,index_feature]) for cycle in train])
            feature_max = max([max(cycle[0][:,index_feature]) for cycle in train])
            for i in range(len(train)):
                train[i][0][:,index_feature] = (train[i][0][:,index_feature]-feature_min)/(feature_max-feature_min)
            if scale_test:
                for i in range(len(test)):
                    test[i][0][:,index_feature] = (test[i][0][:,index_feature]-feature_min)/(feature_max-feature_min)

        return train, test



    def get_stateful_cycle(self, cycles, pad_num = 0, steps = 100):
        max_lenght = max(max(len(cycle[0]) for cycle in cycles[0]), max(len(cycle[0]) for cycle in cycles[1]))
        train_x, train_y = self._to_padded_cycle(cycles[0], pad_num, max_lenght)
        test_x, test_y = self._to_padded_cycle(cycles[1], pad_num, max_lenght)
        train_x = self._split_cycle(train_x, steps)
        train_y = self._split_cycle(train_y, steps)
        test_x = self._split_cycle(test_x, steps)
        test_y = self._split_cycle(test_y, steps)
        self.logger.info("Train x: %s, train y: %s | Test x: %s, test y: %s" %
                         (train_x.shape, train_y.shape, test_x.shape, test_y.shape))
        return (train_x, train_y, test_x, test_y)

    def _to_padded_cycle(self, cycles, pad_num, max_lenght):
        x_length = len(cycles[0][0][0])
        y_length = len(cycles[0][1][0])
        x = np.full((len(cycles), max_lenght, x_length), pad_num, dtype=float)
        y = np.full((len(cycles), max_lenght, y_length), pad_num, dtype=float)
        for i, cycle in enumerate(cycles):
            x[i, :cycle[0].shape[0]] = cycle[0]
            y[i, :cycle[1].shape[0]] = cycle[1]
        return x, y

    def _split_cycle(self, cycles, steps):
        features = cycles.shape[2]
        time_steps = cycles.shape[1]
        new_cycles = np.empty((0, time_steps//steps, steps, features), float)
        for cycle in cycles:
            new_cycle = np.empty((0, steps, features), float)
            for i in range(0, len(cycle) - steps, steps):
                next_split = np.array(cycle[i:i + steps]).reshape(1, steps, features)
                new_cycle = np.concatenate((new_cycle, next_split))
            new_cycles = np.concatenate((new_cycles, new_cycle.reshape(1, time_steps//steps, steps, features)))
        return new_cycles

    def get_discharge_multiple_step(self, cycles, steps):
        train_x, train_y = self._split_to_multiple_step(cycles[0], steps)
        test_x, test_y = self._split_to_multiple_step(cycles[1], steps)
        self.logger.info("Train x: %s, train y: %s | Test x: %s, test y: %s" %
                         (train_x.shape, train_y.shape, test_x.shape, test_y.shape))
        return (train_x, train_y, test_x, test_y)

    def _split_to_multiple_step(self, cycles, steps):
        x_length = len(cycles[0][0][0])
        y_length = len(cycles[0][1][0])
        x = np.empty((0, steps, x_length), float)
        y = np.empty((0, steps, y_length), float)
        for cycle in cycles:
            for i in range(0, len(cycle[0]) - steps, steps):
                next_x = np.array(cycle[0][i:i + steps]).reshape(1, steps, x_length)
                next_y = np.array(cycle[1][i:i + steps]).reshape(1, steps, y_length)
                x = np.concatenate((x, next_x))
                y = np.concatenate((y, next_y))
        return x, y

    def keep_only_y_end(self, y, step, is_stateful=False):
        if is_stateful:
            return y[:,:,[-1]]
        else:
            return y[:,[-1]]

