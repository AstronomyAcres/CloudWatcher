# CloudWatcher
Python code for sending Lunatico CloudWatcher data over MQTT

## Syntax Help:
```
usage: cw2mqtt.py [-h] [-b BROKER] [-e ELEVATION] [-i INTERVAL] [-p PORT] [-r] [-t TOPIC]

options:
  -h, --help            show this help message and exit
  -b BROKER, --broker BROKER
                        MQTT Broker to publish to
  -e ELEVATION, --elevation ELEVATION
                        Elevation above Sea Level in Meters ( for relative atmospheric pressure calculation )
  -i INTERVAL, --interval INTERVAL
                        MQTT update interval ( default 15 second )
  -p PORT, --port PORT  Comm port descriptor, e.g /dev/ttyUSB0 or COM1
  -r, --retain          MQTT Retain?
  -t TOPIC, --topic TOPIC
                        MQTT topic prefix
```

## Installation:
```
git clone https://github.com/AstronomyAcres/CloudWatcher.git
cd CloudWatcher
make install
```

## Configuration:
1. Edit `/etc/default/cloudwatcher` with your favorite editor
2. Set the `OPTS=` parameters, excluding the Port ( `-p` ) option
3. Reload the SystemD daemon:
```
systemctl daemon-reload
```
4. Enable and start the SystemD unit file:
```
systemctl enable --now cloudwatcher@ttyUSB0
```
  - Note: Adjust the `ttyUSB0` port to match the port on which your CloudWatcher is connected
5. Check `systemctl` for any reported errors:
```
systemctl status cloudwatcher@ttyUSB0
```
  - Note: Again, use the correct port, in place of `ttyUSB0`


