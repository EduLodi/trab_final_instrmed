import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, welch, find_peaks
from scipy.interpolate import interp1d
import os

# --- Constantes de Análise ---
EXPECTED_FS = 100.0  # The effective sampling rate of the system (20kHz / 200)

EEG_BANDS = {
    'Delta': (0.5, 4),
    'Theta': (4, 8),
    'Alpha': (8, 12),
    'Beta': (12, 30),
    'Gamma': (30, 45)
}

def load_signal_data(file_path, fs):
    """
    Carrega os dados, IGNORA os timestamps defeituosos do arquivo e
    CRIA UMA NOVA LINHA DO TEMPO correta. NÃO HÁ PERDA DE DADOS.
    """
    if not os.path.exists(file_path):
        print(f"Erro: Arquivo '{file_path}' não encontrado.")
        return None, None

    try:
        # Carrega os dados, mas usaremos apenas a coluna 'value'
        df = pd.read_csv(file_path)
        signal = df['value'].values
        num_samples = len(signal)
        
        print(f"Arquivo carregado com sucesso. Total de {num_samples} amostras preservadas.")
        
        # --- ETAPA DE CORREÇÃO DA LINHA DO TEMPO ---
        # Cria um novo vetor de tempo baseado na taxa de amostragem esperada
        # Ex: [0.00, 0.01, 0.02, 0.03, ...]
        timestamps_sec = np.arange(num_samples) / fs
        
        print(f"Nova linha do tempo gerada para {num_samples} amostras com fs = {fs:.2f} Hz.")
        
        return timestamps_sec, signal

    except Exception as e:
        print(f"Erro ao carregar ou processar o arquivo: {e}")
        return None, None

# A função de plotagem permanece a mesma, pois agora receberá timestamps corretos
def plot_signal(timestamps, signal, title, xlabel="Tempo (s)", ylabel="Amplitude (unidade de ADC)"):
    """
    Função de plotagem aprimorada com interpolação para uma visualização suave.
    """
    interp_func = interp1d(timestamps, signal, kind='cubic', bounds_error=False, fill_value="extrapolate")
    num_points_interp = len(timestamps) * 10
    timestamps_interp = np.linspace(timestamps.min(), timestamps.max(), num=num_points_interp)
    signal_interp = interp_func(timestamps_interp)
    
    plt.figure(figsize=(15, 5))
    plt.plot(timestamps_interp, signal_interp, label="Sinal Interpolado (Suave)")
    plt.plot(timestamps, signal, 'o', markersize=2, alpha=0.3, color='red', label=f"Pontos Originais ({len(signal)} amostras)")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.legend()
    plt.autoscale(enable=True, axis='x', tight=True)
    plt.show()

# As funções de análise (analyze_eeg, analyze_ecg) não precisam de alteração
def analyze_eeg(timestamps, signal, fs):
    print("\n--- Iniciando Análise de EEG ---")
    plot_signal(timestamps, signal, "Sinal de EEG Bruto (Visualização Suave)")
    
    nyquist = 0.5 * fs
    low = 1.0 / nyquist
    high = 45.0 / nyquist
    b, a = butter(4, [low, high], btype='band')
    filtered_signal = filtfilt(b, a, signal)
    plot_signal(timestamps, filtered_signal, "Sinal de EEG Filtrado (1-45 Hz) (Visualização Suave)")
    
    print("Calculando a Densidade Espectral de Potência (PSD)...")
    freqs, psd = welch(signal, fs, nperseg=fs*4)

    plt.figure(figsize=(12, 6))
    plt.semilogy(freqs, psd)
    plt.title("Análise Espectral de EEG (Método de Welch)")
    plt.xlabel("Frequência (Hz)")
    plt.ylabel("Densidade Espectral de Potência (unidade^2/Hz)")
    plt.grid(True)
    
    for band, (low_freq, high_freq) in EEG_BANDS.items():
        plt.axvspan(low_freq, high_freq, alpha=0.2, label=f"{band}: {low_freq}-{high_freq} Hz")
    plt.legend()
    plt.xlim(0, 45)
    plt.show()

    peak_freq_index = np.argmax(psd[(freqs > 0.5) & (freqs < 45)])
    peak_freq = freqs[(freqs > 0.5) & (freqs < 45)][peak_freq_index]
    print(f"Frequência de pico detectada: {peak_freq:.2f} Hz.")
    if 8 <= peak_freq <= 12:
        print("--> Pico notável na banda Alfa. O voluntário provavelmente estava relaxado e de olhos fechados. ✅")

