# =================================================================
# FINAL PYTHON GUI - WITH DATA RECORDING TO CSV
# =================================================================
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from queue import Queue
from collections import deque
from datetime import datetime
import csv # Import the csv module for file writing

# --- Required Imports ---
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from flask import Flask, request, jsonify

# --- Configuration ---
HOST = '0.0.0.0'
PORT = 5000
INITIAL_HISTORY_LENGTH = 5000

# A thread-safe queue to pass data from the Flask thread to the GUI thread
data_queue = Queue()

# --- NEW: Global variables for recording state ---
is_recording = False
recording_lock = threading.Lock() # To safely change the recording state from the GUI
csv_writer = None
csv_file = None


# --- Flask Backend (runs in a background thread) ---
flask_app = Flask(__name__)
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@flask_app.route("/data", methods=['POST'])
def receive_data():
    """Receives the 'samples' array, puts it in the GUI queue, and saves it to a file if recording."""
    global is_recording, csv_writer, csv_file
    try:
        data = request.get_json()
        if 'samples' in data and isinstance(data['samples'], list):
            samples = data['samples']
            # Put data in the queue for the live plot
            data_queue.put(samples)

            # --- NEW: Write data to CSV if recording is active ---
            with recording_lock:
                if is_recording and csv_writer is not None:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    for value in samples:
                        csv_writer.writerow([timestamp, value])

            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error", "message": "Invalid data format"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask_app():
    """Target function for the server thread."""
    print(f"Flask server starting at http://{HOST}:{PORT}")
    print("Waiting for data from ESP32...")
    flask_app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


# --- Tkinter GUI Application ---
class SensorPlotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scrolling ESP32 History Plotter")
        self.root.geometry("1100x650")

        self.is_paused = False
        self.history_length = INITIAL_HISTORY_LENGTH
        
        self.y_data = deque(maxlen=self.history_length)
        self.x_data = deque(maxlen=self.history_length)
        self.x_counter = 0

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        controls_frame = ttk.Frame(main_frame, padding="10")
        controls_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        plot_frame = ttk.Frame(main_frame)
        plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.set_title("Live ESP32 Signal History")
        self.ax.set_xlabel("Sample Count")
        self.ax.set_ylabel("ADC Value")
        self.ax.grid(True)
        self.line, = self.ax.plot([], [], color='#e63946') 
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.create_controls(controls_frame)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_queue()

    def create_controls(self, parent):
        """Creates the GUI controls."""
        # --- NEW: Recording Button ---
        self.record_button = ttk.Button(parent, text="Start Recording", command=self.toggle_recording)
        self.record_button.pack(fill=tk.X, pady=5)
        
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=10)

        self.pause_button = ttk.Button(parent, text="Pause Plot", command=self.toggle_pause)
        self.pause_button.pack(fill=tk.X, pady=5)
        
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=10)

        ttk.Label(parent, text="History Length").pack(anchor=tk.W)
        self.history_var = tk.StringVar(value=str(self.history_length))
        history_entry = ttk.Entry(parent, textvariable=self.history_var)
        history_entry.pack(fill=tk.X)
        ttk.Button(parent, text="Apply History Length", command=self.apply_history_length).pack(fill=tk.X, pady=(0, 10))

    def toggle_recording(self):
        """Starts or stops saving data to a CSV file."""
        global is_recording, csv_writer, csv_file
        with recording_lock:
            is_recording = not is_recording
            if is_recording:
                filename = f"eeg_data_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
                try:
                    # Open the file for writing
                    csv_file = open(filename, 'w', newline='', encoding='utf-8')
                    csv_writer = csv.writer(csv_file)
                    # Write a header row
                    csv_writer.writerow(['timestamp', 'value'])
                    print(f"Recording started. Saving data to {filename}")
                    self.record_button.config(text="Stop Recording")
                except Exception as e:
                    messagebox.showerror("File Error", f"Could not open file for writing:\n{e}")
                    is_recording = False # Revert state if file opening failed
            else:
                if csv_file:
                    csv_file.close()
                    csv_file = None
                    csv_writer = None
                    print("Recording stopped.")
                self.record_button.config(text="Start Recording")
                
    def on_closing(self):
        """Safely close the file when the user closes the GUI window."""
        global is_recording
        if is_recording:
            self.toggle_recording() # This will handle closing the file
        self.root.destroy()

    def apply_history_length(self, *args): # (The rest of the class methods are unchanged)
        try:
            new_len = int(self.history_var.get())
            if new_len <= 1: raise ValueError
            self.history_length = new_len
            self.x_data = deque(self.x_data, maxlen=self.history_length)
            self.y_data = deque(self.y_data, maxlen=self.history_length)
            messagebox.showinfo("Success", f"History length set to {new_len} points.")
        except ValueError:
            messagebox.showerror("Invalid Input", "History length must be an integer greater than 1.")
            self.history_var.set(str(self.history_length))

    def toggle_pause(self, *args):
        self.is_paused = not self.is_paused
        self.pause_button.config(text="Resume Plot" if self.is_paused else "Pause Plot")
        if not self.is_paused:
            print("Resumed. Clearing data backlog...")
            with data_queue.mutex:
                data_queue.queue.clear()

    def check_queue(self, *args):
        if not self.is_paused:
            data_was_added = False
            try:
                while not data_queue.empty():
                    new_samples = data_queue.get_nowait()
                    data_was_added = True
                    for sample in new_samples:
                        self.y_data.append(sample)
                        self.x_data.append(self.x_counter)
                        self.x_counter += 1
                if data_was_added:
                    self.update_plot()
            except Exception:
                pass
        self.root.after(100, self.check_queue)

    def update_plot(self, *args):
        self.line.set_data(self.x_data, self.y_data)
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.tight_layout()
        self.canvas.draw()

# --- Main Execution Block ---
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask_app)
    server_thread.daemon = True
    server_thread.start()

    root = tk.Tk()
    app = SensorPlotterApp(root)
    root.mainloop()