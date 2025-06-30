/*
  Rui Santos
  Complete project details at Complete project details at https://RandomNerdTutorials.com/esp32-http-get-post-arduino/

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files.

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_adc/adc_continuous.h"

const uint8_t VREF_PIN = 39;
const uint8_t ACQ_PINS[] = { 36 };

const int N_VREF = 16;
uint16_t vref;

const float T_WINDOW = 5;
const uint32_t SAMP_FREQ = 240;
const uint32_t DECIM = 100;
const uint32_t N_SAMPLES = T_WINDOW * SAMP_FREQ;

// Result structure for ADC Continuous reading
uint8_t result[DECIM*SOC_ADC_DIGI_RESULT_BYTES];
uint16_t data[N_SAMPLES];
int data_idx = 0;

// Flag which will be set in ISR when conversion is done
adc_continuous_handle_t adc_handle = NULL;
volatile bool adc_conversion_done = false;


//Wifi network and password (needs to be 2.4 GHz)
const char* ssid = "";
const char* password = "";


//Your Domain name with URL path or IP address with path
const char* serverName = "";

// the following variables are unsigned longs because the time, measured in
// milliseconds, will quickly become a bigger number than can be stored in an int.
unsigned long lastTime = 0;
// Timer set to 10 minutes (600000)
//unsigned long timerDelay = 600000;
// Set timer to 5 seconds (5000)
unsigned long timerDelay = 5000;

static bool IRAM_ATTR s_conv_done_cb(adc_continuous_handle_t handle, const adc_continuous_evt_data_t *edata, void *user_data)
{ 
  static uint32_t ret_num;
  esp_err_t ret = adc_continuous_read(adc_handle, result, SOC_ADC_DIGI_DATA_BYTES_PER_CONV*DECIM, &ret_num, 0);
  uint32_t sum = 0;
  for(int i = 0; i < ret_num; i += SOC_ADC_DIGI_RESULT_BYTES){
    adc_digi_output_data_t *p = (adc_digi_output_data_t*)&result[i];
    uint16_t res = ((p)->type1.data);
    sum += res;
  }
  if(data_idx == N_SAMPLES-2){
    adc_conversion_done = true;
  }
  data[data_idx] = sum/ret_num;
  data_idx = (data_idx + 1) % N_SAMPLES;
  return true;
}

static void continuous_adc_init(adc_continuous_handle_t *out_handle)
{
    adc_continuous_handle_t handle = NULL;

    adc_continuous_handle_cfg_t adc_config = {
        .max_store_buf_size = SOC_ADC_DIGI_DATA_BYTES_PER_CONV*DECIM,
        .conv_frame_size = SOC_ADC_DIGI_DATA_BYTES_PER_CONV*DECIM,
    };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&adc_config, &handle));

    adc_continuous_config_t dig_cfg = {
        .sample_freq_hz = SAMP_FREQ*DECIM,
        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
        .format = ADC_DIGI_OUTPUT_FORMAT_TYPE1,
    };

    const int channel_num = 1;
    static adc_channel_t channel[channel_num] = {ADC_CHANNEL_0};
    adc_digi_pattern_config_t adc_pattern[SOC_ADC_PATT_LEN_MAX] = {0};
    dig_cfg.pattern_num = channel_num;
    for (int i = 0; i < channel_num; i++) {
        adc_pattern[i].atten = ADC_ATTEN_DB_12;
        adc_pattern[i].channel = channel[i] & 0x7;
        adc_pattern[i].unit = ADC_UNIT_1;
        adc_pattern[i].bit_width = ADC_BITWIDTH_12;

        ESP_LOGI(TAG, "adc_pattern[%d].atten is :%"PRIx8, i, adc_pattern[i].atten);
        ESP_LOGI(TAG, "adc_pattern[%d].channel is :%"PRIx8, i, adc_pattern[i].channel);
        ESP_LOGI(TAG, "adc_pattern[%d].unit is :%"PRIx8, i, adc_pattern[i].unit);
    }
    dig_cfg.adc_pattern = adc_pattern;
    ESP_ERROR_CHECK(adc_continuous_config(handle, &dig_cfg));

    *out_handle = handle;
}


void setup() {
  Serial.begin(115200);

  WiFi.begin(ssid, password);
  Serial.println("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to WiFi network with IP Address: ");
  Serial.println(WiFi.localIP());

  Serial.println("Timer set to 5 seconds (timerDelay variable), it will take 5 seconds before publishing the first reading.");

  continuous_adc_init(&adc_handle);
  adc_continuous_evt_cbs_t cbs = {
      .on_conv_done = s_conv_done_cb,
  };
  adc_continuous_register_event_callbacks(adc_handle, &cbs, NULL);
  adc_continuous_start(adc_handle);
}

void loop() {
  if (adc_conversion_done) {
    adc_conversion_done = false;
    for(int i = 0; i < N_SAMPLES; i++){
      Serial.println(data[i]);
    }

    // ADC 1 canal 0 -> GPIO 36 (pino SP aqui na minha esp)
    // Esse data vai preencher a cada 5 segundos, a ideia é mandar ele em um array no json pra mandar no post, aí ficaria um plot dos últimos 5 segundos no site.
    // O 5 segundos é o que eu programei, mas medindo aqui na mão não tá dando 5, tem que ver o que é
    // A ideia é colocar o filtro no data. Agora só está uma média (filtro ruim) pra conseguir ver o que tá saindo do ADC.
  }

  // Send an HTTP POST request every 10 minutes
  if ((millis() - lastTime) > timerDelay) {
    //Check WiFi connection status
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClient client;
      HTTPClient http;

      // Your Domain name with URL path or IP address with path
      http.begin(client, serverName);

      //If you need an HTTP request with a content type: application/json, use the following:
      http.addHeader("Content-Type", "application/json");
      int httpResponseCode = http.POST("{\"api_key\":\"tPmAT5Ab3j7F9\",\"sensor\":\"BME280\",\"value\":\"24.25\",\"value2\":\"49.54\",\"value3\":\"1005.14\"}");


      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);

      // Free resources
      http.end();
    } else {
      Serial.println("WiFi Disconnected");
    }
    lastTime = millis();
  }
}