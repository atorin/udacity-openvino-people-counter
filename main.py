"""People Counter."""
"""
 Copyright (c) 2018 Intel Corporation.
 Permission is hereby granted, free of charge, to any person obtaining
 a copy of this software and associated documentation files (the
 "Software"), to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish,
 distribute, sublicense, and/or sell copies of the Software, and to
 permit person to whom the Software is furnished to do so, subject to
 the following conditions:
 The above copyright notice and this permission notice shall be
 included in all copies or substantial portions of the Software.
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
 LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
 OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
 WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


import os
import sys
import time
import socket
import json
import cv2
import numpy as np

import time
import logging as log
import paho.mqtt.client as mqtt

from argparse import ArgumentParser
from inference import Network
from cocohelper import extract_people
from handle_image import preprocessing, draw_box

# MQTT server environment variables
HOSTNAME = socket.gethostname()
IPADDRESS = socket.gethostbyname(HOSTNAME)
MQTT_HOST = IPADDRESS
MQTT_PORT = 3001
MQTT_KEEPALIVE_INTERVAL = 60


def build_argparser():
    """
    Parse command line arguments.

    :return: command line arguments
    """
    parser = ArgumentParser()
    parser.add_argument("-m", "--model", required=True, type=str,
                        help="Path to an xml file with a trained model.")
    parser.add_argument("-i", "--input", required=True, type=str,
                        help="Path to image or video file")
    parser.add_argument("-l", "--cpu_extension", required=False, type=str,
                        default=None,
                        help="MKLDNN (CPU)-targeted custom layers."
                             "Absolute path to a shared library with the"
                             "kernels impl.")
    parser.add_argument("-d", "--device", type=str, default="CPU",
                        help="Specify the target device to infer on: "
                             "CPU, GPU, FPGA or MYRIAD is acceptable. Sample "
                             "will look for a suitable plugin for device "
                             "specified (CPU by default)")
    parser.add_argument("-pt", "--prob_threshold", type=float, default=0.5,
                        help="Probability threshold for detections filtering"
                        "(0.5 by default)")
    return parser


def connect_mqtt():
    ### Connect to the MQTT client ###
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE_INTERVAL)

    return client


def infer_on_stream(args, client):
    """
    Initialize the inference network, stream video to network,
    and output stats and video.

    :param args: Command line arguments parsed by `build_argparser()`
    :param client: MQTT client
    :return: None
    """
    # Initialise the class
    inf_net = Network()
    # Set Probability threshold for detections
    prob_threshold = args.prob_threshold

    # Create inference network and load model
    inf_net = Network()
    inf_net.load_model(args.model, args.device, args.cpu_extension)
    
    # dimensions of input image
    dims = inf_net.get_input_shape()
    n, c, h, w = dims

    ### Handle the input stream ###
    # Get and open video capture
    cap = cv2.VideoCapture(args.input)
    cap.open(args.input)

    # print("Start inference loop")
    start_time = time.time()

    ### Loop until stream is over ###
    # TODO: Remove dummy counter
    c = 0

    tot_people = 0

    while cap.isOpened():

        ### Read from the video capture ###
        flag, frame = cap.read()
        if not flag:
            break
        key_pressed = cv2.waitKey(60)

        ### Pre-process the image as needed ###
        proc_frame = preprocessing(frame, h, w)

        ### Start asynchronous inference for specified request ###
        inf_net.exec_net(proc_frame)

        ### Wait for the result ###
        if inf_net.wait() == 0:

            ### Get the results of the inference request ###
            output = inf_net.get_output()

            ### TODO: Extract any desired stats from the results ###
            people = extract_people(output)
            people_count = people.shape[0]

            for person in people:
                frame = draw_box(frame, person)

            ### TODO: Calculate and send relevant information on ###
            ### current_count, total_count and duration to the MQTT server ###
            ### Topic "person": keys of "count" and "total" ###
            ### Topic "person/duration": key of "duration" ###
            if not client is None:
                client.publish("person", json.dumps({"count": people_count, 'total': str(c)}))
                client.publish("person/duration", json.dumps({"duration": str(c)}))
                c+=1

        ### Send the frame to the FFMPEG server ###
        try:
            sys.stdout.buffer.write(frame)  
            sys.stdout.flush()
        except BrokenPipeError:
            print ('BrokenPipeError caught', file = sys.stderr)

        ### TODO: Write an output image if `single_image_mode` ###

        # Break if escape key pressed
        if key_pressed == 27:
            break

    end_time = time.time()
    # print("End inference loop")

    # print(f'Elapsed time: {end_time-start_time:.2f}')
    sys.stderr.close()
    client.disconnect()

def main():
    """
    Load the network and parse the output.

    :return: None
    """
    # Grab command line args
    args = build_argparser().parse_args()
    # Connect to the MQTT server
    client = connect_mqtt()
    # Perform inference on the input stream
    infer_on_stream(args, client)

def test_inference():
    args = build_argparser().parse_args()

    # Create inference network and load model
    inf_net = Network()
    inf_net.load_model(args.model, args.device, args.cpu_extension)
    
    # dimensions of input image
    dims = inf_net.get_input_shape()
    n, c, h, w = dims

    # Read the input image and preprocess
    image = cv2.imread(args.input)
    input_img = preprocessing(image, h, w)

    # Start async inference
    inf_net.exec_net(input_img)
    inf_net.wait()

    output = inf_net.get_output()

    people = extract_people(output)
    print(people)

    for person in people:
        image = draw_box(image, person)

    cv2.imwrite('./test.jpg', image)

if __name__ == '__main__':
    main()
    # test_inference()