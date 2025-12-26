from smbus2 import SMBus
import time

# =============================
# I2C i adres czujnika
# =============================
I2C_ADDR = 0x74
bus = SMBus(1)

# =============================
# Rejestry AS7331 (POPRAWIONE WG DOKUMENTACJI)
# =============================

# Rejestry sterujące
REG_OSR   = 0x00  # Rejestr: Włącznik / Stan
REG_CREG1 = 0x06  # Rejestr: Konfiguracja GAIN (Wzmocnienie)
REG_CREG3 = 0x08  # Rejestr: Konfiguracja TIME

# Wyniki pomiarów (16-bit) - POPRAWIONE ADRESY
# Wcześniej miałaś 0x10 - to była temperatura!
UVA_L = 0x0A
UVA_H = 0x0B
UVB_L = 0x0C
UVB_H = 0x0D

# =============================
# Progi ostrzegawcze (µW/cm²)
# =============================
UVA_WARN = 2000
UVA_ALARM = 4000
UVB_WARN = 200
UVB_ALARM = 400

# =============================
# Funkcje pomocnicze
# =============================

def init_sensor():
    """Włącza czujnik i ustawia małą czułość (żeby nie było 65535)"""
    print("Inicjalizacja czujnika...")
    try:
        # 1. Włączamy czujnik (Bit 7: MSS = 1 -> Power ON & Measurement)
        bus.write_byte_data(I2C_ADDR, REG_OSR, 0x83) # 0x83 = 10000011

        # 2. Ustawiamy GAIN na minimum (1x), żeby uniknąć nasycenia w pokoju
        # Rejestr 0x06: Wartość 0x00 to Gain 1x.
        bus.write_byte_data(I2C_ADDR, REG_CREG1, 0x00) 
        
        print("-> Czujnik włączony, Gain ustawiony na 1x.")
    except Exception as e:
        print(f"BŁĄD INICJALIZACJI: {e}")

def read_u16(low_reg, high_reg):
    try:
        # Czytanie blokowe jest bezpieczniejsze (dwa bajty na raz)
        block = bus.read_i2c_block_data(I2C_ADDR, low_reg, 2)
        return block[0] | (block[1] << 8)
    except Exception as e:
        print(f"Błąd I2C: {e}")
        return 0

# =============================
# Przeliczenie RAW → µW/cm²
# =============================

def raw_to_uwcm2(raw):
    """
    Uproszczony przelicznik dla GAIN=1x.
    Dla Gain 1x czułość jest najmniejsza, więc mnożnik jest największy.
    """
    # Te wartości trzeba skalibrować, ale dla testu:
    # Przy Gain 1x (najniższym) surowe wyniki są małe, więc mnożymy je mocniej
    SCALE_FACTOR = 0.25 
    return raw * SCALE_FACTOR

# =============================
# Główna pętla programu
# =============================

print("AS7331 UV Monitor – start\n")

# WAŻNE: Musimy obudzić czujnik przed pętlą!
init_sensor()
time.sleep(1) # Czekamy na stabilizację

while True:
    # Odczyt surowych danych
    raw_uva = read_u16(UVA_L, UVA_H)
    raw_uvb = read_u16(UVB_L, UVB_H)

    # Przeliczanie
    uva_calc = raw_to_uwcm2(raw_uva)
    uvb_calc = raw_to_uwcm2(raw_uvb)

    # Logika statusu
    status = "OK"
    if uva_calc > UVA_ALARM or uvb_calc > UVB_ALARM:
        status = "ALARM !!!"
    elif uva_calc > UVA_WARN or uvb_calc > UVB_WARN:
        status = "OSTRZEŻENIE"

    # Wyświetlanie (Pokazuję też RAW, żebyś widziała czy czujnik reaguje)
    print(f"RAW_A: {raw_uva:5} | UVA: {uva_calc:6.1f} µW/cm² | "
          f"RAW_B: {raw_uvb:5} | UVB: {uvb_calc:6.1f} µW/cm² | {status}")

    time.sleep(1)