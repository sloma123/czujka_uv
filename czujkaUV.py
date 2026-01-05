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
TIME_1MS  = 0x00  # Najkrótszy (dla potężnych lamp)
TIME_64MS = 0x06  # Standardowy (dla biurka/słońca)

# Zmienne globalne stanu
current_gain_index = 6   # Startujemy od środka
current_time_mode = TIME_64MS # Startujemy w trybie standardowym

# Mnożnik korekcyjny: Jeśli mierzymy przez 1ms zamiast 64ms,
# wpada 64x mniej światła, więc wynik końcowy trzeba pomnożyć przez 64.
TIME_MULTIPLIER = {
    TIME_1MS: 64.0,  # (64ms / 1ms)
    TIME_64MS: 1.0   # (64ms / 64ms)
}

def set_conf(gain_index, time_code):
    """Ustawia jednocześnie GAIN i CZAS"""
    # Zabezpieczenia zakresów
    if gain_index < 0: gain_index = 0
    if gain_index > 11: gain_index = 11
    
    # Składamy bajt konfiguracyjny
    # Bity 7:4 -> Gain, Bity 3:0 -> Time
    config_byte = (gain_index << 4) | time_code
    
    try:
        bus.write_byte_data(I2C_ADDR, OSR, 0x02) # Config Mode
        time.sleep(0.01) # Krótka przerwa
        bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
        time.sleep(0.01) # Czas na zastosowanie zmian
    except OSError:
        pass

def smart_measure_v5():
    """Super-inteligentny pomiar z przełączaniem biegów czasu"""
    global current_gain_index, current_time_mode
    
    uva_raw = 0
    uvb_raw = 0
    
    # Pętla prób (dajemy mu szansę znaleźć idealne ustawienia)
    for attempt in range(10):
        try:
            # 1. Start pomiaru
            bus.write_byte_data(I2C_ADDR, OSR, 0x83)
            
            # Czekamy tyle, ile wynosi czas pomiaru + mały margines
            if current_time_mode == TIME_64MS:
                time.sleep(0.08) # 64ms + zapas
            else:
                time.sleep(0.005) # 1ms + zapas (bardzo szybko!)
            
            # 2. Pobranie danych i flag
            uva_raw, uvb_raw = read_measurement()
            
            # Odczyt flagi nasycenia (ADCOF)
            status_data = bus.read_i2c_block_data(I2C_ADDR, 0x00, 2)
            status_val = status_data[1]
            is_saturated = (status_val >> 5) & 1 # Bit 5: ADCOF
            
            # --- LOGIKA DECYZYJNA ---
            
            # SYTUACJA A: Jest ZA JASNO (Lampa UV)
            if is_saturated or uva_raw > 60000:
                print(f"! ZA JASNO (G:{GAIN_LEVELS[current_gain_index]}x, T:{'64ms' if current_time_mode==0x06 else '1ms'})")
                
                # Krok 1: Zmniejszamy Gain
                if current_gain_index > 0:
                    current_gain_index = max(0, current_gain_index - 3) # Szybki zjazd
                    set_conf(current_gain_index, current_time_mode)
                    continue
                
                # Krok 2: Gain jest już 1x, a nadal jasno? Zmieniamy CZAS!
                elif current_gain_index == 0 and current_time_mode == TIME_64MS:
                    print("!!! WŁĄCZAM TRYB OCHRONNY (1ms) !!!")
                    current_time_mode = TIME_1MS
                    set_conf(current_gain_index, current_time_mode)
                    continue
                
                # Krok 3: Jesteśmy na Gain 1x i Time 1ms - to już koniec możliwości sensora
                else:
                    break # Zwracamy to co mamy (maksimum)

            # SYTUACJA B: Jest ZA CIEMNO (Biurko po wyjęciu z lampy)
            elif uva_raw < 1000:
                # Jeśli jesteśmy w trybie "szybkim" (1ms), najpierw wróćmy do "normalnego" (64ms)
                if current_time_mode == TIME_1MS:
                    current_time_mode = TIME_64MS
                    set_conf(current_gain_index, current_time_mode)
                    continue
                
                # Jeśli jesteśmy w normalnym czasie, zwiększamy Gain
                if current_gain_index < 11:
                    current_gain_index += 1
                    set_conf(current_gain_index, current_time_mode)
                    continue
            
            # SYTUACJA C: Jest IDEALNIE (1000 < RAW < 60000)
            break
            
        except OSError:
            continue

    # --- PRZELICZANIE WYNIKÓW ---
    if uva_raw is None: uva_raw = 0; uvb_raw = 0
    
    used_gain = GAIN_LEVELS[current_gain_index]
    
    # Mnożnik czasu: jeśli mierzyliśmy krótko (1ms), musimy wynik pomnożyć x64,
    # żeby pasował do kalibracji (która jest dla 64ms)
    time_factor = TIME_MULTIPLIER[current_time_mode]
    
    # Standardowa czułość dla Gain (przy 64ms)
    Re_uva_base = RE_BASE_UVA * (used_gain / 2048.0)
    Re_uvb_base = RE_BASE_UVB * (used_gain / 2048.0)
    
    # Matematyka: (RAW / Czułość) * KorektaCzasu
    if Re_uva_base > 0:
        uva_uW = (uva_raw / Re_uva_base) * time_factor
    else: uva_uW = 0
        
    if Re_uvb_base > 0:
        uvb_uW = (uvb_raw / Re_uvb_base) * time_factor
    else: uvb_uW = 0

    return uva_raw, uvb_raw, uva_uW, uvb_uW, used_gain, current_time_mode

