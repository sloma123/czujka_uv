import time
import sys
import st7789
from PIL import Image, ImageDraw, ImageFont
from smbus2 import SMBus

# --- KONFIGURACJA EKRANU ---
DC_PIN = 25
RST_PIN = 27
BL_PIN = 18
OFFSET_X = 40
OFFSET_Y = 53

# --- STEROWNIK CZUJNIKA AS7331 (Wbudowany) ---
class AS7331_MiniDriver:
    def __init__(self, address=0x74, bus_id=1):
        self.address = address
        self.bus = SMBus(bus_id)
        
    def start_measurement(self):
        try:
            # Rejestr 0x00 (OSR) -> Wpisujemy 0x02 (Tryb Command/Measurement)
            # To budzi czujnik i każe mu wykonać jeden pomiar
            self.bus.write_byte_data(self.address, 0x00, 0x02) 
            return True
        except Exception:
            return False

    def read_values(self):
        try:
            # Odczytujemy 6 bajtów danych zaczynając od rejestru 0x02
            # 0x02 = UVA LSB, 0x03 = UVA MSB
            # 0x04 = UVB LSB, 0x05 = UVB MSB
            # 0x06 = UVC LSB, 0x07 = UVC MSB
            data = self.bus.read_i2c_block_data(self.address, 0x02, 6)
            
            # Konwersja dwóch bajtów na liczbę (Little Endian)
            uva = data[0] | (data[1] << 8)
            uvb = data[2] | (data[3] << 8)
            uvc = data[4] | (data[5] << 8)
            return uva, uvb, uvc
        except Exception as e:
            print(f"Błąd I2C: {e}")
            return 0, 0, 0

# --- INICJALIZACJA EKRANU ---
print("1. Inicjalizacja ekranu...")
disp = st7789.ST7789(
    port=0, cs=st7789.BG_SPI_CS_FRONT,
    dc=DC_PIN, rst=RST_PIN, backlight=BL_PIN,
    spi_speed_hz=80 * 1000 * 1000,
    width=240, height=240, rotation=90
)
disp.set_backlight(100)

# --- INICJALIZACJA CZUJNIKA ---
print("2. Inicjalizacja czujnika UV (I2C Direct)...")
sensor = AS7331_MiniDriver()

# Sprawdzamy czy działa (próbny odczyt)
if sensor.start_measurement():
    print("Czujnik I2C odpowiada!")
    sensor_active = True
else:
    print("BŁĄD: Nie wykryto czujnika pod adresem 0x74.")
    sensor_active = False

# Fonty
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
except:
    font_large = ImageFont.load_default()
    font_small = ImageFont.load_default()

print("START. Naciśnij Ctrl+C aby przerwać.")

try:
    while True:
        if sensor_active:
            # 1. Zleć nowy pomiar
            sensor.start_measurement()
            # Czekamy chwilę na przetworzenie (katalogowo ok. 100-200ms)
            time.sleep(0.2)
            # 2. Odczytaj wynik
            uva, uvb, uvc = sensor.read_values()
        else:
            uva, uvb, uvc = (0, 0, 0)

        # Rysowanie
        image = Image.new("RGB", (240, 240), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Ramka robocza
        draw.rectangle((OFFSET_X, OFFSET_Y, OFFSET_X+240, OFFSET_Y+135), outline="blue")

        if sensor_active:
            draw.text((OFFSET_X + 10, OFFSET_Y + 5), "Skaner UV", font=font_small, fill="white")
            
            # Wyświetlamy surowe dane (RAW)
            draw.text((OFFSET_X + 10, OFFSET_Y + 35), f"UVA: {uva}", font=font_large, fill=(200, 100, 255))
            draw.text((OFFSET_X + 10, OFFSET_Y + 70), f"UVB: {uvb}", font=font_small, fill=(0, 255, 0))
            draw.text((OFFSET_X + 10, OFFSET_Y + 95), f"UVC: {uvc}", font=font_small, fill=(255, 100, 100))
        else:
            draw.text((OFFSET_X + 10, OFFSET_Y + 50), "BŁĄD I2C", font=font_large, fill="red")

        disp.display(image)
        time.sleep(0.1)

except KeyboardInterrupt:
    disp.set_backlight(0)
    print("Koniec.")
