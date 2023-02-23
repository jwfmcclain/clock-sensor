import sys
import shutil
import datetime
import urllib.parse
from io import BytesIO

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jinja2 import Environment, FileSystemLoader

import matplotlib
from matplotlib.figure import Figure

from circular_log import CircularLog

host_name = ''
env = Environment(loader=FileSystemLoader("templates"), autoescape=True)
plot_template = env.get_template("plot.html")

clog = CircularLog.from_file("circular-log",
                             4*24*32) # a month plus some slop

class MyServer(BaseHTTPRequestHandler):
    def do_POST(self):
        pp = urllib.parse.urlparse(self.path)
        path = pp.path
        params = urllib.parse.parse_qs(pp.query)

        if path == "/clock-report":
            content_length = int(self.headers['Content-Length'])
            data = self.rfile.read(content_length)
            distance, battery = data.split()
            distance = int(distance)
            battery = int(battery)

            print(distance, battery)
            clog.write(distance, battery)

            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404, f"unknown: {path}")

    def do_GET(self):
        pp = urllib.parse.urlparse(self.path)
        path = pp.path
        params = urllib.parse.parse_qs(pp.query)

        if path == '/':
            self.send_response(302)
            self.send_header('Location', "/plot.html")
            self.end_headers()
        elif path == "/last" or path == '/':
            try:
                n = int(params.get('count', (12,) )[0])
            except ValueError:
                self.send_error(400, f"count must be a number: {params['count']}")
                return

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()

            for timestamp, distance, battery in clog.last_records(n):
                self.wfile.write(bytes(f"{timestamp}: {distance}mm {battery}%\n", "utf-8"))
        elif path == "/plot.html":
            try:
                days_back = float(params.get('days', (4,), )[0])
            except ValueError:
                self.send_error(400, f"count must be a number: {params['count']}")
                return

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            for s in plot_template.stream(days_back=days_back):
                self.wfile.write(bytes(s, "utf-8"))
        elif path == "/plot.png":
            try:
                days_back = datetime.timedelta(float(params.get('days', (4,), )[0]))
            except ValueError:
                self.send_error(400, f"count must be a number: {params['count']}")
                return

            self.send_response(200)
            self.send_header("Content-type", "image/png")
            self.end_headers()

            now = datetime.datetime.utcnow()
            raw_data = [(timestamp, distance, battery) for timestamp, distance, battery in clog.records_from_to(now-days_back, now)]
            times = [ timestamp for timestamp, distance, battery in raw_data ]
            battery_data = [ battery for timestamp, distance, battery in raw_data ]
            distances = [ distance for timestamp, distance, battery in raw_data ]

            fig = Figure()
            ax_distance = fig.subplots()
            ax_distance.set_xlabel("Date")
            ax_distance.set_ylabel("mm")
            l_distance, = ax_distance.plot(times, distances, 'r')

            cdf = matplotlib.dates.ConciseDateFormatter(ax_distance.xaxis.get_major_locator())
            ax_distance.xaxis.set_major_formatter(cdf)

            ax_battery = ax_distance.twinx()
            ax_battery.set_ylabel("%")
            l_battery, = ax_battery.plot(times, battery_data, 'y')

            ax_battery.legend([l_distance, l_battery], ["Drive Weigth Drop", "Battery Level"])

            # Save it to a temporary buffer.
            buf = BytesIO()
            fig.savefig(buf, format="png")
            self.wfile.write(buf.getbuffer())
        else:
            self.send_error(404, f"unknown: {path}")

if __name__ == "__main__":
    server_port = int(sys.argv[1])

    webServer = ThreadingHTTPServer((host_name, server_port), MyServer)
    print("Server started http://%s:%s" % (host_name, server_port))
    print(clog.next_free)

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    print("Server stopped")
