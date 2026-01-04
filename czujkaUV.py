from smbus2 import SMBus
import time

#WAVESHARE LCD (OFICJALNY DRIVER) =====
from lib import LCD_1inch14
from PIL import Image, ImageDraw, ImageFont


# ===== LCD INIT (DOKŁADNIE JAK W DEMO) =====
disp = LCD_1inch14.LCD_1inch14()
disp.Init()
disp.clear()
disp.bl_DutyCycle(50)

font = ImageFont.load_default()

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
RE_BASE_UVB = 347      # counts/(μW/cm²) dla λ=300nm

# --- Ustawienia Auto-Gain ---
# Lista dostępnych wzmocnień (Gain) w AS7331 (kroki od 0 do 11)
# Wartość rejestru to (INDEX << 4) | TIME. Przyjmijmy TIME = 64ms (kod 0110 = 0x06)
# Gain: 1x, 2x, 4x ... 2048x
GAIN_LEVELS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
current_gain_index = 6  # Startujemy od środka (Gain 64x, index 6)

# ===== LCD DRAW =====
def lcd_display(uva, uvb, gain):
    image = Image.new("RGB", (disp.width, disp.height), "BLACK")
    draw = ImageDraw.Draw(image)

    draw.text((10, 10), "AS7331 UV SENSOR", font=font, fill="WHITE")
    draw.text((10, 45), f"UVA RAW: {uva}", font=font, fill="CYAN")
    draw.text((10, 70), f"UVB RAW: {uvb}", font=font, fill="YELLOW")
    draw.text((10, 100), f"GAIN: {gain}x", font=font, fill="GREEN")

    disp.ShowImage(image)


def set_gain(gain_index):
    """Ustawia Gain zachowując TIME=64ms (0x06)"""
    if gain_index < 0: gain_index = 0
    if gain_index > 11: gain_index = 11
    
    config_byte = (gain_index << 4) | 0x06
    
    try:
        # Configuration mode
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.02) 
        
        # Zmień Gain
        bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
        time.sleep(0.02)
        
        # Wróć do Measurement mode (0x03 nie jest konieczne jesli uzywamy OSR 0x83 pozniej, ale OK)
        # Tu w Twoim kodzie było OSR 0x03 - to tryb Measurement ciągły, 
        # ale my używamy CMD (jednorazowy). Zostawiam jak jest, żeby nie mieszać w logice init.
        
    except OSError:
        pass
    return gain_index


def init_sensor():
    global current_gain_index
    try:
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.15)
        
        current_gain_index = 6 
        set_gain(current_gain_index)
        
        # CMD mode
        bus.write_byte_data(I2C_ADDR, CREG3, 0x40)
        time.sleep(0.05)
        
        print("Czujnik AS7331 zainicjalizowany")
        return True
    except Exception as e:
        print(f"Błąd init: {e}")
        return False


def read_measurement():
    try:
        data_uva = bus.read_i2c_block_data(I2C_ADDR, MRES1, 2)
        uva = data_uva[0] | (data_uva[1] << 8)
        
        data_uvb = bus.read_i2c_block_data(I2C_ADDR, MRES2, 2)
        uvb = data_uvb[0] | (data_uvb[1] << 8)
        
        return uva, uvb
    except OSError:
        return None, None


def smart_measure():
    global current_gain_index
    
    for attempt in range(5):
        try:
            bus.write_byte_data(I2C_ADDR, OSR, 0x83) # Start
            time.sleep(0.08) 
            
            uva_raw, uvb_raw = read_measurement()
            if uva_raw is None:
                time.sleep(0.1)
                continue
            
            # --- Logika Auto-Gain ---
            print(f"[Pomiar] RAW={uva_raw}, Gain={GAIN_LEVELS[current_gain_index]}x")
            
            # A: Saturacja
            if uva_raw >= 65500:
                if current_gain_index == 0:
                    return 65535, uvb_raw, -1.0, -1.0, 1
                
                print(f"SATURACJA! Zmniejszam Gain (skok -3)")
                current_gain_index = max(0, current_gain_index - 3)
                set_gain(current_gain_index)
                continue
            
            # B: Bardzo jasno
            elif uva_raw > 39000:
                if current_gain_index > 0:
                    current_gain_index -= 1
                    set_gain(current_gain_index)
                    continue
            
            # C: Jasno
            elif uva_raw > 19600:
                if current_gain_index > 0:
                    current_gain_index -= 1
                    set_gain(current_gain_index)
                    continue
            
            # D: Za ciemno
            elif uva_raw < 1300 and current_gain_index < 11:
                current_gain_index += 1
                set_gain(current_gain_index)
                continue
            
            # E: OK
            break
            
        except OSError:
            time.sleep(0.1)
            continue
    
    # --- PRZELICZANIE (Poprawione .0) ---
    used_gain = GAIN_LEVELS[current_gain_index]
    
    #POPRAWKA: Dodano .0 aby wymusić dzielenie zmiennoprzecinkowe
    Re_uva = RE_BASE_UVA * (used_gain / 2048.0)
    Re_uvb = RE_BASE_UVB * (used_gain / 2048.0)
    
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
        
        if uva_uW < 0:
            print(f"SATURACJA! RAW: {uva_raw}")
        else:
            print(f"{gain:4}x | UVA: {uva_uW:.2f} uW | RAW: {uva_raw}")
        
        
        lcd_display(uva_raw, uvb_raw, gain)
        
        time.sleep(2)

except KeyboardInterrupt:
    print("\n\n Pomiary zakończone")
    bus.close()