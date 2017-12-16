# Copyright (c) 2016, NVIDIA CORPORATION. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#  * Neither the name of NVIDIA CORPORATION nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import re
import numpy as np
import tensorflow as tf
import tensorflow.contrib.layers as layers
from Config import Config


class NetworkVP:
    def __init__(self, device, model_name, num_actions):
        self.device = device
        self.model_name = model_name
        self.num_actions = num_actions

        self.img_width = Config.IMAGE_WIDTH
        self.img_height = Config.IMAGE_HEIGHT
        self.img_channels = Config.STACKED_FRAMES

        self.learning_rate = Config.LEARNING_RATE_START
        self.beta = Config.BETA_START
        self.log_epsilon = Config.LOG_EPSILON

        self.graph = tf.Graph()
        with self.graph.as_default() as g:
            with tf.device(self.device):
                self._create_graph()

                self.sess = tf.Session(
                    graph=self.graph,
                    config=tf.ConfigProto(
                        allow_soft_placement=True,
                        log_device_placement=False,
                        gpu_options=tf.GPUOptions(allow_growth=True)))
                self.sess.run(tf.global_variables_initializer())

                if Config.TENSORBOARD: self._create_tensor_board()
                if Config.LOAD_CHECKPOINT or Config.SAVE_MODELS:
                    vars = tf.global_variables()
                    self.saver = tf.train.Saver({var.name: var for var in vars}, max_to_keep=0)
                
    
    def tiny_yolo(self, X):
        '''
        0 conv     16  3 x 3 / 1   224 x 224 x   3   ->   224 x 224 x  16
        1 max          2 x 2 / 2   224 x 224 x  16   ->   112 x 112 x  16
        2 conv     32  3 x 3 / 1   112 x 112 x  16   ->   112 x 112 x  32
        3 max          2 x 2 / 2   112 x 112 x  32   ->    56 x  56 x  32
        4 conv     16  1 x 1 / 1    56 x  56 x  32   ->    56 x  56 x  16
        5 conv    128  3 x 3 / 1    56 x  56 x  16   ->    56 x  56 x 128
        6 conv     16  1 x 1 / 1    56 x  56 x 128   ->    56 x  56 x  16
        7 conv    128  3 x 3 / 1    56 x  56 x  16   ->    56 x  56 x 128
        8 max          2 x 2 / 2    56 x  56 x 128   ->    28 x  28 x 128
        9 conv     32  1 x 1 / 1    28 x  28 x 128   ->    28 x  28 x  32
       10 conv    256  3 x 3 / 1    28 x  28 x  32   ->    28 x  28 x 256
       11 conv     32  1 x 1 / 1    28 x  28 x 256   ->    28 x  28 x  32
       12 conv    256  3 x 3 / 1    28 x  28 x  32   ->    28 x  28 x 256
       13 max          2 x 2 / 2    28 x  28 x 256   ->    14 x  14 x 256
       14 conv     64  1 x 1 / 1    14 x  14 x 256   ->    14 x  14 x  64
       15 conv    512  3 x 3 / 1    14 x  14 x  64   ->    14 x  14 x 512
       16 conv     64  1 x 1 / 1    14 x  14 x 512   ->    14 x  14 x  64
       17 conv    512  3 x 3 / 1    14 x  14 x  64   ->    14 x  14 x 512
       18 conv    128  1 x 1 / 1    14 x  14 x 512   ->    14 x  14 x 128
       19 conv   1000  1 x 1 / 1    14 x  14 x 128   ->    14 x  14 x1000
       20 avg                       14 x  14 x1000   ->  1000
       21 softmax                                        1000
       22 cost                                           1000
        '''
        conv0 = tf.layers.conv2d(inputs=X, filters=16, kernel_size=[3, 3], strides=1, padding="same", activation=tf.nn.relu)
        max1 = tf.layers.max_pooling2d(inputs=conv0, pool_size=[2, 2], strides=2)
        conv2 = tf.layers.conv2d(inputs=max1, filters=32, kernel_size=[3, 3], strides=1, padding="same",
                     activation=tf.nn.relu)
        max3 = tf.layers.max_pooling2d(inputs=conv2, pool_size=[2, 2], strides=2)
        conv4 = tf.layers.conv2d(inputs=max3, filters=16, kernel_size=[1, 1], strides=1, padding="same",
                     activation=tf.nn.relu)
        conv5 = tf.layers.conv2d(inputs=conv4, filters=128, kernel_size=[3, 3], strides=1, padding="same",
                     activation=tf.nn.relu)
        conv6 = tf.layers.conv2d(inputs=conv5, filters=16, kernel_size=[1, 1], strides=1, padding="same",
                     activation=tf.nn.relu)
        conv7 = tf.layers.conv2d(inputs=conv6, filters=128, kernel_size=[3, 3], strides=1, padding="same",
                     activation=tf.nn.relu)
        max8 = tf.layers.max_pooling2d(inputs=conv7, pool_size=[2, 2], strides=2)
        conv9 = tf.layers.conv2d(inputs=max8, filters=32, kernel_size=[1, 1], strides=1, padding="same",
                     activation=tf.nn.relu)
        conv10 = tf.layers.conv2d(inputs=conv9, filters=256, kernel_size=[3, 3], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv11 = tf.layers.conv2d(inputs=conv10, filters=32, kernel_size=[1, 1], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv12 = tf.layers.conv2d(inputs=conv11, filters=256, kernel_size=[3, 3], strides=1, padding="same",
                      activation=tf.nn.relu)
        max13 = tf.layers.max_pooling2d(inputs=conv12, pool_size=[2, 2], strides=2)
        conv14 = tf.layers.conv2d(inputs=max13, filters=64, kernel_size=[1, 1], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv15 = tf.layers.conv2d(inputs=conv14, filters=512, kernel_size=[3, 3], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv16 = tf.layers.conv2d(inputs=conv15, filters=64, kernel_size=[1, 1], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv17 = tf.layers.conv2d(inputs=conv16, filters=512, kernel_size=[3, 3], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv18 = tf.layers.conv2d(inputs=conv17, filters=128, kernel_size=[1, 1], strides=1, padding="same",
                      activation=tf.nn.relu)
        conv19 = tf.layers.conv2d(inputs=conv18, filters=1000, kernel_size=[1, 1], strides=1, padding="same",
                      activation=tf.nn.relu)
        avg20 = tf.layers.average_pooling2d(inputs=conv19, pool_size=[conv19.shape[1], conv19.shape[2]], strides=1)
        return layers.flatten(avg20)

    def _create_graph(self):
        self.x = tf.placeholder(
            tf.float32, [None, 28], name='X')
        self.y_r = tf.placeholder(tf.float32, [None], name='Yr')

        self.var_beta = tf.placeholder(tf.float32, name='beta', shape=[])
        self.var_learning_rate = tf.placeholder(tf.float32, name='lr', shape=[])

        self.global_step = tf.Variable(0, trainable=False, name='step')

        self.action_index = tf.placeholder(tf.float32, [None, self.num_actions])

        #(v, o, r, rgbd) = tf.split(self.x, [1, 3, 3, int(self.x.shape[1])-7], 1)
        #rgbd = tf.reshape(rgbd, [-1, 288, 256, 4])
        #rgbd0, rgbd1 = tf.split(rgbd, [144, 144], 1)
        #(rgb0, depth0) = tf.split(rgbd0, [3,1], 3)
        #(rgb1, depth1) = tf.split(rgbd1, [3,1], 3)
        #rgb = tf.concat([rgb0, rgb1], 3)
        #depth = tf.concat([depth0, depth1], 3)
        #self.n1 = self.tiny_yolo(rgb0)
        ##self.n1_1 = self.tiny_yolo(rgb1)
        #self.n2 = self.tiny_yolo(depth0)
        ##self.n2_1 = self.tiny_yolo(depth1)
        #self.flat = tf.concat([v, o, r, self.n1, self.n2], 1)
        self.flat = self.x
        self.d1 = self.dense_layer(self.flat, 4096, 'dense1')
        self.d2 = self.dense_layer(self.d1, 4096, 'dense2')
        self.d3 = self.dense_layer(self.d2, 2048, 'dense3')
        self.d4 = self.dense_layer(self.d3, 2048, 'dense4')
        self.d5 = self.dense_layer(self.d4, 1024, 'dense5')
        self.d6 = self.dense_layer(self.d5, 1024, 'dense6')
        self.logits_v = tf.squeeze(self.dense_layer(self.d6, 1, 'logits_v', func=None), axis=[1])

        '''
        # As implemented in A3C paper
        self.n1 = self.conv2d_layer(self.x, 8, 16, 'conv11', strides=[1, 4, 4, 1])
        self.n2 = self.conv2d_layer(self.n1, 4, 32, 'conv12', strides=[1, 2, 2, 1])
        self.action_index = tf.placeholder(tf.float32, [None, self.num_actions])
        _input = self.n2

        flatten_input_shape = _input.get_shape()
        nb_elements = flatten_input_shape[1] * flatten_input_shape[2] * flatten_input_shape[3]

        self.flat = tf.reshape(_input, shape=[-1, nb_elements._value])
        self.d1 = self.dense_layer(self.flat, 256, 'dense1')
        
        self.logits_v = tf.squeeze(self.dense_layer(self.d1, 1, 'logits_v', func=None), axis=[1])
        '''
        self.cost_v = 0.5 * tf.reduce_sum(tf.square(self.y_r - self.logits_v), axis=0)
        

        self.logits_p = self.dense_layer(self.d1, self.num_actions, 'logits_p', func=None)
        if Config.USE_LOG_SOFTMAX:
            self.softmax_p = tf.nn.softmax(self.logits_p)
            self.log_softmax_p = tf.nn.log_softmax(self.logits_p)
            self.log_selected_action_prob = tf.reduce_sum(self.log_softmax_p * self.action_index, axis=1)

            self.cost_p_1 = self.log_selected_action_prob * (self.y_r - tf.stop_gradient(self.logits_v))
            self.cost_p_2 = -1 * self.var_beta * \
                        tf.reduce_sum(self.log_softmax_p * self.softmax_p, axis=1)
        else:
            self.softmax_p = (tf.nn.softmax(self.logits_p) + Config.MIN_POLICY) / (1.0 + Config.MIN_POLICY * self.num_actions)
            self.selected_action_prob = tf.reduce_sum(self.softmax_p * self.action_index, axis=1)

            self.cost_p_1 = tf.log(tf.maximum(self.selected_action_prob, self.log_epsilon)) \
                        * (self.y_r - tf.stop_gradient(self.logits_v))
            self.cost_p_2 = -1 * self.var_beta * \
                        tf.reduce_sum(tf.log(tf.maximum(self.softmax_p, self.log_epsilon)) *
                                      self.softmax_p, axis=1)
        
        self.cost_p_1_agg = tf.reduce_sum(self.cost_p_1, axis=0)
        self.cost_p_2_agg = tf.reduce_sum(self.cost_p_2, axis=0)
        self.cost_p = -(self.cost_p_1_agg + self.cost_p_2_agg)
        
        if Config.DUAL_RMSPROP:
            self.opt_p = tf.train.RMSPropOptimizer(
                learning_rate=self.var_learning_rate,
                decay=Config.RMSPROP_DECAY,
                momentum=Config.RMSPROP_MOMENTUM,
                epsilon=Config.RMSPROP_EPSILON)

            self.opt_v = tf.train.RMSPropOptimizer(
                learning_rate=self.var_learning_rate,
                decay=Config.RMSPROP_DECAY,
                momentum=Config.RMSPROP_MOMENTUM,
                epsilon=Config.RMSPROP_EPSILON)
        else:
            self.cost_all = self.cost_p + self.cost_v
            self.opt = tf.train.RMSPropOptimizer(
                learning_rate=self.var_learning_rate,
                decay=Config.RMSPROP_DECAY,
                momentum=Config.RMSPROP_MOMENTUM,
                epsilon=Config.RMSPROP_EPSILON)

        if Config.USE_GRAD_CLIP:
            if Config.DUAL_RMSPROP:
                self.opt_grad_v = self.opt_v.compute_gradients(self.cost_v)
                self.opt_grad_v_clipped = [(tf.clip_by_norm(g, Config.GRAD_CLIP_NORM),v) 
                                            for g,v in self.opt_grad_v if not g is None]
                self.train_op_v = self.opt_v.apply_gradients(self.opt_grad_v_clipped)
            
                self.opt_grad_p = self.opt_p.compute_gradients(self.cost_p)
                self.opt_grad_p_clipped = [(tf.clip_by_norm(g, Config.GRAD_CLIP_NORM),v)
                                            for g,v in self.opt_grad_p if not g is None]
                self.train_op_p = self.opt_p.apply_gradients(self.opt_grad_p_clipped)
                self.train_op = [self.train_op_p, self.train_op_v]
            else:
                self.opt_grad = self.opt.compute_gradients(self.cost_all)
                self.opt_grad_clipped = [(tf.clip_by_average_norm(g, Config.GRAD_CLIP_NORM),v) for g,v in self.opt_grad]
                self.train_op = self.opt.apply_gradients(self.opt_grad_clipped)
        else:
            if Config.DUAL_RMSPROP:
                self.train_op_v = self.opt_p.minimize(self.cost_v, global_step=self.global_step)
                self.train_op_p = self.opt_v.minimize(self.cost_p, global_step=self.global_step)
                self.train_op = [self.train_op_p, self.train_op_v]
            else:
                self.train_op = self.opt.minimize(self.cost_all, global_step=self.global_step)


    def _create_tensor_board(self):
        summaries = tf.get_collection(tf.GraphKeys.SUMMARIES)
        summaries.append(tf.summary.scalar("Pcost_advantage", self.cost_p_1_agg))
        summaries.append(tf.summary.scalar("Pcost_entropy", self.cost_p_2_agg))
        summaries.append(tf.summary.scalar("Pcost", self.cost_p))
        summaries.append(tf.summary.scalar("Vcost", self.cost_v))
        summaries.append(tf.summary.scalar("LearningRate", self.var_learning_rate))
        summaries.append(tf.summary.scalar("Beta", self.var_beta))
        for var in tf.trainable_variables():
            summaries.append(tf.summary.histogram("weights_%s" % var.name, var))

        #ummaries.append(tf.summary.histogram("activation_n1", self.n1))
        #summaries.append(tf.summary.histogram("activation_n2", self.n2))
        summaries.append(tf.summary.histogram("activation_d2", self.d1))
        summaries.append(tf.summary.histogram("activation_v", self.logits_v))
        summaries.append(tf.summary.histogram("activation_p", self.softmax_p))

        self.summary_op = tf.summary.merge(summaries)
        self.log_writer = tf.summary.FileWriter("logs/%s" % self.model_name, self.sess.graph)

    def dense_layer(self, input, out_dim, name, func=tf.nn.relu):
        in_dim = input.get_shape().as_list()[-1]
        d = 1.0 / np.sqrt(in_dim)
        with tf.variable_scope(name):
            w_init = tf.random_uniform_initializer(-d, d)
            b_init = tf.random_uniform_initializer(-d, d)
            w = tf.get_variable('w', dtype=tf.float32, shape=[in_dim, out_dim], initializer=w_init)
            b = tf.get_variable('b', shape=[out_dim], initializer=b_init)

            output = tf.matmul(input, w) + b
            if func is not None:
                output = func(output)

        return output

    def conv2d_layer(self, input, filter_size, out_dim, name, strides, func=tf.nn.relu):
        in_dim = input.get_shape().as_list()[-1]
        d = 1.0 / np.sqrt(filter_size * filter_size * in_dim)
        with tf.variable_scope(name):
            w_init = tf.random_uniform_initializer(-d, d)
            b_init = tf.random_uniform_initializer(-d, d)
            w = tf.get_variable('w',
                                shape=[filter_size, filter_size, in_dim, out_dim],
                                dtype=tf.float32,
                                initializer=w_init)
            b = tf.get_variable('b', shape=[out_dim], initializer=b_init)

            output = tf.nn.conv2d(input, w, strides=strides, padding='SAME') + b
            if func is not None:
                output = func(output)

        return output

    def __get_base_feed_dict(self):
        return {self.var_beta: self.beta, self.var_learning_rate: self.learning_rate}

    def get_global_step(self):
        step = self.sess.run(self.global_step)
        return step

    def predict_single(self, x):
        return self.predict_p(x[None, :])[0]

    def predict_v(self, x):
        prediction = self.sess.run(self.logits_v, feed_dict={self.x: x})
        return prediction

    def predict_p(self, x):
        prediction = self.sess.run(self.softmax_p, feed_dict={self.x: x})
        return prediction
    
    def predict_p_and_v(self, x):
        return self.sess.run([self.softmax_p, self.logits_v], feed_dict={self.x: x})
    
    def train(self, x, y_r, a, trainer_id):
        feed_dict = self.__get_base_feed_dict()
        feed_dict.update({self.x: x, self.y_r: y_r, self.action_index: a})
        self.sess.run(self.train_op, feed_dict=feed_dict)

    def log(self, x, y_r, a):
        feed_dict = self.__get_base_feed_dict()
        feed_dict.update({self.x: x, self.y_r: y_r, self.action_index: a})
        step, summary = self.sess.run([self.global_step, self.summary_op], feed_dict=feed_dict)
        self.log_writer.add_summary(summary, step)

    def _checkpoint_filename(self, episode):
        return 'checkpoints/%s_%08d' % (self.model_name, episode)
    
    def _get_episode_from_filename(self, filename):
        # TODO: hacky way of getting the episode. ideally episode should be stored as a TF variable
        return int(re.split('/|_|\.', filename)[2])

    def save(self, episode):
        self.saver.save(self.sess, self._checkpoint_filename(episode))

    def load(self):
        filename = tf.train.latest_checkpoint(os.path.dirname(self._checkpoint_filename(episode=0)))
        if Config.LOAD_EPISODE > 0:
            filename = self._checkpoint_filename(Config.LOAD_EPISODE)
        self.saver.restore(self.sess, filename)
        return self._get_episode_from_filename(filename)
       
    def get_variables_names(self):
        return [var.name for var in self.graph.get_collection('trainable_variables')]

    def get_variable_value(self, name):
        return self.sess.run(self.graph.get_tensor_by_name(name))