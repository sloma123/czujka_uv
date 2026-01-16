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

# --- KONFIGURACJA CZASÓW ---
# AS7331 Time codes (bits 3:0 in CREG1)
# --- TIME kroki: 1,2,4,8,16,32,64 ms (kody 0..6) ---
TIME_STEPS = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06]

def time_code_to_ms(code: int) -> int:
    # dla 0..6: 1<<code daje 1,2,4,...,64 ms
    return 1 << (code & 0x0F)

BASE_TIME_CODE = 0x06  # 64 ms jest bazą Twojej "kalibracji"
BASE_TIME_MS = time_code_to_ms(BASE_TIME_CODE)  # 64


# Zmienne globalne stanu
current_gain_index = 6   # Startujemy od środka
current_time_mode = TIME_STEPS.index(0x06)

def gain_index_to_reg_code(gain_index: int) -> int:
    # AS7331: 0 => 2048x ... 11 => 1x  (odwrotnie niż intuicja) :contentReference[oaicite:3]{index=3}
    return 11 - gain_index

def set_conf(gain_index, time_code):
    """Ustawia jednocześnie GAIN i TIME (właściwe kodowanie GAIN)"""
    global current_gain_index, current_time_mode

    gain_index = max(0, min(11, gain_index))
    time_code   = time_code & 0x0F

    gain_code = gain_index_to_reg_code(gain_index)
    config_byte = ((gain_code & 0x0F) << 4) | time_code

    # Configuration state + PD off: 0x02 (DOS=010, PD=0, SS=0) :contentReference[oaicite:4]{index=4}
    bus.write_byte_data(I2C_ADDR, OSR, 0x02)
    time.sleep(0.005)
    bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
    time.sleep(0.005)

def init_sensor():
    """Inicjalizacja od ZERA (Gain 1x) dla bezpieczeństwa"""
    global current_gain_index, current_time_mode
    try:
        # Reset programowy (Config mode)
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.15)
        
        # ZMIANA: Startujemy od Gain 1x (Index 0).
        # To zapobiega 'szokowi' jeśli uruchomisz program wewnątrz lampy.
        current_gain_index = 0
        current_time_mode = TIME_STEPS.index(0x06)
        set_conf(current_gain_index, current_time_mode)
        # set_gain(current_gain_index)
        
        # Ustawienie trybu CMD (Measurement on demand)
        bus.write_byte_data(I2C_ADDR, CREG3, 0x40)
        time.sleep(0.05)
        
        print("Czujnik AS7331 zainicjalizowany (Start: Gain 1x)")
        return True
    except Exception as e:
        print(f"Błąd init (sprawdź kable): {e}")
        return False

STATUS_ADDR = 0x00  # czytamy 2 bajty: OSR + STATUS

def read_status_byte():
    # zwraca 2. bajt (STATUS)
    data = bus.read_i2c_block_data(I2C_ADDR, STATUS_ADDR, 2)
    return data[1]

def measure_once(time_code: int):
    """
    Startuje pomiar w CMD i zwraca (uva, uvb, status).
    Minimalizujemy I2C podczas konwersji: najpierw śpimy ~TCONV, potem sprawdzamy status.
    """
    bus.write_byte_data(I2C_ADDR, OSR, 0x83)  # measurement + start

    t_ms = time_code_to_ms(time_code)
    time.sleep((t_ms + 2) / 1000.0)  # TCONV + mały margines

    # jeśli jeszcze nie gotowe, dopolluj krótko (zwykle to już chwila)
    deadline = time.monotonic() + 0.05
    status = read_status_byte()
    notready = (status >> 2) & 1
    while notready and time.monotonic() < deadline:
        time.sleep(0.001)
        status = read_status_byte()
        notready = (status >> 2) & 1

    uva, uvb = read_measurement()
    return uva, uvb, status


def read_measurement():
    """Czytamy UVA+UVB jednym odczytem: 4 bajty od 0x02 (MRES1+MRES2), LSB first """
    try:
        data = bus.read_i2c_block_data(I2C_ADDR, MRES1, 4)
        uva = data[0] | (data[1] << 8)
        uvb = data[2] | (data[3] << 8)
        return uva, uvb
    except OSError:
        return None, None

