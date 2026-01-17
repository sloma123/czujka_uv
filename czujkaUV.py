from smbus2 import SMBus
import time

# WAVESHARE LCD (OFICJALNY DRIVER) =====
from lib import LCD_1inch14
from PIL import Image, ImageDraw, ImageFont

try:
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
except:
    font_title = ImageFont.load_default()
    font_big   = ImageFont.load_default()

# ===== LCD INIT =====
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
MRES1 = 0x02  # UVA (LSB..MSB)
# MRES2 w datasheet jest kolejnym wynikiem, ale czytamy blokiem od 0x02, więc nie trzeba osobno

STATUS_ADDR = 0x00  # odczyt 2 bajty: OSR + STATUS

# Charakterystyka optyczna (Twoje stałe)
RE_BASE_UVA = 385
RE_BASE_UVB = 347

UVA_ALARM_TSH = 5000.0
UVB_ALARM_TSH = 300.0
# GAIN: Twoja lista (indeks 0=1x ... 11=2048x)
GAIN_LEVELS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

# TIME kroki: 1,2,4,8,16,32,64 ms (kody 0..6)
TIME_STEPS = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06]

def time_code_to_ms(code: int) -> int:
    return 1 << (code & 0x0F)

BASE_TIME_CODE = 0x06
BASE_TIME_MS = time_code_to_ms(BASE_TIME_CODE)  # 64

current_gain_index = 0                 
current_time_step_idx = TIME_STEPS.index(0x06)  

