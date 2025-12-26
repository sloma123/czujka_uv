import st7789
from PIL import Image, ImageDraw, ImageFont
import time
import czujkaUV

# --- KONFIGURACJA PINÓW ---
# BCM: DC=25, RST=27, BL=18, CS=8 (CE0)
DC_PIN = 25
RST_PIN = 27
BL_PIN = 18
CS_PIN = 8

print("Inicjalizacja wyświetlacza...")

# --- INICJALIZACJA EKRANU (POPRAWIONA) ---
# Uwaga: Dla ekranu 1.14" podajemy fizyczne wymiary matrycy (135x240),
# a następnie obracamy o 90 stopni (rotation=90).
# Konieczne są też offsety, bo matryca jest wycięta z większego wafla.
disp = st7789.ST7789(
    port=0,
    cs=st7789.BG_SPI_CS_FRONT,  # SPI 0, CE0
    dc=DC_PIN,
    rst=RST_PIN,
    backlight=BL_PIN,
    spi_speed_hz=80 * 1000 * 1000,
    width=135,      # Fizyczna szerokość (krótszy bok)
    height=240,     # Fizyczna wysokość (dłuższy bok)
    rotation=90,    # Obrót do poziomu
        # Przesunięcie X (dla Waveshare 1.14)
         # Przesunięcie Y (dla Waveshare 1.14)
)

# Włącz podświetlenie (100% jasności)
disp.set_backlight(100)

# --- TWORZENIE OBRAZU ---
# Pobieramy logiczne wymiary (już po obrocie 90 stopni)
width = disp.width   # Powinno być 240
height = disp.height # Powinno być 135

print(f"Rozdzielczość logiczna: {width}x{height}")

# Tworzymy czarne tło
image = Image.new("RGB", (width, height), (0, 0, 0))
draw = ImageDraw.Draw(image)

# 1. Rysujemy ramkę (aby sprawdzić, czy obraz jest wyśrodkowany)
draw.rectangle((0, 0, width-1, height-1), outline="blue", width=2)

# 2. Rysujemy tekst
try:
    # Próba załadowania ładniejszej czcionki systemowej
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 25)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
except IOError:
    # Jeśli nie ma, użyj domyślnej
    font = ImageFont.load_default()
    font_small = ImageFont.load_default()

# Napis główny
text = "DZIAŁA!"
# Centrowanie tekstu (metoda textbbox dla nowszych wersji Pillow)
bbox = draw.textbbox((0, 0), text, font=font)
text_w = bbox[2] - bbox[0]
text_h = bbox[3] - bbox[1]
x = (width - text_w) // 2
y = (height // 2) - text_h - 10

draw.text((x, y), text, font=font, fill=(0, 255, 0)) # Zielony
draw.text((10, height-30), "Raspberry Pi Zero 2", font=font_small, fill="white")

# --- WYŚWIETLANIE ---
print("Wysyłam obraz...")
disp.display(image)

print("Gotowe. Wciśnij Ctrl+C aby zakończyć.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nZamykanie...")
    # Opcjonalnie wyłącz podświetlenie przy wyjściu
    disp.set_backlight(0)