def smart_measure_v5():
    """Super-inteligentny pomiar z przełączaniem biegów czasu"""
    global current_gain_index, current_time_mode
    
    uva_raw = 0
    uvb_raw = 0

    RAW_TARGET_MIN = 2000
    RAW_TARGET_MAX = 50000
    RAW_HARD_LOW   = 300      # "bardzo ciemno" -> reaguj od razu
    RAW_HARD_HIGH  = 65000    # "bardzo jasno"  -> reaguj od razu

    bright_streak = 0
    dark_streak = 0

    uva_raw = 0
    uvb_raw = 0
    status_val = 0

    
    # Pętla prób (dajemy mu szansę znaleźć idealne ustawienia)
    for attempt in range(10):
        try:
            time_code = TIME_STEPS[current_time_step_idx]
            uva_raw, uvb_raw, status_val = measure_once(time_code)

            if uva_raw is None:
                continue

            # bierzemy "najgorszy" kanał jako referencję do auto-range
            raw_ref = max(uva_raw, uvb_raw)

            adcof = (status_val >> 5) & 1  # nasycenie ADC

            too_bright_hard = adcof or (raw_ref >= RAW_HARD_HIGH)
            too_dark_hard   = (raw_ref <= RAW_HARD_LOW)

            too_bright_soft = (raw_ref > RAW_TARGET_MAX)
            too_dark_soft   = (raw_ref < RAW_TARGET_MIN)

            # --- ZA JASNO ---
            if too_bright_hard or (too_bright_soft and bright_streak >= 1):
                bright_streak += 1
                dark_streak = 0

                # 1) zjedź gainem (szybciej przy hard)
                if current_gain_index > 0:
                    step = 2 if too_bright_hard else 1
                    current_gain_index = max(0, current_gain_index - step)
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                # 2) gain już 1x -> skróć czas
                if current_time_step_idx > 0:
                    current_time_step_idx -= 1
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                # już nie ma gdzie uciekać
                break

            # --- ZA CIEMNO ---
            if too_dark_hard or (too_dark_soft and dark_streak >= 1):
                dark_streak += 1
                bright_streak = 0

                # 1) wydłuż czas do 64ms
                if current_time_step_idx < (len(TIME_STEPS) - 1):
                    current_time_step_idx += 1
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                # 2) czas max -> podbij gain
                if current_gain_index < 11:
                    current_gain_index += 1
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                break

            # --- W OKNIE (stabilnie) ---
            bright_streak = 0
            dark_streak = 0
            break

        except OSError:
            continue

    # --- przeliczanie na µW/cm² z korektą TIME ---
    used_gain = GAIN_LEVELS[current_gain_index]
    used_time_code = TIME_STEPS[current_time_step_idx]
    used_time_ms = time_code_to_ms(used_time_code)

    # korekta do "bazy 64ms": jeśli mierzysz krócej, wynik * (64/used_time)
    time_factor = BASE_TIME_MS / float(used_time_ms)

    Re_uva_base = RE_BASE_UVA * (used_gain / 2048.0)
    Re_uvb_base = RE_BASE_UVB * (used_gain / 2048.0)

    uva_uW = (uva_raw / Re_uva_base) * time_factor if Re_uva_base > 0 else 0.0
    uvb_uW = (uvb_raw / Re_uvb_base) * time_factor if Re_uvb_base > 0 else 0.0

    return uva_raw, uvb_raw, uva_uW, uvb_uW, used_gain, used_time_ms

# --- PROGRAM GŁÓWNY ---
if not init_sensor():
    exit(1)

print("\n=== Rozpoczynam pomiary UV ===")
print("Gain | UVA [μW/cm²] | UVB [μW/cm²] | RAW UVA | RAW UVB")
print("-" * 65)

try:
    while True:
        uva_raw, uvb_raw, uva_uW, uvb_uW, gain, time_ms = smart_measure_v5()

        print(f"G:{gain:<4}x | T:{time_ms:>3}ms | UVA: {uva_uW:.2f} uW | RAW: {uva_raw}")
        
        
        lcd_display(uva_raw, uvb_raw, gain)
        
        time.sleep(2)

except KeyboardInterrupt:
    print("\n\n Pomiary zakończone")
    bus.close()