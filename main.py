import requests
import logging
import sys
import time
import json
import yaml  # reading the config
import os
import RPi.GPIO as GPIO 
from w1thermsensor import W1ThermSensor
from RPLCD.i2c import CharLCD   # LCD
import socket                   # IP
import fcntl                    # IP
import struct                   # IP
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from yaml.loader import SafeLoader

logging.basicConfig(filename='./bricks.log', filemode='w+', level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

APIKEY = "tbd"
TYPE = "RaspberryPi"
CHIPID = "tbd"
CHARMAP = "A00"     # LCD
ADDRESS = int("0x27", 16)

# Open the file and load the file
config = {}  # will hold the config from bricks.yaml and cache local relay states
with open('./bricks.yaml') as f:
    config = yaml.load(f, Loader=SafeLoader)
    logging.info("read config")
    
    APIKEY = config["apikey"]
    CHIPID = config["device_id"]
    TYPE = config["meta"]["platform"]
    
    logging.info(f"apikey={APIKEY}, device_id={CHIPID}, platform={TYPE}")
    

GPIO.setwarnings(False)

try:
    lcd = CharLCD(i2c_expander='PCF8574', address=ADDRESS, port=1, cols=20, rows=4, dotsize=8, charmap=CHARMAP,
                  auto_linebreaks=True, backlight_enabled=True)
except:
    logging.info("Error LCD, can not be initialized")
pass

def initRelays():
    logging.info("setting GPIO to GPIO.BOARD")
    GPIO.setmode(GPIO.BOARD) 
    
    for i in range(0, len(config["relays"])):
        
        config["relays"][i]["state"] = 0
        gpio_number = config["relays"][i]["gpio"]
        logging.info(f"initializing relay {i+1} (GPIO {gpio_number})...")
        GPIO.setup(gpio_number, GPIO.OUT)
        GPIO.output(gpio_number, 0)
        
        
def setRelay(number=0, state=0):
    # number relay number in config
    # state: 0=off, 1=on
    config["relays"][number]["state"] = state
    gpio_number = config["relays"][number]["gpio"]
    logging.info(f"setting relay {number+1} (GPIO {gpio_number}) to {state}...")
    corrected_state = -1
    invert = config["relays"][number]["invert"]
    if invert:
        if state == 0:
            corrected_state = 1
        else:
            corrected_state = 0
        
        logging.info(f"inverted {state} to {corrected_state}")
    
    GPIO.output(gpio_number, corrected_state)
        
        
def getRelay(number=0):
    return config["relays"][number]["state"]  # TODO: get from GPIO?


def set_ip():
    if get_ip('wlan0') != 'Not connected':
        ip = get_ip('wlan0')
    elif get_ip('eth0') != 'Not connected':
        ip = get_ip('eth0')
    elif get_ip('enxb827eb488a6e') != 'Not connected':
        ip = get_ip('enxb827eb488a6e')
    else:
        ip = 'Not connected'
    pass
    return ip


def get_ip(interface):
    ip_addr = 'Not connected'
    so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ip_addr = socket.inet_ntoa(
            fcntl.ioctl(so.fileno(), 0x8915, struct.pack('256s', bytes(interface.encode())[:15]))[20:24])
    except Exception as e:
        logging.warning('no ip found')
        logging.warning(e)
        return ip_addr
    finally:
        pass
    return ip_addr


def request():

    logging.info("starting request")
    url = 'https://brewbricks.com/api/iot/v1'

    # craft request
    post_fields = {
        "type": TYPE,
        "brand": "oss",
        "version": "0.1",
        "chipid": CHIPID,
        "apikey": APIKEY
    }  # baseline
    # add relay states to request
    for i in range(0, len(config["relays"])):
        key = f"a_bool_epower_{i}"
        value = getRelay(i)
        post_fields[key] = value
        logging.info(f"set relay {i} to {value}")
    
    # add temperatures to request
    for i, sensor_id in enumerate(config["temperature_sensors"]):
        key = f"s_number_temp_{i}"
        
        sensor = W1ThermSensor(sensor_id=sensor_id)
        temperature = sensor.get_temperature()
        
        value = str(temperature)
        post_fields[key] = value
        logging.info(f"set tempsensor {i} with id {sensor_id} to {temperature}")

    response = requests.get(url, params=post_fields)
    
    try:
        if response.text == "internal.":
            logging.info("please activate RaspberryPi under https://bricks.bierbot.com > Bricks")
            # time.sleep(nextRequestMs / 1000)
        else:
            jsonResponse = json.loads(response.text)

            nextRequestMs = jsonResponse["next_request_ms"]

            # set relays based on response
            for i in range(0, len(config["relays"])):
                relay_key = f"epower_{i}_state"
                if relay_key in jsonResponse:
                    # relay_key is e.g. "epower_0_state"
                    new_relay_state = int(jsonResponse[relay_key])
                    logging.info(f"received new target state {new_relay_state} for {relay_key}")
                    setRelay(i, new_relay_state)
                else:
                    logging.warning(f"relay key {relay_key} for relay idx={i} was expected but "
                                    f"not in response. This is normal before activation.")
                    setRelay(i, 0)

            logging.info(f"sleeping for {nextRequestMs}ms")
            time.sleep(nextRequestMs / 250)  # ursprünglich 1000
    except:
        logging.warning("failed processing request: " + response.text)
        time.sleep(60)


def run():
    # Display First Test
    line1 = 'Beer Bot Bricks LCD '
    line2 = '--------------------'
    line3 = set_ip()
    line4 = '--------------------'

    lcd._set_cursor_mode('hide')
    lcd.cursor_pos = (0, 0)
    lcd.write_string(line1.ljust(20))
    lcd.cursor_pos = (1, 0)
    lcd.write_string(line2.ljust(20))
    lcd.cursor_pos = (2, 0)
    lcd.write_string(line3.ljust(20))
    lcd.cursor_pos = (3, 0)
    lcd.write_string(line4.ljust(20))

    initRelays()

    while True:
        request()


if __name__ == '__main__':
    logging.info("BierBot Bricks RaspberryPi client started.")
    run()
