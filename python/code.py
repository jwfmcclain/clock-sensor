import time
import board
import adafruit_vl53l4cd
import terminalio
import displayio
from adafruit_display_text import bitmap_label
from adafruit_lc709203f import LC709203F, PackSize

ZERO_HEIGHT = 5 # Sensor reads ~5cm when the weight hits the bottom of bracket

# cm from sensor to weight with i winds remaining
WIND_DATA = (ZERO_HEIGHT, 10.4, 15.5, 21.5, 28, 34.5, 41, 47, 55.5, 59, 62)

def winds_needed(distance):
    if distance <= WIND_DATA[0]:
        return 0

    if distance > WIND_DATA[-1]:
        return len(WIND_DATA)

    for i in range(len(WIND_DATA)):
        if distance <= WIND_DATA[i]:
            break

    integer_part = i - 1
    remainder_distance = distance - WIND_DATA[integer_part]
    delta = WIND_DATA[i] - WIND_DATA[integer_part]
    fraction_part = remainder_distance / delta
    return integer_part + fraction_part

def battery_only(text_area, battery_monitor):
    while True:
        text_area.text = f"battery: {battery_monitor.cell_percent:.2f}%"
        time.sleep(1)

i2c = board.I2C()

battery_monitor = LC709203F(board.I2C())
battery_monitor.pack_size = PackSize.MAH2000

group = displayio.Group()

text = "Hello, World!"
wind_area = bitmap_label.Label(terminalio.FONT, text=text, scale=6)
wind_area.x = 15
wind_area.y = 40
group.append(wind_area)

units_area = bitmap_label.Label(terminalio.FONT, text="winds", scale=2)
units_area.x = 170
units_area.y = wind_area.y
group.append(units_area)

raw_area = bitmap_label.Label(terminalio.FONT, text=text, scale=2)
raw_area.x = 0
raw_area.y = wind_area.y + 45
group.append(raw_area)

battery_area = bitmap_label.Label(terminalio.FONT, text=text, scale=2)
battery_area.x = 0
battery_area.y = raw_area.y + 25
group.append(battery_area)

board.DISPLAY.show(group)

try:
    vl53 = adafruit_vl53l4cd.VL53L4CD(i2c)
except ValueError as e:
    print(e)
    print("Falling back to battery only")

    units_area.text = ""
    wind_area.text = "No Sensor"
    raw_area.text  = "Connect and power cycle"
    battery_only(battery_area, battery_monitor) # doesn't return

# OPTIONAL: can set non-default values
vl53.inter_measurement = 0
vl53.timing_budget = 200

vl53.start_ranging()

while True:
    start = time.monotonic_ns()
    now = start
    sample_window = []

    while (now - start) < 1_000_000_000:
        while not vl53.data_ready:
            pass

        vl53.clear_interrupt()
        sample_window.append(vl53.distance)

        now = time.monotonic_ns()

    average = sum(sample_window) / len(sample_window)
    clearance = average - ZERO_HEIGHT
    noise = max(sample_window) - min(sample_window)

    print(f"Distance: {average} cm (noise: {noise} cm) winds: {winds_needed(average)} Battery: {battery_monitor.cell_percent:.2f}% {battery_monitor.cell_voltage:.2f}V")

    wind_area.text = f"{winds_needed(average):.2f}"
    raw_area.text =  f"{clearance:.1f} cm (+/- {noise*5:.1f} mm)"
    battery_area.text = f"battery: {battery_monitor.cell_percent:.2f}%"
    
