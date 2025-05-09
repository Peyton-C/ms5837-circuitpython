import board
import time
import busio
import ms5837

i2c = busio.I2C(board.SCL, board.SDA)
sensor = ms5837.MS5837(i2c, model=0) 

while True:
    print(sensor.read())
    time.sleep(1)
