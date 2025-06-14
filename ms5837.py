from board import *
import sys
from adafruit_bus_device.i2c_device import I2CDevice
    
import time

try: # This was in the library i was using for refrence so I'm including it.
    import typing  # pylint: disable=unused-import
    from typing_extensions import Literal
    from busio import I2C
except ImportError:
    pass


# Models
MODEL_02BA = 0
MODEL_30BA = 1

# Oversampling options
OSR_256  = 0
OSR_512  = 1
OSR_1024 = 2
OSR_2048 = 3
OSR_4096 = 4
OSR_8192 = 5

# kg/m^3 convenience
DENSITY_FRESHWATER = 997
DENSITY_SALTWATER = 1029

# Conversion factors (from native unit, mbar)
UNITS_Pa     = 100.0
UNITS_hPa    = 1.0
UNITS_kPa    = 0.1
UNITS_mbar   = 1.0
UNITS_bar    = 0.001
UNITS_atm    = 0.000986923
UNITS_Torr   = 0.750062
UNITS_psi    = 0.014503773773022


class MS5837():
    # Registers
    _MS5837_ADDR             = 0x76  
    _MS5837_RESET            = 0x1E
    _MS5837_ADC_READ         = 0x00
    _MS5837_PROM_READ        = 0xA0
    _MS5837_CONVERT_D1_256   = 0x40
    _MS5837_CONVERT_D2_256   = 0x50

    # stolen from actual ms5837 library, this does some error checking I think
    def _crc4(self, n_prom):
        n_rem = 0
        
        n_prom[0] = ((n_prom[0]) & 0x0FFF)
        n_prom.append(0)
        
        for i in range(16):
            if i%2 == 1:
                n_rem ^= ((n_prom[i>>1]) & 0x00FF)
            else:
                n_rem ^= (n_prom[i>>1] >> 8)
                
            for n_bit in range(8,0,-1):
                if n_rem & 0x8000:
                    n_rem = (n_rem << 1) ^ 0x3000
                else:
                    n_rem = (n_rem << 1)

        n_rem = ((n_rem >> 12) & 0x000F)

        self.n_prom = n_prom
        self.n_rem = n_rem

        return n_rem ^ 0x00

    def _read_word(self, register): # Circuitpython's bus device doesn't have an equivilant to smbus2's read_word_data
        result = bytearray(2)
        self._i2c_device.write_then_readinto(bytes({register}), result)
        return int.from_bytes(result, 'big')

    def __init__(self, i2c_bus, model=MODEL_30BA, FD=DENSITY_FRESHWATER):
        self._i2c_device = I2CDevice(i2c_bus, self._MS5837_ADDR)
        self._model = model
        
        self._fluidDensity = FD
        self._pressure = 0
        self._temperature = 0
        self._D1 = 0
        self._D2 = 0
        self._C = []
        self._FD = FD

        with self._i2c_device:
            self._i2c_device.write(bytes([self._MS5837_RESET])) # Reset sensor

            time.sleep(0.1) # Wait for reset to complete
            
            for i in range(7): # Grabs the calibration data
                register = self._MS5837_PROM_READ + 2 * i # Everything bellow probaly could be 1 line but that would be terrible to read.
                c = self._read_word(register)
                self._C.append(c)
            
            crc = (self._C[0] & 0xF000) >> 12
            if crc != self._crc4(self._C): # The first value gets changed for some reason that I don't fully understand, don't panic if you see it be some other value
                sys.exit("PROM read error, CRC Failed")

    def _calculate(self):
        OFFi = 0
        SENSi = 0
        Ti = 0

        dT = self._D2-self._C[5]*256
        if self._model == MODEL_02BA:
            SENS = self._C[1]*65536+(self._C[3]*dT)/128
            OFF = self._C[2]*131072+(self._C[4]*dT)/64
            self._pressure = (self._D1*SENS/(2097152)-OFF)/(32768)
        else:
            SENS = self._C[1]*32768+(C[3]*dT)/256
            OFF = self._C[2]*65536+(C[4]*dT)/128
            self._pressure = (self._D1*SENS/(2097152)-OFF)/(8192)
            
        self._temperature = 2000+dT*self._C[6]/8388608

        # Second order compensation
        if self._model == MODEL_02BA:
            if (self._temperature/100) < 20: # Low temp
                Ti = (11*dT*dT)/(34359738368)
                OFFi = (31*(self._temperature-2000)*(self._temperature-2000))/8
                SENSi = (63*(self._temperature-2000)*(self._temperature-2000))/32
                    
        else:
            if (self._temperature/100) < 20: # Low temp
                Ti = (3*dT*dT)/(8589934592)
                OFFi = (3*(self._temperature-2000)*(self._temperature-2000))/2
                SENSi = (5*(self._temperature-2000)*(self._temperature-2000))/8
                if (self._temperature/100) < -15: # Very low temp
                    OFFi = OFFi+7*(self._temperature+1500)*(self._temperature+1500)
                    SENSi = SENSi+4*(self._temperature+1500)*(self._temperature+1500)
            elif (self._temperature/100) >= 20: # High temp
                    Ti = 2*(dT*dT)/(137438953472)
                    OFFi = (1*(self._temperature-2000)*(self._temperature-2000))/16
                    SENSi = 0
            
        OFF2 = OFF-OFFi
        SENS2 = SENS-SENSi
            
        if self._model == MODEL_02BA:
            self._temperature = (self._temperature-Ti)
            self._pressure = (((self._D1*SENS2)/2097152-OFF2)/32768)/100.0
        else:
            self._temperature = (self._temperature-Ti)
            self._pressure = (((self._D1*SENS2)/2097152-OFF2)/8192)/10.0

    def read(self, P_UNIT=UNITS_psi, oversampling=OSR_8192): # We need to read both temperature and pressure because it gave weird results when I tried to seperate them
        if oversampling < OSR_256 or oversampling > OSR_8192:
            sys.exit("Invalid oversampling option!")
        
        with self._i2c_device:
            register = self._MS5837_CONVERT_D1_256 + 2*oversampling
            self._i2c_device.write(bytes([register]))

            # Maximum conversion time increases linearly with oversampling
            # max time (seconds) ~= 2.2e-6(x) where x = OSR = (2^8, 2^9, ..., 2^13)
            # We use 2.5e-6 for some overhead
            time.sleep(2.5e-6 * 2**(8+oversampling))

            d = bytearray(3)
            self._i2c_device.write(bytes([self._MS5837_ADC_READ])) # Without this it would read into MS5837_CONVERT_D1_256 and not MS5837_ADC_READ
            self._i2c_device.readinto(d)

            self._D1 = d[0] << 16 | d[1] << 8 | d[2]

            register = self._MS5837_CONVERT_D2_256 + 2*oversampling
            self._i2c_device.write(bytes([register]))
            time.sleep(2.5e-6 * 2**(8+oversampling)) # Same applies as above

            d = bytearray(3)
            self._i2c_device.write(bytes([self._MS5837_ADC_READ])) # Same applies as above
            self._i2c_device.readinto(d)

            self._D2 = d[0] << 16 | d[1] << 8 | d[2]
        
        self._calculate() # Calculate compensated pressure and temperature using raw ADC values and internal calibration
        temp = self._temperature / 100
        pressure = self._pressure * P_UNIT
        return temp, pressure

    def read_temp(self, P_UNIT=UNITS_psi, oversampling=OSR_8192): 
        results = self.read(P_UNIT, oversampling)
        return self._temperature

    def read_pressure(self, P_UNIT=UNITS_psi, oversampling=OSR_8192):
        temperature, pressure = self.read(P_UNIT, oversampling)
        return pressure

    def depth(self): # Depth relative to MSL pressure in given fluid density
        temperature, pressure = self.read(UNITS_Pa)
        return (pressure-101300)/(self._FD*9.80665)

    def altitude(self): # Altitude relative to MSL pressure
        temperature, pressure = self.read(UNITS_mbar)
        return (1-pow((pressure/1013.25),.190284))*145366.45*.3048      