#client bloccante: se tutte le operazioni sono sequenziali possiamo usare questo client single threaded.

#from asyncio.windows_events import NULL
import paho.mqtt.client as paho
import pandas as pd
import numpy as np
import json
import datetime
import os

from log_to_json import JsonFormatter
import logging

def setup_logger(name, log_file, level=logging.INFO):
    """To setup as many loggers as you want"""

    handler = logging.FileHandler(log_file)        

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger, handler

# first file logger
logger_client_error, handler_client_error = None, None
json_formatter = JsonFormatter(
    #keys=("message", "name")
)


# second file logger
logger_output, handler_output = None, None



class BrokerNameException(Exception):
    """Raised when the broker name is none or empty """
    def __init__(self, message="the broker name is none or empty"):
        self.message = message
        logger_client_error.error({
            'timestamp_unibo': int(datetime.datetime.now().timestamp() * 1000),
            "topic": None,
            "msg": message
        })
        super().__init__(self.message)

class PortNumberException(Exception):
    """Raised when the port number is none"""
    def __init__(self, message="the port number is none"):
        self.message = message
        logger_client_error.error({
            'timestamp_unibo': int(datetime.datetime.now().timestamp() * 1000),
            "topic": None,
            "msg": message
        })
        super().__init__(self.message)

class EmptyMessageException(Exception):
    """Raised when the message is empty"""
    def __init__(self, topic, message="the message is empty"):
        self.topic = topic
        self.message = self.topic +': '+ message
        logger_client_error.error({
            'timestamp_unibo': int(datetime.datetime.now().timestamp() * 1000),
            "topic": self.topic,
            "msg": message
        })
        super().__init__(self.message)



#initialize weights and variable

FTD_MAX_PUBLISH = 1

FTD = 1

IDC = 0
IDV = 0
threshold_i_c = 1
threshold_i_v = 2
weight = 1.01
threshold_v = 300
decimals = 4
weight_anger = 0.125
weight_happiness = 0.125
weight_fear = 0.083
weight_sadness = 0.083
weight_neutral = 0
weight_disgust = 0.042
weight_sorprise = 0.042
weights_emozioni = pd.Series([weight_anger, weight_happiness, weight_fear, weight_sadness, weight_neutral, weight_disgust, weight_sorprise])
s = 0 #speed value
Ei = 0
DCi = 0
DVi = 0
timestamp_relab = 0

flagE = False
flagD = False
flagV = False



#variable for log
anger = 0
happiness = 0
fear = 0
sadness = 0
neutral = 0
disgust = 0
surprise = 0
cd = 0 #cognitive distraction value
vd = 0 #visual distraction value

arousal = 0

anger_buffer = [0,0,0,0]
happiness_buffer = [0,0,0,0]
fear_buffer = [0,0,0,0]
sadness_buffer = [0,0,0,0]
neutral_buffer = [0,0,0,0]
disgust_buffer = [0,0,0,0]
surprise_buffer = [0,0,0,0]
speed_buffer = [0,0,0,0]

arousal_buffer = [0, 0, 0, 0] # 1 arousal max, 0 arousal min

user = ''


def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed: "+str(mid)+" "+str(granted_qos))

