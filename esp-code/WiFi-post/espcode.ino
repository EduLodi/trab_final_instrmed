#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_adc/adc_continuous.h"
#include <ArduinoJson.h>

// --- Network Configuration ---
const char *ssid = "";
const char *password = "";
const char *serverName = "";

int buffer_index = 0;

static float w1[2] = { 0, 0 };
static float w2[2] = { 0, 0 };
static float w3[2] = { 0, 0 };
static float w4[2] = { 0, 0 };
static float w5[2] = { 0, 0 };

float update_filter(float x, float a1, float a2, float w[]) {
  float next_w = x - a1 * w[0] - a2 * w[1];
  float y = next_w + 2 * w[0] + w[1];
  w[1] = w[0];
  w[0] = next_w;
  return y;
}

// --- ADC Configuration ---
#define READ_LEN_BYTES SOC_ADC_DIGI_RESULT_BYTES*100
const int N_SAMPLES_PER_BUFFER = READ_LEN_BYTES / SOC_ADC_DIGI_RESULT_BYTES;  // Should be 256

// --- Global Variables for Task Communication ---
volatile int16_t data_buffer[N_SAMPLES_PER_BUFFER];
SemaphoreHandle_t dataReadySemaphore;
TaskHandle_t ProcessingTaskHandle;
adc_continuous_handle_t adc_handle = NULL;
SemaphoreHandle_t payloadReadySemaphore;

// =================================================================
// INTERRUPT SERVICE ROUTINE (ISR) - Kept extremely short and fast
// =================================================================
static bool IRAM_ATTR s_conv_done_cb(adc_continuous_handle_t handle, const adc_continuous_evt_data_t *edata, void *user_data) {
  BaseType_t mustYield = pdFALSE;
  xSemaphoreGiveFromISR(dataReadySemaphore, &mustYield);
  portYIELD_FROM_ISR(mustYield);
  return true;
}

// =================================================================
// TASK: Data Processing and Filtering (Runs on Core 1)
// =================================================================
void processing_task(void *pvParameters) {
  Serial.print("Processing Task started on core ");
  Serial.println(xPortGetCoreID());

  uint8_t result[READ_LEN_BYTES];
  uint32_t ret_num = 0;

  for (;;) {
    xSemaphoreTake(dataReadySemaphore, portMAX_DELAY);

    esp_err_t ret = adc_continuous_read(adc_handle, result, READ_LEN_BYTES, &ret_num, 0);
    if (ret == ESP_OK) {
      float y5; 
      // --- Process the received data chunk ---
      for (int i = 0; i < ret_num; i += SOC_ADC_DIGI_RESULT_BYTES) {
        adc_digi_output_data_t *p = (adc_digi_output_data_t *)&result[i];
        float x = p->type1.data;

        float x1 = x * 1.232515933224931e-04f;
        float y1 = update_filter(x1, -1.992572665214539f, 0.993065595626831f, w1);
        float x2 = y1 * 1.224440784426406e-04f;
        float y2 = update_filter(x2, -1.979517698287964f, 0.980007469654083f, w2);
        float x3 = y2 * 1.217654426000081e-04f;
        float y3 = update_filter(x3, -1.968546509742737f, 0.969033539295197f, w3);
        float x4 = y3 * 1.212770876009017e-04f;
        float y4 = update_filter(x4, -1.960651397705078f, 0.961136460304260f, w4);
        float x5 = y4 * 1.210219124914147e-04f;
        y5 = update_filter(x5, -1.956526041030884f, 0.957010090351105f, w5);
      }

            
      data_buffer[buffer_index] = y5;
      buffer_index += 1;   
      if(buffer_index == N_SAMPLES_PER_BUFFER){
        xSemaphoreGive(payloadReadySemaphore);
        buffer_index = 0;
      }
    } else {
      Serial.println("ADC Read Error!");
    }
  }
}

// =================================================================
// SETUP: Runs once on Core 1
// =================================================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- Board starting up ---");

  // --- Initialize Wi-Fi ---
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");

  // --- Initialize ADC and its callbacks ---
  adc_continuous_handle_cfg_t adc_config = { .max_store_buf_size = READ_LEN_BYTES * 2, .conv_frame_size = READ_LEN_BYTES };
  ESP_ERROR_CHECK(adc_continuous_new_handle(&adc_config, &adc_handle));
  adc_continuous_config_t dig_cfg = { .sample_freq_hz = 24000, .conv_mode = ADC_CONV_SINGLE_UNIT_1, .format = ADC_DIGI_OUTPUT_FORMAT_TYPE1 };
  adc_digi_pattern_config_t adc_pattern[1] = { 0 };
  adc_pattern[0].atten = ADC_ATTEN_DB_12;
  adc_pattern[0].channel = ADC_CHANNEL_0;
  adc_pattern[0].unit = ADC_UNIT_1;
  adc_pattern[0].bit_width = ADC_BITWIDTH_12;
  dig_cfg.pattern_num = 1;
  dig_cfg.adc_pattern = adc_pattern;
  ESP_ERROR_CHECK(adc_continuous_config(adc_handle, &dig_cfg));
  adc_continuous_evt_cbs_t cbs = { .on_conv_done = s_conv_done_cb };
  ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adc_handle, &cbs, NULL));
  ESP_ERROR_CHECK(adc_continuous_start(adc_handle));

  // --- Create Semaphore and Processing Task ---
  dataReadySemaphore = xSemaphoreCreateBinary();
  payloadReadySemaphore = xSemaphoreCreateBinary();
  xTaskCreatePinnedToCore(processing_task, "ProcessingTask", 4096, NULL, 1, &ProcessingTaskHandle, 1);

  Serial.println("Setup complete. Network task waiting in main loop...");
}

// =================================================================
// LOOP: Network Task (UPDATED LOGIC)
// =================================================================
void loop() {
  // Send data more frequently for a real-time feel
  if(xSemaphoreTake(payloadReadySemaphore, portMAX_DELAY) == pdTRUE){

    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\n--- [Network Task] Sending POST request... ---");

      WiFiClient client;
      HTTPClient http;
      http.setTimeout(5000);  // 5 second timeout
      http.begin(client, serverName);
      http.addHeader("Content-Type", "application/json");

      // --- Create JSON payload using ArduinoJson ---
      StaticJsonDocument<4096> doc;  // Create a JSON document. 4096 bytes should be enough.

      // Create a JSON array inside the document
      JsonArray samples = doc.createNestedArray("samples");

      // Add all the data from our buffer to the JSON array
      for (int i = 0; i < N_SAMPLES_PER_BUFFER; i++) {
        samples.add(data_buffer[i]);
      }

      // Serialize the JSON document to a String
      String payload;
      serializeJson(doc, payload);

      // --- PRINT: --- Show the exact JSON payload being sent
      Serial.println("[Payload] JSON payload generated:");
      if (payload.length() > 256) {
        Serial.print(payload.substring(0, 256));
        Serial.println("... (payload truncated)");
      } else {
        Serial.println(payload);
      }

      // --- Send the JSON payload ---
      int httpResponseCode = http.POST(payload);

      if (httpResponseCode > 0) {
        Serial.print("POST successful. HTTP Response code: ");
        Serial.println(httpResponseCode);
      } else {
        Serial.print("POST failed. Error: ");
        Serial.println(http.errorToString(httpResponseCode).c_str());
      }

      http.end();
    } else {
      Serial.println("Network Task: WiFi is disconnected.");
    }
  }
}