# def set_gain(gain_index):
#     """Ustawia Gain bezpiecznie, ignorując chwilowe błędy I2C"""
#     if gain_index < 0: gain_index = 0
#     if gain_index > 11: gain_index = 11
    
#     # Budujemy bajt: Gain na bitach 7:4, Time=64ms (0110) na bitach 3:0
#     config_byte = (gain_index << 4) | 0x06
    
#     try:
#         # 1. Tryb konfiguracji
#         bus.write_byte_data(I2C_ADDR, OSR, 0x02)
#         time.sleep(0.02) # Pauza dla elektroniki
        
#         # 2. Wysłanie nowego Gain
#         bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
#         time.sleep(0.02) # Pauza na przeładowanie
#     except OSError:
#         # Jeśli nie uda się zmienić Gainu (zakłócenia), trudno.
#         # Spróbujemy przy następnym obiegu pętli. Nie crashujemy programu.
#         pass
        
#     return gain_index


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
        current_time_mode = TIME_64MS
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


# def smart_measure():
#     """Inteligentny pomiar z obsługą błędów i przeliczaniem jednostek"""
#     global current_gain_index
    
#     # Zmienne na wyniki (domyślne zera, żeby nie było błędu "variable not assigned")
#     uva_raw = 0
#     uvb_raw = 0
    
#     # 1. PĘTLA PRÓB (Do 5 podejść, żeby uzyskać dobry wynik)
#     for attempt in range(15):
#         try:
#             # a) Start pomiaru
#             bus.write_byte_data(I2C_ADDR, OSR, 0x83)
#             time.sleep(0.1) 
            
#             # b) Pobranie danych
#             uva_raw, uvb_raw = read_measurement()

#             # Diagnostyka STATUSU (szukamy ukrytych błędów nasycenia)
#             try:
#                 # Czytamy 2 bajty z adresu 0x00 (OSR + STATUS)
#                 status_data = bus.read_i2c_block_data(I2C_ADDR, 0x00, 2)
                
#                 osr_val = status_data[0]    # To już znasz
#                 status_val = status_data[1] # TO JEST REJESTR STATUSU!

#                 # Analiza bitów rejestru STATUS (wg dokumentacji str. 60, Fig 55)
#                 adc_overflow = (status_val >> 5) & 1   # Bit 5: ADCOF
#                 mres_overflow = (status_val >> 6) & 1  # Bit 6: MRESOF
#                 out_overflow = (status_val >> 7) & 1   # Bit 7: OUTCONVOF

#                 if adc_overflow:
#                     print(f"!!! ALARM: Przepełnienie analogowe (ADCOF)! Sensor oślepiony! Gain: {GAIN_LEVELS[current_gain_index]}x")
                
