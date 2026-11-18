# Schematics of ESP32-DIV

The **ESP32-DIV** integrates multiple components with the ESP32 microcontroller for its wireless capabilities. Below are the key connections. Refer to the [ESP32-DIV GitHub repository](https://github.com/cifertech/ESP32-DIV/tree/main/Schematic) for detailed schematic files.


<div>&nbsp;</div>

## ⚙️ TFT Display + ESP32
<div class="relative overflow-hidden shadow-md rounded-lg">
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32-S3 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">TFT Pin</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 36</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SCK / CLK</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Clock</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 35</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MOSI / SDI / DIN</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Input</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 37</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MISO / SDO</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Output</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 17</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CS</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 16</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">DC / RS</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Data / Command</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">EN/RESET</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">RESET</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Display Reset</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 7</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">BL / LED</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Backlight Control
                    <br>(SI2302)</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">3.3V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">VCC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Power Supply</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
</div>

- **ILI9341 TFT Display**: Connected to the ESP32 for the user interface.
- **LED Backlight Control**: Managed via a transistor switch (Q3, 8050) with a 1kΩ resistor (R26) at the base. Supports PWM for brightness adjustment if implemented.

<div>&nbsp;</div>

## 🖥️ XPT2046 + ESP32

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32-S3 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">XPT2046 Pin</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 36</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">T_CLK / SCK</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Clock</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 35</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">T_DIN / MOSI</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Input</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 37</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">T_DO / MISO</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Output</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 18</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">T_CS</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Touch Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">-</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">T_IRQ</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Touch Interrupt / Pen Detect</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">3.3V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">VCC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Power Supply</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
</div>

- **XPT2046**: Touch controller for the TFT display, interfaced with the ESP32 for touch input.

<div>&nbsp;</div>

## 📡 NRF24 Modules - Connections to ESP32

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">NRF24 PIN</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">DESCRIPTION</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 12</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SCK</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Clock (Shared)</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 11</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MOSI</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Input (Shared)</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 13</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MISO</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Output (Shared)</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 4</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CSN (NRF24 #1)</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 15</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CE (NRF24 #1)</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Enable</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 48</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CSN (NRF24 #2)</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 47</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CE (NRF24 #2)</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Enable</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 21</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CSN (NRF24 #3)</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 14</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CE (NRF24 #3)</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Enable</td>
            </tr>
            <tr class=" py-1" style="">
                <td spellcheck="true" class=" py-1 border  border-gray-300 text-center  p-4">3.3V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">VCC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Power Supply (3.3V ONLY)</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
</div>

- **3 x NRF24 Modules**: Connected to the ESP32 for 2.4GHz operations (scanning, jamming, etc.). Each module uses SPI pins for communication.

<div>&nbsp;</div>

## 📻 CC1101 Sub-GHz Transceiver - Connections to ESP32

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">CC1101 Pin</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 12</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SCK</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Clock</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 11</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MOSI</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Input</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 13</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MISO</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Output</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 5</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CSN / CS</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 6</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GDO0</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">General Digital Output / Interrupt</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 3</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GDO2</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">General Digital Output</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">3.3V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">VCC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Power Supply (3.3V ONLY)</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
</div>

- **CC1101 Module**: Connected to the ESP32 via SPI for Sub-GHz signal capture, replay, and jamming.

<div>&nbsp;</div>

## 💾 SD Card - Connections to ESP32

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">SD Card Pin</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 12</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SCK / CLK</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Clock</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 11</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MOSI / DI</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Input</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 13</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">MISO / DO</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SPI Data Output</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 10</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">CS</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Chip Select</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 38</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Detect pin /&nbsp;CD</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SD card detect pin</td>
            </tr>
            <tr class=" py-1" style="">
                <td spellcheck="true" class=" py-1 border  border-gray-300 text-center  p-4">3.3V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">VCC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Power Supply (3.3V)</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
</div>

- **SD Card Slot**: Interfaced with the ESP32 via SPI for storing signals, logs, and firmware files.

<div>&nbsp;</div>

## 📤 IR → ESP32 - Connections to ESP32
- **IR Receiver → ESP32**

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">IR RECEIVER PIN</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 21</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">OUT</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">IR Signal Output</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">3.3V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">VCC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Power Supply</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
</div>

<div>&nbsp;</div>

- **IR Transmitter (BC847) → ESP32**

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">BC847 / IR PIN</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 14</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">BC847 BASE</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">IR Signal (via 220R Base Resistor)</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GND</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">BC847 EMITTER</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Ground</td>
                <!--]-->
            </tr>
            <tr class=" py-1" style="">
                <td spellcheck="true" class=" py-1 border  border-gray-300 text-center  p-4">5V</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">IR LED ANODE</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">IR LED Power (with 220R Resistor)</td>
            </tr>
            <tr class=" py-1" style="">
                <td class=" py-1 border  border-gray-300 text-center  p-4">BC847 COLLECTOR</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">IR LED CATHODE</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Low-Side Switching</td>
            </tr>
            <!--]-->
        </tbody>
    </table>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
