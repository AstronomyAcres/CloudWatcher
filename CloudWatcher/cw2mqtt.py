#!/usr/bin/env python3
'''
Lunatico CloudWatcher Python -to- MQTT Bridge
by Michael J. Kidd
https://github.com/linuxkidd/

- Provides decoded packet data to MQTT in JSON format.
- HomeAssistant Discovery protocol enabled.

Implements CloudWatcher protocol versions 1.0 to 1.4

For command line option help, please run with --help.
'''
import argparse,json,math,signal,time
import CloudWatcher as cf

def signal_handler(signal, frame):
    print('SIGINT received.  Terminating.')
    exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_avg(mylist: list):
    return sum(mylist)/len(mylist)

def get_stdev(mylist: list):
    avg = get_avg(mylist)
    ls=[]
    for i in mylist:
        ls.append((i - avg)**2)
    return math.sqrt( sum(ls) / (len(mylist) - 1) )

def trim_list(mylist: list):
    '''
    Trim a list of entries which fall outside of 1 stdev
    '''
    avg = get_avg(mylist)
    stdev = get_stdev(mylist)
    min = avg - stdev
    max = avg + stdev
    newlist = []

    for x in mylist:
        if x >= min or x <= max:
            newlist.append(x)
    return newlist

def mqtt_on_connect(client, userdata, flags, rc):
    mqtt_connected = True
    if debug>0:
        print("MQTT Connected with code "+str(rc))

def mqtt_send(resp: dict):
    #if mqtt_connected:
    if True:
        for key in resp.keys():
            mqttc.publish(f"{topic}/{key}", json.dumps(resp[key]), retain=retain)

def main():

    def mainLoop():
        cloud_list = []
        retain = True
        mqtt_send(cw.get_serial())
        mqtt_send(cw.get_version())
        mqtt_send(cw.get_constants())
        last_refresh = 0
        retain = args.retain
        while True:
            lists = {}
            last = {}
            last_refresh = time.time()

            for i in range(0,5):
                for x in [ 'hum_temp', 'humidity', 'values', 'rain_freq', 'pressure', 'atm_temp', 'sensor_temp', 'wind_speed', 'sky_irtemp']:
                    method = getattr(cw,'get_'+x)
                    temp = method()
                    for k in temp.keys():
                        last[k] = temp[k]
                        if k not in lists:
                            lists[k] = []
                        lists[k].append(temp[k]['value'])
            for k in lists.keys():
                tmplist = trim_list(lists[k])
                last[k]['value'] = round(get_avg(tmplist),2)
                mqtt_send({ f"{k}": last[k] })
                if k=="wind":
                    mqtt_send({ 'gust': { 'name': 'Wind Gust', 'value': max(lists[k]), 'unit': 'km/h' }})

            try:
                cloud_list.append(cw.get_adjusted_sky(last['skyir']['value'],cw.ambient_temp,cf.SkyTemperatureModel(30, 200, 6, 140, 100, 0, 0)))
            except:
                pass
            if len(cloud_list) > 21:
                excess = len(cloud_list)-21
                del cloud_list[:excess]

            if len(cloud_list):
                clouds = round(get_avg(cloud_list),1)

            mqtt_send({ 'clouds': { 'value': clouds, 'unit': 'delta C', 'epoch': math.floor(time.time()), 'cloud_list': cloud_list }})

            time.sleep(max([interval - ( time.time() - last_refresh ),0]))

    mainLoop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--broker",   default = "",                             help="MQTT Broker to publish to")
    parser.add_argument("-e", "--elevation", default = 0, type=int,                   help="Elevation above Sea Level in Meters ( for relative atmospheric pressure calculation )")
    parser.add_argument("-i", "--interval", default = 15, type=int,                   help="MQTT update interval ( default 15 second )")
    parser.add_argument("-p", "--port",     default = "/dev/ttyAMA3",                 help="Comm port descriptor, e.g /dev/ttyUSB0 or COM1")
    parser.add_argument("-r", "--retain",   action = 'store_true',                    help="MQTT Retain?")
    parser.add_argument("-t", "--topic",    default = "cloudwatcher",                 help="MQTT topic prefix")
    args = parser.parse_args()

    broker      = args.broker
    retain      = args.retain
    topic       = args.topic
    interval    = args.interval

    lastMQTT    = {}

    if broker!="":
        import paho.mqtt.client as mqtt
        mqtt_connected = False
        mqttc = mqtt.Client() #create new instance
        mqttc.on_connect = mqtt_on_connect

        try:
            mqttc.connect(args.broker, port=1883) #connect to broker
        except:
            print("MQTT Broker ( {0:s} ) Connection Failed".format(args.broker))

    cw = cf.CloudWatcher(args.port, args.elevation )

    main()
