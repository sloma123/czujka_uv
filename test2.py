#!/usr/bin/python3
# -*- coding:utf-8 -*-

import time
from PIL import Image, ImageDraw, ImageFont

import LCD_1inch14
import RPi.GPIO as GPIO

# --- inicjalizacja LCD ---
LCD = LCD_1inch14.LCD_1inch14()
LCD.Init()
LCD.clear()

# --- utworzenie obrazu ---
WIDTH = 240
HEIGHT = 135

image = Image.new("RGB", (WIDTH, HEIGHT), "black")
draw = ImageDraw.Draw(image)

# --- czcionka ---
font = ImageFont.load_default()

# --- rysowanie tekstu ---
draw.text((10, 10), "Raspberry Pi Zero 2 W", fill="white", font=font)
draw.text((10, 40), "LCD 1.14 SPI", fill="white", font=font)
draw.text((10, 70), "Test wyswietlania", fill="white", font=font)
draw.text((10, 100), "Dziala OK!", fill="white", font=font)

# --- wyslanie obrazu na LCD ---
LCD.ShowImage(image)

# --- program nie zamyka sie od razu ---
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    LCD.clear()
    GPIO.cleanup()