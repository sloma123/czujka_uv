import smbus2
import time

I2C_ADDR = 0x74  # adres AS7331 (sprawdź i2cdetect)
REG_OSR = 0x00
UVA_L = 0x0A
UVA_H = 0x0B
UVB_L = 0x0C
UVB_H = 0x0D

bus = smbus2.SMBus(1)

try:
    bus.write_byte_data(I2C_ADDR, REG_OSR, 0x83)
    print("Czujnik włączony.")
except Exception as e:
    print(f"Błąd komunikacji: {e}")

time.sleep(1)

while True:
    
    try:
        #łączenie bitów
        uva = bus.read_byte_data(I2C_ADDR, UVA_L) | (bus.read_byte_data(I2C_ADDR, UVA_H) << 8)

        uvb = bus.read_byte_data(I2C_ADDR, UVB_L) | (bus.read_byte_data(I2C_ADDR, UVB_H) << 8)

        print(f"UVA: {uva}  UVB: {uvb}")
        time.sleep(1)
        
    except Exception as e:
        print(f"Błąd odczytu: {e}")
        time.sleep(1)

