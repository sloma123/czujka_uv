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


# =================================================================
# TYLKO TE FUNKCJE ZOSTAŁY ZMIENIONE (Wersja Pancerna v3)
# =================================================================

def set_gain(gain_index):
    """Ustawia Gain bezpiecznie, ignorując chwilowe błędy I2C"""
    if gain_index < 0: gain_index = 0
    if gain_index > 11: gain_index = 11
    
    # Budujemy bajt: Gain na bitach 7:4, Time=64ms (0110) na bitach 3:0
    config_byte = (gain_index << 4) | 0x06
    
    try:
        # 1. Tryb konfiguracji
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.02) # Pauza dla elektroniki
        
        # 2. Wysłanie nowego Gain
        bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
        time.sleep(0.02) # Pauza na przeładowanie
    except OSError:
        # Jeśli nie uda się zmienić Gainu (zakłócenia), trudno.
        # Spróbujemy przy następnym obiegu pętli. Nie crashujemy programu.
        pass
        
    return gain_index


def init_sensor():
    """Inicjalizacja od ZERA (Gain 1x) dla bezpieczeństwa"""
    global current_gain_index
    try:
        # Reset programowy (Config mode)
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.15)
        
        # ZMIANA: Startujemy od Gain 1x (Index 0).
        # To zapobiega 'szokowi' jeśli uruchomisz program wewnątrz lampy.
        current_gain_index = 0
        set_gain(current_gain_index)
        
        # Ustawienie trybu CMD (Measurement on demand)
        bus.write_byte_data(I2C_ADDR, CREG3, 0x40)
        time.sleep(0.05)
        
        print("Czujnik AS7331 zainicjalizowany (Start: Gain 1x)")
        return True
    except Exception as e:
        print(f"Błąd init (sprawdź kable): {e}")
        return False


def read_measurement():
    """Odczyt danych z zabezpieczeniem przed zerwaniem kabla"""
    try:
        # Czytamy blokami (bezpieczniej niż bajt po bajcie)
        # Odczyt UVA
        data_uva = bus.read_i2c_block_data(I2C_ADDR, MRES1, 2)
        uva = data_uva[0] | (data_uva[1] << 8)
        
        # Odczyt UVB
        data_uvb = bus.read_i2c_block_data(I2C_ADDR, MRES2, 2)
        uvb = data_uvb[0] | (data_uvb[1] << 8)
        
        return uva, uvb
    except OSError:
        # Jeśli wystąpi błąd I2C, zwracamy None.
        # Funkcja nadrzędna będzie wiedziała, że pomiar jest nieważny.
        return None, None


def smart_measure():
    """Inteligentny pomiar z obsługą błędów i przeliczaniem jednostek"""
    global current_gain_index
    
    # Zmienne na wyniki (domyślne zera, żeby nie było błędu "variable not assigned")
    uva_raw = 0
    uvb_raw = 0
    
    # 1. PĘTLA PRÓB (Do 5 podejść, żeby uzyskać dobry wynik)
    for attempt in range(15):
        try:
            # a) Start pomiaru
            bus.write_byte_data(I2C_ADDR, OSR, 0x83)
            time.sleep(0.08) # Czekamy 80ms
            
            # b) Pobranie danych
            uva_raw, uvb_raw = read_measurement()
            
            # c) Jeśli błąd odczytu (None) - czekamy i próbujemy jeszcze raz
            if uva_raw is None:
                time.sleep(0.1)
                continue
            
            # --- LOGIKA AUTO-GAIN ---
            print(f"[Pomiar] RAW={uva_raw}, Gain={GAIN_LEVELS[current_gain_index]}x")
            
            # SCENARIUSZ A: SATURACJA (Za mocno!)
            # Jeśli włożysz do lampy na wysokim Gainie, tu wejdzie.
            if uva_raw >= 65000:
                print("!!! SATURACJA !!! Zjazd w dół...")
                if current_gain_index == 0:
                    # Jesteśmy na 1x i nadal za jasno - zwracamy max
                    break 
                
                # Szybki zjazd o 4 poziomy (np. z 2048x na 128x w jednym kroku)
                current_gain_index = max(0, current_gain_index - 4)
                set_gain(current_gain_index)
                continue # Mierz od nowa
            
            # SCENARIUSZ B: BARDZO JASNO (>40000)
            elif uva_raw > 40000:
                if current_gain_index > 0:
                    current_gain_index -= 1
                    set_gain(current_gain_index)
                    continue
            
            # SCENARIUSZ C: ZA CIEMNO (<1000)
            # Jeśli wyjmiesz na biurko, tu wejdzie.
            elif uva_raw < 1000:
                if current_gain_index < 11:
                    current_gain_index += 1
                    set_gain(current_gain_index)
                    continue
            
            # SCENARIUSZ D: JEST IDEALNIE (1000 - 40000)
            break
            
        except OSError:
            time.sleep(0.1)
            continue
            
    # 2. PRZELICZANIE FIZYCZNE (uW/cm2)
    # Zabezpieczenie: Jeśli po 5 próbach uva_raw to None, ustawiamy 0
    if uva_raw is None: 
        uva_raw = 0
        uvb_raw = 0
        
    used_gain = GAIN_LEVELS[current_gain_index]
    
    # Obliczamy aktualną czułość (maleje wraz ze spadkiem Gainu)
    # Dodano .0 aby wymusić dzielenie dziesiętne
    Re_uva = RE_BASE_UVA * (used_gain / 2048.0)
    Re_uvb = RE_BASE_UVB * (used_gain / 2048.0)
    
    # Dzielimy RAW przez Czułość
    if Re_uva > 0.00001:
        uva_uW = uva_raw / Re_uva
    else:
        uva_uW = 0.0
        
    if Re_uvb > 0.00001:
        uvb_uW = uvb_raw / Re_uvb
    else:
        uvb_uW = 0.0
    
    # Zwracamy komplet danych dla pętli głównej i LCD
    return uva_raw, uvb_raw, uva_uW, uvb_uW, used_gain

# =================================================================



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