def on_message(client, userdata, msg):
    global FTD, IDC, IDV, weight, decimals, threshold_v, threshold_i_v, threshold_i_c, DCi, DVi, s, Ei, flagD, flagE, flagV
    global anger, happiness, fear, sadness, neutral, disgust, surprise, cd, vd, arousal
    global anger_buffer, happiness_buffer, fear_buffer, sadness_buffer, neutral_buffer, disgust_buffer, surprise_buffer, speed_buffer, arousal_buffer, timestamp_relab
    global user
    #print("topic: "+msg.topic)

    # Topic velocità
    if msg.topic == 'NP_RELAB_VD':
        s = json.loads(str(msg.payload.decode("utf-8")))
        timestamp_relab = s['VehicleDynamics']['timestamp']
        speed_buffer.pop(0)
        speed_buffer.append(s['VehicleDynamics']['speed']['x'])

        #flagV = True

    # Topic distrazione cognitiva e visuale
    elif msg.topic == 'NP_UNITO_DCDC':
        try:
            if len(str(msg.payload.decode('utf-8'))) == 0:
                raise EmptyMessageException(topic='NP_UNITO_DCDC')
            else:
                D = json.loads(str(msg.payload.decode("utf-8")))

                # Distrazione cognitiva
                cd = D['cognitive_distraction'] if D['cognitive_distraction_confidence'] != 0 else 0.0
                if D['cognitive_distraction_confidence'] == 0.0:
                    logger_client_error.warning({
                        'timestamp_unibo': int(datetime.datetime.now().timestamp() * 1000),
                        "topic": 'NP_UNITO_DCDC',
                        "msg": 'NO cognitive distraction value'
                    })
                    print('NO cognitive distraction value')

                # Distrazione visuale
                vd = D['eyesOffRoad'] if D['eyesOffRoad_confidence'] != 0.0 else 0.0
                if D['eyesOffRoad_confidence'] == 0.0:
                    logger_client_error.warning({
                            'timestamp_unibo': int(datetime.datetime.now().timestamp() * 1000),
                            "topic": 'NP_UNITO_DCDC',
                            "msg": 'NO visual distraction value'
                        })
                    print('NO visual distraction value')
        except Exception as exception:
            cd = 0.0
            vd = 0.0
            print(exception)

        # Calcolo DCi e DVi. In formula cd e vd sono bool
        speed_mean = np.mean(speed_buffer)
        DCi = round(cd * speed_mean/threshold_v * weight **(IDC - threshold_i_c), decimals)
        DVi = round(vd * speed_mean/threshold_v * weight **(IDV - threshold_i_v), decimals)

        flagD = True

    # Topic per emozioni
    elif msg.topic == 'Emotions':
        try:
            if len(str(msg.payload.decode('utf-8'))) == 0:
                e = {"predominant" : "0","neutral":"0","happiness": "0","surprise":"0","sadness": "0","anger": "0","disgust": "0","fear": "0","engagement": "0","valence": "0"}
                raise EmptyMessageException(topic='Emotions')

            if len(json.loads(str(msg.payload.decode("utf-8")))) == 0:
                e = {"predominant" : "0","neutral":"0","happiness": "0","surprise":"0","sadness": "0","anger": "0","disgust": "0","fear": "0","engagement": "0","valence": "0"}
                logger_client_error.warning({
                    'timestamp_unibo': int(datetime.datetime.now().timestamp() * 1000),
                    "topic": "Emotions",
                    "msg": 'NO emotion value'
                })
                print('NO emotion value')
            else:
                e = json.loads(str(msg.payload.decode("utf-8")))[user]
        except Exception as exception:
                print(exception)

        #flagE = True

        anger_buffer.pop(0)
        happiness_buffer.pop(0)
        fear_buffer.pop(0)
        sadness_buffer.pop(0)
        neutral_buffer.pop(0)
        disgust_buffer.pop(0)
        surprise_buffer.pop(0)

        anger_buffer.append(float(e['anger']))
        happiness_buffer.append(float(e['happiness']))
        fear_buffer.append(float(e['fear']))
        sadness_buffer.append(float(e['sadness']))
        neutral_buffer.append(float(e['neutral']))
        disgust_buffer.append(float(e['disgust']))
        surprise_buffer.append(float(e['surprise']))
        #emotions_total= Ei
    elif msg.topic == 'NP_UNIBO_FTD':
        FTD = json.loads(str(msg.payload.decode("utf-8")))['person0']['ftd']
    
    elif msg.topic == 'NP_UNIPR_AROUSAL':
        data = json.loads(str(msg.payload.decode("utf-8")))
        if "arousal" in data:
            arousal_buffer.pop(0)
            arousal_buffer.append(data['arousal'])
            arousal = np.mean(arousal_buffer)
    
    
    if flagD: #flagE and flagD and flagV:

        anger = np.mean(anger_buffer)
        happiness = np.mean(happiness_buffer)
        fear = np.mean(fear_buffer)
        sadness = np.mean(sadness_buffer)
        neutral = np.mean(neutral_buffer)
        disgust = np.mean(disgust_buffer)
        surprise = np.mean(surprise_buffer)

        emotions = pd.Series([anger, happiness, fear, sadness, neutral, disgust, surprise])
        
        Ei =  round(((emotions * weights_emozioni).sum() / weights_emozioni.sum()) * arousal, decimals)

        ftd = {user:{
            'timestamp': timestamp_relab,
            'ftd' : max(0, 1 - (DCi + DVi + Ei))
            }}
        client.publish("NP_UNIBO_FTD", json.dumps(ftd))

        msg = {
            'FTD': max(0, 1 - (DCi + DVi + Ei)),
            'cognitive distraction' : cd,
            'visual distraction': vd,
            'emotion': {
                    'anger': anger,
                    'happiness': happiness,
                    'fear': fear,
                    'sadness': sadness,
                    'neutral': neutral,
                    'disgust': disgust,
                    'surprise': surprise
            },
            'arousal': arousal,
            'speed': np.mean(speed_buffer)
        }

        logger_output.critical({
            'timestamp_relab': timestamp_relab, #ftd[user]['timestamp']
            'timestamp_unibo': datetime.datetime.now().timestamp() * 1000, #convert to milliseconds
            'FTD': max(0, 1 - (DCi + DVi + Ei)),
            'cognitive distraction' : cd,
            'visual distraction': vd,
            'emotion': {
                    'anger': anger,
                    'happiness': happiness,
                    'fear': fear,
                    'sadness': sadness,
                    'neutral': neutral,
                    'disgust': disgust,
                    'surprise': surprise
            },
            'arousal': arousal,
            'speed': np.mean(speed_buffer)
        })
        
        #flagE = False
        flagD = False
        #flagV = False
        #FTDs.append(max(0, 1 - (DCi + DVi + Ei)))
        print()
        print('FTD =', max(0, 1 - (DCi + DVi + Ei)))
        print()
    
        
        #TODO INSERT INTO DATABASE
        

