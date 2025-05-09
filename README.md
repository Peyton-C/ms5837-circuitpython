# ms5837-circuitpython
An exprimental CircuitPython module to interface with MS5837-30BA and MS5837-02BA waterproof pressure and temperature sensors. 

## Testing
This library has been tested on:
- ESP32-S3 running CircuitPython 9.2.7 & 9.2.1 with a Blue Robotics Bar02 Sensor
- Raspberry PI 4B running Adafruit Blinka with a Blue Robotics Bar02 Sensor

# Dependencies
This driver depends on:
- [Adafruit CircuitPython](https://github.com/adafruit/circuitpython)
- [Adafruit Circuitpython BusDevice](https://github.com/adafruit/Adafruit_CircuitPython_BusDevice)

# Important Information
- This library will not be rececing any major updates or changes, I do not have access to the hardware anymore.
- Certain functionality of the BlueRobotics Python library are missing or broken.
- The BlueRobotics sensors lack pull-up resistors, which are required for i2C.
