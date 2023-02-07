import time
import board
import digitalio
import alarm

import terminalio
import displayio

import ipaddress
import ssl
import wifi
import socketpool
import adafruit_requests

import adafruit_vl53l4cd
from adafruit_display_text import bitmap_label
from adafruit_lc709203f import LC709203F, PackSize

RETRY_INTERVAL = 60

ZERO_HEIGHT = 5 # Sensor reads ~5cm when the weight hits the bottom of bracket

# cm from sensor to weight with i winds remaining
WIND_DATA = (ZERO_HEIGHT, 10.4, 15.5, 21.5, 28, 34.5, 41, 47, 55.5, 59, 62)

tft_power = digitalio.DigitalInOut(board.TFT_I2C_POWER)
tft_power.direction = digitalio.Direction.OUTPUT
tft_power.value = True

neo_power =  digitalio.DigitalInOut(board.NEOPIXEL_POWER)
neo_power.direction = digitalio.Direction.OUTPUT
neo_power.value = True

def go_to_sleep(sleep_period):
    # Create a an alarm that will trigger sleep_period number of seconds from now.
    time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + sleep_period)
    # Exit and deep sleep until the alarm wakes us.
    alarm.exit_and_deep_sleep_until_alarms(time_alarm)

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

def battery_only(ux, battery_monitor):
    while True:
        ux.set_battery_text(f"battery: {battery_monitor.cell_percent:.2f}%")
        time.sleep(1)

def read_distance(vl53):
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

    return average, clearance, noise

class Display:
    def __init__(self):
        self.group = displayio.Group()

        text = "Hello, World!"
        self.wind_area = bitmap_label.Label(terminalio.FONT, text=text, scale=6)
        self.wind_area.x = 15
        self.wind_area.y = 40
        self.group.append(self.wind_area)

        self.units_area = bitmap_label.Label(terminalio.FONT, text="winds", scale=2)
        self.units_area.x = 170
        self.units_area.y = self.wind_area.y
        self.group.append(self.units_area)

        self.raw_area = bitmap_label.Label(terminalio.FONT, text=text, scale=2)
        self.raw_area.x = 0
        self.raw_area.y = self.wind_area.y + 45
        self.group.append(self.raw_area)

        self.battery_area = bitmap_label.Label(terminalio.FONT, text=text, scale=2)
        self.battery_area.x = 0
        self.battery_area.y = self.raw_area.y + 25
        self.group.append(self.battery_area)

        board.DISPLAY.show(self.group)

    def set_units_text(self, t):
        self.units_area.text = t

    def set_wind_text(self, t):
        self.wind_area.text = t

    def set_raw_text(self, t):
        self.raw_area.text = t

    def set_battery_text(self, t):
        self.battery_area.text = t

def setup_vl53(battery_monitor):
    try:
        vl53 = adafruit_vl53l4cd.VL53L4CD(board.I2C())
    except ValueError as e:
        print(e)
        print("Falling back to battery only")

        ux = Display()
        ux.set_units_text("")
        ux.set_wind_text("No Sensor")
        ux.set_raw_text("Connect and power cycle")
        battery_only(ux, battery_monitor) # doesn't return

    # OPTIONAL: can set non-default values
    vl53.inter_measurement = 0
    vl53.timing_budget = 200

    vl53.start_ranging()
    return vl53

battery_monitor = LC709203F(board.I2C())
# battery_monitor.pack_size = PackSize.MAH2000
battery_monitor.pack_size = PackSize.MAH400
vl53 =  setup_vl53(battery_monitor)

boot_time = time.time()
if 0 == alarm.sleep_memory[0]:
    # first boot after power cycle, activate UX
    alarm.sleep_memory[0] = 0xFF # but skip on reboot
    time_since_boot = 0
    
    ux = Display()
    while time_since_boot < 300:
        average, clearance, noise = read_distance(vl53)
        print(f"Distance: {average} cm (noise: {noise} cm) winds: {winds_needed(average)} Battery: {battery_monitor.cell_percent:.2f}% {battery_monitor.cell_voltage:.2f}V")

        ux.set_wind_text(f"{winds_needed(average):.2f}")
        ux.set_raw_text(f"{clearance:.1f} cm (+/- {noise*5:.1f} mm)")
        ux.set_battery_text(f"battery: {battery_monitor.cell_percent:.2f}%")

        time_since_boot = time.time() - boot_time

# Post current sensor readings, and then go to sleep
#

# Defer all the network setup to here so networking failures don't
# keep the display from working

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

print("MAC addr:", ':'.join([f'{i:02x}' for i in wifi.radio.mac_address]))
for network in wifi.radio.start_scanning_networks():
    print(f"\t{str(network.ssid, "utf-8")} {network.rssi} {network.channel}")
print(f"Connecting to {secrets['ssid']}")
try:
    wifi.radio.connect(secrets["ssid"], secrets["password"])
except Exception as e: # pylint: disable=broad-except
    state.record_wifi_failure()
    print(e)
    print(f"Sleeping, will retry in {RETRY_INTERVAL}")
    go_to_sleep(RETRY_INTERVAL)

print(f"Connected to {secrets['ssid']}\nIP: {wifi.radio.ipv4_address}")
pool = socketpool.SocketPool(wifi.radio)
session = adafruit_requests.Session(pool, ssl.create_default_context())
LOGGING_URL = f"https://i0-20113a9fe59ce34c5da6b1947fc38bf7.srv.kou.services/clock-report"

average = read_distance(vl53)[0]
data = f"{int(round(average*10))} {int(round(battery_monitor.cell_percent))}"
try:
    response = session.post(LOGGING_URL, data=data,
                            headers={"Authorization" : f"Bearer {secrets['kou_key']}"})

except Exception as e: # pylint: disable=broad-except
    state.record_http_failure()
    print(e)
    print(f"Sleeping, will retry in {RETRY_INTERVAL}")
    go_to_sleep(RETRY_INTERVAL)

print(response.text, data)

print("nap time")

vl53.stop_ranging()
tft_power.value = False
neo_power.value = False

time_since_boot = time.time() - boot_time
go_to_sleep(15*60-time_since_boot)
    