</div>

<div>&nbsp;</div>

## 🔊 Buzzer - Connections to ESP32
- **Buzzer → ESP32**

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">BUZZER PIN</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 2</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">SIGNAL</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">PWM / Tone Output</td>
                <!--]-->
            </tr>
            <!--]-->
        </tbody>
    </table>
</div>

<div>&nbsp;</div>

## 🚨 NeoPixel - Connections to ESP32
- **NeoPixel (WS2812) → ESP32**

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">NEOPIXEL PIN</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 1</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">DIN</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">NeoPixel Data Input</td>
                <!--]-->
            </tr>
            <!--]-->
        </tbody>
    </table>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
    <grammarly-extension-vbars data-grammarly-shadow-root="true" class="dnXmp" style="display: contents; --rem: 16;"></grammarly-extension-vbars>
</div>

<div>&nbsp;</div>

## 🔋 Battery Voltage Divider - Connections to ESP32
- **Battery Voltage Divider → ESP32**

<div class="relative overflow-hidden shadow-md rounded-lg">
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <grammarly-extension data-grammarly-shadow-root="true" class="dnXmp" style="position: absolute; top: 0px; left: 0px; pointer-events: none; --rem: 16;"></grammarly-extension>
    <table class="table-fixed w-full text-left">
        <thead class="uppercase bg-[#FF8200] text-[#2c2e32]" style="background-color: rgb(255, 130, 0); color: rgb(44, 46, 50);">
            <tr>
                <!--[-->
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">ESP32 GPIO</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">SIGNAL</td>
                <td class="py-2 border  border-gray-300 text-center font-bold p-4">Description</td>
                <!--]-->
            </tr>
        </thead>
        <tbody class="bg-white text-gray-500 bg-[#1e1e1e] text-[#FF8200]" style="background-color: rgb(30, 30, 30); color: rgb(255, 130, 0);">
            <!--[-->
            <tr class=" py-1" style="">
                <!--[-->
                <td class=" py-1 border  border-gray-300 text-center  p-4">GPIO 2</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">ADC</td>
                <td class=" py-1 border  border-gray-300 text-center  p-4">Battery Voltage Sense (via Divider)</td>
                <!--]-->
            </tr>
            <!--]-->
        </tbody>
    </table>
</div>


<div>&nbsp;</div>

## 🧲 PN532 RFID/NFC → ESP32 (SPI)

**Library:** Adafruit PN532 (`rfid.cpp`). SPI is shared with other peripherals on the same clock/data lines; **PN532 uses its own chip select (`PN532_SS`)**.

| ESP32 GPIO | PN532 pin | Description |
| ---------- | --------- | ----------- |
| GPIO 12 | SCK | SPI clock (`PN532_SCK`) |
| GPIO 11 | MISO | SPI MISO (`PN532_MISO`) |
| GPIO 13 | MOSI | SPI MOSI (`PN532_MOSI`) |
| GPIO 4 | SS / CS | Chip select (`PN532_SS`) |
| 3.3V | VCC | Power |
| GND | GND | Ground |

<img width="856" height="856" alt="schematic-pn532" src="https://github.com/user-attachments/assets/2457db2b-ad1e-42d4-9f88-77ea3fe276ab" />


**Build-time overrides:** `PN532_SCK`, `PN532_MISO`, `PN532_MOSI`, `PN532_SS`

> **Note (shared SPI):** On ESP32-DIV, SD card and CC1101 typically use **SCK 12, MOSI 11, MISO 13** on the same bus. Wire the PN532 to those **physical** MOSI/MISO/SCK lines; if your copper matches the stock wiki, `PN532_MOSI` / `PN532_MISO` should match **11 = MOSI, 13 = MISO** regardless of label order in a given snippet—verify against your schematic.

<div>&nbsp;</div>

## 🛰️ Neo-6M GPS → ESP32 (UART)

**Defaults:** `HardwareSerial` **UART2**, **9600 8N1** (`GPS_UART_NUM`, `GPS_UART_BAUD` in `gps.cpp`).

| ESP32 GPIO | GPS module | Description |
| ---------- | ---------- | ----------- |
| GPIO 47 | Module **TX** → ESP **RX** | NMEA input (`GPS_UART_RX`) |
| GPIO 48 | Module **RX** ← ESP **TX** | Optional commands (`GPS_UART_TX`) |
| 3.3V or 5V | VCC | Per module rating |
| GND | GND | Ground |


<img width="856" height="856" alt="schematic-neo6m" src="https://github.com/user-attachments/assets/3aa4b28a-5e1d-4425-b14c-3a295e70c34f" />


**Build-time overrides:** `GPS_UART_RX`, `GPS_UART_TX`, `GPS_UART_NUM`, `GPS_UART_BAUD`


---
*Build or troubleshoot your ESP32-DIV with these connections. See the [Hardware](Hardware) page for component details or the [Firmware Upload Guide](Firmware-Upload-Guide) for setup.*