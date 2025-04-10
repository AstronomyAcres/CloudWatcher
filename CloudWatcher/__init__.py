'''
Packet processing functions for cw2mqtt
See: https://github.com/linuxkidd/cw2mqtt
'''

__version__ = "0.9"
__author__ = "Michael J. Kidd"

from dataclasses import dataclass
import math, serial, time
from typing import Dict, Optional


@dataclass
class CWAnalogCache:
    zener_voltage: float
    ldr_voltage: float
    rain_sensor_temp: float
    last_refresh: int

@dataclass
class CWConstants:
    AbsZero: float
    AmbPullUpResistance: float
    AmbResAt25: float
    AmbBeta: float
    LDRMaxResistance: float
    LDRPullUpResistance: float
    RainBeta: float
    RainPullUpResistance: float
    RainResAt25: float
    SQReference: float

@dataclass
class Auto_Shutdown:
    delay: int
    switch: int
    heat: int

@dataclass
class SkyTemperatureModel:
    K1: float
    K2: float
    K3: float
    K4: float
    K5: float
    K6: float
    K7: float

default_sky_temperature_model = SkyTemperatureModel(100,0,0,0,0,0,0)

class CloudWatcherException(Exception):
    pass

class CloudWatcher:
    ambient_temp: float
    analog_cache: CWAnalogCache
    auto_shutdown: Auto_Shutdown
    constants: CWConstants
    errors: int
    HASL: float
    serial: serial.Serial
    has8: bool

    def __init__(self, port: str, HASL: float):
        self.errors = 0
        self.has8 = False
        self.HASL = HASL
        self.ambient_temp = -999
        self.serial = serial.Serial(
            port = port,
            baudrate = 9600,
            parity = serial.PARITY_NONE,
            bytesize = serial.EIGHTBITS,
            xonxoff = False,
            timeout = 2,
        )
        self.constants = CWConstants( 
            AbsZero = 273.15,
            AmbPullUpResistance = 9.9,
            AmbResAt25 = 10.0,
            AmbBeta = 3811.0,
            LDRMaxResistance = 0,
            LDRPullUpResistance = 56,
            RainBeta = 3450.0,
            RainPullUpResistance = 1.0,
            RainResAt25 = 1.0,
            SQReference = 22,
        )
        self.analog_cache = CWAnalogCache(
            zener_voltage = 3.0,
            ldr_voltage = 0,
            rain_sensor_temp = 0,
            last_refresh = 0,
        )
        self.auto_shutdown = Auto_Shutdown( 
            delay = 0,
            switch = 0,
            heat = 0.
        )


    def open(self) -> None:
        try:
            self.serial.open()
        except Exception:
            raise CloudWatcherException("Fatal: cannot open port")
        self.errors = 0

    def close(self) -> None:
        self.serial.close()

    def read_block(self) -> list:
        result = {}
        max_wait = 5
        start = time.time()
        clean = False
        while abs(time.time() - start) < max_wait:
            if self.serial.in_waiting >= 15:
                block = self.serial.read(min([self.serial.in_waiting,15]))
                if block[0:2] == b"\x21\x11":
                    if self.serial.in_waiting > 0:
                        junk = self.serial.read(self.serial.in_waiting)
                    clean = True
                    break
                elif block[0] == 33:
                    try:
                        res = self.process_block(block)
                    except:
                        pass
                    else:                        
                        try:
                            result.update(res)
                        except:
                            try:
                                for i in res:
                                    result.update(i)
                            except:
                                pass
            time.sleep(0.05)

        if not clean:
            self.errors += 1
        else:
            self.errors = 0
            return result

    def process_block(self, block: bytes) -> Dict[ str, float ]:
        assert block[0] == 33
        ret = str(block[1:3],'ascii').strip()
        func = f"process_{ret}"
        try:
            method = getattr(self,func)
        except:
            ret = str(block[1:2],'ascii').strip()
            func = f"process_{ret}"
            try:
                method = getattr(self,func)
            except:
                return { f"unknown_{ret}": f"{block}"}

        return method(block)

    def process_ntc(self, x: int,pullUp: float,at25: float,beta: float) -> float:
        x = min([max([x,1]),1022])
        r = pullUp / ( ( 1023 / x ) - 1 )
        r = math.log( r / at25 )
        return round(1 / ( ( r / beta ) + ( 1 / ( self.constants.AbsZero + 25 ) ) ) - self.constants.AbsZero, 1)

    def process_1(self, packet: bytes):
        # Sky IR Tempreature
        x = int(str(packet[2:], "ascii").strip())
        return { 'skyir': { 'name': 'Sky IR Temp', 'raw': x, 'value': round(x/100,2), 'unit': 'degC' } }

    def process_2(self, packet: bytes):
        # IR Ambient Temperature
        x = int(str(packet[2:], "ascii").strip())
        return { 'ambir': { 'raw': x, 'name': 'Ambient IR Temp', 'value': round(x/100,2), 'unit': 'degC' } }

    def process_3(self, packet: bytes):
        # NTC Ambient Temperature
        x = int(str(packet[2:], "ascii").strip())
        y = self.process_ntc(
                x, 
                self.constants.AmbPullUpResistance, 
                self.constants.AmbResAt25, 
                self.constants.AmbBeta )
        if y < -40:
            return

        return { 'temp': { 'name': 'NTC Ambient Temp', 'raw': x, 
            'value': y, 'unit': 'degC' } }

    def process_4(self, packet: bytes):
        # LDR Ambient Light
        ## When the NEW light sensor is present (output !8), the old output is synthesized but should be ignored
        if not has8:
            x = int(str(packet[2:], "ascii").strip())
            y = min([max([x,1]),1022])
            return { 'light': { 'raw': x, 'value': round(self.constants.LDRPullUpResistance / ( ( 1023 / y ) - 1 ),1), 'unit': 'kOhm' } }
        return

    def process_5(self, packet: bytes):
        # NTC Temperature of Rain Sensor
        x = int(str(packet[2:], "ascii").strip())
        return { 'temp': { 'raw': x, 'name': 'Rain Sensor NTC Temperature', 'value': 
            self.process_ntc(
                x,
                self.constants.RainPullUpResistance,
                self.constants.RainResAt25, 
                self.constants.RainBeta ), 'unit': 'degC'} }

    def process_6(self, packet: bytes):
        # Zener Voltage reference
        x = int(str(packet[2:], "ascii").strip())
        return { 'zvolt': { 'raw': x, 'name': 'Zener Voltage', 'value': round(1023 * self.analog_cache.zener_voltage / x,3), 'unit': 'V' } }

    def process_8(self, packet: bytes, temp: float = -999):
        # NEW Light Sensor 
        self.has8 = True
        ## When the NEW light sensor is present, the old output is synthesized but should be ignored
        x = int(str(packet[2:], "ascii").strip())
        mpsas = self.constants.SQReference - ( 2.5 * math.log( 250000/x, 10 ))
        if temp > -999:
            mpsas = ( mpsas - 0.042 ) + ( 0.00212 * temp )
        return { 'mpsas': { 'raw': x, 'name': 'SQM', 'value': round(mpsas,1), 'unit': 'mpsas' } }

    def process_h(self, packet: bytes):
        # Humidity
        x = int(str(packet[2:], "ascii").strip())
        if x == 100:
            # sensor error
            return
        y = min([ max([ 0, x ]), 100 ])
        return { 'hum': { 'raw': x, 'name': 'Humidity', 'value': round( y * 125 / 100 - 6, 1 ), 'unit': '%' } }

    def process_hh(self, packet: bytes):
        # High Res Humidity
        x = int(str(packet[3:], "ascii").strip())
        return { 'hum': { 'raw': x, 'name': 'Humidity', 'value': round( x * 125 / 65536 - 6, 1 ), 'unit': '%' } }

    def process_K(self, packet: bytes):
        # Serial Number
        return { 'serial': { 'name': 'Serial Number', 'value': str(packet[2:14], "ascii").strip() } }

    def process_M(self, packet: bytes):
        x = packet[2:]
        self.analog_cache.zener_voltage     = ( 256 * x[0] + x[1] ) / 100
        self.constants.LDRMaxResistance     = ( 256 * x[2] + x[3] )
        self.constants.LDRPullUpResistance  = ( 256 * x[4] + x[5] ) / 10
        self.constants.RainBeta             = ( 256 * x[6] + x[7] )
        self.constants.RainResAt25          = ( 256 * x[8] + x[9] ) / 10
        self.constants.RainPullUpResistance = ( 256 * x[10] + x[11] ) / 10
        
        return [ 
            { "zener_voltage": { 'name': 'Zener Constant', 'value': self.analog_cache.zener_voltage }},
            { "LDRMaxResistance": { 'name': 'LDR Max Resistance', 'value': self.constants.LDRMaxResistance }},
            { "LDRPullUpResistance": { 'name': 'LDR Pull Up Resistance', 'value': self.constants.LDRPullUpResistance }},
            { "RainBeta": { 'name': 'Rain Beta', 'value': self.constants.RainBeta }},
            { "RainResAt25": { 'name': 'Rain Resistance at 25C', 'value': self.constants.RainResAt25 }},
            { "RainPullUpResistance": { 'name': 'Rain Pull Up Resistance', 'value': self.constants.RainPullUpResistance }},
        ]

    def process_m(self, packet: bytes):
        x = packet[2:]
        self.auto_shutdown.delay  = ( 256 * x[0] + x[1] ) * 1.1
        self.auto_shutdown.switch = x[2]
        self.auto_shutdown.heat   = x[3]
        if x[3] > 98:
            self.auto_shutdown.heat = 10
        return [
            { "auto_shutdown_dealy": { "name": "Auto Shutdown Delay", "value": self.auto_shutdown.delay, "unit": "seconds" }},
            { "auto_shutdown_switch": { "name": "Auto Shutdown Switch State", "value": self.auto_shutdown.switch }},
            { "auto_shutodwn_heater": { "name": "Auto Shutdown Rain Heat Level", "value": self.auto_shutdown.heat, "unit": "%" }}
        ]

    def process_N(self, packet: bytes):
        # Name
        return { "name": { 'name': 'Device Name', 'value': str(packet[2:],"ascii").strip() } }

    def process_p(self, packet: bytes ):
        # Atmospheric Pressure, Pascals
        results = []
        x = int(str(packet[2:],"ascii").strip())
        press = x / 16
        results.append({ 'abspress': { 'name': 'Absolute Pressure', "raw": x, "value": round(press,1), "unit": "hPa" }})
        if self.HASL > -999 and self.ambient_temp > -999:
            press *= math.pow( 1 - ( 0.0065 * self.HASL / ( self.ambient_temp + 0.0065 * self.HASL + self.constants.AbsZero )), -5.275 )
            results.append({ 'relpress': { 'name': 'Relative Pressure', "raw": x, "value": round(press,1), "unit": "hPa" }})
        return results

    def process_Q(self, packet: bytes):
        # PWM Duty Cycle
        x = int(str(packet[2:],"ascii").strip())
        return { 'pwm': { 'raw': x, 'name': 'PWM Level', 'value': round( x * 100 / 1023, 1 ), "unit": "%" } }

    def process_q(self, packet: bytes):
        # Temperature of Atmospheric Pressure Sensor
        x = int(str(packet[2:],"ascii").strip())
        return { 'atmtemp': { 'raw': x, 'name': 'Temperature at Atm Press Sensor', 'value': round( x / 100, 1 ), 'unit': 'degC' } }

    def process_R(self, packet: bytes):
        # Rain Frequence Counter
        x = int(str(packet[2:],"ascii").strip())
        return { 'rain_freq': { 'value': x, 'name': 'Rain Sensor Frequency', 'unit': 'Hz' } }

    def process_t(self, packet: bytes):
        # Temperature of Relative Humidity sensor
        x = int(str(packet[2:],"ascii").strip())
        if x == 100:
            return
        y = ( x * 1.7572 ) - 46.85
        self.ambient_temp = y
        return { 'hum_temp': { 'raw': x, 'name': 'Temperature at Humidity Sensor', 'value': round( y, 1), 'unit': 'degC' } }

    def process_th(self, packet: bytes):
        # Temperature of Relative Humidity sensor
        x = int(str(packet[3:],"ascii").strip())
        y = ( x * 175.72 / 65536 ) - 46.85
        self.ambient_temp = y
        return { 'hum_temp': { 'raw': x, 'name': 'Temperature at Humidity Sensor', 'value': round( y, 1 ), 'unit': 'degC' } }

    def process_V(self, packet: bytes):
        # Firmware Version Number
        x = int(str(packet[2:14],"ascii").strip())/100
        return { 'version': { 'name': 'FW Version', 'value': x } }

    def process_v(self, packet: bytes):
        # is Wind Sensor Present
        x = int(str(packet[2:],"ascii").strip())
        return { "windpresent": { 'name': 'Wind Sensor Present?', 'value': x } }

    def process_w(self, packet: bytes, sensor: int = 1):
        # Wind Speed
        # sensor: 
        #   0 = grey model ( discontinued )
        #   1 = black model
        x = int(str(packet[2:],"ascii").strip())
        if sensor==0:
            return { "wind": x }
        elif sensor==1:
            if x == 0:
                wind = 0
            else:
                wind = x * 0.84 + 3
            return { "wind": { 'raw': x, 'name': 'Wind Speed', 'value': round(wind,1), 'unit': 'km/h' } }

    def process_X(self, packet: bytes):
        return { "switch": { 'name': 'Switch State', 'value': "open" } }

    def process_Y(self, packet: bytes):
        return { "switch": { 'name': 'Switch State', 'value': "closed" } }

    def get_atm_temp(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"q!")
        return self.read_block()

    def get_constants(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"M!")
        return self.read_block()

    def get_humidity(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"h!")
        return self.read_block()

    def get_hum_temp(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"t!")
        return self.read_block()

    def get_name(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"A!")
        return self.read_block()

    def get_pressure(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"p!")
        return self.read_block()

    def set_pwm(self,pwm) -> None:
        packet = "P"+("0000"+str(max(min(1023,pwm),0)))[-4:]+"!"
        self.reset_serial_buffers()
        self.serial.write(str.encode(packet,"ascii"))

    def get_pwm(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"Q!")
        return self.read_block()

    def get_rain_freq(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"E!")
        return self.read_block()

    def get_sensor_temp(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"T!")
        return self.read_block()

    def get_serial(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"K!")
        return self.read_block()

    def set_shutdown(self, delay: int, state: int, heat_power: int) -> None:
        '''
        auto_shutdown.delay  = ( 256 * x[0] + x[1] ) * 1.1
        auto_shutdown.switch = x[2]
        auto_shutdown.heat   = x[3]
        '''
        packet = [ "l", 0, 0, 0, 0, " ", " ", " ", " ", " ", " ", " ", " ", "!" ]

        d = math.floor(delay / 1.1)
        if d >= 256:
            packet[1] = math.floor(d/256)
        
        packet[2] = d - ( packet[1] * 256 )
        packet[3] = max(min(2,state),0)
        packet[4] = max(min(99,heat_power),0)

        self.reset_serial_buffers()
        self.serial.write(packet)

    def get_shutdown(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"m!")
        return self.read_block()
    
    def get_sky_irtemp(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"S!")
        return self.read_block()

    def get_switch(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"F!")
        return self.read_block()
    
    def set_switch_close(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"H!")
        return self.read_block()

    def set_switch_open(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"G!")
        return self.read_block()

    def get_values(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"C!")
        return self.read_block()

    def get_version(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"B!")
        return self.read_block()

    def get_wind_sensor(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"v!")
        return self.read_block()

    def get_wind_speed(self) -> None:
        self.reset_serial_buffers()
        self.serial.write(b"V!")
        return self.read_block()

    def reset_serial_buffers(self) -> None:
        self.serial.write(b"z!")
        self.read_block()

    def get_adjusted_sky(self, Ts: float, Ta: float, model: SkyTemperatureModel = default_sky_temperature_model) -> float:
        if abs((model.K2 / 10 - Ta)) < 1:
            T67 = (
                math.copysign(1, model.K6)
                * math.copysign(1, Ta - model.K2 / 10)
                * abs((model.K2 / 10 - Ta))
            )
        else:
            T67 = (
                model.K6
                / 10
                * math.copysign(1, Ta - model.K2 / 10)
                * (math.log(abs((model.K2 / 10 - Ta))) / math.log(10) + model.K7 / 100)
            )

        Td = (
            (model.K1 / 100) * (Ta - model.K2 / 10)
            + (model.K3 / 100) * pow(math.exp(Ta * model.K4 / 1000), model.K5 / 100)
            + T67
        )

        return round(Ts-Td, 2)
