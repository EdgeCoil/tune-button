#!/bin/sh
# SPDX-FileCopyrightText: 2026 edgecoil
# SPDX-License-Identifier: MIT
#
# Merge the PlatformIO build into one image, flashed at offset 0:
#   esptool.py --chip esp32c3 write_flash 0 tune-button-c3.bin
# Pass the env for another build: sh scripts/merge.sh xiao_esp32c3_1btn → tune-button-c3-1btn.bin
set -eu
cd "$(dirname "$0")/.."
ENV=${1:-xiao_esp32c3}
B=.pio/build/$ENV
OUT=tune-button-c3${ENV#xiao_esp32c3}.bin
OUT=$(echo "$OUT" | tr _ -)
P=${PLATFORMIO_CORE_DIR:-$HOME/.platformio}/packages
python3 "$P/tool-esptoolpy/esptool.py" --chip esp32c3 merge_bin -o "$OUT" \
  --flash_mode dio --flash_freq 80m --flash_size 4MB \
  0x0 "$B/bootloader.bin" 0x8000 "$B/partitions.bin" \
  0xe000 "$P/framework-arduinoespressif32/tools/partitions/boot_app0.bin" 0x10000 "$B/firmware.bin"