#                 if mres_overflow:
#                     print(f"!!! ALARM: Przepełnienie cyfrowe (MRESOF)! Wynik ucięty!")

#             except Exception as e:
#                 print(f"Błąd odczytu statusu: {e}")
            
#             # c) Jeśli błąd odczytu (None) - czekamy i próbujemy jeszcze raz
#             if uva_raw is None:
#                 time.sleep(0.1)
#                 continue
            
#             # --- LOGIKA AUTO-GAIN ---
#             print(f"[Pomiar] RAW={uva_raw}, Gain={GAIN_LEVELS[current_gain_index]}x")
            
#             # SCENARIUSZ A: SATURACJA (Za mocno!)
#             # Jeśli włożysz do lampy na wysokim Gainie, tu wejdzie.
#             if uva_raw >= 65000:
#                 print("!!! SATURACJA !!! Zjazd w dół...")
#                 if current_gain_index == 0:
#                     # Jesteśmy na 1x i nadal za jasno - zwracamy max
#                     break 
                
#                 # Szybki zjazd o 4 poziomy (np. z 2048x na 128x w jednym kroku)
#                 current_gain_index = max(0, current_gain_index - 4)
#                 set_gain(current_gain_index)
#                 continue # Mierz od nowa
            
#             # SCENARIUSZ B: BARDZO JASNO (>40000)
#             elif uva_raw > 40000:
#                 if current_gain_index > 0:
#                     current_gain_index -= 1
#                     set_gain(current_gain_index)
#                     continue
            
#             # SCENARIUSZ C: ZA CIEMNO (<1000)
#             # Jeśli wyjmiesz na biurko, tu wejdzie.
#             elif uva_raw < 1000:
#                 if current_gain_index < 11:
#                     current_gain_index += 1
#                     set_gain(current_gain_index)
#                     continue
            
#             # SCENARIUSZ D: JEST IDEALNIE (1000 - 40000)
#             break
            
#         except OSError:
#             time.sleep(0.1)
#             continue
            
#     # 2. PRZELICZANIE FIZYCZNE (uW/cm2)
#     # Zabezpieczenie: Jeśli po 5 próbach uva_raw to None, ustawiamy 0
#     if uva_raw is None: 
#         uva_raw = 0
#         uvb_raw = 0
        
#     used_gain = GAIN_LEVELS[current_gain_index]
    
#     # Obliczamy aktualną czułość (maleje wraz ze spadkiem Gainu)
#     # Dodano .0 aby wymusić dzielenie dziesiętne
#     Re_uva = RE_BASE_UVA * (used_gain / 2048.0)
#     Re_uvb = RE_BASE_UVB * (used_gain / 2048.0)
    
#     # Dzielimy RAW przez Czułość
#     if Re_uva > 0.00001:
#         uva_uW = uva_raw / Re_uva
#     else:
#         uva_uW = 0.0
        
#     if Re_uvb > 0.00001:
#         uvb_uW = uvb_raw / Re_uvb
#     else:
#         uvb_uW = 0.0
    
#     # Zwracamy komplet danych dla pętli głównej i LCD
#     return uva_raw, uvb_raw, uva_uW, uvb_uW, used_gain



# --- PROGRAM GŁÓWNY ---
if not init_sensor():
    exit(1)

print("\n=== Rozpoczynam pomiary UV ===")
print("Gain | UVA [μW/cm²] | UVB [μW/cm²] | RAW UVA | RAW UVB")
print("-" * 65)

try:
    while True:
        uva_raw, uvb_raw, uva_uW, uvb_uW, gain, time_mode = smart_measure_v5()
        
        # if uva_uW < 0:
        #     print(f"SATURACJA! RAW: {uva_raw}")
        # else:
        #     print(f"{gain:4}x | UVA: {uva_uW:.2f} uW | RAW: {uva_raw}")

        time_str = "1ms" if time_mode == 0x00 else "64ms"

        print(f"G:{gain:<4}x | T:{time_str} | UVA: {uva_uW:.2f} uW | RAW: {uva_raw}")
        
        
        lcd_display(uva_raw, uvb_raw, gain)
        
        time.sleep(2)

except KeyboardInterrupt:
    print("\n\n Pomiary zakończone")
    bus.close()