import time
import sys
import st7789
import qwiic_as7331
from PIL import Image, ImageDraw, ImageFont

# --- KONFIGURACJA EKRANU (Twoje ustawienia) ---
# Piny BCM
DC_PIN = 25
RST_PIN = 27
BL_PIN = 18
CS_PIN = 8

# Ustawienia fizyczne dla Waveshare 1.14"
OFFSET_X = 40
OFFSET_Y = 53

print("1. Inicjalizacja ekranu...")
try:
    disp = st7789.ST7789(
        port=0,
        cs=st7789.BG_SPI_CS_FRONT,
        dc=DC_PIN,
        rst=RST_PIN,
        backlight=BL_PIN,
        spi_speed_hz=80 * 1000 * 1000,
        width=240,      # "Oszukane" 240x240
        height=240,
        rotation=90
    )
    disp.set_backlight(100)
except Exception as e:
    print(f"Błąd ekranu: {e}")
    sys.exit(1)

print("2. Inicjalizacja czujnika UV (AS7331)...")
try:
    my_sensor = qwiic_as7331.QwiicAs7331()
    
    if my_sensor.is_connected() == False:
        print("BŁĄD: Nie wykryto czujnika AS7331 na I2C.")
        print("Sprawdź kabelki (SDA, SCL) i zasilanie.")
        # Mimo błędu, spróbujemy wyświetlić info na ekranie
        sensor_active = False
    else:
        my_sensor.begin()
        print("Czujnik wykryty i gotowy.")
        sensor_active = True
        
        # Opcjonalnie: Włączamy tryb ciągłego pomiaru (jeśli biblioteka wymaga)
        # my_sensor.set_measurement_mode(my_sensor.MEASUREMENT_MODE_CONTINUOUS) 
        # (Dla domyślnych ustawień biblioteki Sparkfun begin() wystarczy)

except Exception as e:
    print(f"Błąd inicjalizacji czujnika: {e}")
    sensor_active = False

# --- PRZYGOTOWANIE CZCIONEK ---
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
except:
    font_large = ImageFont.load_default()
    font_small = ImageFont.load_default()

# --- GŁÓWNA PĘTLA ---
print("Uruchamianie pętli pomiarowej. Naciśnij Ctrl+C aby przerwać.")

try:
    while True:
        # 1. Odczyt danych (jeśli czujnik działa)
        if sensor_active:
            # Pobieramy surowe wartości mocy promieniowania (mW/cm2)
            uva = my_sensor.get_uva()
            uvb = my_sensor.get_uvb()
            uvc = my_sensor.get_uvc()
            
            # Wersja awaryjna - biblioteka czasem zwraca surowe bity zamiast mW
            # Jeśli wartości są ogromne, trzeba je przeliczyć, ale na start wyświetlamy co daje czujnik
        else:
            uva, uvb, uvc = (0, 0, 0)

        # 2. Rysowanie
        # Tworzymy puste tło (dla całego sterownika 240x240)
        image = Image.new("RGB", (240, 240), (0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Obszar roboczy (240x135) zaczyna się od OFFSET_X, OFFSET_Y
        # Rysujemy ramkę obszaru roboczego
        draw.rectangle((OFFSET_X, OFFSET_Y, OFFSET_X+240, OFFSET_Y+135), outline="blue")

        if sensor_active:
            # Tytuł
            draw.text((OFFSET_X + 10, OFFSET_Y + 5), "POMIAR UV", font=font_small, fill="white")
            
            # Wartości
            draw.text((OFFSET_X + 10, OFFSET_Y + 35), f"UVA: {uva}", font=font_large, fill=(180, 0, 255)) # Fioletowy
            draw.text((OFFSET_X + 10, OFFSET_Y + 70), f"UVB: {uvb}", font=font_small, fill=(0, 255, 0))   # Zielony
            draw.text((OFFSET_X + 10, OFFSET_Y + 95), f"UVC: {uvc}", font=font_small, fill=(255, 100, 100)) # Czerwony
        else:
            # Komunikat błędu na ekranie
            draw.text((OFFSET_X + 10, OFFSET_Y + 40), "BRAK CZUJNIKA!", font=font_small, fill="red")
            draw.text((OFFSET_X + 10, OFFSET_Y + 70), "Sprawdź I2C", font=font_small, fill="white")

        # 3. Aktualizacja ekranu
        disp.display(image)

        # Odświeżanie co 0.5 sekundy
        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nZamykanie...")
    disp.set_backlight(0)