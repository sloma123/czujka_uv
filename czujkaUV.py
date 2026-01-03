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

# --- Ustawienia Auto-Gain ---
# Lista dostępnych wzmocnień (Gain) w AS7331 (kroki od 0 do 11)
# Wartość rejestru to (INDEX << 4) | TIME. Przyjmijmy TIME = 64ms (kod 0110 = 0x06)
# Gain: 1x, 2x, 4x ... 2048x
GAIN_LEVELS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
current_gain_index = 6  # Startujemy od środka (Gain 64x, index 6)

def set_gain(gain_index):
    """Ustawia nowy Gain w czujniku zachowując czas 64ms"""
    # Zabezpieczenie przed wyjściem poza listę (0-11)
    if gain_index < 0: gain_index = 0
    if gain_index > 11: gain_index = 11
    
    # Budowa bajtu konfiguracji:
    # Bity 7:4 to Gain (index), Bity 3:0 to Time (0x06 = 64ms)
    config_byte = (gain_index << 4) | 0x06
    
    try:
        bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
        return gain_index
    except OSError:
        return gain_index

def init_sensor():
    try:
        bus.write_byte_data(I2C_ADDR, OSR, 0x02) # Config mode
        time.sleep(0.01)
        
        # Ustawiamy startowy Gain (64x)
        set_gain(current_gain_index)
        
        # CMD mode (0x40 = MMODE:01, CCLK:00)
        bus.write_byte_data(I2C_ADDR, CREG3, 0x40)
        print("Czujnik zainicjalizowany (Tryb Auto-Gain)")
        return True
    except Exception as e:
        print(f"Błąd init: {e}")
        return False

def smart_measure():
    global current_gain_index
    
    # 1. Wykonaj pomiar na obecnych ustawieniach
    bus.write_byte_data(I2C_ADDR, OSR, 0x83) # Start
    time.sleep(0.08) # Czekamy 80ms (dla Time 64ms)
    
    # Odczyt UVA (jako referencja do sterowania)
    uva = bus.read_word_data(I2C_ADDR, MRES1)
    uvb = bus.read_word_data(I2C_ADDR, MRES2)
    
    # 2. Logika Auto-Gain (Sprawdzamy czy zmienić czułość)
    
    # SYTUACJA A: Za jasno! (Nasycenie > 60000)
    if uva > 60000 and current_gain_index > 0:
        print(f"Za jasno ({uva})! Zmniejszam Gain...")
        current_gain_index -= 1 # Zmniejszamy o krok
        set_gain(current_gain_index)
        return smart_measure() # Rekurencja: Mierz jeszcze raz z nowym ustawieniem!
        
    # SYTUACJA B: Za ciemno! (Wynik < 500, a mamy zapas wzmocnienia)
    elif uva < 500 and current_gain_index < 11:
        # Małe zabezpieczenie, żeby nie skakał przy totalnej ciemności
        # Zwiększamy tylko jeśli nie jesteśmy już na maxa
        print(f"Za ciemno ({uva})! Zwiększam Gain...")
        current_gain_index += 1 # Zwiększamy o krok
        set_gain(current_gain_index)
        return smart_measure() # Mierz jeszcze raz
        
    # 3. Jeśli jest OK, zwracamy wyniki i aktualny mnożnik Gain
    return uva, uvb, GAIN_LEVELS[current_gain_index]

# --- PROGRAM GŁÓWNY ---
if not init_sensor():
    exit(1)

print("Rozpoczynam pomiary inteligentne...")

while True:
    try:
        # Pobieramy wynik, ale też info jaki Gain został użyty!
        uva_raw, uvb_raw, used_gain = smart_measure()
        
        # --- MATEMATYKA (Skalowanie wyniku) ---
        # Wiemy, że dla Gain 64x faktor to 0.083
        # Jeśli Gain jest inny, musimy przeliczyć faktor.
        # Wzór: factor = base_factor * (base_gain / current_gain)
        
        base_factor = 0.083
        current_factor = base_factor * (64 / used_gain)
        
        uva_uW = uva_raw * current_factor
        uvb_uW = uvb_raw * current_factor
        
        print(f"Gain: {used_gain:4}x | UVA: {uva_uW:7.2f} uW/cm2 | UVB: {uvb_uW:7.2f} uW/cm2 (RAW: {uva_raw})")
        
        time.sleep(1)

    except KeyboardInterrupt:
        print("\nKoniec.")
        break
    except Exception as e:
        print(f"Błąd: {e}")