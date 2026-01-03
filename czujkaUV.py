from smbus2 import SMBus
import time

from luma.core.interface.serial import spi, noop
from luma.lcd.device import st7789
from PIL import Image, ImageDraw, ImageFont




# --- LCD INIT ---
serial = spi(
    port=0,
    device=0,
    gpio_DC=25,
    gpio_RST=27,
    bus_speed_hz=40000000
)

device = st7789(
    serial,
    width=240,
    height=135,
    rotation=270,
    offset_left=40,
    offset_top=53
)

font = ImageFont.load_default()

image = Image.new("RGB", (240, 135), "black")
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, 239, 134), outline="red", width=3)
draw.text((30, 60), "LCD TEST", font=font, fill="white")
device.display(image)
time.sleep(5)

I2C_ADDR = 0x74
bus = SMBus(1)

# Rejestry
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

def lcd_display(uva, uvb):
    image = Image.new("RGB", (240, 135), "black")
    draw = ImageDraw.Draw(image)

    draw.text((10, 10),  "AS7331 UV SENSOR", font=font, fill="white")
    draw.text((10, 40),  f"UVA RAW: {uva}", font=font, fill="cyan")
    draw.text((10, 70),  f"UVB RAW: {uvb}", font=font, fill="yellow")

    device.display(image)


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
        time.sleep(0.02)
    except OSError:
        pass
    return gain_index

def init_sensor():
    try:
        bus.write_byte_data(I2C_ADDR, OSR, 0x02) # Config mode
        time.sleep(0.1)
        
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
    """Wersja odporna na błędy (iteracyjna, nie rekurencyjna)"""
    global current_gain_index
    
    # Pętla próbkowania (max 5 prób dopasowania)
    for proba in range(5):
        try:
            # 1. Start Pomiaru
            bus.write_byte_data(I2C_ADDR, OSR, 0x83)
            time.sleep(0.08) # Czekamy na wynik (64ms + margines)
            
            # 2. Odczyt
            uva = bus.read_word_data(I2C_ADDR, MRES1)
            uvb = bus.read_word_data(I2C_ADDR, MRES2)
            
            # 3. Decyzja Auto-Gain
            
            # A: OŚLEPIENIE (Lampa UV z bliska)
            if uva >= 65535:
                if current_gain_index == 0:
                    return uva, uvb, GAIN_LEVELS[0]
                
                print(f" OŚLEPIENIE! Skaczę w dół...")
                #  KLUCZOWA ZMIANA: Skok o 3 poziomy naraz!
                current_gain_index -= 3
                set_gain(current_gain_index)
                continue # Ponów pętlę

            # B: Za jasno (ale nie max)
            elif uva > 50000:
                if current_gain_index > 0:
                    current_gain_index -= 1
                    set_gain(current_gain_index)
                    continue

            # C: Za ciemno
            elif uva < 1000:
                if current_gain_index < 11:
                    current_gain_index += 1
                    set_gain(current_gain_index)
                    continue
            
            # D: Wynik OK (pomiędzy 1000 a 50000)
            return uva, uvb, GAIN_LEVELS[current_gain_index]

        except OSError:
            # KLUCZOWA ZMIANA: Łapiemy błąd wewnątrz pętli i próbujemy jeszcze raz
            print("Błąd I/O - ponawiam pomiar...")
            time.sleep(0.1)
            continue

    # Jeśli po 5 próbach nadal nie pasuje, zwróć to co masz
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
        print(f"UVA RAW: {uva_raw:6d} | UVB RAW: {uvb_raw:6d}")
        lcd_display(uva_raw, uvb_raw)

        time.sleep(30)

    except KeyboardInterrupt:
        print("\nKoniec.")
        break
    except Exception as e:
        print(f"Błąd: {e}")
        time.sleep(2)