def lcd_display(uva_raw, uvb_raw, gain, time_ms):
    uva_val, uvb_val = raw_to_uW_cm2(uva_raw, uvb_raw, gain, time_ms)

    disp.clear()

    # --- TRYB ALARMU ---
    if uva_val >= UVA_ALARM_TSH:
        image = Image.new("RGB", (disp.width, disp.height), "RED")
        draw = ImageDraw.Draw(image)

        lines = [
            "UWAGA!",
            "NIEBEZPIECZNA",
            "DAWKA",
            "PROMIENIOWANIA",
            "UVA",
            f"UVA: {uva_val:7.2f} {unit}", 
        ]

        # wyśrodkuj blok tekstu w pionie
        # (tu liczymy total_h podobnie jak w helperze)
        tmp_heights = []
        for ln in lines:
            bb = draw.textbbox((0, 0), ln, font=font_big)
            tmp_heights.append(bb[3] - bb[1])
        spacing = 3
        total_h = sum(tmp_heights) + spacing * (len(lines) - 1)
        y0 = (disp.height - total_h) // 2

        draw_centered_lines(draw, lines, font_big, "BLACK", y_top=y0, spacing=spacing)
        disp.ShowImage(image)
        return

    if uvb_val >= UVB_ALARM_TSH:
        image = Image.new("RGB", (disp.width, disp.height), "RED")
        draw = ImageDraw.Draw(image)

        lines = [
            "UWAGA!",
            "NIEBEZPIECZNA",
            "DAWKA",
            "PROMIENIOWANIA",
            "UVB",
            f"UVB: {uvb_val:7.2f} {unit}", 
        ]

        # wyśrodkuj blok tekstu w pionie
        # (tu liczymy total_h podobnie jak w helperze)
        tmp_heights = []
        for ln in lines:
            bb = draw.textbbox((0, 0), ln, font=font_big)
            tmp_heights.append(bb[3] - bb[1])
        spacing = 3
        total_h = sum(tmp_heights) + spacing * (len(lines) - 1)
        y0 = (disp.height - total_h) // 2

        draw_centered_lines(draw, lines, font_big, "BLACK", y_top=y0, spacing=spacing)
        disp.ShowImage(image)
        return
    
    # --- TRYB NORMALNY ---
    image = Image.new("RGB", (disp.width, disp.height), "BLACK")
    draw = ImageDraw.Draw(image)

    title = "POMIAR UV"
    unit = "uW/cm2"

    line1 = f"UVA:{uva_val:7.2f} {unit}"
    line2 = f"UVB:{uvb_val:7.2f} {unit}"

    tb = draw.textbbox((0, 0), title, font=font_title)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    draw.text(((disp.width - tw) // 2, 6), title, font=font_title, fill="WHITE")

    b1 = draw.textbbox((0, 0), line1, font=font_big)
    w1, h1 = b1[2] - b1[0], b1[3] - b1[1]
    b2 = draw.textbbox((0, 0), line2, font=font_big)
    w2, h2 = b2[2] - b2[0], b2[3] - b2[1]

    spacing = 6
    total_h = h1 + spacing + h2
    y0 = max(28, (disp.height - total_h) // 2)

    x1 = (disp.width - w1) // 2
    x2 = (disp.width - w2) // 2

    draw.text((x1, y0), line1, font=font_big, fill="CYAN")
    draw.text((x2, y0 + h1 + spacing), line2, font=font_big, fill="YELLOW")

    disp.ShowImage(image)


def draw_centered_lines(draw, lines, font, fill, y_top=0, spacing=4):
    # policz łączną wysokość bloku tekstu
    heights = []
    widths = []
    for ln in lines:
        bb = draw.textbbox((0, 0), ln, font=font)
        widths.append(bb[2] - bb[0])
        heights.append(bb[3] - bb[1])

    total_h = sum(heights) + spacing * (len(lines) - 1)
    y = y_top

    for ln, w, h in zip(lines, widths, heights):
        x = (disp.width - w) // 2
        draw.text((x, y), ln, font=font, fill=fill)
        y += h + spacing



def gain_index_to_reg_code(gain_index: int) -> int:
    # AS7331: kod 0 => 2048x ... kod 11 => 1x
    # u Ciebie gain_index 0=>1x ... 11=>2048x, więc odwracamy:
    return 11 - gain_index

def set_conf(gain_index: int, time_code: int):
    """Ustawia GAIN i TIME (time_code to KOD 0..15, nie indeks listy)"""
    gain_index = max(0, min(11, gain_index))
    time_code  = time_code & 0x0F

    gain_code = gain_index_to_reg_code(gain_index)
    config_byte = ((gain_code & 0x0F) << 4) | time_code

    # CONFIG state
    bus.write_byte_data(I2C_ADDR, OSR, 0x02)
    time.sleep(0.005)
    bus.write_byte_data(I2C_ADDR, CREG1, config_byte)
    time.sleep(0.005)

def init_sensor():
    global current_gain_index, current_time_step_idx
    try:
        bus.write_byte_data(I2C_ADDR, OSR, 0x02)
        time.sleep(0.05)

        current_gain_index = 0  # 1x
        current_time_step_idx = TIME_STEPS.index(0x06)  # 64ms
        set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])

        # CMD mode
        bus.write_byte_data(I2C_ADDR, CREG3, 0x40)
        time.sleep(0.01)

        print("AS7331 OK (Gain 1x, Time 64ms)")
        return True
    except Exception as e:
        print(f"Błąd init: {e}")
        return False

def read_status_byte():
    data = bus.read_i2c_block_data(I2C_ADDR, STATUS_ADDR, 2)
    return data[1]

def read_measurement():
    """UVA + UVB jednym odczytem: 4 bajty od 0x02"""
    try:
        data = bus.read_i2c_block_data(I2C_ADDR, MRES1, 4)
        uva = data[0] | (data[1] << 8)
        uvb = data[2] | (data[3] << 8)
        return uva, uvb
    except OSError:
        return None, None

def measure_once(time_code: int):
    bus.write_byte_data(I2C_ADDR, OSR, 0x83)  # start pomiaru

    t_ms = time_code_to_ms(time_code)
    time.sleep((t_ms + 2) / 1000.0)

    # opcjonalne dopollowanie NOTREADY (bit 2)
    deadline = time.monotonic() + 0.05
    status = read_status_byte()
    notready = (status >> 2) & 1
    while notready and time.monotonic() < deadline:
        time.sleep(0.001)
        status = read_status_byte()
        notready = (status >> 2) & 1

    uva, uvb = read_measurement()
    return uva, uvb, status

def raw_to_uW_cm2(uva_raw: int, uvb_raw: int, gain: int, time_ms: int):
    """
    Przelicza RAW na mikrowaty na centymetr kwadratowy [µW/cm²]
    Zakłada, że RE_BASE_UVA/RE_BASE_UVB są dla GAIN=2048x i TIME=BASE_TIME_MS (64ms).
    """
    if uva_raw is None or uvb_raw is None:
        return 0.0, 0.0

    gain_factor = gain / 2048.0
    time_factor = BASE_TIME_MS / float(time_ms)

    Re_uva = RE_BASE_UVA * gain_factor
    Re_uvb = RE_BASE_UVB * gain_factor

    uva_uW_cm2 = (uva_raw / Re_uva) * time_factor if Re_uva > 0 else 0.0
    uvb_uW_cm2 = (uvb_raw / Re_uvb) * time_factor if Re_uvb > 0 else 0.0

    return uva_uW_cm2, uvb_uW_cm2



def smart_measure_auto():
    global current_gain_index, current_time_step_idx

    RAW_TARGET_MIN = 2000
    RAW_TARGET_MAX = 50000
    RAW_HARD_LOW   = 300
    RAW_HARD_HIGH  = 65000

    bright_streak = 0
    dark_streak = 0

    uva_raw = 0
    uvb_raw = 0
    status_val = 0

    for _ in range(12):
        try:
            time_code = TIME_STEPS[current_time_step_idx]
            uva_raw, uvb_raw, status_val = measure_once(time_code)

            if uva_raw is None:
                continue

            raw_ref = max(uva_raw, uvb_raw)

            adcof = (status_val >> 5) & 1

            too_bright_hard = adcof or (raw_ref >= RAW_HARD_HIGH)
            too_dark_hard   = (raw_ref <= RAW_HARD_LOW)

            too_bright_soft = (raw_ref > RAW_TARGET_MAX)
            too_dark_soft   = (raw_ref < RAW_TARGET_MIN)

            # ZA JASNO
            if too_bright_hard or (too_bright_soft and bright_streak >= 1):
                bright_streak += 1
                dark_streak = 0

                if current_gain_index > 0:
                    step = 2 if too_bright_hard else 1
                    current_gain_index = max(0, current_gain_index - step)
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                if current_time_step_idx > 0:
                    current_time_step_idx -= 1
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                break

            # ZA CIEMNO
            if too_dark_hard or (too_dark_soft and dark_streak >= 1):
                dark_streak += 1
                bright_streak = 0

                if current_time_step_idx < (len(TIME_STEPS) - 1):
                    current_time_step_idx += 1
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                if current_gain_index < 11:
                    current_gain_index += 1
                    set_conf(current_gain_index, TIME_STEPS[current_time_step_idx])
                    continue

                break

            # OK
            break

        except OSError:
            continue

    used_gain = GAIN_LEVELS[current_gain_index]
    used_time_code = TIME_STEPS[current_time_step_idx]
    used_time_ms = time_code_to_ms(used_time_code)

    time_factor = BASE_TIME_MS / float(used_time_ms)

    Re_uva_base = RE_BASE_UVA * (used_gain / 2048.0)
    Re_uvb_base = RE_BASE_UVB * (used_gain / 2048.0)

    uva_uW = (uva_raw / Re_uva_base) * time_factor if Re_uva_base > 0 else 0.0
    uvb_uW = (uvb_raw / Re_uvb_base) * time_factor if Re_uvb_base > 0 else 0.0

    return uva_raw, uvb_raw, uva_uW, uvb_uW, used_gain, used_time_ms

# --- PROGRAM GŁÓWNY ---
if not init_sensor():
    exit(1)

try:
    while True:
        uva_raw, uvb_raw, uva_uW, uvb_uW, gain, time_ms = smart_measure_auto()
        print(f"G:{gain:<4}x | T:{time_ms:>3}ms | UVA: {uva_uW:.2f} | UVB: {uvb_uW:.2f} | RAW UVA:{uva_raw} UVB:{uvb_raw}")
        lcd_display(uva_raw, uvb_raw, gain, time_ms)
        time.sleep(2)

except KeyboardInterrupt:
    bus.close()