def analyze_ecg(timestamps, signal, fs):
    print("\n--- Iniciando Análise de ECG ---")
    plot_signal(timestamps, signal, "Sinal de ECG Bruto (Visualização Suave)")
    
    nyquist = 0.5 * fs
    low = 0.5 / nyquist
    high = 40.0 / nyquist
    b, a = butter(3, [low, high], btype='band')
    filtered_signal = filtfilt(b, a, signal)
    
    peaks, _ = find_peaks(filtered_signal, height=np.mean(filtered_signal) + 0.5 * np.std(filtered_signal), distance=fs*0.3)
    if len(peaks) < 3:
        print("Não foi possível detectar picos QRS suficientes para uma análise confiável.")
        return
    print(f"Detectados {len(peaks)} picos QRS.")
    
    plot_signal(timestamps, filtered_signal, "Sinal de ECG Filtrado (Visualização Suave)")
    
    plt.figure(figsize=(15, 5))
    plt.plot(timestamps, filtered_signal)
    plt.plot(timestamps[peaks], filtered_signal[peaks], "x", color='red', markersize=10, label=f"{len(peaks)} Picos QRS")
    plt.title("Localização dos Picos QRS no Sinal Filtrado")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Amplitude (unidade de ADC)")
    plt.legend()
    plt.grid(True)
    plt.show()
    
    rr_intervals_samples = np.diff(peaks)
    rr_intervals_sec = rr_intervals_samples / fs
    heart_rate_bpm = 60 / rr_intervals_sec
    avg_hr = np.mean(heart_rate_bpm)
    min_hr = np.min(heart_rate_bpm)
    max_hr = np.max(heart_rate_bpm)
    hrv_sdnn_ms = np.std(rr_intervals_sec) * 1000

    print("\n--- Resultados da Análise Cardíaca ---")
    print(f"Frequência Cardíaca Média: {avg_hr:.2f} bpm ❤️")
    print(f"Frequência Cardíaca Mínima/Máxima: {min_hr:.2f}/{max_hr:.2f} bpm")
    print(f"Variabilidade da Frequência Cardíaca (SDNN): {hrv_sdnn_ms:.2f} ms")


def main():
    """Função principal para interagir com o usuário."""
    while True:
        print("\n=============================================")
        print("  Analisador de Sinais Biomédicos (EEG/ECG)")
        print("=============================================")
        file_name = input("Digite o nome do arquivo de dados (ex: eeg_data.csv) ou 'sair': ")
        if file_name.lower() == 'sair':
            break
        signal_type = input("Qual o tipo de sinal? ('eeg' ou 'ecg'): ").lower()
        
        timestamps, signal = load_signal_data(file_name, fs=EXPECTED_FS)
        
        if signal is not None:
            if signal_type == 'eeg':
                analyze_eeg(timestamps, signal, fs=EXPECTED_FS)
            elif signal_type == 'ecg':
                analyze_ecg(timestamps, signal, fs=EXPECTED_FS)
            else:
                print("Tipo de sinal inválido. Por favor, escolha 'eeg' ou 'ecg'.")
        else:
            print("Não foi possível continuar a análise devido a um erro ao carregar os dados.")

if __name__ == "__main__":
    main()