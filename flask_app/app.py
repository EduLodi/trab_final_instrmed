# =================================================================
#        FINAL PYTHON GUI - SCROLLING HISTORY PLOTTER
# =================================================================
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from queue import Queue
from collections import deque # Import deque for efficient fixed-length storage
from flask import Flask, request, jsonify
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- Configuration ---
HOST = '0.0.0.0'
PORT = 5000
INITIAL_HISTORY_LENGTH = 5000 # The number of historical data points to display

# A thread-safe queue to pass data from the Flask thread to the GUI thread
data_queue = Queue()

# --- Flask Backend (runs in a background thread) ---
flask_app = Flask(__name__)
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@flask_app.route("/data", methods=['POST'])
def receive_data():
    """Receives the 'samples' array and puts it in the queue."""
    try:
        data = request.get_json()
        if 'samples' in data and isinstance(data['samples'], list):
            data_queue.put(data['samples'])
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

        # --- NEW: State and Data Variables for Historical Plot ---
        self.is_paused = False
        self.history_length = INITIAL_HISTORY_LENGTH
        
        # Use deques for efficient appending and popping from both ends
        self.y_data = deque(maxlen=self.history_length) # For sensor values
        self.x_data = deque(maxlen=self.history_length) # For a continuous x-axis
        self.x_counter = 0 # A continuous counter for the x-axis

        # --- GUI Layout ---
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        controls_frame = ttk.Frame(main_frame, padding="10")
        controls_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        plot_frame = ttk.Frame(main_frame)
        plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # --- Matplotlib Figure and Plot ---
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.set_title("Live ESP32 Signal History")
        self.ax.set_xlabel("Sample Count") # X-axis is now a running count
        self.ax.set_ylabel("ADC Value")
        self.ax.grid(True)
        self.line, = self.ax.plot([], [], color='#e63946') 
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Controls ---
        self.create_controls(controls_frame)
        
        # Start the periodic check for new data
        self.check_queue()

    def create_controls(self, parent):
        """Creates the GUI controls."""
        self.pause_button = ttk.Button(parent, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(fill=tk.X, pady=5)
        
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=10)

        ttk.Label(parent, text="History Length").pack(anchor=tk.W)
        self.history_var = tk.StringVar(value=str(self.history_length))
        history_entry = ttk.Entry(parent, textvariable=self.history_var)
        history_entry.pack(fill=tk.X)
        ttk.Button(parent, text="Apply History Length", command=self.apply_history_length).pack(fill=tk.X, pady=(0, 10))

    def apply_history_length(self):
        """Updates the maxlen of the deques to change the history size."""
        try:
            new_len = int(self.history_var.get())
            if new_len <= 1: raise ValueError
            self.history_length = new_len
            # Recreate deques with the new maxlen, preserving existing data
            self.x_data = deque(self.x_data, maxlen=self.history_length)
            self.y_data = deque(self.y_data, maxlen=self.history_length)
            messagebox.showinfo("Success", f"History length set to {new_len} points.")
        except ValueError:
            messagebox.showerror("Invalid Input", "History length must be an integer greater than 1.")
            self.history_var.set(str(self.history_length))

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.pause_button.config(text="Resume" if self.is_paused else "Pause")
        if not self.is_paused:
            print("Resumed. Clearing data backlog...")
            with data_queue.mutex:
                data_queue.queue.clear()

    def check_queue(self):
        """Checks the queue for new data and appends it to the history."""
        if not self.is_paused:
            data_was_added = False
            try:
                while not data_queue.empty():
                    # Get the new buffer of samples
                    new_samples = data_queue.get_nowait()
                    data_was_added = True
                    
                    # NEW: Append each new sample to our historical deques
                    for sample in new_samples:
                        self.y_data.append(sample)
                        self.x_data.append(self.x_counter)
                        self.x_counter += 1
                
                if data_was_added:
                    self.update_plot()
            except Exception:
                pass
        self.root.after(100, self.check_queue)

    def update_plot(self):
        """Redraws the plot with the full history."""
        # Update the data of the line with the entire history
        self.line.set_data(self.x_data, self.y_data)
        # Autoscale the axes
        self.ax.relim()
        self.ax.autoscale_view()
        # Redraw the canvas
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