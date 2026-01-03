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

# Charakterystyka optyczna (datasheet str. 52)
# Dla GAIN=2048x, TIME=64ms, λ=360nm (UVA)
RE_BASE_UVA = 385      # counts/(μW/cm²)
FSR_BASE_UVA = 170     # μW/cm²
RE_BASE_UVB = 347      # counts/(μW/cm²) dla λ=300nm
FSR_BASE_UVB = 189     # μW/cm²

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
    """Ustawia Gain zachowując TIME=64ms (0x06)"""
    if gain_index < 0: gain_index = 0
    if gain_index > 11: gain_index = 11
    
    config_byte = (gain_index << 4) | 0x06
    
    try:
        # KLUCZOWE: Przejdź do Configuration mode
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.005)
        
        # Zmień Gain
        bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
        time.sleep(0.005)
        
        # Wróć do Measurement mode
        bus.write_byte_data(I2C_ADDR, OSR, 0x03)
        time.sleep(0.005)
    except OSError:
        pass
    return gain_index


def init_sensor():
    try:
        # 1. Software reset
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.15)
        
        # 2. Ustaw początkowy Gain (64x)
        set_gain(current_gain_index)
        
        # 3. CMD mode (MMODE=01, CCLK=00)
        bus.write_byte_data(I2C_ADDR, CREG3, 0x40)
        time.sleep(0.05)
        
        # 4. Przejdź do trybu pomiarowego
        bus.write_byte_data(I2C_ADDR, OSR, 0x03)
        time.sleep(0.05)
        
        print("✓ Czujnik AS7331 zainicjalizowany")
        return True
    except Exception as e:
        print(f"✗ Błąd init: {e}")
        return False


def read_measurement():
    """Poprawny odczyt 16-bit LSB-first"""
    try:
        # Odczyt UVA (2 bajty, LSB first)
        data_uva = bus.read_i2c_block_data(I2C_ADDR, MRES1, 2)
        uva = data_uva[0] | (data_uva[1] << 8)
        
        # Odczyt UVB
        data_uvb = bus.read_i2c_block_data(I2C_ADDR, MRES2, 2)
        uvb = data_uvb[0] | (data_uvb[1] << 8)
        
        return uva, uvb
    except OSError as e:
        print(f"Błąd I2C: {e}")
        return None, None


def smart_measure():
    """Pomiar z Auto-Gain i poprawnym przeliczeniem"""
    global current_gain_index
    
    for attempt in range(5):
        try:
            # 1. Start pomiaru
            bus.write_byte_data(I2C_ADDR, OSR, 0x83)
            time.sleep(0.08)  # 64ms pomiar + margines
            
            # 2. Odczyt
            uva_raw, uvb_raw = read_measurement()
            if uva_raw is None:
                time.sleep(0.1)
                continue
            
            # 3. Decyzja Auto-Gain (ULEPSZONA WERSJA)
            
            # A: Saturacja (lampa UV z bliska)
            if uva_raw >= 65500:
                if current_gain_index == 0:
                    break  # Już najniższy Gain
                print(f"⚠ SATURACJA! Gain {GAIN_LEVELS[current_gain_index]}x → {GAIN_LEVELS[max(0, current_gain_index-3)]}x")
                current_gain_index = max(0, current_gain_index - 3)
                set_gain(current_gain_index)
                continue
            
            # B: Za jasno (>75% zakresu)
            elif uva_raw > 49000:
                if current_gain_index > 0:
                    print(f"↓ Za jasno. Gain {GAIN_LEVELS[current_gain_index]}x → {GAIN_LEVELS[current_gain_index-1]}x")
                    current_gain_index -= 1
                    set_gain(current_gain_index)
                    continue
            
            # C: Za ciemno (<2% zakresu)
            elif uva_raw < 1300 and current_gain_index < 11:
                print(f"↑ Za ciemno. Gain {GAIN_LEVELS[current_gain_index]}x → {GAIN_LEVELS[current_gain_index+1]}x")
                current_gain_index += 1
                set_gain(current_gain_index)
                continue
            
            # D: Wynik OK (1300-49000)
            break
            
        except OSError:
            print("Błąd I2C - ponawiam...")
            time.sleep(0.1)
            continue
    
    # 4. Przeliczenie na μW/cm² (zgodnie z datasheet)
    used_gain = GAIN_LEVELS[current_gain_index]
    
    # Responsivity dla aktualnego Gain (wzór ze str. 52)
    Re_uva = RE_BASE_UVA * (2048 / used_gain)
    Re_uvb = RE_BASE_UVB * (2048 / used_gain)
    
    uva_uW = uva_raw / Re_uva if Re_uva > 0 else 0
    uvb_uW = uvb_raw / Re_uvb if Re_uvb > 0 else 0
    
    return uva_raw, uvb_raw, uva_uW, uvb_uW, used_gain


# --- PROGRAM GŁÓWNY ---
if not init_sensor():
    exit(1)

print("\n=== Rozpoczynam pomiary UV ===")
print("Gain | UVA [μW/cm²] | UVB [μW/cm²] | RAW UVA | RAW UVB")
print("-" * 65)

try:
    while True:
        uva_raw, uvb_raw, uva_uW, uvb_uW, gain = smart_measure()
        
        print(f"{gain:4}x | {uva_uW:12.3f} | {uvb_uW:12.3f} | {uva_raw:7d} | {uvb_raw:7d}")
        
        lcd_display(uva_raw, uvb_raw)
        
        time.sleep(2)

except KeyboardInterrupt:
    print("\n\n✓ Pomiary zakończone")
    bus.close()