from smbus2 import SMBus
import time

I2C_ADDR = 0x74
bus = SMBus(1)

# --- Rejestry ---
OSR   = 0x00
CREG1 = 0x06
CREG3 = 0x08

MRES1 = 0x02  # UVA
MRES2 = 0x03  # UVB

# --- Parametry detekcji zmiany ---
DELTA_THRESHOLD = 50   # minimalna zmiana RAW uznana za istotną

def init_sensor():
    try:
        # 1. Wyjście z Power Down → CONFIGURATION
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.01)

        # 2. Ustaw GAIN=64x (0101), TIME=64 ms (0110)
        # 0101_0110 = 0x56
        bus.write_byte_data(I2C_ADDR, CREG1, 0x56)

        # 3. CMD mode
        bus.write_byte_data(I2C_ADDR, CREG3, 0x01)

        print(" Czujnik AS7331 poprawnie zainicjalizowany")

        return True

    except Exception as e:
        print(" Błąd inicjalizacji czujnika!")
        print(e)
        return False


def read_measurement():
    # Start pojedynczego pomiaru
    bus.write_byte_data(I2C_ADDR, OSR, 0x83)  # MEAS + SS=1
    time.sleep(0.08)  # czas konwersji (64 ms + zapas)

    # Odczyt UVA
    uva_l = bus.read_byte_data(I2C_ADDR, MRES1)
    uva_h = bus.read_byte_data(I2C_ADDR, MRES1)
    uva = uva_l | (uva_h << 8)

    # Odczyt UVB
    uvb_l = bus.read_byte_data(I2C_ADDR, MRES2)
    uvb_h = bus.read_byte_data(I2C_ADDR, MRES2)
    uvb = uvb_l | (uvb_h << 8)

    return uva, uvb


# --- PROGRAM GŁÓWNY ---
if not init_sensor():
    exit(1)

prev_uva = None
prev_uvb = None

print(" Rozpoczęcie pomiarów (RAW)...")
print("Zmieniaj oświetlenie (zasłoń czujnik / zapal lampę / słońce)\n")

while True:
    try:
        uva, uvb = read_measurement()

        print(f"UVA RAW: {uva:6d} | UVB RAW: {uvb:6d}", end="")

        if prev_uva is not None:
            duva = abs(uva - prev_uva)
            duvb = abs(uvb - prev_uvb)

            if duva > DELTA_THRESHOLD or duvb > DELTA_THRESHOLD:
                print("  ZMIANA OŚWIETLENIA")
            else:
                print()

        else:
            print()

        prev_uva = uva
        prev_uvb = uvb

        time.sleep(1)

    except Exception as e:
        print("\n Błąd podczas pomiaru!")
        print(e)
        time.sleep(1)
