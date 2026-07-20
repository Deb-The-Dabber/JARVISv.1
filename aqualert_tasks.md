# AquAlert: Acoustic Wrist Device for Diver Communication
## Task List & Progress Tracker

**Goal:** #10 — AquAlert (P8)
**MCU Decision:** ESP32-S3 (dual-core Xtensa LX7 @ 240 MHz, 512 KB SRAM, USB OTG, Wi-Fi 4, BT 5 LE, vector extensions, PSRAM support)
**Date:** 2026-07-10

---

### Phase 1: Component Selection & BOM (Week 1-2)
- [ ] **1.1 Finalize MCU variant** — ESP32-S3-WROOM-1 (16 MB flash, 8 MB PSRAM) or ESP32-S3-WROOM-1U (antenna variant)
- [ ] **1.2 Select piezo transducer** — Target: 20-40 kHz resonant, low drive voltage (< 20 Vpp), compact (≤ 15 mm)
  - Candidates: Murata MA40S4S, STEMiNC SMD40T20R110, custom
- [ ] **1.3 Select hydrophone/preamp** — Sensitivity > -180 dB re 1V/µPa, low noise, small form factor
  - Candidates: Aquarian Audio H1C, Cetacean Research hydrophone, custom JFET preamp
- [ ] **1.4 Audio codec / ADC/DAC** — ESP32-S3 has I2S + ADC, but consider dedicated codec for quality
  - Options: ES8388, WM8960, or use ESP32-S3 internal ADC + external preamp
- [ ] **1.5 Battery & power management** — Target: 8+ hr dive time
  - LiPo 3.7V 500-800 mAh (18650 too large), TP4056 charging, LDO/buck for 3.3V
- [ ] **1.6 Enclosure & sealing** — Wrist-mount, 30m+ depth rating, ultrasonic transparency window
  - Materials: PETG/TPU 3D print + acrylic window, or machined Delrin/Al
- [ ] **1.7 User interface** — Capacitive touch (ESP32-S3 has 14 touch channels), haptic motor, LED status
- [ ] **1.8 Generate BOM** — Cost target: < $100/unit prototype, < $50/unit at volume

---

### Phase 2: Schematic & PCB Design (Week 2-3)
- [ ] **2.1 Schematic capture** — KiCad, hierarchical sheets per subsystem
- [ ] **2.2 Power tree design** — Battery → protection → buck/boost → 3.3V rail, piezo boost converter (20-100V)
- [ ] **2.3 Piezo driver circuit** — H-bridge or transformer drive, impedance matching
- [ ] **2.4 Hydrophone preamp** — Low-noise JFET input, gain staging, anti-aliasing filter
- [ ] **2.5 PCB layout** — 4-layer, controlled impedance for USB/I2S, antenna keepout, thermal vias
- [ ] **2.6 Design review & DRC** — Signal integrity, power integrity, EMI/EMC
- [ ] **2.7 Fabrication & assembly** — JLCPCB / PCBWay, stencil, hand-place or SMT service

---

### Phase 3: Firmware Bring-Up (Week 3-4)
- [ ] **3.1 ESP-IDF project setup** — FreeRTOS, logging, NVS, OTA partitions
- [ ] **3.2 Peripheral drivers** — I2S audio, ADC/DMA, touch, PWM (piezo), I2C (sensors), USB CDC
- [ ] **3.3 Power management** — Deep sleep, wake sources (touch, timer, GPIO), battery monitor
- [ ] **3.4 Audio pipeline** — Capture (hydrophone) → DSP → encode → transmit; Receive → decode → DSP → piezo
- [ ] **3.5 Acoustic modem** — FSK/PSK/OFDM at 20-40 kHz, Doppler tolerant, error correction
  - Start with simple FSK (Bell 103 style), iterate to OFDM
- [ ] **3.6 Protocol stack** — Packet framing, addressing, ACK/retry, mesh relay
- [ ] **3.7 Phone app (BLE)** — Config, status, log download, firmware update

---

### Phase 4: Integration & Pool Testing (Week 4-6)
- [ ] **4.1 Bench testing** — Signal generation, SNR measurement, power profiling
- [ ] **4.2 Waterproof validation** — Pressure test to 30m, ultrasonic window transmission loss
- [ ] **4.3 Pool tests** — Range, multipath, buddy pairing, latency, battery life
- [ ] **4.4 Iterate** — Firmware tuning, antenna matching, mechanical fixes

---

### Phase 5: Open Water Validation & Docs (Week 6-8)
- [ ] **5.1 Lake/ocean trials** — Real conditions, thermoclines, biological noise
- [ ] **5.2 Finalize enclosure** — Strap design, quick-release, charging port sealing
- [ ] **5.3 Documentation** — Build guide, BOM, firmware flashing, user manual
- [ ] **5.4 Open source release** — GitHub, Hackaday.io, PCB files, firmware, app

---

### Key Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-10 | ESP32-S3 as MCU | Most powerful ESP32: dual-core 240 MHz, USB, PSRAM, vector DSP, BT 5 LE, mature SDK |

---

### Next Immediate Actions (This Week)
1. **Order ESP32-S3-DevKitC-1** (~$15) for software bring-up while PCB is designed
2. **Source piezo samples** — Order 3-4 candidate transducers for impedance/SPL testing
3. **Design piezo driver topology** — H-bridge (DRV8871) vs. transformer vs. boost+H-bridge
4. **Sketch power budget** — Active TX, active RX, sleep, charge cycles → battery size