import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
from queue import Queue
import time
from collections import deque
from datetime import datetime

# --- Required Imports ---
# For the GUI and Plotting
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
# For the Backend Server
from flask import Flask, request, jsonify

# --- Configuration ---
HOST = '0.0.0.0'  # Listen on all available network interfaces
PORT = 5000       # Port to listen on (must match Arduino code)
INITIAL_MAX_POINTS = 50 # The initial number of data points to display

# A thread-safe queue to pass data from the Flask server thread to the GUI thread
data_queue = Queue()

# --- Flask Backend to Receive Data ---

# Create a Flask app instance. We will run this in a separate thread.
flask_app = Flask(__name__)

# Suppress Flask's default logging to keep the console clean
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@flask_app.route("/data", methods=['POST'])
def receive_data():
    """
    This endpoint runs in the background Flask thread.
    It receives data from the Arduino and puts it into our shared queue.
    """
    try:
        data = request.get_json()
        print(f"Received from Arduino: {data}")

        # Add a proper datetime object for plotting
        data['timestamp'] = datetime.now()
        data_queue.put(data)

        # Send a success response back to the Arduino
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error processing POST request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask_app():
    """Function to run the Flask app. We'll target this in a thread."""
    print(f"Flask server starting at http://{HOST}:{PORT}")
    print("Waiting for data from Arduino...")
    flask_app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


# --- Tkinter GUI Application ---

class SensorPlotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Real-Time Arduino Sensor Plot (Flask Backend)")
        self.root.geometry("1100x650")

        # --- State and Data Variables ---
        self.max_points = INITIAL_MAX_POINTS
        self.is_paused = False
        
        # Use a single deque for timestamps
        self.timestamps = deque(maxlen=self.max_points)
        # Use a dictionary of deques to hold data for multiple lines
        self.sensor_data = {}
        # Use a dictionary to hold the matplotlib line objects
        self.lines = {}
        # Predefined colors for the lines
        self.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']

        # --- GUI Layout ---
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        plot_frame = ttk.Frame(main_frame)
        plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        controls_frame = ttk.Frame(main_frame, padding="10")
        controls_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        # --- Matplotlib Figure and Plot (in plot_frame) ---
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.set_title("Live Sensor Data")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Sensor Value")
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Configuration Controls (in controls_frame) ---
        self.create_controls(controls_frame)

        # Start the periodic check for new data from the queue
        self.check_queue()

    def create_controls(self, parent):
        """Creates the user interface controls for configuration."""
        # --- Pause/Resume Button ---
        self.pause_button = ttk.Button(parent, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(fill=tk.X, pady=5)
        
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=10)

        # --- Max Points Control ---
        ttk.Label(parent, text="Max Data Points").pack(anchor=tk.W)
        self.max_points_var = tk.StringVar(value=str(self.max_points))
        max_points_entry = ttk.Entry(parent, textvariable=self.max_points_var)
        max_points_entry.pack(fill=tk.X)
        ttk.Button(parent, text="Apply Max Points", command=self.apply_max_points).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=10)

        # --- Autoscale Control ---
        self.autoscale_var = tk.BooleanVar(value=True)
        autoscale_check = ttk.Checkbutton(parent, text="Autoscale Y-Axis", variable=self.autoscale_var, command=self.toggle_autoscale)
        autoscale_check.pack(anchor=tk.W)
        
        # --- Manual Y-Scale Controls ---
        self.manual_scale_frame = ttk.LabelFrame(parent, text="Manual Y-Axis Scale")
        self.manual_scale_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(self.manual_scale_frame, text="Y-Min:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.ymin_var = tk.StringVar(value="0")
        self.ymin_entry = ttk.Entry(self.manual_scale_frame, textvariable=self.ymin_var, width=10)
        self.ymin_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(self.manual_scale_frame, text="Y-Max:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.ymax_var = tk.StringVar(value="100")
        self.ymax_entry = ttk.Entry(self.manual_scale_frame, textvariable=self.ymax_var, width=10)
        self.ymax_entry.grid(row=1, column=1, padx=5, pady=2)
        
        self.toggle_autoscale() # Initialize state

    # --- Control Logic Functions ---
    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.pause_button.config(text="Resume" if self.is_paused else "Pause")

    def apply_max_points(self):
        try:
            new_max = int(self.max_points_var.get())
            if new_max <= 1:
                raise ValueError
            self.max_points = new_max
            # Recreate deques with the new maxlen
            self.timestamps = deque(self.timestamps, maxlen=self.max_points)
            for key in self.sensor_data:
                self.sensor_data[key] = deque(self.sensor_data[key], maxlen=self.max_points)
        except ValueError:
            messagebox.showerror("Invalid Input", "Max points must be an integer greater than 1.")
            self.max_points_var.set(str(self.max_points))

    def toggle_autoscale(self):
        if self.autoscale_var.get():
            # Disable manual scale entries
            for child in self.manual_scale_frame.winfo_children():
                child.configure(state='disabled')
        else:
            # Enable manual scale entries
            for child in self.manual_scale_frame.winfo_children():
                child.configure(state='normal')

    # --- Plotting and Data Handling ---
    def add_new_series(self, key):
        """Dynamically adds a new data series to the plot."""
        if key not in self.sensor_data:
            print(f"New data series detected: '{key}'. Adding to plot.")
            self.sensor_data[key] = deque(maxlen=self.max_points)
            color = self.colors[len(self.lines) % len(self.colors)]
            line, = self.ax.plot([], [], color=color, marker='o', linestyle='-', label=key)
            self.lines[key] = line
            self.ax.legend()

    def check_queue(self):
        """Periodically checks the queue for new data from the Flask thread."""
        if not self.is_paused:
            try:
                while not data_queue.empty():
                    data_point = data_queue.get_nowait()
                    timestamp = data_point.pop('timestamp', None)

                    if timestamp:
                        self.timestamps.append(timestamp)

                        for key, value in data_point.items():
                            if key.startswith('value'):
                                if key not in self.sensor_data:
                                    self.add_new_series(key)
                                try:
                                    self.sensor_data[key].append(float(value))
                                except (ValueError, TypeError):
                                    self.sensor_data[key].append(0)

                        for key in self.sensor_data:
                            while len(self.sensor_data[key]) < len(self.timestamps):
                                self.sensor_data[key].appendleft(None)

                self.update_plot()
            except Exception as e:
                print(f"Error updating GUI: {e}")

        self.root.after(200, self.check_queue)

    def update_plot(self):
        """Redraws the Matplotlib plot with the current data."""
        if not self.timestamps:
            return

        for key, line in self.lines.items():
            line.set_data(list(self.timestamps), list(self.sensor_data[key]))

        if self.autoscale_var.get():
            self.ax.relim()
            self.ax.autoscale_view(True, True, True)
        else:
            try:
                ymin = float(self.ymin_var.get())
                ymax = float(self.ymax_var.get())
                self.ax.set_ylim(ymin, ymax)
                self.ax.autoscale_view(scalex=True, scaley=False) # Only autoscale X
            except ValueError:
                # If input is invalid, fallback to autoscale for this frame
                self.ax.relim()
                self.ax.autoscale_view(True, True, True)


        self.fig.autofmt_xdate()
        self.fig.tight_layout()
        self.canvas.draw()

# --- Main Execution ---
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask_app)
    server_thread.daemon = True
    server_thread.start()

    root = tk.Tk()
    app = SensorPlotterApp(root)
    root.mainloop()
