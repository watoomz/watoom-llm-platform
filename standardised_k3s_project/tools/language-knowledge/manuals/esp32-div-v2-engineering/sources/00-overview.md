# ESP32-DIV v2 engineering guide: overview and index

This set documents the lab's ESP32-DIV v2 board end to end: silicon and identity, the pin map, every chip and add-on, the application firmware, the build/flash/serial workflow on the lab server, the SD and shared-SPI engineering, memory and heap, and a debugging playbook. It complements the stored vendor manual (`esp32-div`, verbatim upstream pages); where the two disagree, this guide says so and labels the evidence.

Guides: 1 board identity and firmware profile; 2 pin map and buses; 3 chips and modules; 4 vendor wiring against firmware config; 5 firmware architecture; 6 build, flash and serial workflow; 7 SD card and shared SPI (T-0045); 8 memory and heap; 9 debugging and troubleshooting.

Evidence labels: MEASURED means observed on the lab board with a named job; CONFIG means read from the application headers or tooling and not checked on hardware; VENDOR means stated by the upstream project; DATASHEET means general chip knowledge not re-measured here; INFERRED means reasoned and untested. Treat INFERRED and CONFIG statements as hypotheses until a bring-up test confirms them.