def main():
    global user, logger_client_error, handler_client_error, logger_output, handler_output
    
    broker_name = None #'tools.lysis-iot.com'
    port = None #1883

    try:

        with open((os.path.dirname(os.path.abspath(__file__)) +'/config.json').replace ('\\', '/'),'r') as json_file:
            file = json.load(json_file)
            data = file['client_mqtt_config']
            print(data['broker_name'])
            broker_name = data['broker_name']
            print(data['port'])
            port = int(data['port'])
            user = file['person_config']
            print(user)
            logger_client_error, handler_client_error = setup_logger('main_logger', user+'_client.log')
            handler_client_error.setFormatter(json_formatter)
            logger_output, handler_output = setup_logger('output_logger', user+'_result.log')
            handler_output.setFormatter(json_formatter)
            

            
    except Exception as exception:
        print(exception)



    try:
        if broker_name is None:
            raise BrokerNameException
        elif port is None:
            raise PortNumberException

        client = paho.Client()
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.connect(broker_name, port) 
        client.subscribe('NP_UNITO_DCDC', qos=1)
        client.subscribe('Emotions', qos=1)
        client.subscribe('NP_RELAB_VD', qos=1)# Effective speed
        client.subscribe('NP_UNIPR_AROUSAL', qos=1) # Arousal
        client.loop_forever()
    except Exception as exception:
        print('connect to client error')
        print(exception)

    


if __name__=="__main__":
    main()